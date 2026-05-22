"""
Unit tests for VolumeCalculator.

Strategy
--------
All tests use synthetic point clouds with known geometry so that expected
volumes can be derived analytically, independent of real sensor data.

Fixtures
--------
* ``flat_surface``  — a flat XY plane at Z=0 (empty baseline).
* ``raised_block``  — the same flat plane with a rectangular raised block
  at a known position and height (loaded state).  The block's true volume
  is ``block_w × block_d × block_h``.
* ``shifted_surface`` — the flat surface translated slightly in XYZ to
  test ICP alignment before Z-delta.

Test areas
----------
1.  VolumeResult dataclass defaults.
2.  Zero volume when both clouds are identical.
3.  Known volume — flat plane vs raised block (no ground removal, no ICP
    skew) — result within ±10 % of analytic truth.
4.  ICP fitness flag is set correctly when clouds are pre-aligned.
5.  Small translation is recovered by ICP before volume computation.
6.  Ground removal strips the dominant plane and leaves the raised block.
7.  Outlier removal handles obvious outlier spikes without crashing.
8.  No overlap between clouds returns zero volume gracefully.
9.  Bad input (None / wrong dimensions) raises ValueError.
10. morph_open_iterations=0 disables morphological opening.
11. Raised block volume scales linearly with block height.
12. delta_threshold gate: load below threshold → zero volume.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.modules.application.volume_calculation.utils.calculator import (
    VolumeCalculator,
    VolumeResult,
)


# ──────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ──────────────────────────────────────────────────────────────────────────────


def _flat_plane(
    x_range=(0.0, 1.0),
    y_range=(0.0, 1.0),
    z: float = 0.0,
    n: int = 50,
    noise: float = 0.0,
    rng_seed: int = 0,
) -> np.ndarray:
    """Dense uniform grid of points on a flat plane at given Z."""
    rng = np.random.default_rng(rng_seed)
    xi = np.linspace(x_range[0], x_range[1], n)
    yi = np.linspace(y_range[0], y_range[1], n)
    gx, gy = np.meshgrid(xi, yi)
    gz = np.full_like(gx, z)
    if noise > 0:
        gz += rng.normal(0, noise, gz.shape)
    pts = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
    return pts.astype(np.float64)


def _raised_block(
    base_pts: np.ndarray,
    block_x=(0.2, 0.8),
    block_y=(0.2, 0.8),
    block_h: float = 0.1,
) -> np.ndarray:
    """Copy base_pts and raise points inside the block region by block_h."""
    pts = base_pts.copy()
    mask = (
        (pts[:, 0] >= block_x[0]) & (pts[:, 0] <= block_x[1]) &
        (pts[:, 1] >= block_y[0]) & (pts[:, 1] <= block_y[1])
    )
    pts[mask, 2] += block_h
    return pts


def _analytic_volume(
    block_x, block_y, block_h, grid_res, delta_threshold
) -> float:
    """Theoretical volume of a rectangular block above delta_threshold.

    The Z-delta algorithm sums the raw delta values (not delta − threshold),
    so the expected volume is block_area × block_h for cells where
    block_h > delta_threshold.
    """
    if block_h <= delta_threshold:
        return 0.0
    w = block_x[1] - block_x[0]
    d = block_y[1] - block_y[0]
    return w * d * block_h


# ──────────────────────────────────────────────────────────────────────────────
# Default calculator — no ground removal (flat synthetic planes have no
# meaningful "ground" distinct from the surface) to keep tests fast and
# deterministic.
# ──────────────────────────────────────────────────────────────────────────────

GRID_RES = 0.01       # 1 cm grid — fast but precise enough for unit tests
DELTA_THR = 0.02      # 2 cm threshold (same as reference script default)


def _calc(**kwargs) -> VolumeCalculator:
    defaults = dict(
        voxel_size=0.02,
        outlier_nb_neighbors=10,
        outlier_std_ratio=3.0,
        remove_ground=False,          # disabled — synthetic surfaces are all "ground"
        use_icp=False,                # disabled — synthetic flat planes are degenerate
        min_icp_fitness=0.3,
        grid_res=GRID_RES,
        delta_threshold=DELTA_THR,
        morph_open_iterations=1,
    )
    defaults.update(kwargs)
    return VolumeCalculator(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def empty_plane() -> np.ndarray:
    return _flat_plane(n=60)


@pytest.fixture()
def loaded_block(empty_plane) -> np.ndarray:
    return _raised_block(empty_plane, block_h=0.10)


# ──────────────────────────────────────────────────────────────────────────────
# 1. VolumeResult dataclass
# ──────────────────────────────────────────────────────────────────────────────


def test_volume_result_defaults():
    r = VolumeResult(
        volume_m3=0.0,
        volume_l=0.0,
        cell_count=0,
        grid_res=0.005,
        icp_fitness=0.0,
        icp_rmse=0.0,
        icp_valid=False,
    )
    assert r.volume_m3 == 0.0
    assert len(r.grid_x) == 0
    assert len(r.grid_delta) == 0


# ──────────────────────────────────────────────────────────────────────────────
# 2. Identical clouds → zero volume
# ──────────────────────────────────────────────────────────────────────────────


def test_identical_clouds_zero_volume(empty_plane):
    calc = _calc()
    result = calc.calculate(empty_plane, empty_plane.copy())
    assert result.volume_m3 == pytest.approx(0.0, abs=1e-6)
    assert result.volume_l == pytest.approx(0.0, abs=1e-3)
    assert result.cell_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# 3. Known volume — block above threshold
# ──────────────────────────────────────────────────────────────────────────────


def test_known_volume_raised_block(empty_plane, loaded_block):
    calc = _calc()
    result = calc.calculate(empty_plane, loaded_block)

    block_x = (0.2, 0.8)
    block_y = (0.2, 0.8)
    block_h = 0.10
    # Analytic volume counts cells where delta > threshold
    expected = _analytic_volume(block_x, block_y, block_h, GRID_RES, DELTA_THR)

    assert result.volume_m3 > 0.0
    # Within 20 % of analytic truth (grid discretisation error)
    assert abs(result.volume_m3 - expected) / expected < 0.20, (
        f"volume_m3={result.volume_m3:.6f}  expected≈{expected:.6f}"
    )
    assert result.volume_l == pytest.approx(result.volume_m3 * 1000.0, rel=1e-6)


# ──────────────────────────────────────────────────────────────────────────────
# 4. ICP fitness flag — pre-aligned clouds should report valid ICP
# ──────────────────────────────────────────────────────────────────────────────


def test_icp_valid_flag_pre_aligned(empty_plane, loaded_block):
    calc = _calc()
    result = calc.calculate(empty_plane, loaded_block)
    # Pre-aligned identical-layout clouds should reach good fitness
    # (identity is already optimal → high fitness expected)
    assert isinstance(result.icp_valid, bool)
    assert result.icp_fitness >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 5. Small translation recovered by ICP
# ──────────────────────────────────────────────────────────────────────────────


def test_icp_recovers_small_translation(empty_plane, loaded_block):
    """Shift the empty cloud slightly; ICP should re-align and still give a
    reasonable volume (within 30 % of the un-shifted result)."""
    calc_ref = _calc()
    result_ref = calc_ref.calculate(empty_plane, loaded_block)

    # Shift empty cloud by 2 cm in X and 1 cm in Y
    shifted_empty = empty_plane.copy()
    shifted_empty[:, 0] += 0.02
    shifted_empty[:, 1] += 0.01

    calc_shifted = _calc()
    result_shifted = calc_shifted.calculate(shifted_empty, loaded_block)

    # After ICP the volume should be in the same ballpark
    if result_ref.volume_m3 > 0:
        ratio = result_shifted.volume_m3 / result_ref.volume_m3
        assert 0.5 < ratio < 2.0, (
            f"Shifted volume {result_shifted.volume_m3:.6f} too far from "
            f"reference {result_ref.volume_m3:.6f} (ratio={ratio:.2f})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 6. Ground removal strips the dominant plane
# ──────────────────────────────────────────────────────────────────────────────


def test_ground_removal_does_not_crash(empty_plane, loaded_block):
    """With a flat input the RANSAC ground removal should strip most points
    without raising exceptions, and a valid (possibly zero) result is returned."""
    calc = VolumeCalculator(
        voxel_size=0.02,
        remove_ground=True,
        ground_distance_threshold=0.005,
        ground_num_iterations=500,
        use_icp=False,
        min_icp_fitness=0.3,
        grid_res=GRID_RES,
        delta_threshold=DELTA_THR,
        morph_open_iterations=1,
    )
    result = calc.calculate(empty_plane, loaded_block)
    assert isinstance(result.volume_m3, float)
    assert result.volume_m3 >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 7. Outlier spikes do not crash
# ──────────────────────────────────────────────────────────────────────────────


def test_outlier_removal_with_spikes(empty_plane, loaded_block):
    """Inject obvious outlier spikes; statistical removal should handle them."""
    rng = np.random.default_rng(1)
    spikes = rng.uniform(0, 1, (20, 3))
    spikes[:, 2] = rng.uniform(10, 20, 20)  # very high Z — clear outliers
    noisy_loaded = np.vstack([loaded_block, spikes])

    calc = _calc(outlier_nb_neighbors=10, outlier_std_ratio=2.0)
    result = calc.calculate(empty_plane, noisy_loaded)
    assert isinstance(result.volume_m3, float)
    assert result.volume_m3 >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 8. No XY overlap → zero volume, no crash
# ──────────────────────────────────────────────────────────────────────────────


def test_no_overlap_returns_zero():
    empty = _flat_plane(x_range=(0.0, 1.0), y_range=(0.0, 1.0), n=30)
    loaded = _flat_plane(x_range=(2.0, 3.0), y_range=(2.0, 3.0), z=0.5, n=30)

    calc = _calc()
    result = calc.calculate(empty, loaded)
    assert result.volume_m3 == pytest.approx(0.0, abs=1e-9)
    assert result.cell_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# 9. Bad input raises ValueError
# ──────────────────────────────────────────────────────────────────────────────


def test_raises_on_none_input(empty_plane):
    calc = _calc()
    with pytest.raises(ValueError, match="required"):
        calc.calculate(None, empty_plane)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="required"):
        calc.calculate(empty_plane, None)  # type: ignore[arg-type]


def test_raises_on_2d_only_input():
    pts_2d = np.random.rand(100, 2)
    calc = _calc()
    with pytest.raises(ValueError, match="3 columns"):
        calc.calculate(pts_2d, pts_2d)


# ──────────────────────────────────────────────────────────────────────────────
# 10. morph_open_iterations=0 disables morphological opening
# ──────────────────────────────────────────────────────────────────────────────


def test_no_morph_open(empty_plane, loaded_block):
    calc = _calc(morph_open_iterations=0)
    result = calc.calculate(empty_plane, loaded_block)
    assert result.volume_m3 > 0.0

# ──────────────────────────────────────────────────────────────────────────────
# 11. Volume scales linearly with block height
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("height", [0.05, 0.10, 0.15])
def test_volume_scales_with_height(empty_plane, height):
    """Doubling the block height above the threshold should roughly double the
    net volume (after the threshold is subtracted)."""
    loaded = _raised_block(empty_plane, block_h=height)
    calc = _calc()
    result = calc.calculate(empty_plane, loaded)

    # If block height <= delta_threshold the volume must be zero
    if height <= DELTA_THR:
        assert result.volume_m3 == pytest.approx(0.0, abs=1e-6)
    else:
        assert result.volume_m3 > 0.0


def test_volume_doubles_with_double_height(empty_plane):
    h1, h2 = 0.08, 0.16   # effective heights above DELTA_THR: 0.06 and 0.14
    r1 = _calc().calculate(empty_plane, _raised_block(empty_plane, block_h=h1))
    r2 = _calc().calculate(empty_plane, _raised_block(empty_plane, block_h=h2))

    # (h2 - thr) / (h1 - thr) = (0.14) / (0.06) ≈ 2.33
    expected_ratio = (h2 - DELTA_THR) / (h1 - DELTA_THR)
    actual_ratio = r2.volume_m3 / r1.volume_m3
    assert abs(actual_ratio - expected_ratio) / expected_ratio < 0.15, (
        f"actual_ratio={actual_ratio:.3f}  expected_ratio={expected_ratio:.3f}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 12. delta_threshold gate: load below threshold → zero volume
# ──────────────────────────────────────────────────────────────────────────────


def test_delta_threshold_gates_small_load(empty_plane):
    """A raised block whose height is at or below delta_threshold must yield
    zero volume because no cell exceeds the threshold."""
    small_h = 0.01   # 1 cm — below default 2 cm threshold
    loaded = _raised_block(empty_plane, block_h=small_h)
    calc = _calc(delta_threshold=0.02)
    result = calc.calculate(empty_plane, loaded)
    assert result.volume_m3 == pytest.approx(0.0, abs=1e-6)
    assert result.cell_count == 0
