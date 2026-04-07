"""
densify.py — Backward-compatible re-export shim.
==================================================

All densify functionality has been refactored into the ``density/`` sub-package.
This shim re-exports every public symbol so that existing imports like::

    from app.modules.pipeline.operations.densify import Densify
    from app.modules.pipeline.operations.densify import DensifyConfig

continue to work without modification.

For new code, prefer importing directly from the package::

    from app.modules.pipeline.operations.density import Densify
    from app.modules.pipeline.operations.density import NearestNeighborDensify
"""
from .density import (  # noqa: F401  — re-export everything
    Densify,
    DensityAlgorithmBase,
    DensifyAlgorithm,
    DensifyConfig,
    DensifyLogLevel,
    DensifyMetadata,
    DensifyMLSParams,
    DensifyNNParams,
    DensifyPoissonParams,
    DensifyQualityPreset,
    DensifyStatisticalParams,
    DensifyStatus,
    MLSDensify,
    NearestNeighborDensify,
    PoissonDensify,
    StatisticalDensify,
    MAX_MULTIPLIER,
    MIN_INPUT_POINTS,
    PRESET_ALGORITHM_MAP,
)
