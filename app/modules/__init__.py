"""
Self-contained pluggable modules for the DAG orchestrator.

This package provides an auto-discovery mechanism that loads module registries
on import. Each sub-package (lidar, fusion, pipeline, etc.) must expose a
`registry` module that performs side-effect registrations:
    - NodeDefinition schemas via node_schema_registry.register()
    - Factory builders via @NodeFactory.register()
"""
import importlib
import pkgutil
import os
from app.core.logging import get_logger

logger = get_logger(__name__)


def discover_modules():
    """
    Auto-discover and import all module registry files.
    
    Iterates through all sub-packages in this directory and imports their
    `registry.py` module (if it exists). This triggers side-effect registrations
    of NodeDefinitions and factory builders.
    
    Called once during application startup via app.services.nodes.instance.
    """
    package_dir = os.path.dirname(__file__)
    
    for info in pkgutil.iter_modules([package_dir]):
        if not info.ispkg:
            continue
            
        module_name = info.name
        try:
            # Attempt to import the registry module from each sub-package
            importlib.import_module(f".{module_name}.registry", package=__name__)
            logger.info(f"Loaded module registry: {module_name}")
        except ModuleNotFoundError:
            # Module has no registry.py -- skip silently
            logger.debug(f"Module '{module_name}' has no registry.py -- skipped")
        except Exception as e:
            # Log errors but don't crash the entire app
            logger.error(f"Failed to load module '{module_name}' registry: {e}", exc_info=True)
