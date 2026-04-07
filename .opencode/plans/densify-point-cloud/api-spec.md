# Densify Point Cloud — API Specification

**Feature:** `densify-point-cloud`  
**Module:** `app/modules/pipeline/operations/densify.py`  
**Schema Location:** `app/modules/pipeline/operations/densify.py` (inline Pydantic models)  
**Version:** 1.0  
**References:** `technical.md` §7, §8, §11

---

## 1. Pydantic Configuration Model

### 1.1 Enums

```python
from enum import Enum

class DensifyAlgorithm(str, Enum):
    """Available densification algorithms."""
    NEAREST_NEIGHBOR = "nearest_neighbor"
    MLS              = "mls"
    POISSON          = "poisson"
    STATISTICAL      = "statistical"


class DensifyQualityPreset(str, Enum):
    """Quality preset. Determines default algorithm and latency target."""
    FAST   = "fast"    # → nearest_neighbor, target <100ms
    MEDIUM = "medium"  # → statistical,      target <300ms
    HIGH   = "high"    # → mls,              target <2s


class DensifyStatus(str, Enum):
    """Operation outcome status embedded in metadata."""
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR   = "error"
```

---

### 1.2 Configuration Model (`DensifyConfig`)

This model represents the `config` dict passed through `OperationFactory.create("densify", config)`.
It is also the schema for DAG node persistence and the REST API config endpoint.

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional

class DensifyConfig(BaseModel):
    """
    Configuration for the Densify pipeline operation.

    Persistence format (DAG node config stored in DB):
    {
        "type": "densify",
        "config": { ... DensifyConfig fields ... }
    }
    """

    # ── Core toggles ──────────────────────────────────────────────────────────
    enabled: bool = Field(
        default=True,
        description="Enable/disable this operation. Disabled nodes pass through unchanged."
    )

    # ── Algorithm selection ───────────────────────────────────────────────────
    algorithm: DensifyAlgorithm = Field(
        default=DensifyAlgorithm.NEAREST_NEIGHBOR,
        description=(
            "Densification algorithm. If set explicitly, takes precedence over quality_preset. "
            "Defaults to nearest_neighbor."
        )
    )

    # ── Density target ────────────────────────────────────────────────────────
    density_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=8.0,
        description=(
            "Target density increase factor. 2.0 doubles the point count. "
            "Range: 1.0 (no change) to 8.0 (max, memory guard). "
            "Ignored if target_point_count is set."
        )
    )

    target_point_count: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional: absolute target output point count (e.g. 20000 to produce 20k points). "
            "If provided, overrides density_multiplier. "
            "The effective multiplier is clamped to [1.0, 8.0]."
        )
    )

    # ── Quality preset ────────────────────────────────────────────────────────
    quality_preset: DensifyQualityPreset = Field(
        default=DensifyQualityPreset.FAST,
        description=(
            "Quality/speed preset. Determines default algorithm when 'algorithm' is not explicitly "
            "overridden. fast=<100ms, medium=<300ms, high=<2s."
        )
    )

    # ── Normals ───────────────────────────────────────────────────────────────
    preserve_normals: bool = Field(
        default=True,
        description=(
            "If True, estimate surface normals for synthetic points using k=10 nearest neighbors "
            "from the original cloud. Silently skipped if input has no normals."
        )
    )

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("density_multiplier")
    @classmethod
    def validate_multiplier(cls, v: float) -> float:
        if not (1.0 <= v <= 8.0):
            raise ValueError(
                f"density_multiplier must be in [1.0, 8.0], got {v}"
            )
        return round(v, 4)

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
    }
