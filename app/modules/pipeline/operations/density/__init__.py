"""
density — Modular densification algorithms for the pipeline.
=============================================================

Package layout::

    density/
        __init__.py          ← this file (public re-exports)
        density_base.py      ← DensityAlgorithmBase, enums, param models, shared utils
        densify.py           ← Densify (PipelineOperation dispatcher)
        nearest_neighbor.py  ← NearestNeighborDensify(DensityAlgorithmBase)
        mls.py               ← MLSDensify(DensityAlgorithmBase)
        poisson.py           ← PoissonDensify(DensityAlgorithmBase)
        statistical.py       ← StatisticalDensify(DensityAlgorithmBase)

Public API
----------
The ``Densify`` class is the sole PipelineOperation entry point.  Algorithm
classes are importable for direct use or testing but are not registered in
the DAG factory — ``Densify`` dispatches internally.
"""

# Main dispatcher (PipelineOperation subclass)
from .densify import Densify

# Algorithm implementations
from .nearest_neighbor import NearestNeighborDensify
from .mls import MLSDensify
from .poisson import PoissonDensify
from .statistical import StatisticalDensify

# Base class
from .density_base import DensityAlgorithmBase

# Enums
from .density_base import (
    DensifyAlgorithm,
    DensifyStatus,
)

# Pydantic config / param models
from .density_base import (
    DensifyConfig,
    DensifyMetadata,
    DensifyMLSParams,
    DensifyNNParams,
    DensifyPoissonParams,
    DensifyStatisticalParams,
)

# Constants
from .density_base import (
    MAX_MULTIPLIER,
    MIN_INPUT_POINTS,
)

__all__ = [
    # Dispatcher
    "Densify",
    # Algorithm classes
    "NearestNeighborDensify",
    "MLSDensify",
    "PoissonDensify",
    "StatisticalDensify",
    # Base
    "DensityAlgorithmBase",
    # Enums
    "DensifyAlgorithm",
    "DensifyStatus",
    # Models
    "DensifyConfig",
    "DensifyMetadata",
    "DensifyMLSParams",
    "DensifyNNParams",
    "DensifyPoissonParams",
    "DensifyStatisticalParams",
    # Constants
    "MAX_MULTIPLIER",
    "MIN_INPUT_POINTS",
]
