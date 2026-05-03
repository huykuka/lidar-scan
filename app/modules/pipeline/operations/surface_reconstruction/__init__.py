"""
surface_reconstruction — Surface reconstruction algorithms for the pipeline.
=============================================================================

Package layout::

    surface_reconstruction/
        __init__.py                  ← this file (public re-exports)
        reconstruction_base.py       ← ReconstructionAlgorithmBase, enums, param models
        surface_reconstruction.py    ← SurfaceReconstruction (PipelineOperation dispatcher)
        alpha_shape.py               ← AlphaShapeReconstruction
        ball_pivoting.py             ← BallPivotingReconstruction
        poisson.py                   ← PoissonReconstruction

Public API
----------
The ``SurfaceReconstruction`` class is the sole PipelineOperation entry point.
Algorithm classes are importable for direct use or testing but are not
registered in the DAG factory — ``SurfaceReconstruction`` dispatches internally.
"""

# Main dispatcher (PipelineOperation subclass)
from .surface_reconstruction import SurfaceReconstruction

# Algorithm implementations
from .alpha_shape import AlphaShapeReconstruction
from .ball_pivoting import BallPivotingReconstruction
from .poisson import PoissonReconstruction

# Base class
from .reconstruction_base import ReconstructionAlgorithmBase

# Enums
from .reconstruction_base import (
    ReconstructionAlgorithm,
    ReconstructionStatus,
)

# Pydantic config / param models
from .reconstruction_base import (
    AlphaShapeParams,
    BallPivotingParams,
    PoissonReconstructionParams,
    ReconstructionConfig,
    ReconstructionMetadata,
)

# Constants
from .reconstruction_base import MIN_INPUT_POINTS

__all__ = [
    # Dispatcher
    "SurfaceReconstruction",
    # Algorithm classes
    "AlphaShapeReconstruction",
    "BallPivotingReconstruction",
    "PoissonReconstruction",
    # Base
    "ReconstructionAlgorithmBase",
    # Enums
    "ReconstructionAlgorithm",
    "ReconstructionStatus",
    # Models
    "AlphaShapeParams",
    "BallPivotingParams",
    "PoissonReconstructionParams",
    "ReconstructionConfig",
    "ReconstructionMetadata",
    # Constants
    "MIN_INPUT_POINTS",
]
