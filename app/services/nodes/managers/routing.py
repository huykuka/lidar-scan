"""
Data routing and forwarding logic.

This module handles routing data through the DAG, including WebSocket broadcasting,
recording interception, and forwarding to downstream nodes with throttling.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.services.websocket.manager import manager
from app.services.shared.topics import slugify_topic_prefix

logger = get_logger(__name__)

# Maximum number of shapes broadcast per frame (performance constraint)
MAX_SHAPES_PER_FRAME = 500


class DataRouter:
    """Handles data routing through the DAG."""

    def __init__(self, manager_ref):
        """
        Initialize the data router.

        Args:
            manager_ref: Reference to the NodeManager instance
        """
        from app.services.nodes.shape_tracker import ShapeTracker

        self.manager = manager_ref
        self._shape_tracker = ShapeTracker()

    async def handle_incoming_data(self, payload: Dict[str, Any]):
        """
        Route incoming data to the appropriate node handler, then publish shapes.

        After the source node (and all downstream nodes in the DAG) have finished
        processing the current frame, ``publish_shapes()`` is called to collect any
        shapes emitted by ShapeCollectorMixin nodes and broadcast them on the
        'shapes' WebSocket topic.

        Args:
            payload: Data payload from queue
        """
        node_id = payload.get("lidar_id") or payload.get("node_id")
        if not node_id or node_id not in self.manager.nodes:
            logger.warning(f"Received data for unknown node: {node_id}")
            return

        node_instance = self.manager.nodes[node_id]

        if hasattr(node_instance, "handle_data"):
            # Legacy handle_data method (LidarSensor specific)
            await node_instance.handle_data(payload, self.manager.node_runtime_status)
        elif hasattr(node_instance, "on_input"):
            # Standard on_input method (ModuleNode interface)
            await node_instance.on_input(payload)

        # After all forward_data calls for this frame have settled (downstream tasks
        # are gathered inside forward_data → _forward_to_downstream_nodes), collect
        # and broadcast any shapes emitted by ShapeCollectorMixin nodes.
        await self.publish_shapes()

    async def forward_data(
        self, source_id: str, payload: Any, active_port: Optional[str] = None
    ):
        """
        Forward data to all connected downstream nodes and handle broadcasting.

        This is the central routing method that:
        1. Broadcasts to WebSocket clients if subscribed
        2. Records data if recording is active
        3. Forwards to downstream nodes in the DAG (with throttling)

        Args:
            source_id: Source node ID
            payload: Data payload to forward
            active_port: If set, only forward edges whose source_port matches this value.
                         Used by port-aware nodes like IfConditionNode to restrict fan-out
                         to a single output port.
        """
        source_node = self.manager.nodes.get(source_id)
        if not source_node:
            logger.warning(f"forward_data called for unknown node: {source_id}")
            return

        topic = self._get_node_topic(source_id, source_node)

        # All three actions are independent — run in parallel
        await asyncio.gather(
            self._broadcast_to_websocket(source_id, topic, payload),
            self._record_node_data(source_id, payload),
            self._forward_to_downstream_nodes(
                source_id, payload, active_port=active_port
            ),
        )

    def _get_node_topic(self, source_id: str, source_node: Any) -> Optional[str]:
        """
        Generate topic name for a node: {slugified_node_name}_{node_id[:8]}

        Returns None if the node is invisible (has _ws_topic = None).

        Args:
            source_id: Node ID
            source_node: Node instance

        Returns:
            Topic name string or None if node is invisible
        """
        # Prefer node_instance._ws_topic if the attribute exists (may be None)
        if hasattr(source_node, "_ws_topic"):
            return source_node._ws_topic

        # Keep legacy fallback (re-derive from name) only for nodes without _ws_topic attribute at all
        node_name = getattr(source_node, "name", source_id)
        safe_name = slugify_topic_prefix(node_name)
        return f"{safe_name}_{source_id[:8]}"

    async def _broadcast_to_websocket(
        self, source_id: str, topic: Optional[str], payload: Dict[str, Any]
    ):
        """
        Broadcast point cloud data to WebSocket subscribers.

        Args:
            source_id: Source node ID
            topic: WebSocket topic name (None for invisible nodes)
            payload: Data payload
        """
        # Early return guard: if topic is None, return
        if topic is None:
            return

        if "points" not in payload or not manager.has_subscribers(topic):
            return

        try:
            from app.services.shared.binary import pack_points_binary

            timestamp = payload.get("timestamp") or time.time()
            binary = await asyncio.to_thread(
                pack_points_binary, payload["points"], timestamp
            )
            await manager.broadcast(topic, binary)
            logger.debug(
                f"Broadcasted {len(payload['points'])} points from {source_id} on topic '{topic}'"
            )
        except Exception as e:
            logger.error(
                f"Error broadcasting from node '{source_id}': {e}", exc_info=True
            )

    async def _record_node_data(self, source_id: str, payload: Dict[str, Any]):
        """
        Record node output data if recording is active.

        Bypasses WebSocket's XYZ-only format to capture complete N-dimensional arrays.

        Args:
            source_id: Source node ID
            payload: Data payload
        """
        if "points" not in payload:
            return

        from app.services.shared.recorder import get_recorder

        recorder = get_recorder()

        if not recorder.is_recording(source_id):
            return

        try:
            timestamp = payload.get("timestamp") or time.time()
            await recorder.record_node_payload(source_id, payload["points"], timestamp)
        except Exception as e:
            logger.error(
                f"Error intercepting recording payload for node '{source_id}': {e}",
                exc_info=True,
            )

    async def _forward_to_downstream_nodes(
        self, source_id: str, payload: Dict[str, Any], active_port: Optional[str] = None
    ):
        """
        Forward data to all downstream nodes in the DAG, applying throttling.

        Supports both legacy format (list of target_id strings) and
        port-aware format (list of edge dictionaries with target_id and port info).

        When active_port is set, only edges whose source_port matches active_port
        are forwarded.  String-format (legacy, portless) edges are always forwarded
        when active_port is None, and skipped when active_port is set (they carry no
        port information so they cannot match).

        Input-gate awareness: if a NodeInputGate exists for a target in
        ``manager._input_gates`` and that gate is paused (closed), the payload is
        buffered via ``gate.buffer_nowait()`` instead of calling ``on_input``.
        This is an O(1) dict lookup — no overhead when no gates are active.

        Args:
            source_id: Source node ID
            payload: Data payload
            active_port: If set, restrict forwarding to edges with matching source_port.
        """
        targets = self.manager.downstream_map.get(source_id, [])

        for target in targets:
            # All edges are port-aware dicts: {"target_id": ..., "source_port": ..., "target_port": ...}
            target_id = target.get("target_id")
            # Port filtering: skip if active_port is set and edge port doesn't match
            if active_port is not None and target.get("source_port") != active_port:
                continue

            if not target_id:
                continue

            if self._should_skip_due_to_throttling(source_id, target_id):
                continue

            # ── Input-gate check (O(1) dict lookup) ──────────────────────
            # Gate lifecycle: created at pause, deleted after drain in SelectiveReloadManager.
            # When gate is paused, buffer the payload rather than forwarding — the gate will
            # drain the buffer and call on_input after the new node instance is started.
            gate = self.manager._input_gates.get(target_id)
            if gate is not None and not gate.is_open():
                gate.buffer_nowait(payload)
                continue

            await self._send_to_target_node(source_id, target_id, payload)

    def _should_skip_due_to_throttling(self, source_id: str, target_id: str) -> bool:
        """
        Check if data should be throttled for the target node.

        Args:
            source_id: Source node ID
            target_id: Target node ID

        Returns:
            True if should skip, False otherwise
        """
        # Access throttle manager directly from parent
        if not self.manager._throttle_manager.should_process(target_id):
            logger.debug(f"Throttled forwarding from {source_id} to {target_id}")
            return True
        return False

    async def _send_to_target_node(
        self, source_id: str, target_id: str, payload: Dict[str, Any]
    ):
        """
        Send data to a specific target node.

        Args:
            source_id: Source node ID (for error logging)
            target_id: Target node ID
            payload: Data payload
        """
        target_node = self.manager.nodes.get(target_id)

        if not target_node or not hasattr(target_node, "on_input"):
            return

        try:
            await target_node.on_input({**payload})
        except Exception as e:
            logger.error(f"Error forwarding data from {source_id} to {target_id}: {e}")

    async def publish_shapes(self) -> None:
        """
        Collect shapes from all ShapeCollectorMixin nodes and broadcast to 'shapes' topic.

        Called after all forward_data calls per frame settle. Assigns stable IDs and
        node_name to each shape, caps at MAX_SHAPES_PER_FRAME, and broadcasts a
        ShapeFrame JSON payload to the 'shapes' WebSocket topic.

        Threading note: collect_and_clear_shapes() is called from the asyncio event
        loop (after asyncio.to_thread returns), so no locking is needed.
        """
        from app.services.nodes.shape_collector import ShapeCollectorMixin
        from app.services.nodes.shapes import ShapeFrame

        all_shapes: List[dict] = []

        for node in self.manager.nodes.values():
            if not isinstance(node, ShapeCollectorMixin):
                continue
            node_id: str = getattr(node, "id", "")
            node_name: str = getattr(node, "name", node_id)
            for shape in node.collect_and_clear_shapes():
                shape.node_name = node_name
                raw = shape.model_dump()
                # id will be assigned by the shape tracker below
                raw["id"] = ""
                all_shapes.append(raw)

        # Assign stable IDs via spatial IoU matching
        all_shapes = self._shape_tracker.stabilize(all_shapes)

        # Cap at 500 shapes per frame (performance constraint)
        if len(all_shapes) > MAX_SHAPES_PER_FRAME:
            logger.warning(
                f"Shape count {len(all_shapes)} exceeds cap of {MAX_SHAPES_PER_FRAME}; "
                "truncating to first 500 shapes."
            )
            all_shapes = all_shapes[:MAX_SHAPES_PER_FRAME]

        if all_shapes or manager.has_subscribers("shapes"):
            frame = ShapeFrame(timestamp=time.time(), shapes=[])  # type: ignore[arg-type]
            # Build frame dict directly with already-dumped shapes to avoid re-parsing
            frame_dict = {"timestamp": frame.timestamp, "shapes": all_shapes}
            await manager.broadcast("shapes", frame_dict)
