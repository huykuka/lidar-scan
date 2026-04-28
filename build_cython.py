"""
Cython build script for lidar-standalone.

Compiles all Python source files under ``app/`` into native C extension
modules (``.so`` on Linux), stripping readable source from the deployment
image.  ``__init__.py`` files are kept as plain Python so that the package
hierarchy and dynamic discovery (``pkgutil.iter_modules``) continue to work.

Usage (inside Docker or locally)::

    python build_cython.py build_ext --inplace

After the build, remove the now-redundant ``.py`` and ``.c`` artefacts::

    find app/ -name '*.py' ! -name '__init__.py' -delete
    find app/ -name '*.c' -delete
"""

from __future__ import annotations

from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

# Collect every .py under app/, excluding __init__.py (needed for packages).
_ROOT = Path(__file__).resolve().parent
_PY_FILES = sorted(
    p
    for p in _ROOT.glob("app/**/*.py")
    if p.name != "__init__.py"
)

extensions: list[Extension] = []
for py_path in _PY_FILES:
    # Dotted module name, e.g. "app.services.nodes.orchestrator"
    module_name = (
        str(py_path.relative_to(_ROOT))
        .replace("/", ".")
        .removesuffix(".py")
    )
    extensions.append(Extension(module_name, [str(py_path)]))

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
