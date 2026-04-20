"""
PlaybackNode — DAG source node that replays a recorded ZIP PCD archive.

Reads frames from a RecordingReader at the correct speed, forwarding each
frame payload to downstream nodes via manager.forward_data().
"""
from __future__ import annotations

import asyncio
import os
from asyncio import sleep as asyncio_sleep
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.repositories.recordings_orm import RecordingRepository
from app.services.nodes.base_module import ModuleNode
from app.schemas.status import NodeStatusUpdate, OperationalState, ApplicationState

logger = get_logger(__name__)

# Allowed playback speed values — validated at construction and in the factory.
VALID_SPEEDS: frozenset = frozenset({0.1, 0.25, 0.5, 1.0})


def _validate_speed(value: float) -> float:
    """Validate that *value* is one of the four allowed playback speeds.

    Args:
        value: Candidate playback_speed value.

    Returns:
        The validated value (unchanged).

    Raises:
        ValueError: If *value* is not in VALID_SPEEDS.
    """
    if value not in VALID_SPEEDS:
        raise ValueError(
            f"Invalid playback_speed {value!r}. Must be one of {sorted(VALID_SPEEDS)}"
        )
    return value


class PlaybackNode(ModuleNode):
    """Source node that streams frames from a previously recorded ZIP archive.

    Config:
        recording_id  — DB UUID resolved to file_path at start()
        playback_speed — one of {0.1, 0.25, 0.5, 1.0}; validated at construction
        loopable       — if True, replay from frame 0 after the last frame
        throttle_ms    — extra fixed sleep added per frame (milliseconds)
    """

    id: str
    name: str
    manager: Any

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        recording_id: str,
        playback_speed: float = 1.0,
        loopable: bool = False,
        throttle_ms: float = 0,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name

        # Config
        self._recording_id: str = recording_id
        self._playback_speed: float = _validate_speed(float(playback_speed))
        self._loopable: bool = bool(loopable)
        self._throttle_ms: float = float(throttle_ms)

        # Runtime state
        self._reader: Any = None          # RecordingReader | None
        self._task: Optional[asyncio.Task] = None
        self._status: str = "idle"
        self._current_frame: int = 0
        self._total_frames: int = 0
        self._error_message: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, data_queue: Any = None, runtime_status: Optional[Dict[str, Any]] = None) -> None:
        """Resolve the recording from DB, validate, and launch the playback loop.

        If a playback loop is already running (e.g. config update changed recording_id),
        it is stopped first so only one loop is ever active per node instance.
        """
        # Guard: stop any existing loop before starting a new one to prevent duplicate emission.
        if self._task is not None and not self._task.done():
            logger.info(
                "[%s] Stopping existing playback loop before starting new one (recording_id=%s → %s).",
                self.id, self._recording_id, self._recording_id,
            )
            await self.stop()

        logger.info(
            "[%s] PlaybackNode.start() entered (node_id=%s, recording_id=%s)",
            self.id, self.id, self._recording_id,
        )
        from app.services.shared.recording import RecordingReader

        # Resolve recording record from DB
        try:
            with SessionLocal() as db:
                repo = RecordingRepository(db)
                record = repo.get_by_id(self._recording_id)
        except Exception as exc:
            logger.error("[%s] DB error resolving recording_id=%s: %s", self.id, self._recording_id, exc)
            self._status = "error"
            self._error_message = str(exc)
            return

        if record is None:
            msg = f"recording_id '{self._recording_id}' not found in DB"
            logger.error("[%s] %s", self.id, msg)
            self._status = "error"
            self._error_message = msg
            return

        file_path: str = record.get("file_path", "")
        frame_count: int = int(record.get("frame_count", 0))
        duration_seconds: float = float(record.get("duration_seconds", 0.0))

        # Guard: zero frames
        if frame_count == 0:
            msg = f"Recording '{self._recording_id}' has zero frames — cannot play"
            logger.error("[%s] %s", self.id, msg)
            self._status = "error"
            self._error_message = msg
            return

        # Guard: file existence (RecordingReader appends .zip; check both)
        from pathlib import Path
        resolved = Path(file_path).with_suffix(".zip")
        if not resolved.exists():
            msg = f"Recording file not found on disk: {resolved}"
            logger.error("[%s] %s", self.id, msg)
            self._status = "error"
            self._error_message = msg
            return

        self._total_frames = frame_count
        self._current_frame = 0

        self._task = asyncio.create_task(
            self._run_loop(file_path=file_path, duration_seconds=duration_seconds),
            name=f"playback-{self.id}",
        )
        logger.info(
            "[%s] Playback task created (task_name=playback-%s): %d frames, speed=%.2f×, loopable=%s",
            self.id, self.id, frame_count, self._playback_speed, self._loopable,
        )

    async def stop(self) -> None:
        """Cancel the playback task and reset state."""
        task_name = self._task.get_name() if self._task is not None else "none"
        logger.info(
            "[%s] PlaybackNode.stop() called (node_id=%s, task=%s, done=%s)",
            self.id, self.id, task_name,
            self._task.done() if self._task is not None else True,
        )
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

        self._task = None

        if self._reader is not None:
            try:
                self._reader.zipf.close()
            except Exception:
                pass
            self._reader = None

        self._status = "idle"
        self._current_frame = 0
        logger.info("[%s] Playback stopped (node_id=%s).", self.id, self.id)

    # ------------------------------------------------------------------
    # ModuleNode interface
    # ------------------------------------------------------------------

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """No-op: PlaybackNode is a source node with no upstream input."""
        pass

    def emit_status(self) -> NodeStatusUpdate:
        """Map internal _status to OperationalState + ApplicationState."""
        if self._status == "playing":
            operational_state = OperationalState.RUNNING
            app_state = ApplicationState(
                label="status",
                value=f"playing ({self._current_frame}/{self._total_frames})",
                color="green",
            )
            error_msg = None
        elif self._status == "error":
            operational_state = OperationalState.ERROR
            app_state = ApplicationState(
                label="status",
                value=self._error_message or "error",
                color="red",
            )
            error_msg = self._error_message
        else:  # "idle"
            operational_state = OperationalState.STOPPED
            app_state = ApplicationState(
                label="status",
                value="idle",
                color="gray",
            )
            error_msg = None

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=operational_state,
            application_state=app_state,
            error_message=error_msg,
        )

    # ------------------------------------------------------------------
    # Internal playback loop
    # ------------------------------------------------------------------

    async def _run_loop(self, file_path: str, duration_seconds: float) -> None:
        """Main playback coroutine. Runs until all frames are exhausted or cancelled."""
        from app.services.shared.recording import RecordingReader

        # Open reader on thread (ZIP open is I/O)
        try:
            reader: RecordingReader = await asyncio.to_thread(RecordingReader, file_path)
        except Exception as exc:
            logger.error("[%s] Failed to open RecordingReader: %s", self.id, exc)
            self._status = "error"
            self._error_message = str(exc)
            return

        self._reader = reader
        total = reader.frame_count
        self._total_frames = total
        self._status = "playing"

        # Average inter-frame interval scaled by speed
        avg_interval: float = duration_seconds / max(total - 1, 1)
        sleep_s: float = max(0.0, avg_interval / self._playback_speed) + self._throttle_ms / 1000.0

        frame_idx: int = 0

        try:
            while True:
                # Read frame off the event loop thread
                try:
                    points, timestamp = await asyncio.to_thread(reader.get_frame, frame_idx)
                except Exception as exc:
                    logger.warning("[%s] Frame %d parse error (skipping): %s", self.id, frame_idx, exc)
                    frame_idx += 1
                    if frame_idx >= total:
                        if self._loopable:
                            frame_idx = 0
                        else:
                            break
                    continue

                self._current_frame = frame_idx + 1  # 1-based for display

                # ── Zombie-task guard ─────────────────────────────────────
                # Check that this node_id is still registered in the orchestrator
                # before emitting. If the node was removed (DAG reload or config
                # update replaced it), we must stop immediately to prevent stale
                # frames from leaking into downstream nodes or WebSocket topics.
                manager_nodes: Optional[Dict[str, Any]] = getattr(
                    self.manager, "nodes", None
                )
                if isinstance(manager_nodes, dict) and self.id not in manager_nodes:
                    logger.warning(
                        "[%s] forward_data guard: node_id '%s' no longer registered in "
                        "manager.nodes — stopping zombie playback loop at frame %d.",
                        self.id, self.id, frame_idx,
                    )
                    break
                # ─────────────────────────────────────────────────────────

                payload: Dict[str, Any] = {
                    "points": points,
                    "timestamp": timestamp,
                    "node_id": self.id,
                    "metadata": {
                        "source": "playback",
                        "recording_id": self._recording_id,
                        "frame": frame_idx,
                        "total_frames": total,
                        "playback_speed": self._playback_speed,
                        "loopable": self._loopable,
                    },
                }

                await self.manager.forward_data(self.id, payload)

                await asyncio_sleep(sleep_s)

                frame_idx += 1
                if frame_idx >= total:
                    if self._loopable:
                        frame_idx = 0
                    else:
                        break

        except asyncio.CancelledError:
            logger.info("[%s] Playback loop cancelled at frame %d.", self.id, frame_idx)
            raise
        except Exception as exc:
            logger.error("[%s] Playback loop I/O error: %s", self.id, exc, exc_info=True)
            self._status = "error"
            self._error_message = str(exc)
            return
        finally:
            try:
                reader.zipf.close()
            except Exception:
                pass
            self._reader = None

        # Clean finish
        self._status = "idle"
        logger.info("[%s] Playback finished (%d frames).", self.id, total)
