"""
User plugin directory.

Drop a plugin package here (or upload via the API) and it will be
importable as ``app.plugins.<name>.registry``.

Each plugin package must contain at minimum:

    my_plugin/
        __init__.py
        registry.py   ← registers NodeDefinition + NodeFactory builder

Runtime API
-----------
    from app.plugins import load_plugin, unload_plugin, list_plugins

    load_plugin("my_plugin")    # import registry, track registered types
    unload_plugin("my_plugin")  # remove from registries + evict sys.modules
    install_plugin_zip(raw_bytes)  # extract zip, install, auto-load
"""
import ast
import importlib
import pkgutil
import shutil
import sys
import os
import tempfile
import zipfile
from typing import Set

from app.core.logging import get_logger

logger = get_logger(__name__)

_PLUGINS_DIR: str = os.path.dirname(__file__)

# plugin_name -> set of node-type strings it registered
_loaded_plugins: dict[str, Set[str]] = {}


# ── Internal helpers ───────────────────────────────────────────────────────


def _evict_from_sys_modules(plugin_name: str) -> None:
    """Remove all sys.modules entries belonging to a plugin package."""
    prefix = f"{__name__}.{plugin_name}"
    to_remove = [
        k for k in list(sys.modules)
        if k == prefix or k.startswith(prefix + ".")
    ]
    for k in to_remove:
        del sys.modules[k]


# ── Public API ─────────────────────────────────────────────────────────────


def load_plugin(name: str) -> Set[str]:
    """Load (or reload) a plugin by name.

    Evicts the plugin from ``sys.modules`` so the import is always fresh,
    then snapshots both registries before and after to track which node
    types were added.

    Args:
        name: Sub-directory name under ``app/plugins/`` (e.g. ``"my_plugin"``).

    Returns:
        Set of newly registered node-type strings.

    Raises:
        FileNotFoundError: Plugin directory does not exist.
        ModuleNotFoundError: Plugin has no ``registry.py``.
        Exception: Any error raised during import is propagated.
    """
    from app.services.nodes.schema import node_schema_registry
    from app.services.nodes.node_factory import NodeFactory

    plugin_dir = os.path.join(_PLUGINS_DIR, name)
    if not os.path.isdir(plugin_dir):
        raise FileNotFoundError(
            f"Plugin '{name}' not found in app/plugins/ — "
            "upload it first via POST /nodes/plugins/upload"
        )
    if not os.path.exists(os.path.join(plugin_dir, "registry.py")):
        raise ModuleNotFoundError(f"Plugin '{name}' has no registry.py")

    # Unload existing version first (clean re-import)
    if name in _loaded_plugins:
        unload_plugin(name)
    else:
        _evict_from_sys_modules(name)

    before_schema = set(node_schema_registry._definitions.keys())
    before_factory = set(NodeFactory._registry.keys())

    importlib.import_module(f".{name}.registry", package=__name__)

    added_schema = set(node_schema_registry._definitions.keys()) - before_schema
    added_factory = set(NodeFactory._registry.keys()) - before_factory
    registered_types = added_schema | added_factory

    _loaded_plugins[name] = registered_types
    logger.info(f"[plugins] Loaded plugin '{name}': registered types {registered_types}")
    return registered_types


def unload_plugin(name: str) -> Set[str]:
    """Unload a plugin by name.

    Removes all node types the plugin registered from both ``NodeFactory``
    and ``SchemaRegistry``, and evicts its modules from ``sys.modules``.

    Args:
        name: Plugin name (must be currently loaded).

    Returns:
        Set of type strings that were removed (empty if not loaded).
    """
    from app.services.nodes.schema import node_schema_registry
    from app.services.nodes.node_factory import NodeFactory

    registered_types = _loaded_plugins.pop(name, set())

    for node_type in registered_types:
        node_schema_registry.unregister(node_type)
        NodeFactory.unregister(node_type)

    _evict_from_sys_modules(name)
    logger.info(f"[plugins] Unloaded plugin '{name}': removed types {registered_types}")
    return registered_types


def remove_plugin(name: str) -> Set[str]:
    """Unload a plugin and permanently delete its directory from disk.

    Args:
        name: Plugin package name.

    Returns:
        Set of type strings that were removed.

    Raises:
        FileNotFoundError: If the plugin directory does not exist.
    """
    plugin_dir = os.path.join(_PLUGINS_DIR, name)
    if not os.path.isdir(plugin_dir):
        raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

    # Unload from registries first (no-op if already unloaded)
    removed_types = unload_plugin(name)

    shutil.rmtree(plugin_dir)
    logger.info(f"[plugins] Removed plugin '{name}' from disk (types: {removed_types})")
    return removed_types


