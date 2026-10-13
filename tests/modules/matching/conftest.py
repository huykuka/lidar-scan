import numpy as np
import pytest
from scipy.spatial.transform import Rotation as R


def _box(rng, c, s, n):
    p = rng.uniform(-0.5, 0.5, (n, 3))
    f = rng.integers(0, 3, n)
    p[np.arange(n), f] = rng.choice([-0.5, 0.5], n)
    return p * np.asarray(s) + np.asarray(c)


@pytest.fixture
def reference():
    """Asymmetric L-shaped object with a post (unambiguous pose)."""
    rng = np.random.default_rng(0)
    return np.vstack([
        _box(rng, [0, 0, 0], [1.0, 0.4, 0.3], 6000),
        _box(rng, [0.4, 0.5, 0], [0.2, 0.8, 0.3], 4000),
        _box(rng, [-0.3, 0, 0.4], [0.15, 0.15, 0.6], 2000),
    ])


@pytest.fixture
def make_scene(reference):
    def _make(yaw_deg=70.0, translation=(4.0, -2.0, 0.5), seed=1):
        rng = np.random.default_rng(seed)
        T = np.eye(4)
        T[:3, :3] = R.from_euler("z", yaw_deg, degrees=True).as_matrix()
        T[:3, 3] = translation
        obj = reference @ T[:3, :3].T + T[:3, 3]
        floor = np.c_[rng.uniform(-10, 10, (30000, 2)), rng.normal(0, 0.005, 30000) - 0.3]
        clutter = np.vstack([
            _box(rng, [-3, 3, 0.5], [1.5, 1.5, 1.5], 5000),
            _box(rng, [2, 6, 0.2], [2, 0.5, 0.8], 3000),
        ])
        scene = np.vstack([obj, floor, clutter])
        scene = scene + rng.normal(0, 0.003, scene.shape)
        centre = T[:3, :3] @ reference.mean(axis=0) + T[:3, 3]
        return scene.astype(np.float32), T, centre
    return _make
