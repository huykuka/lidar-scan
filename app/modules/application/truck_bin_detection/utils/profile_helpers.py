"""
Shared data types and pure helper functions for the bin detector.

Kept separate from BinDetector so the profile math can be tested and
reasoned about in isolation, without the full detection state machine.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class BinDetectionResult:
    """Everything the system needs to know about a detected bin."""

    detected: bool
    x_rear_internal: float = 0.0   # inner face of rear wall (m)
    x_front_internal: float = 0.0  # inner face of front wall (m)
    x_center: float = 0.0          # midpoint between the two walls (m)
    length: float = 0.0            # internal cavity length (m)
    confidence: float = 0.0        # 0–1, fraction of bed points on a flat plane
    status: str = "SEARCH"
    bin_points: Optional[np.ndarray] = None  # wall edge point clouds (rear + front)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "x_rear_internal": round(self.x_rear_internal, 3),
            "x_front_internal": round(self.x_front_internal, 3),
            "x_center": round(self.x_center, 3),
            "length": round(self.length, 3),
            "confidence": round(self.confidence, 2),
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def miss(status: str) -> BinDetectionResult:
    """Return a not-detected result with the given status string."""
    return BinDetectionResult(detected=False, status=status)


def rolling_fwd_max(arr: np.ndarray, W: int) -> np.ndarray:
    """Precompute max(arr[i+1 : i+W]) for every i in O(N).

    Why: the peak search in step 5a checks whether arr[i] is greater than
    everything in the next W cells.  Doing np.max(arr[i+1:i+W]) inside the
    loop would be O(N×W).  Building this lookup table once with
    sliding_window_view reduces every per-cell check to a single array read.

    Positions where the window would extend past the end of the array are
    filled with -inf so they never falsely satisfy the peak condition.
    """
    W -= 1  # window starts at i+1, so effective width is W-1
    N = len(arr)
    if W <= 0 or N == 0:
        return np.full(N, -np.inf)
    # arr[1:] shifts the source so window[i] covers arr[i+1:i+1+W].
    # Pad the right with W values of -inf so windows near the tail still
    # have full width — padding entries ensure those windows never beat a
    # real threshold, making them equivalent to -inf results.
    # After padding: len = (N-1) + W = N+W-1.
    # sliding_window_view of size W gives (N+W-1) - W + 1 = N rows. ✓
    shifted = np.concatenate([arr[1:], np.full(W, -np.inf)])
    wins = np.lib.stride_tricks.sliding_window_view(shifted, W)
    return wins.max(axis=1)  # shape (N,)


def rolling_bwd_max(arr: np.ndarray, W: int) -> np.ndarray:
    """Precompute max(arr[i-W : i]) for every i in O(N).

    Only positions with a full W-cell history are filled; positions with
    fewer than W cells before them return -inf.

    Why: the front-wall check in step 5c needs the candidate cell to be
    higher than the W cells immediately before it — confirming we are at
    the START of the rising edge, not somewhere in the middle of the slope.
    Building the lookup once avoids a per-cell slice.
    """
    N = len(arr)
    if W <= 0 or N == 0:
        return np.full(N, -np.inf)
    # sliding_window_view(arr, W) gives rows [arr[0:W], arr[1:W+1], ...].
    # Row k covers arr[k : k+W].  We want bwd_max[i] = max(arr[i-W : i]),
    # which is row (i-W).  The first valid i is W (row 0); positions 0..W-1
    # have fewer than W cells of history and stay -inf.
    if W > N:
        return np.full(N, -np.inf)
    wins = np.lib.stride_tricks.sliding_window_view(arr, W)  # shape (N-W+1, W)
    # wins[k] = arr[k:k+W].  bwd_max[i] = wins[i-W] for i >= W.
    result = np.full(N, -np.inf)
    result[W:] = wins[:-1].max(axis=1) if len(wins) > 1 else np.full(N - W, -np.inf)
    return result


def build_height_profile(
    pts: np.ndarray,
    x_min: float,
    num_bins: int,
    cell_size: float,
    z_max: float,
) -> np.ndarray:
    """Scatter points into a 1-D height profile (max Z per cell).

    Why max instead of 90th-percentile: z_max clipping upstream removes
    rain/dust spikes, so max is equivalent but runs in O(N) with a single
    vectorised scatter rather than O(N log N) sort + per-bin partition.
    """
    hp = np.zeros(num_bins)
    bin_idx = np.clip(
        ((pts[:, 0] - x_min) / cell_size).astype(np.intp), 0, num_bins - 1
    )
    np.maximum.at(hp, bin_idx, np.minimum(pts[:, 2], z_max))
    return hp


def fill_profile(hp: np.ndarray) -> np.ndarray:
    """Forward-fill then backward-fill empty cells in a height profile.

    Why: some cells have no LiDAR return (open air above the bin cavity,
    sparse coverage).  Empty cells (value 0) break the gradient and
    threshold comparisons that follow.  Forward-fill carries the last
    known height rightward; backward-fill handles any leading zeros at
    the left edge that forward-fill cannot reach.

    The original raw profile (hp) is NOT modified — the caller keeps it
    for occupancy checks where zeros must remain meaningful.
    """
    num_bins = len(hp)
    mask = hp > 0.0

    if not np.any(mask):
        return hp.copy()          # all zeros — nothing to fill

    # Forward fill: propagate the last non-zero value rightward.
    # Sentinel -1 marks cells not yet reached (avoids confusing cell-0
    # index with "not filled").
    fwd_idx = np.where(mask, np.arange(num_bins), -1)
    np.maximum.accumulate(fwd_idx, out=fwd_idx)

    # Backward fill: for leading zeros (fwd_idx still -1), find the index
    # of the next non-zero value to the RIGHT by scanning in reverse.
    bwd_idx = np.where(mask, np.arange(num_bins), num_bins + 1)
    bwd_idx = np.minimum.accumulate(bwd_idx[::-1])[::-1]
    bwd_idx = np.clip(bwd_idx, 0, num_bins - 1)

    # Forward fill has priority; backward fill covers only leading zeros.
    safe_fwd = np.maximum(fwd_idx, 0)
    return np.where(fwd_idx >= 0, hp[safe_fwd], hp[bwd_idx])
