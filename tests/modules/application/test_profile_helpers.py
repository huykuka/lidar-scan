"""
Unit tests for profile_helpers.py — pure functions only, no LiDAR hardware needed.

Each function is tested with:
  - a normal/happy-path case
  - edge cases (empty arrays, single element, all zeros, W=1, etc.)
  - a correctness cross-check against a simple reference implementation
"""
import numpy as np
import pytest

from app.modules.application.truck_bin_detection.utils.profile_helpers import (
    BinDetectionResult,
    build_height_profile,
    fill_profile,
    miss,
    rolling_bwd_max,
    rolling_fwd_max,
)


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _naive_fwd_max(arr: np.ndarray, W: int) -> np.ndarray:
    """Reference: brute-force max(arr[i+1 : i+W]) — correct but O(N×W)."""
    out = np.full(len(arr), -np.inf)
    for i in range(len(arr)):
        window = arr[i + 1: i + W]
        if len(window) > 0:
            out[i] = float(window.max())
    return out


def _naive_bwd_max(arr: np.ndarray, W: int) -> np.ndarray:
    """Reference: brute-force max(arr[i-W : i]) — correct but O(N×W)."""
    out = np.full(len(arr), -np.inf)
    for i in range(len(arr)):
        window = arr[max(0, i - W): i]
        if len(window) == W:      # only count full windows (same as sliding_window_view)
            out[i] = float(window.max())
    return out


# ---------------------------------------------------------------------------
# BinDetectionResult
# ---------------------------------------------------------------------------

class TestBinDetectionResult:

    def test_defaults_are_not_detected(self):
        r = BinDetectionResult(detected=False)
        assert r.detected is False
        assert r.x_rear_internal == 0.0
        assert r.x_front_internal == 0.0
        assert r.x_center == 0.0
        assert r.length == 0.0
        assert r.confidence == 0.0
        assert r.status == "SEARCH"
        assert r.bin_points is None

    def test_to_dict_rounds_correctly(self):
        r = BinDetectionResult(
            detected=True,
            x_rear_internal=1.23456,
            x_front_internal=7.89012,
            x_center=4.56234,
            length=6.65556,
            confidence=0.98765,
            status="DETECTED",
        )
        d = r.to_dict()
        assert d["x_rear_internal"] == 1.235
        assert d["x_front_internal"] == 7.890
        assert d["x_center"] == 4.562
        assert d["length"] == 6.656
        assert d["confidence"] == 0.99
        assert d["detected"] is True
        assert d["status"] == "DETECTED"

    def test_to_dict_excludes_bin_points(self):
        r = BinDetectionResult(detected=True, bin_points=np.zeros((10, 3)))
        d = r.to_dict()
        assert "bin_points" not in d


# ---------------------------------------------------------------------------
# miss()
# ---------------------------------------------------------------------------

class TestMiss:

    def test_returns_not_detected(self):
        r = miss("SEARCH / NO VEHICLE")
        assert r.detected is False

    def test_status_is_propagated(self):
        for s in ["SEARCH / NO VEHICLE", "SEARCH / REAR EDGE NOT FOUND", "CUSTOM"]:
            assert miss(s).status == s

    def test_all_numeric_fields_are_zero(self):
        r = miss("X")
        assert r.x_rear_internal == 0.0
        assert r.x_front_internal == 0.0
        assert r.x_center == 0.0
        assert r.length == 0.0
        assert r.confidence == 0.0


# ---------------------------------------------------------------------------
# rolling_fwd_max()
# ---------------------------------------------------------------------------

