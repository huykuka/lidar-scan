"""
Abstract base class for all application-level DAG nodes.

Application nodes consume processed point cloud data from upstream nodes
and perform higher-level logic (analytics, detection, event processing).
Unlike pipeline operation nodes they are NOT expected to transform and
re-emit point clouds — they MAY forward data or act as sinks.
"""
from abc import abstractmethod
from typing import Any, Dict

from app.schemas.status import NodeStatusUpdate
from app.services.nodes.base_module import ModuleNode


class ApplicationNode(ModuleNode):
    """
    Abstract base class for all pluggable application-level nodes.

    Extends :class:`~app.services.nodes.base_module.ModuleNode` with
    conventions specific to application-layer processing:

    - Nodes should store ``self.id``, ``self.name``, ``self.manager``
      in their ``__init__``.
    - Heavy CPU work MUST be offloaded via
      ``await asyncio.to_thread(...)`` to avoid blocking the FastAPI
      event loop.
    - Results are forwarded downstream via
      ``self.manager.forward_data(self.id, payload)``.

    Required attributes (must be set by concrete subclass ``__init__``):
        id (str):      Unique node instance identifier.
        name (str):    Display name for this node.
        manager (Any): Reference to NodeManager (avoids circular import).

    Note:
        ``start()``, ``stop()``, ``enable()``, ``disable()`` are
        provided as no-ops by :class:`ModuleNode`.  Application nodes
        only need to override them when they manage background resources.
    """

    # ── Abstract interface (inherited from ModuleNode, re-declared here for
    #    documentation purposes and to enforce subclass implementation) ─────

    @abstractmethod
    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Receive a data payload from an upstream DAG node.

        Called by :class:`~app.services.nodes.orchestrator.NodeManager`
        (via ``DataRouter``) when an edge routes data to this node.

        Args:
            payload: Standard DAG payload dictionary.  Expected keys:

                * ``points`` (np.ndarray, shape ``(N, ≥3)`` float32) —
                  XYZ + optional attribute columns.
                * ``timestamp`` (float) — Unix epoch seconds of frame
                  capture.
                * ``node_id`` (str) — ID of the last node that emitted
                  this payload.
        """
        ...

    @abstractmethod
    def emit_status(self) -> NodeStatusUpdate:
        """
        Return a standardised status update for the StatusAggregator.

        Called by
        :func:`~app.services.status_aggregator._collect_and_broadcast`
        on status-change events and during periodic polls.

        Returns:
            :class:`~app.schemas.status.NodeStatusUpdate` describing the
            current operational and application state of this node.
        """
        ...