def list_plugins() -> list[dict]:
    """Return all plugin directories with their load state and registered types."""
    result = []
    for info in pkgutil.iter_modules([_PLUGINS_DIR]):
        if not info.ispkg:
            continue
        loaded_types = _loaded_plugins.get(info.name)
        result.append({
            "name": info.name,
            "loaded": loaded_types is not None,
            "types": sorted(loaded_types) if loaded_types else [],
        })
    return result


# ── AST helpers (called by validate_plugin_zip, never execute plugin code) ─


def _ast_check_registry(source: str, filename: str) -> list[str]:
    """Parse registry.py and return a list of structural error strings."""
    errors: list[str] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"Syntax error in {filename}: {exc}"]

    # 1. node_schema_registry.register(NodeDefinition(...))
    has_schema_register = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "node_schema_registry"
        and n.func.attr == "register"
        for n in ast.walk(tree)
    )
    if not has_schema_register:
        errors.append(
            "registry.py: missing `node_schema_registry.register(NodeDefinition(...))` call"
        )

    # 2. @NodeFactory.register('type') decorated factory function
    factory_funcs = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in n.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "NodeFactory"
                    and dec.func.attr == "register"
                ):
                    factory_funcs.append(n)

    if not factory_funcs:
        errors.append(
            "registry.py: missing `@NodeFactory.register('...')` decorated factory function"
        )
    else:
        for fn in factory_funcs:
            all_args = fn.args.posonlyargs + fn.args.args
            if len(all_args) < 3:
                errors.append(
                    f"registry.py: factory `{fn.name}` must accept at least 3 positional "
                    "args — (node, service_context, edges)"
                )

    return errors


