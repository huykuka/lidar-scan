"""
Core built-in modules for the DAG orchestrator.

This package contains the shipped node implementations (lidar, fusion,
pipeline, etc.).  Each sub-package exposes a ``registry.py`` that registers
its ``NodeDefinition`` schemas and ``NodeFactory`` builders as side-effects
on import.

These modules are loaded once at application startup and are NOT
hot-pluggable via the API.  For user-supplied plugins see ``app/plugins/``.
"""
import importlib
import pkgutil
import os
from app.core.logging import get_logger

logger = get_logger(__name__)


def discover_modules():
    """
    Auto-discover and import all core module registry files.

    Iterates through all sub-packages in this directory and imports their
    ``registry.py`` (if present), triggering NodeDefinition and NodeFactory
    registrations.

    Called once during application startup via ``app.services.nodes.instance``.
    """
    package_dir = os.path.dirname(__file__)

    for info in pkgutil.iter_modules([package_dir]):
        if not info.ispkg:
            continue

        module_name = info.name
        try:
            importlib.import_module(f".{module_name}.registry", package=__name__)
            logger.info(f"[modules] Loaded core module: {module_name}")
        except ModuleNotFoundError:
            logger.debug(f"[modules] Module '{module_name}' has no registry.py — skipped")
        except Exception as exc:
            logger.error(f"[modules] Failed to load '{module_name}': {exc}", exc_info=True)
