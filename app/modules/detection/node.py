"""
DetectionNode — DAG node for real-time ML-based 3D object detection.

Receives point cloud data from upstream nodes, runs inference through a
pluggable :class:`DetectionModel` backend, and emits 3D bounding box shapes
(``CubeShape`` + ``LabelShape``) for the Three.js viewer overlay.

Detection metadata (class, score, bbox) is forwarded downstream so it can
be consumed by ``IfConditionNode``, ``OutputNode``, or other application
logic.

Architecture notes:
  - Inference runs in a **dedicated single-thread executor** to avoid
    starving the shared asyncio thread pool (same pattern as clustering).
  - The **skip-if-busy** guard drops frames when inference is slower than
    the upstream sensor rate, preventing unbounded task accumulation.
  - Model loading is deferred to :meth:`start` so the DAG boots quickly.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import time
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.nodes.shape_collector import ShapeCollectorMixin
from app.services.nodes.shapes import CubeShape, LabelShape
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)

# Distinct colours per class for bounding box overlays
_CLASS_COLORS: Dict[str, str] = {
    "Car": "#00ff00",
    "Pedestrian": "#ff6600",
    "Cyclist": "#00ccff",
    "Truck": "#ffcc00",
    "unknown": "#ffffff",
}


class DetectionNode(ModuleNode, ShapeCollectorMixin):
    """
    Real-time 3D object detection on point cloud streams.

    Configurable via the DAG node ``config`` dict:
        model (str): Registered model name (e.g. ``"pointpillars"``).
        checkpoint (str): Path to ``.pth`` model weights.
        device (str): ``"cpu"`` or ``"cuda"``.
        confidence_threshold (float): Minimum detection score.
        nms_iou_threshold (float): BEV IoU threshold for NMS.
        point_cloud_range (list[float]): ``[x1,y1,z1, x2,y2,z2]``.
        max_detections (int): Cap on returned detections per frame.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
        throttle_ms: float = 0,
    ) -> None:
        ShapeCollectorMixin.__init__(self)
        self.manager = manager
        self.id = node_id
        self.name = name
        self.config = config

        # ── Model parameters ───────────────────────────────────────────────
        self._model_name: str = config.get("model", "pointpillars")
        self._checkpoint: str = config.get("checkpoint", "")
        self._device: str = config.get("device", "cpu")
        self._confidence: float = float(config.get("confidence_threshold", 0.3))
        self._nms_iou: float = float(config.get("nms_iou_threshold", 0.5))
        self._point_range: List[float] = list(
            config.get("point_cloud_range", [0, -39.68, -3, 69.12, 39.68, 1])
        )
        self._max_detections: int = int(config.get("max_detections", 50))
        self._emit_shapes: bool = bool(config.get("emit_shapes", True))

        # ── Runtime state ──────────────────────────────────────────────────
        self._model: Any = None  # DetectionModel instance
        self._model_loaded: bool = False
        self._processing: bool = False
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="detection",
        )

        # ── Stats ──────────────────────────────────────────────────────────
        self.last_input_at: Optional[float] = None
        self.last_output_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0
        self.detection_count: int = 0
        self.frame_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, data_queue: Any = None, runtime_status: Optional[Dict[str, Any]] = None) -> None:
        """Load the selected model when the orchestrator starts."""
        # Recreate executor if it was shut down (e.g. selective-reload rollback)
        if self._executor._shutdown:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="detection",
            )
        self._load_model()

    def stop(self) -> None:
        """Release the model and shut down the executor."""
        self._model_loaded = False
        self._executor.shutdown(wait=True)
        self._model = None

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _resolve_checkpoint(self) -> Optional[str]:
        """Resolve checkpoint config to an absolute path.

        The config value may be a model-store ID (short hex string) or an
        absolute filesystem path.  Model-store IDs are resolved first; if
        no match is found the raw value is returned as-is so legacy
        absolute-path configs keep working.
        """
        if not self._checkpoint:
            return None

        from app.modules.detection.model_store import get_model_store

        store = get_model_store()
        resolved = store.get_checkpoint_path(self._checkpoint)
        if resolved:
            return resolved
        # Fallback: treat as raw absolute path
        return self._checkpoint

    def _load_model(self) -> None:
        """Instantiate and load the configured detection model."""
        from app.modules.detection.models.base import MODEL_REGISTRY

        entry = MODEL_REGISTRY.get(self._model_name)
        if entry is None:
            available = list(MODEL_REGISTRY.keys())
            self.last_error = (
                f"Unknown model '{self._model_name}'. Available: {available}"
            )
            logger.error("[%s] %s", self.id, self.last_error)
            notify_status_change(self.id)
            return

        checkpoint_path = self._resolve_checkpoint()

        try:
            self._model = entry.builder()
            if checkpoint_path:
                self._model.load(checkpoint_path, device=self._device)
                self._model_loaded = True
                self.last_error = None
                logger.info(
                    "[%s] Model '%s' loaded (%s)",
                    self.id, self._model_name, self._device,
                )
            else:
                self.last_error = "No checkpoint configured"
                logger.warning("[%s] %s", self.id, self.last_error)
            notify_status_change(self.id)
        except ImportError as exc:
            self.last_error = f"Missing dependency: {exc}"
            logger.error("[%s] %s", self.id, self.last_error)
            notify_status_change(self.id)
        except Exception as exc:
            self.last_error = f"Model load failed: {exc}"
            logger.error("[%s] %s", self.id, self.last_error, exc_info=True)
            notify_status_change(self.id)

    # ------------------------------------------------------------------
    # DAG input
    # ------------------------------------------------------------------

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Receive point cloud, run detection, emit shapes + forward."""
        self.last_input_at = time.time()

        if not self._model_loaded:
            return

        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        # Skip-if-busy: drop frame when previous inference is still running
        if self._processing:
            logger.debug("[%s] Dropping frame — inference in progress", self.id)
            return

        self._processing = True
        start_time = time.time()
        first_frame = self.frame_count == 0
        self.frame_count += 1

        try:
            loop = asyncio.get_running_loop()
            detections = await loop.run_in_executor(
                self._executor, self._run_inference, points,
            )

            # Cap detections
            if len(detections) > self._max_detections:
                detections = sorted(detections, key=lambda d: d.score, reverse=True)
                detections = detections[: self._max_detections]

            self.detection_count = len(detections)
            self.processing_time_ms = (time.time() - start_time) * 1000
            self.last_output_at = time.time()
            self.last_error = None

            # Emit 3D bounding box shapes to the 'shapes' WebSocket topic
            if self._emit_shapes:
                for det in detections:
                    color = _CLASS_COLORS.get(det.label, _CLASS_COLORS["unknown"])
                    self.emit_shape(
                        CubeShape(
                            center=det.center,
                            size=det.size,
                            rotation=det.rotation,
                            color=color,
                            opacity=0.35,
                            wireframe=True,
                            label=f"{det.label} {det.score:.0%}",
                        )
                    )
                    # Floating label above the bounding box
                    label_pos = [
                        det.center[0],
                        det.center[1],
                        det.center[2] + det.size[2] / 2 + 0.15,
                    ]
                    self.emit_shape(
                        LabelShape(
                            position=label_pos,
                            text=f"{det.label} {det.score:.0%}",
                            color=color,
                            font_size=12,
                        )
                    )

            # Notify status change
            if first_frame or detections:
                notify_status_change(self.id)

            # Forward downstream
            new_payload = payload.copy()
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            new_payload["detections"] = [d.to_dict() for d in detections]
            new_payload["detection_count"] = len(detections)
            new_payload["metadata"] = {
                "detection_count": len(detections),
                "inference_ms": round(self.processing_time_ms, 1),
            }
            asyncio.create_task(self.manager.forward_data(self.id, new_payload))

        except Exception as exc:
            self.last_error = str(exc)
            notify_status_change(self.id)
            logger.error("[%s] Detection error: %s", self.id, exc, exc_info=True)
        finally:
            self._processing = False

    def _run_inference(self, points: np.ndarray) -> List["Detection3D"]:
        """Synchronous inference — called inside the executor thread."""
        return self._model.detect(
            points,
            confidence_threshold=self._confidence,
            nms_iou_threshold=self._nms_iou,
            point_range=self._point_range,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def emit_status(self) -> NodeStatusUpdate:
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="model", value=self._model_name, color="red",
                ),
                error_message=self.last_error,
            )

        if not self._model_loaded:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.STOPPED,
                application_state=ApplicationState(
                    label="model", value="not loaded", color="gray",
                ),
            )

        recently_active = (
            self.last_input_at is not None
            and time.time() - self.last_input_at < 5.0
        )

        if recently_active and self.detection_count > 0:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="detections",
                    value=self.detection_count,
                    color="blue",
                ),
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="model",
                value=self._model_name,
                color="green" if recently_active else "gray",
            ),
        )
