#!/usr/bin/env bash
# scripts/pack_plugin.sh
#
# Package a plugin directory into a zip ready for import via the UI or API.
#
# Usage:
#   scripts/pack_plugin.sh <plugin_dir>
#   scripts/pack_plugin.sh app/plugins/passthrough_logger
#
# Output:
#   plugin_packages/<plugin_name>.zip
#
# The zip layout matches what install_plugin_zip() expects:
#   <plugin_name>/
#       __init__.py
#       registry.py
#       node.py          (and any other .py files)
#
# The generated zip is gitignored (plugin_packages/*.zip).
# Commit and version your plugin SOURCE in app/plugins/<name>/ instead.

set -euo pipefail

# ── Resolve plugin directory ───────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <plugin_dir>" >&2
  echo "  e.g. $0 app/plugins/passthrough_logger" >&2
  exit 1
fi

PLUGIN_DIR="${1%/}"   # strip trailing slash

if [[ ! -d "$PLUGIN_DIR" ]]; then
  echo "Error: '$PLUGIN_DIR' is not a directory." >&2
  exit 1
fi

if [[ ! -f "$PLUGIN_DIR/registry.py" ]]; then
  echo "Error: '$PLUGIN_DIR/registry.py' not found — every plugin needs a registry.py." >&2
  exit 1
fi

PLUGIN_NAME="$(basename "$PLUGIN_DIR")"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/plugin_packages"
OUT_ZIP="$OUT_DIR/${PLUGIN_NAME}.zip"

mkdir -p "$OUT_DIR"

# ── Deep structural validation (AST, no import) ────────────────────────────
echo "Validating '$PLUGIN_NAME'..."
python3 - "$PLUGIN_DIR" "$PLUGIN_NAME" <<'PYEOF'
import sys, ast, os

plugin_dir = sys.argv[1]
plugin_name = sys.argv[2]
errors = []


def check_registry(path):
    src = open(path).read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return [f"Syntax error in registry.py: {e}"]
    errs = []
    has_schema = any(
        isinstance(n, ast.Call)
        and isinstance(getattr(n.func, 'value', None), ast.Name)
        and n.func.value.id == 'node_schema_registry'
        and n.func.attr == 'register'
        for n in ast.walk(tree)
    )
    if not has_schema:
        errs.append("registry.py: missing node_schema_registry.register(NodeDefinition(...))")

    factory_fns = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(d, ast.Call)
            and isinstance(getattr(d.func, 'value', None), ast.Name)
            and d.func.value.id == 'NodeFactory'
            and d.func.attr == 'register'
            for d in n.decorator_list
        )
    ]
    if not factory_fns:
        errs.append("registry.py: missing @NodeFactory.register('...') decorated factory function")
    else:
        for fn in factory_fns:
            n_args = len(fn.args.posonlyargs) + len(fn.args.args)
            if n_args < 3:
                errs.append(f"registry.py: factory '{fn.name}' needs >= 3 args (node, service_context, edges)")
    return errs


def check_node_file(path):
    src = open(path).read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return [], [f"Syntax error in {os.path.basename(path)}: {e}"]

    classes = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
        and any(
            (isinstance(b, ast.Name) and b.id == 'ModuleNode') or
            (isinstance(b, ast.Attribute) and b.attr == 'ModuleNode')
            for b in n.bases
        )
    ]
    errs = []
    for cls in classes:
        fname = os.path.basename(path)
        methods = {
            item.name: item for item in cls.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if 'on_input' not in methods:
            errs.append(f"{fname} · '{cls.name}': missing async def on_input(self, payload)")
        elif not isinstance(methods['on_input'], ast.AsyncFunctionDef):
            errs.append(f"{fname} · '{cls.name}': on_input must be async def")
        if 'emit_status' not in methods:
            errs.append(f"{fname} · '{cls.name}': missing def emit_status(self)")
        if 'start' not in methods and 'enable' not in methods:
            errs.append(f"{fname} · '{cls.name}': must have def start() or def enable()")
    return classes, errs


# Required files
for req in ['__init__.py', 'registry.py']:
    if not os.path.isfile(os.path.join(plugin_dir, req)):
        errors.append(f"Missing required file: {req}")

if not errors:
    errors.extend(check_registry(os.path.join(plugin_dir, 'registry.py')))

    impl_files = [
        os.path.join(plugin_dir, f) for f in os.listdir(plugin_dir)
        if f.endswith('.py') and f not in ('__init__.py', 'registry.py')
    ]
    if not impl_files:
        errors.append("No node implementation file found (e.g. node.py with a ModuleNode subclass)")
    else:
        all_classes = []
        for f in impl_files:
            classes, errs = check_node_file(f)
            errors.extend(errs)
            all_classes.extend(classes)
        if not all_classes:
            errors.append(
                "No class extending ModuleNode found in: " +
                ", ".join(os.path.basename(f) for f in impl_files)
            )

if errors:
    print("\n❌ Plugin validation failed:")
    for e in errors:
        print(f"   • {e}")
    sys.exit(1)

print(f"  ✓ Structure valid ({len(impl_files)} impl file(s))")
PYEOF

# cd to the parent so the zip entry is  <plugin_name>/...  not  .../...
PARENT_DIR="$(dirname "$(realpath "$PLUGIN_DIR")")"

# Exclude Python caches and editor noise
cd "$PARENT_DIR"
zip -r "$OUT_ZIP" "$PLUGIN_NAME" \
  --exclude "*/__pycache__/*" \
  --exclude "*/.DS_Store" \
  --exclude "*/.*" \
  --exclude "*.pyc" \
  --exclude "*.pyo" \
  > /dev/null

echo "✓ Packed '$PLUGIN_NAME' → $OUT_ZIP"
echo ""
echo "  Import via UI  : Admin → Plugins → Upload .zip"
echo "  Import via API : curl -X POST http://localhost:8005/api/v1/nodes/plugins/upload \\"
echo "                        -F 'file=@$OUT_ZIP'"
