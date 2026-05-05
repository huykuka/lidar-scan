"""
Application module registry.

Auto-imports all sub-module registries for application-level nodes.
Each sub-module (e.g. ``hello_world``) owns its own ``registry.py`` which
performs the actual schema and factory registrations.

Adding a new application node
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Create ``app/modules/application/<name>/registry.py`` following the
   ``hello_world`` pattern (schema + lazy-import factory).
2. Add ``from .<name> import registry as <name>_registry`` below.
3. Add the symbol to ``__all__``.

The :func:`~app.modules.discover_modules` auto-discovery mechanism imports
*this* file, so sub-module registries are automatically loaded at startup.
"""

# Import sub-module registries to trigger node registration side-effects
from .environment_filtering import registry as environment_filtering_registry
from .truck_bin_detection import registry as truck_bin_detection_registry
from .vehicle_profiler import registry as vehicle_profiler_registry

__all__ = ["environment_filtering_registry", "truck_bin_detection_registry", "vehicle_profiler_registry"]
