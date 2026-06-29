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
