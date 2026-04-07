# Densify Point Cloud — API Specification

**Feature:** `densify-point-cloud`  
**Module:** `app/modules/pipeline/operations/densify.py`  
**Schema Location:** `app/modules/pipeline/operations/densify.py` (inline Pydantic models)  
**Version:** 1.1  
**References:** `technical.md` §7, §8, §11, §16, §17

---

## 1. Pydantic Configuration Model

### 1.1 Enums

```python
from enum import Enum

class DensifyLogLevel(str, Enum):
    """Controls per-call log verbosity from Densify.apply()."""
    MINIMAL = "minimal"  # Single summary log per apply() call (default)
    FULL    = "full"     # Original verbose per-step DEBUG logging
    NONE    = "none"     # Complete silence except ERROR


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
    algorithm: Optional[DensifyAlgorithm] = Field(
        default=None,
        description=(
            "Densification algorithm.  If set explicitly (not None), takes precedence over "
            "quality_preset.  When None (default), the algorithm is resolved from quality_preset "
            "via PRESET_ALGORITHM_MAP: fast→nearest_neighbor, medium→statistical, high→mls. "
            "Implementation note: Densify.__init__ accepts algorithm=None as 'use preset' mode."
        )
    )

    # ── Density target ────────────────────────────────────────────────────────
    density_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=8.0,
        description=(
            "Target density increase factor. 2.0 doubles the point count. "
            "Range: 1.0 (no change) to 8.0 (max, memory guard)."
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
    @field_validator("density_multiplier")    @classmethod
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

---

### 1.3 Per-Algorithm Parameter Models

Each algorithm exposes a dedicated Pydantic model for fine-tuning. All fields have production-safe defaults; omitting
the sub-dict entirely reverts to the original hardcoded production defaults.

```python
class DensifyNNParams(BaseModel):
    """Tunable parameters for the Nearest Neighbor algorithm."""
    displacement_min: float = Field(
        default=0.05, gt=0.0, lt=1.0,
        description="Lower bound of displacement range as a fraction of mean_nn_dist. Default: 0.05."
    )
    displacement_max: float = Field(
        default=0.5, gt=0.0, le=2.0,
        description="Upper bound of displacement range as a fraction of mean_nn_dist. Default: 0.5."
    )


class DensifyMLSParams(BaseModel):
    """Tunable parameters for the Moving Least Squares algorithm."""
    k_neighbors: int = Field(
        default=20, ge=3, le=100,
        description="KNN count for normal estimation and tangent plane fitting. Default: 20."
    )
    projection_radius_factor: float = Field(
        default=0.5, gt=0.0, le=5.0,
        description="Tangent-plane projection radius as a factor of mean_nn_dist. Default: 0.5."
    )
    min_dist_factor: float = Field(
        default=0.05, gt=0.0, lt=1.0,
        description="Post-filter minimum distance as a factor of mean_nn_dist. Default: 0.05."
    )


class DensifyStatisticalParams(BaseModel):
    """Tunable parameters for the Statistical Upsampling algorithm."""
    k_neighbors: int = Field(
        default=10, ge=3, le=100,
        description="KNN count for local density estimation. Default: 10."
    )
    sparse_percentile: float = Field(
        default=50.0, ge=1.0, le=99.0,
        description="Density percentile below which a region is considered sparse. Default: 50."
    )
    min_dist_factor: float = Field(
        default=0.3, gt=0.0, lt=2.0,
        description="Post-filter minimum distance as a factor of mean_nn_dist. Default: 0.3."
    )


class DensifyPoissonParams(BaseModel):
    """Tunable parameters for the Poisson Reconstruction algorithm."""
    depth: int = Field(
        default=8, ge=4, le=12,
        description="Octree depth for Poisson reconstruction. Higher = finer mesh, slower. Default: 8."
    )
    density_threshold_quantile: float = Field(
        default=0.1, ge=0.0, le=0.5,
        description="Quantile below which low-density Poisson mesh vertices are trimmed. Default: 0.1."
    )
