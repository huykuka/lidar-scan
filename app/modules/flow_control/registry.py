"""
Flow control module registry.

Auto-imports all sub-module registries for conditional routing nodes.
"""

# Import if_condition registry to trigger node registration
from .if_condition import registry as if_condition_registry
from .output import registry as output_registry
from .result_storage import registry as result_storage_registry
from .snapshot import registry as snapshot_registry

__all__ = ["if_condition_registry", "output_registry", "result_storage_registry", "snapshot_registry"]