class TestRollingFwdMax:

    def test_matches_naive_reference(self):
        rng = np.random.default_rng(0)
        arr = rng.uniform(0, 10, 50)
        for W in [2, 3, 5, 10, 30]:
            result = rolling_fwd_max(arr, W)
            ref    = _naive_fwd_max(arr, W)
            np.testing.assert_allclose(
                result, ref, err_msg=f"W={W}: mismatch with naive reference"
            )

    def test_output_length_equals_input_length(self):
        arr = np.ones(20)
        for W in [2, 5, 20, 50]:
            assert len(rolling_fwd_max(arr, W)) == len(arr)

    def test_last_position_is_minus_inf(self):
        # The very last position has no cells ahead of it at all → -inf.
        arr = np.arange(10, dtype=float)
        for W in [2, 4, 10]:
            result = rolling_fwd_max(arr, W)
            assert result[-1] == -np.inf, f"W={W}: last position should be -inf"

    def test_w_equals_1_returns_all_minus_inf(self):
        # W=1 means window of size 0 — nothing to look ahead.
        arr = np.ones(10)
        result = rolling_fwd_max(arr, 1)
        assert np.all(result == -np.inf)

    def test_w_equals_2_is_next_cell(self):
        # W=2 → window is just arr[i+1], so fwd_max[i] == arr[i+1].
        arr = np.array([1.0, 5.0, 3.0, 8.0, 2.0])
        result = rolling_fwd_max(arr, 2)
        np.testing.assert_allclose(result[:4], arr[1:])
        assert result[4] == -np.inf

    def test_constant_array(self):
        arr = np.full(15, 3.0)
        result = rolling_fwd_max(arr, 5)
        # All non-tail positions should be 3.0
        np.testing.assert_allclose(result[:-(5 - 1)], 3.0)

    def test_single_spike(self):
        arr = np.zeros(10)
        arr[5] = 9.9
        result = rolling_fwd_max(arr, 10)
        # Positions 0..4 should see the spike; positions 5..9 should not.
        for i in range(5):
            assert result[i] == 9.9, f"i={i} should see the spike"
        for i in range(5, 10):
            assert result[i] == 0.0 or result[i] == -np.inf, f"i={i} should not see spike"


# ---------------------------------------------------------------------------
# rolling_bwd_max()
# ---------------------------------------------------------------------------

