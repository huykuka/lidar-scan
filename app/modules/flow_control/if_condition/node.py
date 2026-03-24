"""
IfConditionNode - Conditional routing node for DAG orchestration.

Evaluates boolean expressions against payload metadata and routes data
to dual output ports (true/false) based on the result.
"""
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change
from .expression_parser import ExpressionParser

logger = get_logger(__name__)


class IfConditionNode(ModuleNode):
    """
    Conditional routing node with dual output ports.
    
    Evaluates a boolean expression against payload metadata and external state,
    routing data to either the 'true' or 'false' output port based on the result.
    
    Fail-safe design: expression errors route to 'false' port and log errors.
    
    Attributes:
        id: Node identifier
        name: Display name
        manager: Reference to NodeManager orchestrator
        expression: Boolean expression string
        external_state: API-controlled boolean flag (default: False)
        last_evaluation: Most recent condition result (True/False/None)
        last_error: Latest error message (or None)
        _ws_topic: WebSocket topic (None for invisible nodes)
        _parser: Expression parser instance
    """

    def __init__(
            self,
            manager: Any,
            node_id: str,
            name: str,
            expression: str,
            throttle_ms: float = 0
    ):
        """
        Initialize IF condition node.
        
        Args:
            manager: NodeManager reference
            node_id: Unique node identifier
            name: Display name
            expression: Boolean expression string
            throttle_ms: Throttle interval (handled by NodeManager)
        """
        self.id = node_id
        self.name = name
        self.manager = manager
        self.expression = expression
        self.external_state: Optional[bool] = None  # None = use expression, True/False = external control
        self.state: Optional[
            bool] = None  # Current routing state (True = route to 'true' port, False = route to 'false' port)
        self.last_evaluation: Optional[bool] = None  # Most recent condition result
        self.last_error: Optional[str] = None
        self._ws_topic: Optional[str] = None  # Invisible node by default
        self._parser = ExpressionParser()

        logger.debug(f"Created IfConditionNode {node_id} with expression: {expression}")

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Evaluate expression and route to appropriate output port.
        
        Args:
            payload: Input data from upstream nodes
        """
        # Determine final routing state
        if self.external_state is not None:
            # External control is active - use override value
            result = self.external_state
            self.state = result
            self.last_error = None
            logger.debug(f"Node {self.id}: Using external state: {result}")
        else:
            # Use expression evaluation
            context = self._build_context(payload)

            try:
                # Evaluate expression
                result = self._parser.evaluate(self.expression, context)

                # Update status
                self.state = result
                self.last_error = None

                logger.debug(f"Node {self.id}: Expression '{self.expression}' evaluated to {result}")

            except Exception as e:
                # Fail-safe: route to false port on any error
                error_msg = f"Expression evaluation failed: {e}"
                self.last_error = error_msg
                self.state = False
                result = False

                logger.error(f"Node {self.id}: {error_msg}", exc_info=True)

        # Add condition result to payload for debugging
        payload["condition_result"] = result
        payload["metadata"] = result

        # Keep last_evaluation in sync with evaluated result
        self.last_evaluation = result

        # Notify status aggregator on every evaluation
        notify_status_change(self.id)

        # Route to appropriate downstream nodes
        await self._route_to_port("true" if result else "false", payload)

    def _build_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build evaluation context from payload metadata.
        
        Args:
            payload: Input payload
            
        Returns:
            Context dictionary with all available variables
        """
        # Start with copy of payload (to avoid modifying original)
        context = payload.copy()

        # Remove 'points' array to avoid exposing large data in expressions
        context.pop("points", None)

        return context

    async def _route_to_port(self, port_id: str, payload: Dict[str, Any]) -> None:
        """
        Route data to downstream nodes connected to a specific output port.

        Delegates entirely to the NodeManager so that WebSocket broadcasting,
        recording interception, throttling, and fan-out all follow the standard
        pipeline path.  The active_port argument tells the router to restrict
        forwarding to edges whose source_port matches port_id.

        Args:
            port_id: Output port identifier ("true" or "false")
            payload: Data payload to forward
        """
        await self.manager.forward_data(self.id, payload, active_port=port_id)
        logger.debug(f"Node {self.id}: routed payload via port '{port_id}'")

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised status for this if-condition node.

        State mapping:
        - ``last_error`` set → ERROR, no application_state, propagate error_message
        - ``state is None`` → RUNNING, no application_state (not yet evaluated)
        - ``state == True`` → RUNNING, condition="true", green
        - ``state == False`` → RUNNING, condition="false", red

        Returns:
            NodeStatusUpdate with operational_state and optional condition application_state
        """
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                error_message=self.last_error,
            )

        if self.state is None:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="condition",
                value="true" if self.state else "false",
                color="green" if self.state else "red",
            ),
        )
