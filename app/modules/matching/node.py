"""Matching node: finds a stored reference point cloud in the incoming frames."""
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
from app.services.status_aggregator import notify_status_change

from .matcher import Match, Matcher, MatcherConfig, points_near_matches
from .store import AssetNotFound, ReferenceStore, reference_store

logger = get_logger(__name__)

OUTPUT_PASSTHROUGH = "passthrough"
OUTPUT_MATCHED = "matched_points"


class MatchingNode(ModuleNode, ShapeCollectorMixin):
    """Finds the reference asset in each frame and reports its pose(s).

    Payload additions: ``matches`` (list of dicts), ``match_count``, and the
    same under ``metadata``.  ``points`` is forwarded unchanged unless
    ``output_mode == "matched_points"``, in which case only points on the
    matched object(s) are forwarded (and frames without a match are dropped).
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        asset_id: str = "",
        reference_scale: float = 1.0,
        voxel_size: float = 0.05,
        min_fitness: float = 0.3,
        max_instances: int = 1,
        tracking: bool = True,
        output_mode: str = OUTPUT_PASSTHROUGH,
        emit_shapes: bool = True,
        ransac_iterations: int = 100_000,
        icp_iterations: int = 50,
        store: Optional[ReferenceStore] = None,
    ) -> None:
        ShapeCollectorMixin.__init__(self)
        self.manager = manager
        self.id = node_id
        self.name = name

        self.asset_id = asset_id or ""
        self.config = MatcherConfig(
            voxel_size=max(float(voxel_size), 1e-3),
            min_fitness=min(max(float(min_fitness), 0.0), 1.0),
            max_instances=max(int(max_instances), 1),
            ransac_iterations=max(int(ransac_iterations), 1000),
            icp_iterations=max(int(icp_iterations), 1),
            reference_scale=float(reference_scale) or 1.0,
        )
        self.tracking = bool(tracking)
        self.output_mode = output_mode if output_mode in (OUTPUT_PASSTHROUGH, OUTPUT_MATCHED) else OUTPUT_PASSTHROUGH
        self.emit_shapes = bool(emit_shapes)
        self._store = store or reference_store

        self._enabled = False
        self._processing = False
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="matching"
        )
        self._matcher: Optional[Matcher] = None
        self._matcher_version: Optional[float] = None
        self._prev_pose: Optional[np.ndarray] = None
        self._prev_fitness: Optional[float] = None

        self.last_input_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_match_count: int = 0
        self.last_fitness: Optional[float] = None
        self.processing_time_ms: float = 0.0
        self._ws_topic: Optional[str] = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self, data_queue=None, runtime_status=None) -> None:
        self.enable()

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def stop(self) -> None:
        self._enabled = False
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ── matching (runs in the executor thread) ─────────────────────────────

    def _ensure_matcher(self) -> Matcher:
        if not self.asset_id:
            raise AssetNotFound("No reference asset selected")
        version = self._store.version(self.asset_id)
        if version is None:
            raise AssetNotFound(f"Reference asset '{self.asset_id}' not found")
        if self._matcher is None or version != self._matcher_version:
            self._matcher = Matcher(self._store.load(self.asset_id), self.config)
            self._matcher_version = version
            self._prev_pose = None  # old pose is meaningless for a new reference
            self._prev_fitness = None
            logger.info("[%s] Prepared reference '%s'", self.name, self.asset_id)
        return self._matcher

    def _compute(self, points: np.ndarray) -> tuple[List[Match], np.ndarray]:
        matcher = self._ensure_matcher()
        matches = matcher.find(
            points,
            self._prev_pose if self.tracking else None,
            self._prev_fitness if self.tracking else None,
        )
        keep = self.tracking and bool(matches)
        self._prev_pose = matches[0].pose if keep else None
        # Only global results set the quality bar; tracked ones may not lower it.
        if keep and matches[0].stage != "tracking":
            self._prev_fitness = matches[0].fitness
        elif not keep:
            self._prev_fitness = None
        out = points
        if self.output_mode == OUTPUT_MATCHED:
            out = points_near_matches(points, matches, self.config.voxel_size * 2.0)
        return matches, out

    # ── data path ──────────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        if not self._enabled:
            return
        points = payload.get("points")
        if points is None or len(points) == 0:
            return
        self.last_input_at = time.time()

        if self._processing:  # back-pressure: drop frame while busy
            return
        self._processing = True
        start = time.time()
        try:
            loop = asyncio.get_running_loop()
            matches, out_points = await loop.run_in_executor(self._executor, self._compute, points)

            had_error = self.last_error is not None
            self.last_error = None
            self.processing_time_ms = (time.time() - start) * 1000
            changed = had_error or len(matches) != self.last_match_count
            self.last_match_count = len(matches)
            self.last_fitness = matches[0].fitness if matches else None
            if changed:
                notify_status_change(self.id)

            if self.emit_shapes:
                self._emit_match_shapes(matches)

            if self.output_mode == OUTPUT_MATCHED and not matches:
                return

            match_dicts = [m.to_dict() for m in matches]
            new_payload = payload.copy()
            new_payload["points"] = out_points
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            new_payload["matches"] = match_dicts
            new_payload["match_count"] = len(match_dicts)
            new_payload["metadata"] = {"match_count": len(match_dicts), "matches": match_dicts}
            asyncio.create_task(self.manager.forward_data(self.id, new_payload))
        except AssetNotFound as exc:
            self._set_error(str(exc.args[0]) if exc.args else "Reference asset not found")
        except Exception as exc:
            self._set_error(str(exc))
            logger.error("[%s] Matching failed: %s", self.name, exc, exc_info=True)
        finally:
            self._processing = False

    def _set_error(self, message: str) -> None:
        if message != self.last_error:
            self.last_error = message
            notify_status_change(self.id)

    def _emit_match_shapes(self, matches: List[Match]) -> None:
        from app.services.nodes.shapes import CubeShape

        for i, m in enumerate(matches):
            mn, mx = np.asarray(m.bbox_min), np.asarray(m.bbox_max)
            self.emit_shape(CubeShape(
                center=[float(v) for v in (mn + mx) / 2],
                size=[float(v) for v in (mx - mn)],
                color="#00ff00" if m.fitness >= 0.7 else "#ffaa00",
                opacity=0.35,
                wireframe=True,
                label=f"match_{i} ({m.fitness:.2f})",
            ))

    # ── status ─────────────────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(label="matches", value=0, color="red"),
                error_message=self.last_error,
            )
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING if self._enabled else OperationalState.STOPPED,
            application_state=ApplicationState(
                label="matches",
                value=self.last_match_count,
                color="green" if self.last_match_count else "gray",
            ),
            cycle_time_ms=round(self.processing_time_ms, 1) if self.processing_time_ms else None,
        )