```

---

### 1.4 Updated Configuration Model (`DensifyConfig`)

This model represents the `config` dict passed through `OperationFactory.create("densify", config)`.
It is also the schema for DAG node persistence and the REST API config endpoint.

```python
class DensifyConfig(BaseModel):
    # ── Core toggles ──────────────────────────────────────────────────────────
    enabled: bool = Field(default=True)

    # ── Algorithm selection ───────────────────────────────────────────────────
    algorithm: Optional[DensifyAlgorithm] = Field(default=None)

    # ── Density target ────────────────────────────────────────────────────────
    density_multiplier: float = Field(default=2.0, ge=1.0, le=8.0)

    # ── Quality preset ────────────────────────────────────────────────────────
    quality_preset: DensifyQualityPreset = Field(default=DensifyQualityPreset.FAST)

    # ── Normals ───────────────────────────────────────────────────────────────
    preserve_normals: bool = Field(default=True)

    # ── Log level (NEW in v1.1) ───────────────────────────────────────────────
    log_level: DensifyLogLevel = Field(
        default=DensifyLogLevel.MINIMAL,
        description=(
            "Controls per-call log verbosity. "
            "'minimal' = single summary log per apply() (default). "
            "'full' = verbose per-step DEBUG logs. "
            "'none' = silence except ERROR. "
            "Also overridable via DENSIFY_LOG_LEVEL env var (explicit kwarg wins)."
        )
    )

    # ── Per-algorithm tunable params (NEW in v1.1) ────────────────────────────
    nn_params: Optional[DensifyNNParams] = Field(
        default=None,
        description="Nearest Neighbor tunable params. None → production defaults."
    )
    mls_params: Optional[DensifyMLSParams] = Field(
        default=None,
        description="MLS tunable params. None → production defaults."
    )
    statistical_params: Optional[DensifyStatisticalParams] = Field(
        default=None,
        description="Statistical Upsampling tunable params. None → production defaults."
    )
    poisson_params: Optional[DensifyPoissonParams] = Field(
        default=None,
        description="Poisson Reconstruction tunable params. None → production defaults."
    )

    model_config = {"use_enum_values": True, "populate_by_name": True}
