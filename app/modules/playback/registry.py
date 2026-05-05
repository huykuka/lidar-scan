"""
Node registry for the Playback module.

Registers:
  - NodeDefinition (schema for UI config panel)
  - @NodeFactory.register("playback") factory builder

Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List

from app.db.session import SessionLocal
from app.repositories.recordings_orm import RecordingRepository
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry,
)

# ---------------------------------------------------------------------------
# Node schema definition
# ---------------------------------------------------------------------------

node_schema_registry.register(NodeDefinition(
    type="playback",
    display_name="Playback",
    category="sensor",
    description="Replay a recording as synthetic sensor data",
    icon="play_circle",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="recording_id",
            label="Recording",
            type="select",
            required=True,
            options=[],   # populated dynamically by frontend from GET /api/v1/recordings
            help_text="Select a previously saved recording to replay",
        ),
        PropertySchema(
            name="playback_speed",
            label="Playback Speed",
            type="select",
            default=1.0,
            options=[
                {"label": "1.0×", "value": 1.0},
                {"label": "0.5×", "value": 0.5},
                {"label": "0.25×", "value": 0.25},
                {"label": "0.1×", "value": 0.1},
            ],
            help_text="Replay rate multiplier (1× = original speed)",
        ),
        PropertySchema(
            name="loopable",
            label="Loop",
            type="boolean",
            default=False,
            help_text="Restart playback from the beginning after reaching the end",
        ),
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=0,
            min=0,
            step=10,
            help_text="Minimum time between replayed frames (0 = no limit)",
        ),
    ],
    outputs=[PortSchema(id="out", label="Output")],
))


# ---------------------------------------------------------------------------
# Factory builder
# ---------------------------------------------------------------------------

@NodeFactory.register("playback")
def build_playback(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a PlaybackNode from persisted node configuration.

    Args:
        node: Persisted node dict (id, name, type, config, …).
        service_context: NodeManager / orchestrator context.
        edges: DAG edges (unused by source node).

    Returns:
        A fully configured PlaybackNode instance.

    Raises:
        ValueError: If recording_id is not found or playback_speed is invalid.
    """
    from app.modules.playback.node import PlaybackNode, VALID_SPEEDS

    config: Dict[str, Any] = node.get("config", {})
    node_id: str = node["id"]
    name: str = node.get("name", node_id)

    recording_id: str = config.get("recording_id", "")
    playback_speed: float = float(config.get("playback_speed", 1.0))
    loopable: bool = bool(config.get("loopable", False))
    throttle_ms: float = float(config.get("throttle_ms", 0))

    # Validate speed early — raises ValueError → HTTP 400 at DAG API layer
    if playback_speed not in VALID_SPEEDS:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.warning("Invalid playback_speed=%r for node %s", playback_speed, node_id)
        raise ValueError(
            f"Invalid playback_speed {playback_speed!r}. Must be one of {sorted(VALID_SPEEDS)}"
        )

    # Resolve recording from DB to validate recording_id exists
    with SessionLocal() as db:
        repo = RecordingRepository(db)
        record = repo.get_by_id(recording_id)

    if record is None:
        raise ValueError(
            f"recording_id '{recording_id}' not found. "
            "Use GET /api/v1/recordings to list available recordings."
        )

    return PlaybackNode(
        manager=service_context,
        node_id=node_id,
        name=name,
        recording_id=recording_id,
        playback_speed=playback_speed,
        loopable=loopable,
        throttle_ms=throttle_ms,
    )