```

**JSON Schema (for DAG config persistence and REST body):**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DensifyConfig",
  "type": "object",
  "properties": {
    "enabled": {
      "type": "boolean",
      "default": true,
      "description": "Enable/disable this densification node"
    },
    "algorithm": {
      "type": "string",
      "enum": ["nearest_neighbor", "mls", "poisson", "statistical"],
      "default": "nearest_neighbor",
      "description": "Densification algorithm. Overrides quality_preset."
    },
    "density_multiplier": {
      "type": "number",
      "minimum": 1.0,
      "maximum": 8.0,
      "default": 2.0,
      "description": "Target density multiplier. Ignored if target_point_count is set."
    },
    "target_point_count": {
      "type": ["integer", "null"],
      "minimum": 1,
      "default": null,
      "description": "Absolute output point count. Overrides density_multiplier when set."
    },
    "quality_preset": {
      "type": "string",
      "enum": ["fast", "medium", "high"],
      "default": "fast",
      "description": "Preset determining default algorithm when algorithm is not overridden."
    },
    "preserve_normals": {
      "type": "boolean",
      "default": true,
      "description": "Estimate normals for synthetic points using k=10 NN from original cloud."
    }
  },
  "required": [],
  "additionalProperties": false
}
```

---

## 2. Output Metadata Model (`DensifyMetadata`)

Returned as the second element of the `apply()` tuple: `(pcd, metadata_dict)`.
Also propagated into `new_payload` by `OperationNode.on_input()` as `payload["op_result"]` (future use).

```python
class DensifyMetadata(BaseModel):
    """
    Structured output metadata from a Densify.apply() call.
    Always returned — even on skip or error.
    """

    # ── Always present ────────────────────────────────────────────────────────
    status: DensifyStatus = Field(
        ...,
        description="Outcome: success | skipped | error"
    )
    original_count: int = Field(
        ...,
        ge=0,
        description="Number of points in the input cloud before densification"
    )
    densified_count: int = Field(
        ...,
        ge=0,
        description="Number of points in the output cloud (== original_count on skip/error)"
    )
    density_ratio: float = Field(
        ...,
        ge=0.0,
        description="Achieved density ratio: densified_count / original_count"
    )
    algorithm_used: str = Field(
        ...,
        description="Algorithm that was applied, or 'skipped'/'error' on non-success"
    )
    processing_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Wall-clock execution time in milliseconds"
    )

    # ── Conditional ───────────────────────────────────────────────────────────
    skip_reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason for skipping (only set when status=skipped)"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Exception message (only set when status=error)"
    )

    model_config = {
        "use_enum_values": True,
    }
```

**JSON Examples:**

#### Successful densification
```json
{
  "status": "success",
  "original_count": 64000,
  "densified_count": 128000,
  "density_ratio": 2.0,
  "algorithm_used": "nearest_neighbor",
  "processing_time_ms": 45.3,
  "skip_reason": null,
  "error_message": null
}
```

#### Skipped — already dense
```json
{
  "status": "skipped",
  "original_count": 128000,
  "densified_count": 128000,
  "density_ratio": 1.0,
  "algorithm_used": "skipped",
  "processing_time_ms": 0.8,
  "skip_reason": "Input already meets or exceeds target density (current: 128000, target: 64000)",
  "error_message": null
}
```

#### Skipped — insufficient points
```json
{
  "status": "skipped",
  "original_count": 5,
  "densified_count": 5,
  "density_ratio": 1.0,
  "algorithm_used": "skipped",
  "processing_time_ms": 0.1,
  "skip_reason": "Insufficient input points (5 < minimum 10)",
  "error_message": null
}
```

#### Error — algorithm failure
```json
{
  "status": "error",
  "original_count": 64000,
  "densified_count": 64000,
  "density_ratio": 1.0,
  "algorithm_used": "poisson",
  "processing_time_ms": 312.5,
  "skip_reason": null,
  "error_message": "Poisson reconstruction failed: normal estimation diverged"
}
```

---

## 3. DAG Node Configuration Contract

### 3.1 Full Node Payload (as stored/retrieved via DAG REST API)

```json
{
  "id": "densify_01",
  "name": "Point Cloud Densifier",
  "type": "densify",
  "config": {
    "enabled": true,
    "algorithm": "nearest_neighbor",
    "density_multiplier": 2.0,
    "target_point_count": null,
    "quality_preset": "fast",
    "preserve_normals": true,
    "throttle_ms": 0
  }
}
```

### 3.2 Minimal Configuration (all defaults)

```json
{
  "type": "densify",
  "config": {}
}
```

Resolves to `DensifyAlgorithm.NEAREST_NEIGHBOR`, `density_multiplier=2.0`, `quality_preset=FAST`, `preserve_normals=True`.

