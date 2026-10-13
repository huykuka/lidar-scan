import asyncio
import io
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from app.modules.matching.node import MatchingNode
from app.modules.matching.store import (
    AssetError, AssetNotFound, ReferenceStore, parse_point_cloud_bytes,
)
from app.schemas.status import OperationalState


@pytest.fixture
def store(tmp_path):
    return ReferenceStore(tmp_path / "refs")


def _npy_bytes(arr):
    buf = io.BytesIO()
    np.save(buf, arr)
    return buf.getvalue()


# ── store ──────────────────────────────────────────────────────────────────

def test_store_roundtrip(store, reference):
    meta = store.create("pallet", "pallet.npy", reference.astype(np.float32), 123)
    assert meta["point_count"] == len(reference)
    assert store.list()[0]["id"] == meta["id"]
    assert store.load(meta["id"]).shape == reference.shape
    assert store.rename(meta["id"], "pallet v2")["name"] == "pallet v2"
    store.delete(meta["id"])
    assert store.list() == []
    with pytest.raises(AssetNotFound):
        store.load(meta["id"])


@pytest.mark.parametrize("bad_id", ["../etc/passwd", "", "abc", "g" * 32])
def test_store_rejects_path_traversal_ids(store, bad_id):
    with pytest.raises(AssetNotFound):
        store.get(bad_id)
    with pytest.raises(AssetNotFound):
        store.delete(bad_id)


def test_parse_rejects_bad_input():
    with pytest.raises(AssetError):
        parse_point_cloud_bytes(b"x", "a.txt")
    with pytest.raises(AssetError):
        parse_point_cloud_bytes(b"", "a.pcd")
    with pytest.raises(AssetError):
        parse_point_cloud_bytes(_npy_bytes(np.zeros((4, 2))), "a.npy")
    with pytest.raises(AssetError):
        parse_point_cloud_bytes(_npy_bytes(np.full((4, 3), np.nan)), "a.npy")


def test_parse_pcd_and_ply(tmp_path, reference):
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(reference[:500])
    for ext in (".pcd", ".ply"):
        path = tmp_path / f"c{ext}"
        o3d.io.write_point_cloud(str(path), pcd)
        pts = parse_point_cloud_bytes(path.read_bytes(), path.name)
        assert pts.shape == (500, 3)


# ── node ───────────────────────────────────────────────────────────────────

def _node(store, asset_id, **kw):
    manager = Mock()
    manager.forward_data = AsyncMock()
    node = MatchingNode(manager, "n1", "match", asset_id=asset_id, voxel_size=0.08, store=store, **kw)
    node.enable()
    return node, manager


async def _run(node, points):
    await node.on_input({"points": points, "timestamp": 1.0})
    await asyncio.sleep(0.05)  # let the forward_data task run


def test_node_forwards_matches(store, reference, make_scene):
    scene, _, centre = make_scene()
    asset = store.create("ref", "ref.npy", reference.astype(np.float32))
    node, manager = _node(store, asset["id"])

    asyncio.run(_run(node, scene))

    manager.forward_data.assert_awaited_once()
    payload = manager.forward_data.await_args.args[1]
    assert payload["match_count"] == 1
    assert np.linalg.norm(np.array(payload["matches"][0]["position"]) - centre) < 0.05
    assert len(payload["points"]) == len(scene)  # passthrough
    assert node.emit_status().application_state.value == 1
    shapes = node.collect_and_clear_shapes()
    assert len(shapes) == 1 and shapes[0].type == "cube"


def test_node_matched_points_mode_drops_empty_frames(store, reference, make_scene):
    scene, _, _ = make_scene()
    asset = store.create("ref", "ref.npy", reference.astype(np.float32))
    node, manager = _node(store, asset["id"], output_mode="matched_points")

    asyncio.run(_run(node, scene))
    assert len(manager.forward_data.await_args.args[1]["points"]) < len(scene) / 2

    manager.forward_data.reset_mock()
    rng = np.random.default_rng(0)
    floor = np.c_[rng.uniform(-10, 10, (20000, 2)), np.zeros(20000)].astype(np.float32)
    node.config.min_fitness = 0.95
    asyncio.run(_run(node, floor))
    manager.forward_data.assert_not_awaited()


def test_node_reports_error_for_missing_asset(store):
    node, manager = _node(store, "0" * 32)
    asyncio.run(_run(node, np.random.rand(100, 3).astype(np.float32)))
    status = node.emit_status()
    assert status.operational_state == OperationalState.ERROR
    assert "not found" in status.error_message
    manager.forward_data.assert_not_awaited()


def test_node_error_without_asset_selected(store):
    node, _ = _node(store, "")
    asyncio.run(_run(node, np.random.rand(100, 3).astype(np.float32)))
    assert node.emit_status().operational_state == OperationalState.ERROR


def test_node_reloads_replaced_asset_and_recovers_after_delete(store, reference, make_scene):
    scene, _, _ = make_scene()
    asset = store.create("ref", "ref.npy", reference.astype(np.float32))
    node, _ = _node(store, asset["id"])

    asyncio.run(_run(node, scene))
    first = node._matcher
    assert first is not None

    store.delete(asset["id"])
    asyncio.run(_run(node, scene))
    assert node.emit_status().operational_state == OperationalState.ERROR

    # same id re-created (e.g. replaced file) -> matcher rebuilt, error cleared
    d = store.root / asset["id"]
    d.mkdir(parents=True)
    np.save(d / "cloud.npy", reference.astype(np.float32))
    (d / "meta.json").write_text("{}")
    asyncio.run(_run(node, scene))
    assert node._matcher is not first
    assert node.emit_status().operational_state == OperationalState.RUNNING


def test_node_ignores_input_when_disabled(store, reference):
    node, manager = _node(store, "x")
    node.disable()
    asyncio.run(_run(node, np.random.rand(10, 3).astype(np.float32)))
    manager.forward_data.assert_not_awaited()


def test_registry_registers_node_type():
    import app.modules.matching.registry  # noqa: F401
    from app.services.nodes.node_factory import NodeFactory
    from app.services.nodes.schema import node_schema_registry

    definition = node_schema_registry.get("point_cloud_matching")
    assert definition is not None
    assert next(p for p in definition.properties if p.name == "asset_id").options_source == "point_cloud_assets"
    node = NodeFactory.create(
        {"id": "x", "name": "m", "type": "point_cloud_matching", "config": {"voxel_size": "bad", "max_instances": 3}},
        Mock(), [],
    )
    assert isinstance(node, MatchingNode) and node.config.max_instances == 3 and node.config.voxel_size == 0.05
