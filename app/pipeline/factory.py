from typing import Dict, Callable

from .impl import basic, advanced, reflector

# Add new pipelines to this dictionary as you create them in the impl/ folder
_PIPELINE_MAP: Dict[str, Callable] = {
    "basic": basic.create_pipeline,
    "advanced": advanced.create_pipeline,
    "reflector": reflector.create_pipeline
}


class PipelineFactory:
    @staticmethod
    def get(name: str, **kwargs):
        """Resolves a pipeline name to a concrete Pipeline object"""
        if name not in _PIPELINE_MAP:
            raise ValueError(f"Unknown pipeline: '{name}'. Available: {list(_PIPELINE_MAP.keys())}")
        return _PIPELINE_MAP[name](**kwargs)