```

**JSON Schema (for DAG config persistence and REST body — v1.1):**

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
      "description": "Target density multiplier."
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
    },
    "log_level": {
      "type": "string",
      "enum": ["minimal", "full", "none"],
      "default": "minimal",
      "description": "Log verbosity per apply() call. Also settable via DENSIFY_LOG_LEVEL env var."
    },
    "nn_params": {
      "type": "object",
      "description": "Nearest Neighbor algorithm parameters (optional).",
      "properties": {
        "displacement_min": {"type": "number", "default": 0.05},
        "displacement_max": {"type": "number", "default": 0.5}
      }
    },
    "mls_params": {
      "type": "object",
      "description": "MLS algorithm parameters (optional).",
      "properties": {
        "k_neighbors": {"type": "integer", "default": 20},
        "projection_radius_factor": {"type": "number", "default": 0.5},
        "min_dist_factor": {"type": "number", "default": 0.05}
      }
    },
    "statistical_params": {
      "type": "object",
      "description": "Statistical Upsampling parameters (optional).",
      "properties": {
        "k_neighbors": {"type": "integer", "default": 10},
        "sparse_percentile": {"type": "number", "default": 50.0},
        "min_dist_factor": {"type": "number", "default": 0.3}
      }
    },
    "poisson_params": {
      "type": "object",
      "description": "Poisson Reconstruction parameters (optional).",
      "properties": {
        "depth": {"type": "integer", "default": 8},
        "density_threshold_quantile": {"type": "number", "default": 0.1}
      }
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
    "quality_preset": "fast",
    "preserve_normals": true,
    "log_level": "minimal",
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

### 3.4 Fine-Tuned Algorithm Params Example (NEW in v1.1)

```json
{
  "type": "densify",
  "config": {
    "algorithm": "statistical",
    "density_multiplier": 3.0,
    "log_level": "none",
    "statistical_params": {
      "k_neighbors": 15,
      "sparse_percentile": 40.0,
      "min_dist_factor": 0.2
    }
  }
}
```

```json
{
  "type": "densify",
  "config": {
    "algorithm": "poisson",
    "density_multiplier": 2.0,
    "log_level": "full",
    "poisson_params": {
      "depth": 9,
      "density_threshold_quantile": 0.05
    }
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
        algorithm: str = "nearest_neighbor",           # DensifyAlgorithm value
        density_multiplier: float = 2.0,
        quality_preset: str = "fast",                  # DensifyQualityPreset value
        preserve_normals: bool = True,
        # NEW in v1.1 ─────────────────────────────────
        log_level: str | None = None,                  # 'minimal'|'full'|'none'; None → env-var fallback → 'minimal'
        nn_params: dict | DensifyNNParams | None = None,
        mls_params: dict | DensifyMLSParams | None = None,
        statistical_params: dict | DensifyStatisticalParams | None = None,
        poisson_params: dict | DensifyPoissonParams | None = None,
    ) -> None: ...
```

**Constructor receives raw Python types** (str, float, int, bool, dict) to match the pattern used by all existing
`PipelineOperation` subclasses (e.g., `Downsample(voxel_size=0.05)`). The `OperationFactory` passes `**config`
directly from the dict — Pydantic validation happens at the REST/persistence layer upstream, not inside the
operation constructor.

**`log_level` resolution precedence:**
1. Explicit `log_level=` constructor argument (highest priority)
2. `DENSIFY_LOG_LEVEL` environment variable
3. Default: `'minimal'`

**`*_params` coercion:** If a plain `dict` is passed, it is coerced to the typed Pydantic model automatically
(e.g., `nn_params={"displacement_min": 0.1}` → `DensifyNNParams(displacement_min=0.1, displacement_max=0.5)`).

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
| `quality_preset` | `str` (enum) | `"fast"` | One of: `fast`, `medium`, `high` |
| `preserve_normals` | `bool` | `true` | — |
| `log_level` | `str` (enum) | `"minimal"` | One of: `minimal`, `full`, `none`; also settable via `DENSIFY_LOG_LEVEL` env var |
| `nn_params` | `dict` / `DensifyNNParams` | `null` | Optional; keys: `displacement_min ∈ (0,1)`, `displacement_max ∈ (0,2]` |
| `mls_params` | `dict` / `DensifyMLSParams` | `null` | Optional; keys: `k_neighbors ∈ [3,100]`, `projection_radius_factor ∈ (0,5]`, `min_dist_factor ∈ (0,1)` |
| `statistical_params` | `dict` / `DensifyStatisticalParams` | `null` | Optional; keys: `k_neighbors ∈ [3,100]`, `sparse_percentile ∈ [1,99]`, `min_dist_factor ∈ (0,2)` |
| `poisson_params` | `dict` / `DensifyPoissonParams` | `null` | Optional; keys: `depth ∈ [4,12]`, `density_threshold_quantile ∈ [0,0.5]` |

---

## 8. Integration with Existing REST API

The Densify node uses the **existing DAG configuration REST endpoints** — no new routes are added.

- `GET /api/v1/config` → returns DAG definition including densify nodes in `nodes[]`
- `POST /api/v1/config` → accepts full DAG config; densify nodes are parsed via `NodeDefinition` in registry
- `PATCH /api/v1/nodes/{node_id}` → selective node config update (uses `OperationFactory` via selective reload)

The `DensifyConfig` and `DensifyMetadata` Pydantic models are defined in `densify.py` for inline documentation
and type safety within the module. They are **not registered as separate FastAPI response models** — the existing
generic node config response schema is used upstream.
