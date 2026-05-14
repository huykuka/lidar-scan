"""
Unit tests for ResultsStorageService.

TDD: these tests are written before the implementation.
Covers:
  - save → retrieve detail round-trip
  - delete_results_by_node removes DB records and directory
  - Rollback on simulated PCD write failure
  - Concurrent saves to same node (ThreadPoolExecutor)
"""

import asyncio
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_pcd(n_points: int = 10):
    """Return a minimal open3d-like PointCloud mock that passes the 50 MB guard."""
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pts = np.random.rand(n_points, 3).astype(np.float64)
    cols = np.random.rand(n_points, 3).astype(np.float64)
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.colors = o3d.utility.Vector3dVector(cols)
    return pcd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path, monkeypatch):
    """Create a ResultsStorageService backed by the main DB (temp) and temp results dir."""
    results_data_dir = tmp_path / "data" / "results"
    results_data_dir.mkdir(parents=True)

    db_file = tmp_path / "data" / "test_main.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.chdir(tmp_path)  # ensures relative `data/results/` resolves correctly

    from app.db.migrate import ensure_schema
    from app.db.session import init_engine

    engine = init_engine()
    ensure_schema(engine)

    from app.services.results_storage import ResultsStorageService

    return ResultsStorageService()


# ---------------------------------------------------------------------------
# Tests: save + retrieve round-trip
# ---------------------------------------------------------------------------