### 3.3 High-Quality Batch Mode Example

```json
{
  "type": "densify",
  "config": {
    "algorithm": "mls",
    "density_multiplier": 4.0,
    "quality_preset": "high",
    "preserve_normals": true
  }
}
```

### 3.4 Target Point Count Mode Example (10k → 40k points)

```json
{
  "type": "densify",
  "config": {
    "algorithm": "statistical",
    "target_point_count": 40000,
    "quality_preset": "medium",
    "preserve_normals": true
  }
}
```

---

## 4. `Densify.__init__` Signature (Python)

```python
class Densify(PipelineOperation):
    def __init__(
        self,
        enabled: bool = True,
        algorithm: str = "nearest_neighbor",       # DensifyAlgorithm value
        density_multiplier: float = 2.0,
        target_point_count: Optional[int] = None,
        quality_preset: str = "fast",              # DensifyQualityPreset value
        preserve_normals: bool = True,
    ) -> None: ...
```

**Constructor receives raw Python types** (str, float, int, bool) to match the pattern used by all existing
`PipelineOperation` subclasses (e.g., `Downsample(voxel_size=0.05)`). The `OperationFactory` passes `**config`
directly from the dict — Pydantic validation happens at the REST/persistence layer upstream, not inside the
operation constructor.

The constructor MUST validate:
- `algorithm` is one of `{"nearest_neighbor", "mls", "poisson", "statistical"}` → raise `ValueError` on invalid
- `density_multiplier` is in `[1.0, 8.0]` → raise `ValueError` on out-of-range
- `quality_preset` is one of `{"fast", "medium", "high"}` → raise `ValueError` on invalid

---

## 5. Algorithm Description Reference

Used in UI tooltips and documentation:

| Algorithm Key | Display Name | Use Case | Speed | Quality |
|---|---|---|---|---|
| `nearest_neighbor` | Nearest Neighbor | Real-time pipelines, LIDAR layer gap filling | <100ms | Good — preserves sharp features, minor blocky artifacts |
| `statistical` | Statistical Upsampling | General-purpose densification, interactive apps | 100–300ms | Good — adaptive, balanced quality |
| `mls` | Moving Least Squares | Batch processing, smooth surface requirements | 200–500ms | High — smooth surfaces, minor fine-detail loss |
| `poisson` | Poisson Reconstruction | Mesh generation workflows, CAD, digital twins | 500ms–2s | Best — watertight surface, may over-smooth |

---

## 6. Preset Resolution Table

| `quality_preset` | `algorithm` (if not overridden) | Target Latency |
|---|---|---|
| `fast` | `nearest_neighbor` | <100ms |
| `medium` | `statistical` | <300ms |
| `high` | `mls` | <2s |

**Note:** `poisson` is only available through explicit `algorithm` override. It is not assigned to any default preset
due to its latency profile.

---

## 7. Validation Rules Summary

| Parameter | Type | Default | Constraints |
|---|---|---|---|
| `enabled` | `bool` | `true` | — |
| `algorithm` | `str` (enum) | `"nearest_neighbor"` | One of: `nearest_neighbor`, `mls`, `poisson`, `statistical` |
| `density_multiplier` | `float` | `2.0` | `[1.0, 8.0]` |
| `target_point_count` | `int` \| `null` | `null` | `>= 1` if set; effective multiplier clamped to `[1.0, 8.0]` |
| `quality_preset` | `str` (enum) | `"fast"` | One of: `fast`, `medium`, `high` |
| `preserve_normals` | `bool` | `true` | — |

---

## 8. Integration with Existing REST API

The Densify node uses the **existing DAG configuration REST endpoints** — no new routes are added.

- `GET /api/v1/config` → returns DAG definition including densify nodes in `nodes[]`
- `POST /api/v1/config` → accepts full DAG config; densify nodes are parsed via `NodeDefinition` in registry
- `PATCH /api/v1/nodes/{node_id}` → selective node config update (uses `OperationFactory` via selective reload)

The `DensifyConfig` and `DensifyMetadata` Pydantic models are defined in `densify.py` for inline documentation
and type safety within the module. They are **not registered as separate FastAPI response models** — the existing
generic node config response schema is used upstream.
