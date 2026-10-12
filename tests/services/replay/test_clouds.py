"""Unit tests for point-cloud capture, diffing and the binary wire format."""
import struct

import numpy as np

from app.services.replay.clouds import (
    HEADER_FORMAT,
    HEADER_SIZE,
    CloudCapture,
    common_cloud_nodes,
    diff_clouds,
    pack_cloud_diff,
    read_cloud,
)


def test_capture_roundtrip_last_emission_wins(tmp_path):
    frame = {"i": 0}
    cap = CloudCapture(tmp_path, ["n1", "n2"], lambda: frame["i"])
    first = np.arange(30, dtype=np.float32).reshape(10, 3)
    second = first + 100
    cap.record("n1", {"points": first})
    cap.record("n1", {"points": second})          # same frame emitted twice
    frame["i"] = 1
    cap.record("n1", {"points": first[:4]})
    cap.record("other", {"points": first})         # not captured
    meta = cap.finalize({"n1": "Node one"})

    assert meta["n1"]["frames"] == [0, 1] and meta["n1"]["name"] == "Node one"
    assert "n2" not in meta                         # captured nothing
    np.testing.assert_array_equal(read_cloud(tmp_path, "n1", 0), second)
    np.testing.assert_array_equal(read_cloud(tmp_path, "n1", 1), first[:4])
    assert read_cloud(tmp_path, "n1", 7) is None


def test_capture_keeps_xyz_of_wider_clouds(tmp_path):
    cap = CloudCapture(tmp_path, ["n"], lambda: 0)
    cap.record("n", {"points": np.ones((5, 4), dtype=np.float64)})  # xyz + intensity
    cap.finalize({})
    assert read_cloud(tmp_path, "n", 0).shape == (5, 3)


def test_diff_flags_only_points_without_counterpart():
    a = np.array([[0, 0, 0], [1, 0, 0], [5, 5, 5]], dtype=np.float32)
    b = np.array([[0, 0, 0.01], [1, 0, 0], [9, 9, 9]], dtype=np.float32)
    d = diff_clouds(a, b, tol=0.05)
    assert d["flags_a"].tolist() == [0, 0, 1]
    assert d["flags_b"].tolist() == [0, 0, 1]


def test_diff_with_empty_cloud_flags_everything():
    d = diff_clouds(np.zeros((3, 3), np.float32), np.zeros((0, 3), np.float32), 0.1)
    assert d["flags_a"].tolist() == [1, 1, 1] and len(d["flags_b"]) == 0


def test_pack_layout_is_aligned_and_decodable():
    a = np.random.rand(7, 3).astype(np.float32)      # 7 flags -> padded to 8
    b = np.random.rand(5, 3).astype(np.float32)
    d = diff_clouds(a, b, tol=1e-6)
    buf = pack_cloud_diff(a, b, d)

    n_a, n_b, only_a, only_b, mean_a, mean_b = struct.unpack_from(HEADER_FORMAT, buf, 0)
    assert (n_a, n_b) == (7, 5) and only_a == int(d["flags_a"].sum())
    off = HEADER_SIZE
    assert off % 4 == 0
    np.testing.assert_array_equal(np.frombuffer(buf, "<f4", n_a * 3, off).reshape(-1, 3), a)
    off += n_a * 12
    assert np.frombuffer(buf, np.uint8, n_a, off).tolist() == d["flags_a"].tolist()
    off += n_a + (-n_a % 4)
    assert off % 4 == 0
    np.testing.assert_array_equal(np.frombuffer(buf, "<f4", n_b * 3, off).reshape(-1, 3), b)
    assert len(buf) == off + n_b * 12 + n_b + (-n_b % 4)


def test_common_cloud_nodes_intersects_frames():
    a = {"clouds": {"n": {"name": "N", "frames": [0, 1, 2], "truncated": False}, "x": {"name": "X", "frames": [0]}}}
    b = {"clouds": {"n": {"name": "N", "frames": [1, 2, 3], "truncated": True}}}
    assert common_cloud_nodes(a, b) == [{"node_id": "n", "name": "N", "frames": [1, 2], "truncated": True}]
    assert common_cloud_nodes({}, b) == []


def test_capture_is_not_affected_by_later_mutation_of_the_payload(tmp_path):
    frame = {"i": 0}
    cap = CloudCapture(tmp_path, ["n"], lambda: frame["i"])
    pts = np.arange(12, dtype=np.float32).reshape(4, 3)   # already float32 / contiguous
    cap.record("n", {"points": pts})
    pts[:] = -1                                            # node reuses its buffer
    frame["i"] = 1
    cap.record("n", {"points": pts.copy()})
    cap.finalize({})
    np.testing.assert_array_equal(
        read_cloud(tmp_path, "n", 0), np.arange(12, dtype=np.float32).reshape(4, 3)
    )


def test_repeated_emissions_in_one_frame_are_stored_once(tmp_path):
    cap = CloudCapture(tmp_path, ["n"], lambda: 0)
    cap.record("n", {"points": np.zeros((100, 3), np.float32)})
    cap.record("n", {"points": np.ones((100, 3), np.float32)})
    cap.finalize({})
    assert (tmp_path / "clouds" / "n.bin").stat().st_size == 100 * 12
    assert read_cloud(tmp_path, "n", 0).min() == 1.0