class TestSaveAndRetrieve:
    @pytest.mark.asyncio
    async def test_save_returns_result_id(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = await service.save_result(
            node_id="node_abc",
            pcds=[("empty", pcd)],
            metadata={"volume_m3": 1.5},
            status="success",
        )
        assert isinstance(result_id, str)
        assert len(result_id) == 36  # UUID4 format

    @pytest.mark.asyncio
    async def test_save_creates_pcd_file_on_disk(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = await service.save_result(
            node_id="node_abc",
            pcds=[("empty", pcd), ("loaded", pcd)],
            metadata={},
            status="success",
        )
        result_dir = tmp_path / "data" / "results" / "node_abc" / result_id
        assert result_dir.exists()
        assert (result_dir / "empty.pcd").exists()
        assert (result_dir / "loaded.pcd").exists()

    @pytest.mark.asyncio
    async def test_save_sanitizes_labels(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = await service.save_result(
            node_id="node_abc",
            pcds=[("my label/2024", pcd)],
            metadata={},
        )
        result_dir = tmp_path / "data" / "results" / "node_abc" / result_id
        # sanitized: spaces→_ slashes→_
        assert (result_dir / "my_label_2024.pcd").exists()

    @pytest.mark.asyncio
    async def test_get_result_detail_round_trip(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = await service.save_result(
            node_id="node_abc",
            pcds=[("empty", pcd), ("loaded", pcd)],
            metadata={"volume_m3": 2.5, "icp_valid": True},
            status="success",
        )
        detail = await service.get_result_detail("node_abc", result_id)
        assert detail is not None
        assert detail.result_id == result_id
        assert detail.node_id == "node_abc"
        assert detail.status == "success"
        assert detail.metadata["volume_m3"] == 2.5
        assert len(detail.pcd_files) == 2
        labels = [f.label for f in detail.pcd_files]
        assert "empty" in labels
        assert "loaded" in labels

    @pytest.mark.asyncio
    async def test_get_result_detail_returns_none_for_unknown(
        self, service, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        detail = await service.get_result_detail("no_node", "no_result_id")
        assert detail is None

    @pytest.mark.asyncio
    async def test_get_results_by_node_list(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        for i in range(3):
            await service.save_result(
                node_id="node_list",
                pcds=[("pcd", pcd)],
                metadata={"idx": i},
            )
        results = await service.get_results_by_node("node_list")
        assert len(results) == 3
        # Newest first
        assert results[0].timestamp >= results[1].timestamp

    @pytest.mark.asyncio
    async def test_get_results_by_node_empty_for_unknown(
        self, service, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        results = await service.get_results_by_node("ghost_node")
        assert results == []

    @pytest.mark.asyncio
    async def test_metadata_summary_scalar_only(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        await service.save_result(
            node_id="node_meta",
            pcds=[("p", pcd)],
            metadata={"scalar": 42, "nested": {"x": 1}, "arr": [1, 2, 3]},
        )
        results = await service.get_results_by_node("node_meta")
        assert len(results) == 1
        summary = results[0].metadata_summary
        assert "scalar" in summary
        assert "nested" not in summary  # non-scalar excluded
        assert "arr" not in summary  # non-scalar excluded

    @pytest.mark.asyncio
    async def test_get_node_index(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        await service.save_result("node_A", [("p", pcd)], {})
        await service.save_result("node_A", [("p", pcd)], {})
        await service.save_result("node_B", [("p", pcd)], {})
        index = await service.get_node_index()
        node_ids = {n.node_id for n in index}
        assert "node_A" in node_ids
        assert "node_B" in node_ids
        for entry in index:
            if entry.node_id == "node_A":
                assert entry.result_count == 2
            elif entry.node_id == "node_B":
                assert entry.result_count == 1


# ---------------------------------------------------------------------------
# Tests: delete_results_by_node
# ---------------------------------------------------------------------------


class TestDeleteResultsByNode:
    @pytest.mark.asyncio
    async def test_delete_results_by_node_removes_db_and_dir(
        self, service, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = await service.save_result(
            node_id="node_del",
            pcds=[("p", pcd)],
            metadata={},
        )
        node_dir = tmp_path / "data" / "results" / "node_del"
        assert node_dir.exists()

        count = await service.delete_results_by_node("node_del")
        assert count == 1
        assert not node_dir.exists()
        results = await service.get_results_by_node("node_del")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_results_by_node_returns_zero_for_unknown(
        self, service, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        count = await service.delete_results_by_node("ghost_node")
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_single_result(self, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        r1 = await service.save_result("node_del2", [("p", pcd)], {})
        r2 = await service.save_result("node_del2", [("p", pcd)], {})

        deleted = await service.delete_result("node_del2", r1)
        assert deleted is True

        # r1 dir gone, r2 dir still exists
        r1_dir = tmp_path / "data" / "results" / "node_del2" / r1
        r2_dir = tmp_path / "data" / "results" / "node_del2" / r2
        assert not r1_dir.exists()
        assert r2_dir.exists()

        remaining = await service.get_results_by_node("node_del2")
        assert len(remaining) == 1
        assert remaining[0].result_id == r2

    @pytest.mark.asyncio
    async def test_delete_single_result_returns_false_for_unknown(
        self, service, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        deleted = await service.delete_result("no_node", "no_id")
        assert deleted is False


# ---------------------------------------------------------------------------
# Tests: rollback on PCD write failure
# ---------------------------------------------------------------------------


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_on_pcd_write_failure(self, service, tmp_path, monkeypatch):
        """If writing any PCD file fails, directory should be cleaned up and DB unchanged."""
        monkeypatch.chdir(tmp_path)

        import open3d as o3d

        pcd = _make_mock_pcd(5)

        # Patch open3d.io.write_point_cloud to raise
        with patch("open3d.io.write_point_cloud", side_effect=IOError("disk full")):
            with pytest.raises(IOError, match="disk full"):
                await service.save_result(
                    node_id="node_fail",
                    pcds=[("empty", pcd)],
                    metadata={},
                )

        # DB should have no records
        results = await service.get_results_by_node("node_fail")
        assert results == []

        # Result sub-directory should be cleaned up (node dir may still exist; that's fine)
        results_base = tmp_path / "data" / "results"
        if results_base.exists():
            node_dir = results_base / "node_fail"
            # If the node dir exists, it should have no result sub-dirs
            if node_dir.exists():
                sub_dirs = [p for p in node_dir.iterdir() if p.is_dir()]
                assert sub_dirs == [], (
                    f"Expected no result sub-dirs but found: {sub_dirs}"
                )


# ---------------------------------------------------------------------------
# Tests: 50 MB PCD size limit
# ---------------------------------------------------------------------------


class TestSizeLimit:
    @pytest.mark.asyncio
    async def test_pcd_over_50mb_raises_value_error(
        self, service, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)

        # Override the limit to 1 byte for testing
        service._max_pcd_bytes = 1

        with pytest.raises(ValueError, match="exceeds"):
            await service.save_result(
                node_id="node_big",
                pcds=[("big", pcd)],
                metadata={},
            )


# ---------------------------------------------------------------------------
# Tests: concurrent saves to same node
# ---------------------------------------------------------------------------


class TestConcurrentSaves:
    @pytest.mark.asyncio
    async def test_concurrent_saves_no_data_corruption(
        self, service, tmp_path, monkeypatch
    ):
        """Multiple concurrent saves to same node should all succeed without corruption."""
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)

        tasks = [
            service.save_result(
                node_id="node_concurrent",
                pcds=[("p", pcd)],
                metadata={"idx": i},
            )
            for i in range(5)
        ]
        result_ids = await asyncio.gather(*tasks)
        # All must be unique UUIDs
        assert len(set(result_ids)) == 5

        results = await service.get_results_by_node("node_concurrent")
        assert len(results) == 5
