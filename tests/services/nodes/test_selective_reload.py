"""
TDD Tests for SelectiveReloadManager.

Phase 7.3 — written BEFORE implementation per strict TDD.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_node_instance(node_id: str = "abc12345", ws_topic: str = "sensor_abc12345") -> Mock:
    """Create a mock node instance with stop, enable, start, and _ws_topic."""
    instance = Mock()
    instance._ws_topic = ws_topic
    instance.stop = Mock()
    instance.enable = AsyncMock()
    instance.start = Mock()
    instance.on_input = AsyncMock()
    return instance


def _make_node_data(node_id: str = "abc12345") -> dict:
    return {
        "id": node_id,
        "type": "sensor",
        "category": "sensor",
        "enabled": True,
        "visible": True,
        "config": {"hostname": "192.168.1.10", "port": 2115},
        "pose": None,
        "x": 100.0,
        "y": 200.0,
        "name": "Test Sensor",
    }


def _make_manager_ref(
    node_id: str = "abc12345",
    old_instance=None,
    downstream_ids: list[str] | None = None,
) -> Mock:
    """Create a fake NodeManager with all required attributes."""
    if old_instance is None:
        old_instance = _make_node_instance(node_id)

    downstream_ids = downstream_ids or []

    manager = Mock()
    manager.nodes = {node_id: old_instance}
    manager.downstream_map = {
        node_id: [
            {"target_id": did, "source_port": "out", "target_port": "in"}
            for did in downstream_ids
        ]
    }
    manager.is_running = True
    manager._reload_lock = asyncio.Lock()
    manager._input_gates = {}
    manager._rollback_slot = {}
    manager._active_reload_node_id = None
    manager.data_queue = Mock()
    manager.node_runtime_status = {}

    # Sub-managers
    manager._lifecycle_manager = Mock()
    manager._lifecycle_manager._stop_node = Mock()
    manager._config_loader = Mock()
    manager._config_loader._initialize_node_throttling = Mock()
    manager._config_hash_store = Mock()
    manager._config_hash_store.update = Mock()

    return manager


# ---------------------------------------------------------------------------
# SelectiveReloadManager tests
# ---------------------------------------------------------------------------

class TestSelectiveReloadManager:
    """Unit tests for SelectiveReloadManager.reload_single_node()."""

    @pytest.mark.asyncio
    async def test_selective_reload_replaces_node_instance(self):
        """After reload, manager.nodes[node_id] must be a NEW instance, not the old one."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            result = await srm.reload_single_node(node_id)

        assert manager_ref.nodes[node_id] is new_instance
        assert manager_ref.nodes[node_id] is not old_instance
        assert result.status == "reloaded"

    @pytest.mark.asyncio
    async def test_selective_reload_preserves_ws_topic(self):
        """New instance must inherit the same _ws_topic as the old instance."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        original_topic = "sensor_abc12345"
        old_instance = _make_node_instance(node_id, ws_topic=original_topic)
        new_instance = _make_node_instance(node_id, ws_topic=None)  # starts with no topic
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            await srm.reload_single_node(node_id)

        assert new_instance._ws_topic == original_topic

    @pytest.mark.asyncio
    async def test_selective_reload_does_not_call_unregister_topic(self):
        """Selective reload must NOT call websocket_manager.unregister_topic (topic preservation).

        The selective_reload module intentionally does NOT import websocket_manager — it
        never unregisters topics.  We verify this by patching the actual manager module and
        confirming unregister_topic is never invoked during a successful reload.
        """
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"), \
             patch("app.services.websocket.manager.manager") as mock_ws:

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance
            mock_ws.unregister_topic = AsyncMock()

            srm = SelectiveReloadManager(manager_ref)
            await srm.reload_single_node(node_id)

        mock_ws.unregister_topic.assert_not_called()

    @pytest.mark.asyncio
    async def test_selective_reload_pauses_downstream_before_stop(self):
        """Downstream gates must be paused BEFORE the old node is stopped."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager
        from app.services.nodes.input_gate import NodeInputGate

        node_id = "abc12345"
        downstream_id = "downstream01"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)

        downstream_node = _make_node_instance(downstream_id)
        manager_ref = _make_manager_ref(node_id, old_instance, downstream_ids=[downstream_id])
        manager_ref.nodes[downstream_id] = downstream_node
        node_data = _make_node_data(node_id)

        pause_order = []

        original_stop = manager_ref._lifecycle_manager._stop_node

        def track_stop(inst):
            pause_order.append("stop")

        manager_ref._lifecycle_manager._stop_node = track_stop

        created_gates = []

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"), \
             patch("app.services.nodes.managers.selective_reload.NodeInputGate") as MockGate:

            mock_gate_instance = AsyncMock()
            mock_gate_instance.is_open = Mock(return_value=False)
            mock_gate_instance.resume_and_drain = AsyncMock()

            async def gate_pause_track():
                pause_order.append("gate_paused")

            mock_gate_instance.pause = gate_pause_track
            MockGate.return_value = mock_gate_instance

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            await srm.reload_single_node(node_id)

        # gate must have been paused BEFORE stop
        pause_idx = pause_order.index("gate_paused")
        stop_idx = pause_order.index("stop")
        assert pause_idx < stop_idx, (
            f"Expected gate_paused ({pause_idx}) before stop ({stop_idx}). "
            f"Order was: {pause_order}"
        )

    @pytest.mark.asyncio
    async def test_selective_reload_resumes_downstream_after_start(self):
        """Downstream gates must be resumed AFTER the new node is started."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        downstream_id = "downstream01"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)

        downstream_node = _make_node_instance(downstream_id)
        manager_ref = _make_manager_ref(node_id, old_instance, downstream_ids=[downstream_id])
        manager_ref.nodes[downstream_id] = downstream_node
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"), \
             patch("app.services.nodes.managers.selective_reload.NodeInputGate") as MockGate:

            mock_gate_instance = AsyncMock()
            mock_gate_instance.is_open = Mock(return_value=False)
            mock_gate_instance.pause = AsyncMock()
            mock_gate_instance.resume_and_drain = AsyncMock()
            MockGate.return_value = mock_gate_instance

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            await srm.reload_single_node(node_id)

        mock_gate_instance.resume_and_drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_selective_reload_rollback_on_factory_failure(self):
        """When NodeFactory.create() raises, the OLD instance must be restored."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        old_instance = _make_node_instance(node_id)
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.side_effect = RuntimeError("NodeFactory failed: port in use")

            srm = SelectiveReloadManager(manager_ref)
            result = await srm.reload_single_node(node_id)

        # Old instance must be restored
        assert manager_ref.nodes.get(node_id) is old_instance
        assert result.status == "error"
        assert result.rolled_back is True

    @pytest.mark.asyncio
    async def test_selective_reload_rollback_on_start_failure(self):
        """When new_instance.start() raises, the OLD instance must be restored."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)
        new_instance.start = Mock(side_effect=OSError("Address already in use"))

        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            result = await srm.reload_single_node(node_id)

        assert manager_ref.nodes.get(node_id) is old_instance
        assert result.status == "error"
        assert result.rolled_back is True

    @pytest.mark.asyncio
    async def test_selective_reload_updates_hash_store_on_success(self):
        """On success, ConfigHashStore.update() must be called with node_id and new hash."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        new_hash = "newhash" + "0" * 57  # 64 chars
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value=new_hash):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            await srm.reload_single_node(node_id)

        manager_ref._config_hash_store.update.assert_called_once_with(node_id, new_hash)

    @pytest.mark.asyncio
    async def test_selective_reload_returns_duration_ms(self):
        """result.duration_ms must be a non-negative float."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="hash"):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            result = await srm.reload_single_node(node_id)

        assert isinstance(result.duration_ms, float)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_selective_reload_404_on_missing_node(self):
        """reload_single_node() must raise ValueError when node_id not in manager.nodes."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        manager_ref = _make_manager_ref("abc12345")
        # Remove the node so it's missing
        manager_ref.nodes.clear()

        srm = SelectiveReloadManager(manager_ref)
        with pytest.raises(ValueError, match="not found"):
            await srm.reload_single_node("abc12345")

    @pytest.mark.asyncio
    async def test_selective_reload_clears_rollback_slot_on_success(self):
        """On successful reload, _rollback_slot must NOT retain the old instance."""
        from app.services.nodes.managers.selective_reload import SelectiveReloadManager

        node_id = "abc12345"
        old_instance = _make_node_instance(node_id)
        new_instance = _make_node_instance(node_id)
        manager_ref = _make_manager_ref(node_id, old_instance)
        node_data = _make_node_data(node_id)

        with patch("app.services.nodes.managers.selective_reload.NodeRepository") as MockRepo, \
             patch("app.services.nodes.managers.selective_reload.NodeFactory") as MockFactory, \
             patch("app.services.nodes.managers.selective_reload.compute_node_config_hash", return_value="newhash"):

            MockRepo.return_value.get_by_id.return_value = node_data
            MockFactory.create.return_value = new_instance

            srm = SelectiveReloadManager(manager_ref)
            await srm.reload_single_node(node_id)

        assert node_id not in manager_ref._rollback_slot
