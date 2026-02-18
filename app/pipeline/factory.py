from typing import Callable, Literal

from .impl import basic, advanced, reflector

# Single source of truth: add a new pipeline here and the type updates automatically
_PIPELINE_MAP: dict[str, Callable] = {
    "basic": basic.create_pipeline,
    "advanced": advanced.create_pipeline,
    "reflector": reflector.create_pipeline
}

# Derived from the map keys at import time — no duplication needed
PipelineName = Literal[tuple(_PIPELINE_MAP.keys())]  # type: ignore[valid-type]


class PipelineFactory:
    @staticmethod
    def get(name: PipelineName, **kwargs):
        """Resolves a pipeline name to a concrete Pipeline object"""
        if name not in _PIPELINE_MAP:
            raise ValueError(f"Unknown pipeline: '{name}'. Available: {list(_PIPELINE_MAP.keys())}")
        return _PIPELINE_MAP[name](**kwargs)