def _ast_find_module_node_classes(
    source: str, filename: str
) -> tuple[list[ast.ClassDef], list[str]]:
    """Return (classes_extending_ModuleNode, errors)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [], [f"Syntax error in {filename}: {exc}"]

    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if (isinstance(base, ast.Name) and base.id == "ModuleNode") or (
                    isinstance(base, ast.Attribute) and base.attr == "ModuleNode"
                ):
                    classes.append(node)

    return classes, []


def _ast_check_node_class(cls: ast.ClassDef, filename: str) -> list[str]:
    """Return error strings for a single ModuleNode subclass."""
    errors: list[str] = []
    name = cls.name

    # Direct methods only — don't descend into nested classes
    methods: dict[str, ast.stmt] = {}
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods[item.name] = item

    # on_input must be async
    if "on_input" not in methods:
        errors.append(
            f"{filename} · `{name}`: missing `async def on_input(self, payload)`"
        )
    elif not isinstance(methods["on_input"], ast.AsyncFunctionDef):
        errors.append(
            f"{filename} · `{name}`: `on_input` must be declared with `async def`"
        )

    # emit_status required (standardised status contract)
    if "emit_status" not in methods:
        errors.append(
            f"{filename} · `{name}`: missing `def emit_status(self) -> NodeStatusUpdate`"
        )

    # start OR enable required for orchestrator lifecycle
    if "start" not in methods and "enable" not in methods:
        errors.append(
            f"{filename} · `{name}`: must implement `def start(...)` or `def enable()` "
            "so the orchestrator can activate it"
        )

    return errors


def validate_plugin_zip(zip_bytes: bytes) -> str:
    """Deep in-memory validation of a plugin zip — no bytes written to disk.

    Checks (in order):
    1. Valid zip format.
    2. Exactly one top-level directory (ignoring ``__MACOSX``).
    3. Required files: ``<name>/__init__.py`` and ``<name>/registry.py``.
    4. ``registry.py`` AST:
       - calls ``node_schema_registry.register(NodeDefinition(...))``.
       - has ``@NodeFactory.register('...')`` decorated factory function.
       - factory function accepts at least 3 positional parameters.
    5. Node implementation file AST (first ``.py`` that is not ``__init__.py``
       or ``registry.py`` and contains a ``ModuleNode`` subclass):
       - class extends ``ModuleNode``.
       - ``async def on_input(self, payload)`` present.
       - ``def emit_status(self)`` present.
       - ``def start(...)`` or ``def enable()`` present.

    Returns:
        Plugin name (top-level directory name).

    Raises:
        ValueError:         Structural or AST error (message lists all issues).
        zipfile.BadZipFile: File is not a valid zip archive.
    """
    import ast
    import io

    errors: list[str] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()

        # ── 1 + 2: layout ──────────────────────────────────────────────────
        top_level = {
            p.split("/")[0]
            for p in names
            if p.split("/")[0] and not p.startswith("__MACOSX")
        }
        if len(top_level) != 1:
            raise ValueError(
                f"Zip must contain exactly one top-level directory; found: {sorted(top_level)}"
            )

        plugin_name = next(iter(top_level)).rstrip("/")
        file_entries = {p for p in names if not p.endswith("/")}

        # ── 3: required files ──────────────────────────────────────────────
        for required in (f"{plugin_name}/__init__.py", f"{plugin_name}/registry.py"):
            if required not in file_entries:
                errors.append(f"Missing required file '{required}'")

        if errors:
            raise ValueError("Plugin validation failed:\n" + "\n".join(f"  • {e}" for e in errors))

        # ── 4: registry.py AST ─────────────────────────────────────────────
        registry_src = zf.read(f"{plugin_name}/registry.py").decode("utf-8", errors="replace")
        errors.extend(_ast_check_registry(registry_src, f"{plugin_name}/registry.py"))

        # ── 5: node implementation AST ─────────────────────────────────────
        impl_files = [
            p for p in file_entries
            if p.startswith(f"{plugin_name}/")
            and p.endswith(".py")
            and p not in {f"{plugin_name}/__init__.py", f"{plugin_name}/registry.py"}
        ]

        if not impl_files:
            errors.append(
                "No node implementation file found. "
                "Add a Python file (e.g. node.py) with a class extending ModuleNode."
            )
        else:
            all_node_classes: list[tuple[ast.ClassDef, str]] = []
            for path in impl_files:
                src = zf.read(path).decode("utf-8", errors="replace")
                classes, parse_errors = _ast_find_module_node_classes(src, path)
                errors.extend(parse_errors)
                all_node_classes.extend((cls, path) for cls in classes)

            if not all_node_classes and not errors:
                errors.append(
                    f"None of the implementation files define a class extending ModuleNode. "
                    f"Files checked: {', '.join(impl_files)}"
                )

            for cls, path in all_node_classes:
                errors.extend(_ast_check_node_class(cls, path))

    if errors:
        raise ValueError(
            "Plugin validation failed:\n" + "\n".join(f"  • {e}" for e in errors)
        )

    return plugin_name



def install_plugin_zip(zip_bytes: bytes, *, auto_load: bool = True) -> tuple[str, Set[str]]:
    """Install a plugin from a zip archive and optionally load it.

    Expected zip layout (single top-level directory)::

        my_plugin/
            __init__.py
            registry.py
            node.py         (optional)
            ...

    Args:
        zip_bytes: Raw bytes of the zip file.
        auto_load: When ``True`` (default), immediately load the plugin after
                   extraction so it is available in the current process.

    Returns:
        Tuple of ``(plugin_name, registered_types)``.
        ``registered_types`` is empty when ``auto_load=False``.

    Raises:
        ValueError: Zip does not contain exactly one top-level directory.
        zipfile.BadZipFile: Invalid zip data.
    """
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "upload.zip")
        with open(zip_path, "wb") as fh:
            fh.write(zip_bytes)

        with zipfile.ZipFile(zip_path, "r") as zf:
            top_level = {
                p.split("/")[0]
                for p in zf.namelist()
                if p.split("/")[0] and not p.startswith("__MACOSX")
            }
            if len(top_level) != 1:
                raise ValueError(
                    f"Zip must contain exactly one top-level directory; found: {top_level}"
                )
            plugin_name = next(iter(top_level)).rstrip("/")
            zf.extractall(tmp)

        src = os.path.join(tmp, plugin_name)
        dst = os.path.join(_PLUGINS_DIR, plugin_name)

        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    logger.info(f"[plugins] Installed plugin '{plugin_name}' to {dst}")

    if auto_load:
        registered_types = load_plugin(plugin_name)
        return plugin_name, registered_types

    return plugin_name, set()


def discover_plugins() -> None:
    """Auto-load all plugin packages present in the plugins directory.

    Called at application startup (after ``discover_modules()``) so that
    any plugins already on disk are available without a manual load call.
    """
    for info in pkgutil.iter_modules([_PLUGINS_DIR]):
        if not info.ispkg:
            continue
        try:
            load_plugin(info.name)
        except ModuleNotFoundError:
            logger.debug(f"[plugins] Plugin '{info.name}' has no registry.py — skipped")
        except Exception as exc:
            logger.error(f"[plugins] Failed to load plugin '{info.name}': {exc}", exc_info=True)
