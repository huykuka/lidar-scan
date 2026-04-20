"""
TDD test suite for HelloWorldNode — application-level DAG node.


References:
  - technical.md § 10 (test architecture constraints)
  - api-spec.md § 1 (class API contract)
  - requirements.md § Testing Infrastructure
"""
import time

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from app.modules.application.hello_world.node import HelloWorldNode
from app.schemas.status import NodeStatusUpdate, OperationalState


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_manager() -> Mock:
    """A mock NodeManager with a coroutine-capable forward_data."""
    manager = Mock()
    manager.forward_data = AsyncMock()
    return manager


@pytest.fixture
def node(mock_manager: Mock) -> HelloWorldNode:
    """Default HelloWorldNode instance with standard config."""
    return HelloWorldNode(
        manager=mock_manager,
        node_id="hw-node-001",
        name="Test Hello World",
        config={"message": "Test message", "throttle_ms": 0},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.2 — Instantiation
# ─────────────────────────────────────────────────────────────────────────────


class TestHelloWorldInstantiation:
    """Node attributes must be set correctly from constructor arguments."""

    def test_id_stored_correctly(self, node: HelloWorldNode) -> None:
        assert node.id == "hw-node-001"

    def test_name_stored_correctly(self, node: HelloWorldNode) -> None:
        assert node.name == "Test Hello World"

    def test_manager_stored(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        assert node.manager is mock_manager

    def test_config_stored(self, node: HelloWorldNode) -> None:
        assert node.config == {"message": "Test message", "throttle_ms": 0}

    def test_message_extracted_from_config(self, node: HelloWorldNode) -> None:
        assert node.message == "Test message"

    def test_input_count_starts_at_zero(self, node: HelloWorldNode) -> None:
        assert node.input_count == 0

    def test_last_input_at_starts_none(self, node: HelloWorldNode) -> None:
        assert node.last_input_at is None

    def test_last_error_starts_none(self, node: HelloWorldNode) -> None:
        assert node.last_error is None

    def test_processing_time_ms_starts_zero(self, node: HelloWorldNode) -> None:
        assert node.processing_time_ms == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.3 — Config defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestHelloWorldConfigDefaults:
    """Missing config keys must fall back to documented defaults."""

    def test_message_defaults_when_config_empty(self, mock_manager: Mock) -> None:
        node = HelloWorldNode(
            manager=mock_manager,
            node_id="hw-default",
            name="Default Node",
            config={},
        )
        assert node.message == "Hello from DAG!"

    def test_message_defaults_when_key_missing(self, mock_manager: Mock) -> None:
        node = HelloWorldNode(
            manager=mock_manager,
            node_id="hw-default",
            name="Default Node",
            config={"throttle_ms": 100},
        )
        assert node.message == "Hello from DAG!"

    def test_custom_message_honoured(self, mock_manager: Mock) -> None:
        node = HelloWorldNode(
            manager=mock_manager,
            node_id="hw-custom",
            name="Custom Node",
            config={"message": "Custom greeting"},
        )
        assert node.message == "Custom greeting"

    def test_throttle_ms_accepted_without_error(self, mock_manager: Mock) -> None:
        """throttle_ms is an accepted constructor kwarg; should not raise."""
        node = HelloWorldNode(
            manager=mock_manager,
            node_id="hw-throttle",
            name="Throttled Node",
            config={},
            throttle_ms=50.0,
        )
        assert node is not None


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.4 — on_input: normal payload
# ─────────────────────────────────────────────────────────────────────────────


class TestOnInputForwarded:
    """on_input() must annotate the payload and call manager.forward_data."""

    @pytest.mark.asyncio
    async def test_forward_data_called(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        payload = {
            "points": np.zeros((100, 3), dtype=np.float32),
            "timestamp": 1.0,
            "node_id": "upstream-node",
        }
        await node.on_input(payload)
        # asyncio.create_task fires forward_data; we need to drain the event loop
        # The mock is an AsyncMock so calling the task works synchronously in tests
        mock_manager.forward_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_node_id_overwritten_to_self(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        await node.on_input({"points": np.zeros((10, 3)), "node_id": "upstream"})
        _, call_kwargs = mock_manager.forward_data.call_args
        # forward_data(self.id, new_payload) → positional args
        call_args = mock_manager.forward_data.call_args[0]
        assert call_args[0] == node.id
        forwarded_payload = call_args[1]
        assert forwarded_payload["node_id"] == node.id

    @pytest.mark.asyncio
    async def test_processed_by_set_to_self(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        await node.on_input({"points": np.zeros((10, 3)), "node_id": "upstream"})
        forwarded_payload = mock_manager.forward_data.call_args[0][1]
        assert forwarded_payload["processed_by"] == node.id

    @pytest.mark.asyncio
    async def test_app_message_annotated(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        await node.on_input({"points": np.zeros((10, 3)), "node_id": "upstream"})
        forwarded_payload = mock_manager.forward_data.call_args[0][1]
        assert forwarded_payload["app_message"] == node.message

    @pytest.mark.asyncio
    async def test_app_point_count_correct(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        points = np.zeros((100, 3), dtype=np.float32)
        await node.on_input({"points": points, "node_id": "upstream"})
        forwarded_payload = mock_manager.forward_data.call_args[0][1]
        assert forwarded_payload["app_point_count"] == 100

    @pytest.mark.asyncio
    async def test_input_count_incremented(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        assert node.input_count == 0
        await node.on_input({"points": np.zeros((5, 3)), "node_id": "upstream"})
        assert node.input_count == 1
        await node.on_input({"points": np.zeros((5, 3)), "node_id": "upstream"})
        assert node.input_count == 2

    @pytest.mark.asyncio
    async def test_last_input_at_updated(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        before = time.time()
        await node.on_input({"points": np.zeros((5, 3)), "node_id": "upstream"})
        after = time.time()
        assert node.last_input_at is not None
        assert before <= node.last_input_at <= after

    @pytest.mark.asyncio
    async def test_original_payload_not_mutated(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        """Shallow copy must be used; original dict must not be modified."""
        original = {"points": np.zeros((5, 3)), "node_id": "upstream", "timestamp": 42.0}
        original_id = original["node_id"]
        await node.on_input(original)
        assert original["node_id"] == original_id  # must remain "upstream"

    @pytest.mark.asyncio
    async def test_extra_payload_keys_preserved(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        """Existing payload keys must be forwarded unchanged (shallow copy)."""
        await node.on_input({
            "points": np.zeros((5, 3)),
            "node_id": "upstream",
            "lidar_id": "lidar-abc",
            "processing_chain": ["step1", "step2"],
        })
        forwarded = mock_manager.forward_data.call_args[0][1]
        assert forwarded["lidar_id"] == "lidar-abc"
        assert forwarded["processing_chain"] == ["step1", "step2"]


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.5 — on_input: None / empty points
# ─────────────────────────────────────────────────────────────────────────────


class TestOnInputNonePoints:
    """Graceful handling when points is None or empty."""

    @pytest.mark.asyncio
    async def test_none_points_still_forwarded(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        """Payload with points=None must still be forwarded (point_count=0)."""
        await node.on_input({"points": None, "timestamp": 1.0, "node_id": "up"})
        mock_manager.forward_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_points_app_count_zero(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        await node.on_input({"points": None, "timestamp": 1.0, "node_id": "up"})
        forwarded = mock_manager.forward_data.call_args[0][1]
        assert forwarded["app_point_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_array_still_forwarded(self, node: HelloWorldNode, mock_manager: Mock) -> None:
        await node.on_input({"points": np.zeros((0, 3)), "node_id": "up"})
        mock_manager.forward_data.assert_called_once()
        forwarded = mock_manager.forward_data.call_args[0][1]
        assert forwarded["app_point_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.6 — emit_status: idle
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitStatusIdle:
    """Node never received input → RUNNING, processing=False, gray."""

    def test_operational_state_running(self, node: HelloWorldNode) -> None:
        status = node.emit_status()
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING

    def test_application_state_label_processing(self, node: HelloWorldNode) -> None:
        status = node.emit_status()
        assert status.application_state is not None
        assert status.application_state.label == "processing"

    def test_application_state_value_false_when_idle(self, node: HelloWorldNode) -> None:
        node.last_input_at = None
        node.last_error = None
        status = node.emit_status()
        assert status.application_state.value is False

    def test_application_state_color_gray_when_idle(self, node: HelloWorldNode) -> None:
        node.last_input_at = None
        node.last_error = None
        status = node.emit_status()
        assert status.application_state.color == "gray"

    def test_no_error_message_when_idle(self, node: HelloWorldNode) -> None:
        status = node.emit_status()
        assert status.error_message is None

    def test_node_id_matches(self, node: HelloWorldNode) -> None:
        status = node.emit_status()
        assert status.node_id == "hw-node-001"


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.7 — emit_status: active (recent input)
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitStatusActive:
    """Recent input (<5 s ago) → RUNNING, processing=True, blue."""

    def test_operational_state_running(self, node: HelloWorldNode) -> None:
        node.last_input_at = time.time() - 0.5
        node.last_error = None
        status = node.emit_status()
        assert status.operational_state == OperationalState.RUNNING

    def test_application_state_value_true(self, node: HelloWorldNode) -> None:
        node.last_input_at = time.time() - 0.5
        node.last_error = None
        status = node.emit_status()
        assert status.application_state.value is True

    def test_application_state_color_blue(self, node: HelloWorldNode) -> None:
        node.last_input_at = time.time() - 0.5
        node.last_error = None
        status = node.emit_status()
        assert status.application_state.color == "blue"

    def test_stale_input_over_5s_shows_gray(self, node: HelloWorldNode) -> None:
        node.last_input_at = time.time() - 10.0
        node.last_error = None
        status = node.emit_status()
        assert status.application_state.value is False
        assert status.application_state.color == "gray"


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.8 — emit_status: error
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitStatusError:
    """last_error set → ERROR state with error_message propagated."""

    def test_operational_state_error(self, node: HelloWorldNode) -> None:
        node.last_error = "something broke"
        status = node.emit_status()
        assert status.operational_state == OperationalState.ERROR

    def test_error_message_propagated(self, node: HelloWorldNode) -> None:
        node.last_error = "something broke"
        status = node.emit_status()
        assert status.error_message == "something broke"

    def test_application_state_value_false_on_error(self, node: HelloWorldNode) -> None:
        node.last_error = "boom"
        status = node.emit_status()
        assert status.application_state.value is False

    def test_application_state_color_gray_on_error(self, node: HelloWorldNode) -> None:
        node.last_error = "boom"
        status = node.emit_status()
        assert status.application_state.color == "gray"

    def test_error_takes_priority_over_recent_activity(self, node: HelloWorldNode) -> None:
        """Error state must override even if last_input_at is very recent."""
        node.last_error = "critical failure"
        node.last_input_at = time.time()  # recent, but error wins
        status = node.emit_status()
        assert status.operational_state == OperationalState.ERROR


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.9 — Lifecycle: start / stop
# ─────────────────────────────────────────────────────────────────────────────


class TestLifecycle:
    """start() and stop() must execute without raising exceptions."""

    def test_start_does_not_raise(self, node: HelloWorldNode) -> None:
        node.start()

    def test_start_with_data_queue_does_not_raise(self, node: HelloWorldNode) -> None:
        node.start(data_queue=MagicMock(), runtime_status={})

    def test_stop_does_not_raise(self, node: HelloWorldNode) -> None:
        node.stop()

    def test_start_then_stop_does_not_raise(self, node: HelloWorldNode) -> None:
        node.start()
        node.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.10 — Registry: NodeFactory registration
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryNodeFactoryRegistration:
    """Importing registry must register 'hello_world' in NodeFactory._registry.

    Both the submodule registry (hello_world/registry.py) and the parent
    aggregator (application/registry.py) must trigger correct registration.
    """

    def test_hello_world_in_node_factory_via_submodule(self) -> None:
        """Directly importing the submodule registry must register the factory."""
        import app.modules.application.hello_world.registry  # noqa: F401
        from app.services.nodes.node_factory import NodeFactory

        assert "hello_world" in NodeFactory._registry

    def test_hello_world_in_node_factory_via_aggregator(self) -> None:
        """Importing the parent aggregator must also register the factory."""
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.node_factory import NodeFactory

        assert "hello_world" in NodeFactory._registry

    def test_factory_entry_is_callable(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.node_factory import NodeFactory

        builder = NodeFactory._registry.get("hello_world")
        assert callable(builder)


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.11 — Registry: schema registration
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistrySchemaRegistration:
    """Importing registry must register NodeDefinition in node_schema_registry.

    Verified via both the submodule path (hello_world/registry.py) and the
    parent aggregator path (application/registry.py).
    """

    def test_schema_registered(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert defn is not None

    def test_schema_registered_via_submodule(self) -> None:
        """Direct submodule import must also expose the schema."""
        import app.modules.application.hello_world.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert defn is not None

    def test_websocket_enabled(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert defn.websocket_enabled is True

    def test_category_is_application(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert defn.category == "application"

    def test_display_name(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert defn.display_name == "Hello World App"

    def test_has_input_and_output_ports(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert len(defn.inputs) >= 1
        assert len(defn.outputs) >= 1

    def test_has_message_property(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        prop_names = {p.name for p in defn.properties}
        assert "message" in prop_names

    def test_has_throttle_ms_property(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        prop_names = {p.name for p in defn.properties}
        assert "throttle_ms" in prop_names

    def test_icon_set(self) -> None:
        import app.modules.application.registry  # noqa: F401
        from app.services.nodes.schema import node_schema_registry

        defn = node_schema_registry.get("hello_world")
        assert defn.icon == "celebration"


# ─────────────────────────────────────────────────────────────────────────────
# Task 6.12 — Factory: build_hello_world creates correct instance
# ─────────────────────────────────────────────────────────────────────────────


class TestFactoryCreatesCorrectInstance:
    """build_hello_world() must return a configured HelloWorldNode.

    The factory now lives in hello_world/registry.py (submodule).
    The parent application/registry.py is a pure aggregator and does NOT
    re-export build_hello_world — tests import from the submodule directly.
    """

    def test_returns_hello_world_node_instance(self) -> None:
        from app.modules.application.hello_world.registry import build_hello_world

        node_data = {
            "id": "test-hw-001",
            "type": "hello_world",
            "name": "Test Node",
            "config": {"message": "hi", "throttle_ms": 0},
        }
        ctx = MagicMock()
        hw_node = build_hello_world(node_data, ctx, [])
        assert isinstance(hw_node, HelloWorldNode)

    def test_node_id_assigned_correctly(self) -> None:
        from app.modules.application.hello_world.registry import build_hello_world

        node_data = {
            "id": "test-hw-002",
            "type": "hello_world",
            "name": "Test Node 2",
            "config": {},
        }
        ctx = MagicMock()
        hw_node = build_hello_world(node_data, ctx, [])
        assert hw_node.id == "test-hw-002"

    def test_message_from_config(self) -> None:
        from app.modules.application.hello_world.registry import build_hello_world

        node_data = {
            "id": "test-hw-003",
            "type": "hello_world",
            "name": "Config Test",
            "config": {"message": "custom message", "throttle_ms": 0},
        }
        ctx = MagicMock()
        hw_node = build_hello_world(node_data, ctx, [])
        assert hw_node.message == "custom message"

    def test_name_fallback_when_missing(self) -> None:
        from app.modules.application.hello_world.registry import build_hello_world

        node_data = {
            "id": "test-hw-004",
            "type": "hello_world",
            "name": None,
            "config": {},
        }
        ctx = MagicMock()
        hw_node = build_hello_world(node_data, ctx, [])
        assert hw_node.name == "Hello World"

    def test_throttle_ms_float_conversion(self) -> None:
        """throttle_ms must survive string/invalid input via float() conversion."""
        from app.modules.application.hello_world.registry import build_hello_world

        node_data = {
            "id": "test-hw-005",
            "type": "hello_world",
            "name": "Throttle Test",
            "config": {"throttle_ms": "150"},  # string input
        }
        ctx = MagicMock()
        hw_node = build_hello_world(node_data, ctx, [])
        assert isinstance(hw_node, HelloWorldNode)

    def test_invalid_throttle_ms_defaults_to_zero(self) -> None:
        """Invalid throttle_ms (non-numeric) must default to 0.0 without error."""
        from app.modules.application.hello_world.registry import build_hello_world

        node_data = {
            "id": "test-hw-006",
            "type": "hello_world",
            "name": "Invalid Throttle",
            "config": {"throttle_ms": "bad_value"},
        }
        ctx = MagicMock()
        hw_node = build_hello_world(node_data, ctx, [])
        assert isinstance(hw_node, HelloWorldNode)

    def test_node_factory_create_with_hello_world_type(self) -> None:
        """NodeFactory.create() must correctly dispatch to HelloWorldNode."""
        import app.modules.application.registry  # noqa: F401  trigger side-effects
        from app.services.nodes.node_factory import NodeFactory

        node_data = {
            "id": "test-hw-007",
            "type": "hello_world",
            "name": "Factory Test",
            "config": {"message": "factory hello", "throttle_ms": 0},
        }
        ctx = MagicMock()
        hw_node = NodeFactory.create(node_data, ctx, [])
        assert isinstance(hw_node, HelloWorldNode)
        assert hw_node.id == "test-hw-007"
        assert hw_node.message == "factory hello"


# ─────────────────────────────────────────────────────────────────────────────
# Additional integration: ApplicationNode base class hierarchy
# ─────────────────────────────────────────────────────────────────────────────


class TestApplicationNodeHierarchy:
    """HelloWorldNode must satisfy the full ModuleNode/ApplicationNode contract."""

    def test_is_subclass_of_application_node(self) -> None:
        from app.services.nodes.base_module import ModuleNode

        assert issubclass(HelloWorldNode, ModuleNode)

    def test_is_subclass_of_module_node(self) -> None:
        from app.services.nodes.base_module import ModuleNode

        assert issubclass(HelloWorldNode, ModuleNode)

    def test_has_on_input_coroutine(self, node: HelloWorldNode) -> None:
        import asyncio

        assert asyncio.iscoroutinefunction(node.on_input)

    def test_has_emit_status(self, node: HelloWorldNode) -> None:
        assert callable(node.emit_status)

    def test_has_start(self, node: HelloWorldNode) -> None:
        assert callable(node.start)

    def test_has_stop(self, node: HelloWorldNode) -> None:
        assert callable(node.stop)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: aggregator registry structure
# Verifies that application/registry.py acts as a pure aggregator (like
# flow_control/registry.py) and that all registration is owned by the
# hello_world submodule.
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryAggregatorStructure:
    """
    application/registry.py must be a pure aggregator — no direct registration
    logic, only imports from submodule registries.  The submodule
    hello_world/registry.py owns schema + factory.
    """

    def test_application_registry_exposes_hello_world_registry(self) -> None:
        """Parent aggregator must export hello_world_registry attribute."""
        import app.modules.application.registry as app_registry

        assert hasattr(app_registry, "hello_world_registry"), (
            "application/registry.py must expose 'hello_world_registry' "
            "(imported from .hello_world import registry)"
        )

    def test_application_registry_all_contains_hello_world(self) -> None:
        """__all__ in the aggregator must list hello_world_registry."""
        import app.modules.application.registry as app_registry

        assert "hello_world_registry" in app_registry.__all__

    def test_hello_world_registry_is_the_submodule(self) -> None:
        """hello_world_registry re-exported by aggregator must be the submodule."""
        import app.modules.application.registry as app_registry
        import app.modules.application.hello_world.registry as hw_registry

        assert app_registry.hello_world_registry is hw_registry

    def test_application_registry_has_no_build_hello_world(self) -> None:
        """build_hello_world must NOT live in application/registry.py anymore."""
        import app.modules.application.registry as app_registry

        assert not hasattr(app_registry, "build_hello_world"), (
            "build_hello_world must be defined in hello_world/registry.py, "
            "not in the parent aggregator"
        )

    def test_hello_world_submodule_registry_defines_build_hello_world(self) -> None:
        """The factory must live directly in hello_world/registry.py."""
        from app.modules.application.hello_world.registry import build_hello_world

        assert callable(build_hello_world)

    def test_discover_modules_loads_hello_world_via_aggregator(self) -> None:
        """discover_modules() → application/registry.py → hello_world/registry.py."""
        # Simulates the startup path: discover_modules imports each top-level registry.
        from app.modules import discover_modules
        from app.services.nodes.node_factory import NodeFactory
        from app.services.nodes.schema import node_schema_registry

        discover_modules()

        assert "hello_world" in NodeFactory._registry
        defn = node_schema_registry.get("hello_world")
        assert defn is not None
        assert defn.category == "application"