class TestRollingBwdMax:

    def test_matches_naive_reference(self):
        rng = np.random.default_rng(1)
        arr = rng.uniform(0, 10, 50)
        for W in [1, 2, 5, 10]:
            result = rolling_bwd_max(arr, W)
            ref    = _naive_bwd_max(arr, W)
            np.testing.assert_allclose(
                result, ref, err_msg=f"W={W}: mismatch with naive reference"
            )

    def test_output_length_equals_input_length(self):
        arr = np.ones(25)
        for W in [1, 3, 10, 25]:
            assert len(rolling_bwd_max(arr, W)) == len(arr)

    def test_leading_positions_are_minus_inf(self):
        # First W positions have no history — must be -inf.
        arr = np.arange(10, dtype=float)
        W = 3
        result = rolling_bwd_max(arr, W)
        assert np.all(result[:W] == -np.inf)

    def test_w_equals_1_is_previous_cell(self):
        # W=1 → window is just arr[i-1], so bwd_max[i] == arr[i-1].
        arr = np.array([1.0, 5.0, 3.0, 8.0, 2.0])
        result = rolling_bwd_max(arr, 1)
        assert result[0] == -np.inf
        np.testing.assert_allclose(result[1:], arr[:-1])

    def test_constant_array(self):
        arr = np.full(15, 7.0)
        result = rolling_bwd_max(arr, 4)
        np.testing.assert_allclose(result[4:], 7.0)

    def test_no_false_positive_at_rising_edge(self):
        # Simulates a rising edge: flat then climbing.
        # bwd_max should be low while we are still in the flat region.
        arr = np.array([1.0, 1.0, 1.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        result = rolling_bwd_max(arr, 3)
        # At i=4 (first rising cell), the window arr[1:4] = [1,1,1] → max = 1.
        assert result[4] == 1.0
        # At i=7, the window arr[4:7] = [2,3,4] → max = 4.
        assert result[7] == 4.0


# ---------------------------------------------------------------------------
# build_height_profile()
# ---------------------------------------------------------------------------

class TestBuildHeightProfile:

    def _make_pts(self, xs, zs):
        """Build a minimal (N, 3) point array from x and z lists."""
        n = len(xs)
        pts = np.zeros((n, 3), dtype=np.float64)
        pts[:, 0] = xs
        pts[:, 2] = zs
        return pts

    def test_basic_max_per_cell(self):
        # Two points in the same cell: profile should hold the maximum.
        pts = self._make_pts([0.0, 0.01, 1.0], [2.0, 5.0, 3.0])
        hp = build_height_profile(pts, x_min=0.0, num_bins=20, cell_size=0.07, z_max=10.0)
        assert hp[0] == pytest.approx(5.0)  # cell 0 holds max(2.0, 5.0)

    def test_z_max_clips_spikes(self):
        # A rain spike at z=9.9 should be clipped to z_max=4.0.
        pts = self._make_pts([0.5], [9.9])
        hp = build_height_profile(pts, x_min=0.0, num_bins=20, cell_size=0.07, z_max=4.0)
        assert hp.max() == pytest.approx(4.0)

    def test_empty_cells_are_zero(self):
        # Only one point — all other cells must be 0.
        pts = self._make_pts([0.0], [2.5])
        hp = build_height_profile(pts, x_min=0.0, num_bins=10, cell_size=0.07, z_max=10.0)
        assert hp[0] == pytest.approx(2.5)
        assert np.all(hp[1:] == 0.0)

    def test_points_clipped_to_valid_bin_range(self):
        # Points outside [x_min, x_min + num_bins*cell_size] must be
        # clamped to the first / last bin rather than causing an index error.
        pts = self._make_pts([-5.0, 100.0], [1.0, 1.0])
        hp = build_height_profile(pts, x_min=0.0, num_bins=10, cell_size=0.07, z_max=10.0)
        assert hp[0] == pytest.approx(1.0)   # clamped to bin 0
        assert hp[-1] == pytest.approx(1.0)  # clamped to last bin

    def test_does_not_modify_input(self):
        pts = self._make_pts([0.0, 0.5, 1.0], [1.0, 2.0, 3.0])
        original = pts.copy()
        build_height_profile(pts, x_min=0.0, num_bins=20, cell_size=0.07, z_max=10.0)
        np.testing.assert_array_equal(pts, original)

    def test_multiple_points_same_cell_takes_max(self):
        pts = self._make_pts([0.0, 0.02, 0.04], [1.0, 3.0, 2.0])
        hp = build_height_profile(pts, x_min=0.0, num_bins=5, cell_size=0.07, z_max=10.0)
        assert hp[0] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# fill_profile()
# ---------------------------------------------------------------------------

class TestFillProfile:

    def test_no_gaps_unchanged(self):
        hp = np.array([1.0, 2.0, 3.0, 4.0])
        fp = fill_profile(hp)
        np.testing.assert_allclose(fp, hp)

    def test_interior_gap_forward_filled(self):
        # Zero in the middle should get the value from the cell to its left.
        hp = np.array([0.0, 2.0, 0.0, 0.0, 4.0])
        fp = fill_profile(hp)
        assert fp[2] == pytest.approx(2.0)
        assert fp[3] == pytest.approx(2.0)

    def test_leading_zeros_backward_filled(self):
        # Zeros at the start should get the value of the first non-zero cell.
        hp = np.array([0.0, 0.0, 3.0, 3.0])
        fp = fill_profile(hp)
        assert fp[0] == pytest.approx(3.0)
        assert fp[1] == pytest.approx(3.0)

    def test_trailing_zeros_forward_filled(self):
        hp = np.array([2.0, 2.0, 0.0, 0.0])
        fp = fill_profile(hp)
        assert fp[2] == pytest.approx(2.0)
        assert fp[3] == pytest.approx(2.0)

    def test_all_zeros_returns_zeros(self):
        hp = np.zeros(8)
        fp = fill_profile(hp)
        np.testing.assert_array_equal(fp, np.zeros(8))

    def test_single_non_zero(self):
        hp = np.array([0.0, 0.0, 5.0, 0.0, 0.0])
        fp = fill_profile(hp)
        # Every cell should become 5.0 (forward and backward fill).
        np.testing.assert_allclose(fp, 5.0)

    def test_does_not_modify_input(self):
        hp = np.array([0.0, 2.0, 0.0, 4.0, 0.0])
        original = hp.copy()
        fill_profile(hp)
        np.testing.assert_array_equal(hp, original)

    def test_output_has_no_zeros_when_any_nonzero(self):
        rng = np.random.default_rng(42)
        hp = rng.uniform(0, 5, 100)
        hp[::3] = 0.0           # punch holes every 3rd cell
        hp[0] = 0.0             # leading zero
        hp[-1] = 0.0            # trailing zero
        hp[50] = 2.0            # ensure at least one non-zero
        fp = fill_profile(hp)
        assert np.all(fp > 0.0), "fill_profile left zeros when non-zero cells exist"

    def test_cavity_floor_remains_low_after_fill(self):
        # Simulates a real profile: high walls around a low cavity.
        # The cavity cells (zeros) should be filled with low floor values,
        # NOT with the wall height — forward fill from the rear wall.
        hp = np.array([0.0, 2.5, 2.5, 0.0, 0.0, 0.0, 2.5, 2.5])
        fp = fill_profile(hp)
        # Cavity cells (3,4,5) forward-filled from cell 2 (value 2.5).
        # This is expected behaviour — the gradient step will detect the drop.
        assert fp[3] == pytest.approx(2.5)
        # Walls are unchanged.
        assert fp[1] == pytest.approx(2.5)
        assert fp[6] == pytest.approx(2.5)
