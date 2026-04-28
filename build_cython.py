"""
Cython build script for lidar-standalone.

Compiles all Python source files under ``app/`` into native C extension
modules (``.so`` on Linux), stripping readable source from the deployment
image.  ``__init__.py`` files are kept as plain Python so that the package
hierarchy and dynamic discovery (``pkgutil.iter_modules``) continue to work.

Automatically excluded from compilation:

* **Pydantic / SQLAlchemy ORM models** — metaclass introspection is
  incompatible with Cython's ``cyfunction`` type.
* **FastAPI route handlers** — function-signature introspection for
  ``Query``, ``Depends``, etc. breaks with Cython-compiled functions.

Usage (inside Docker or locally)::

    python build_cython.py build_ext --inplace

After the build, remove the now-redundant ``.py`` and ``.c`` artefacts
(but only for files that were actually compiled)::

    # See the Dockerfile for the exact cleanup commands.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# AST-based exclusion rules
# ---------------------------------------------------------------------------

_INCOMPATIBLE_BASES = {
    "BaseModel",
    "DeclarativeBase",
}

_FASTAPI_ROUTE_IMPORTS = {
    "APIRouter",
    "FastAPI",
}


def _should_skip(path: Path) -> str | None:
    """Return a human-readable reason if *path* must stay as plain Python,
    or ``None`` if it is safe to compile."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return "SyntaxError"

    for node in ast.walk(tree):
        # Rule 1: Pydantic / SQLAlchemy ORM class definitions
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = None
                if isinstance(base, ast.Name):
                    name = base.id
                elif isinstance(base, ast.Attribute):
                    name = base.attr
                if name in _INCOMPATIBLE_BASES:
                    return f"inherits {name}"

        # Rule 2: FastAPI route handlers (import APIRouter or FastAPI)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {
                alias.name.split(".")[-1]
                for alias in node.names
            }
            if names & _FASTAPI_ROUTE_IMPORTS:
                return "FastAPI routing"

    return None


# ---------------------------------------------------------------------------
# Collect compilable .py files
# ---------------------------------------------------------------------------
_PY_FILES = sorted(
    p
    for p in _ROOT.glob("app/**/*.py")
    if p.name != "__init__.py"
)

extensions: list[Extension] = []
skipped: list[tuple[str, str]] = []

for py_path in _PY_FILES:
    rel = str(py_path.relative_to(_ROOT))
    reason = _should_skip(py_path)
    if reason:
        skipped.append((rel, reason))
        continue

    module_name = rel.replace("/", ".").removesuffix(".py")
    extensions.append(Extension(module_name, [str(py_path)]))

if skipped:
    print(
        f"[build_cython] Skipping {len(skipped)} file(s):",
        file=sys.stderr,
    )
    for path, reason in skipped:
        print(f"  - {path}  ({reason})", file=sys.stderr)

print(
    f"[build_cython] Compiling {len(extensions)} file(s) to .so",
    file=sys.stderr,
)

setup(
    name="lidar-standalone-compiled",
    packages=[],
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
        },
        nthreads=4,
    ),
)
