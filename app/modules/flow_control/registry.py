"""
Flow control module registry.

Auto-imports all sub-module registries for conditional routing nodes.
"""

# Import if_condition registry to trigger node registration
from .if_condition import registry as if_condition_registry
from .output import registry as output_registry

__all__ = ["if_condition_registry", "output_registry"]
