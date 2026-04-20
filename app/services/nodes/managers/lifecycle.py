"""
Node lifecycle management.

This module handles starting, stopping, enabling, disabling, and removing nodes
from the orchestration system.
"""
from typing import Any

from app.core.logging import get_logger
from app.services.websocket.manager import manager
from app.services.shared.topics import slugify_topic_prefix

logger = get_logger(__name__)


class LifecycleManager:
    """Handles node lifecycle operations."""
    
    def __init__(self, manager_ref):
        """
        Initialize the lifecycle manager.
        
        Args:
            manager_ref: Reference to the NodeManager instance
        """
        self.manager = manager_ref
    
    async def start_all_nodes(self):
        """Start or enable all node instances."""
        import inspect
        for node_id, node_instance in self.manager.nodes.items():
            logger.info(f"[LifecycleManager] Registering/starting node {node_id}")
            if hasattr(node_instance, "start"):
                result = node_instance.start(self.manager.data_queue, self.manager.node_runtime_status)
                if inspect.isawaitable(result):
                    await result
            elif hasattr(node_instance, "enable"):
                node_instance.enable()
    
    def stop_all_nodes(self):
        """Stop or disable all node instances (sync — does NOT await async stop()).

        .. deprecated::
            Prefer ``stop_all_nodes_async()`` which properly awaits PlaybackNode.stop()
            and prevents zombie task leaks during DAG reload.
        """
        for node_id, node_instance in self.manager.nodes.items():
            logger.warning(
                f"[LifecycleManager] stop_all_nodes (sync) called for node {node_id} — "
                "use stop_all_nodes_async() to avoid zombie tasks on PlaybackNode"
            )
            if hasattr(node_instance, "stop"):
                node_instance.stop()
            elif hasattr(node_instance, "disable"):
                node_instance.disable()

    async def stop_all_nodes_async(self) -> None:
        """Async stop all node instances, properly awaiting async stop() coroutines.

        This prevents zombie playback tasks: PlaybackNode.stop() is a coroutine that
        cancels the asyncio.Task and awaits its completion.  Calling it without
        ``await`` (as the sync version does) schedules a coroutine that is never
        collected, leaving the task running until the GC eventually cleans it up.
        """
        for node_id, node_instance in list(self.manager.nodes.items()):
            logger.info(f"[LifecycleManager] Stopping node {node_id} (async)")
            await self._stop_node_async(node_instance)
    
    def remove_node(self, node_id: str):
        """
        Dynamically remove a node from the running pipeline.
        
        This stops the node and cleans up all associated resources including
        WebSocket topics, routing maps, and runtime state.
        
        For async contexts (FastAPI routes), prefer remove_node_async().
        
        Args:
            node_id: The ID of the node to remove
        """
        node_instance = self.manager.nodes.pop(node_id, None)
        if not node_instance:
            return

        logger.info(f"[LifecycleManager] Unregistering node {node_id} (sync remove — prefer remove_node_async)")

        self._stop_node(node_instance)
        self._unregister_node_websocket_topic(node_id, node_instance)
        self._cleanup_node_routing(node_id)
        self._cleanup_node_state(node_id)
    
    async def remove_node_async(self, node_id: str) -> None:
        """
        Async counterpart of remove_node with proper WebSocket teardown.
        
        This stops the node and cleans up all associated resources including
        WebSocket connections, topics, routing maps, and runtime state.
        
        Args:
            node_id: The ID of the node to remove
        """
        node_instance = self.manager.nodes.pop(node_id, None)
        if not node_instance:
            return

        logger.info(f"[LifecycleManager] Unregistering node {node_id} (async remove)")

        await self._stop_node_async(node_instance)
        await self._unregister_node_websocket_topic_async(node_id, node_instance)
        self._cleanup_node_routing(node_id)
        self._cleanup_node_state(node_id)
    
    def _stop_node(self, node_instance: Any):
        """Stop a single node instance (sync fallback).

        .. warning::
            For PlaybackNode (which has an async stop()), this calls stop() without
            awaiting it, leaving the asyncio.Task running until GC.
            Use ``_stop_node_async()`` in async contexts to avoid zombie tasks.
        """
        if hasattr(node_instance, "stop"):
            result = node_instance.stop()
            if result is not None:
                import asyncio
                import inspect
                if inspect.isawaitable(result):
                    node_id = getattr(node_instance, "id", "?")
                    logger.warning(
                        f"[LifecycleManager] _stop_node (sync) called for async-stop node {node_id!r} — "
                        "scheduling stop() as task; zombie risk if event loop is shutting down. "
                        "Use _stop_node_async() instead."
                    )
                    try:
                        asyncio.get_running_loop().create_task(result)
                    except RuntimeError:
                        pass  # No running loop — coroutine is lost

    async def _stop_node_async(self, node_instance: Any) -> None:
        """Async stop a single node instance, awaiting coroutine stop() if present.

        This is the safe way to stop a PlaybackNode (or any node with async stop())
        to guarantee its asyncio.Task is cancelled and joined before the caller continues.
        """
        if hasattr(node_instance, "stop"):
            import inspect
            node_id = getattr(node_instance, "id", "?")
            result = node_instance.stop()
            if inspect.isawaitable(result):
                logger.info(f"[LifecycleManager] Awaiting async stop() for node {node_id!r}")
                try:
                    await result
                except Exception as exc:
                    logger.warning(
                        f"[LifecycleManager] node {node_id!r} stop() raised {exc!r} — ignoring"
                    )
            else:
                logger.debug(f"[LifecycleManager] sync stop() completed for node {node_id!r}")
    
    def _unregister_node_websocket_topic(self, node_id: str, node_instance: Any):
        """
        Unregister WebSocket topic for a node (sync fallback - deprecated).
        
        NOTE: This sync version cannot properly close WebSocket connections.
        Use _unregister_node_websocket_topic_async() for proper cleanup.
        
        Args:
            node_id: The node ID
            node_instance: The node instance
        """
        import asyncio
        
        # Use stored topic if available to guarantee key match with registration
        if hasattr(node_instance, "_ws_topic"):
            topic = node_instance._ws_topic
        else:
            node_name = getattr(node_instance, "name", node_id)
            safe_name = slugify_topic_prefix(node_name)
            topic = f"{safe_name}_{node_id[:8]}"
        
        logger.warning(f"Sync unregister_topic called for {topic} - WebSocket connections may not be properly closed")
        
        # Try to schedule the async version if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            # Schedule the async cleanup but don't wait for it
            asyncio.create_task(manager.unregister_topic(topic))
        except RuntimeError:
            # No running event loop - can only remove from dicts (unsafe)
            logger.error(f"No event loop available to properly unregister topic {topic} - potential connection leaks")
            if topic in manager.active_connections:
                del manager.active_connections[topic]
            if topic in manager._interceptors:
                del manager._interceptors[topic]
    
    async def _unregister_node_websocket_topic_async(self, node_id: str, node_instance: Any) -> None:
        """
        Async unregister WebSocket topic for a node with proper cleanup.
        
        Reads node_instance._ws_topic first (if present) to guarantee key consistency;
        falls back to re-deriving via slugify_topic_prefix if the attribute is absent.
        
        Args:
            node_id: The node ID
            node_instance: The node instance
        """
        # Add early return guard at top: if hasattr(node_instance, "_ws_topic") and node_instance._ws_topic is None: return
        if hasattr(node_instance, "_ws_topic") and node_instance._ws_topic is None:
            return  # This prevents calling unregister_topic() on a non-existent topic for invisible nodes
            
        # Use stored topic if available to guarantee key match with registration
        if hasattr(node_instance, "_ws_topic"):
            topic = node_instance._ws_topic
        else:
            node_name = getattr(node_instance, "name", node_id)
            safe_name = slugify_topic_prefix(node_name)
            topic = f"{safe_name}_{node_id[:8]}"
        
        await manager.unregister_topic(topic)
    
    def _cleanup_node_routing(self, node_id: str):
        """
        Remove node from downstream routing maps.
        
        Args:
            node_id: The node ID to remove
        """
        # Remove as source
        if node_id in self.manager.downstream_map:
            del self.manager.downstream_map[node_id]
        
        # Remove as target from all sources (all edges are port-aware dicts)
        for source, targets in list(self.manager.downstream_map.items()):
            new_targets = [t for t in targets if t.get("target_id") != node_id]
            if len(new_targets) != len(targets):
                if new_targets:
                    self.manager.downstream_map[source] = new_targets
                else:
                    del self.manager.downstream_map[source]
    
    def _cleanup_node_state(self, node_id: str):
        """
        Clean up runtime state for a node.
        
        Args:
            node_id: The node ID to clean up
        """
        if node_id in self.manager.node_runtime_status:
            del self.manager.node_runtime_status[node_id]
        
        # Cleanup throttle state
        self.manager._throttle_config.pop(node_id, None)
        self.manager._last_process_time.pop(node_id, None)
        self.manager._throttled_count.pop(node_id, None)
