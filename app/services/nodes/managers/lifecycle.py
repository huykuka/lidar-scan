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
    
    async def stop_all_nodes(self) -> None:
        """Async stop all node instances, properly awaiting async stop() coroutines.

        This prevents zombie playback tasks: PlaybackNode.stop() is a coroutine that
        cancels the asyncio.Task and awaits its completion.  Calling it without
        ``await`` (as the sync version does) schedules a coroutine that is never
        collected, leaving the task running until the GC eventually cleans it up.

        Sensor nodes are stopped concurrently via ``asyncio.gather`` so their
        blocking ``process.join()`` calls (each up to ~1.5 s) overlap instead
        of stacking.
        """
        import asyncio

        items = list(self.manager.nodes.items())
        if not items:
            return

        async def _stop(node_id: str, node_instance):
            logger.info(f"[LifecycleManager] Stopping node {node_id} (async)")
            await self._stop_node_async(node_instance)

        await asyncio.gather(*[_stop(nid, ni) for nid, ni in items])
    
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
    
    async def _stop_node_async(self, node_instance: Any) -> None:
        """Async stop a single node instance, awaiting coroutine stop() if present.

        For sensor nodes with sync stop() (which calls process.join() and can
        block for up to ~1.5 s), runs stop() in a thread to avoid blocking the
        asyncio event loop. For async-stop nodes (PlaybackNode), awaits normally.
        """
        if hasattr(node_instance, "stop"):
            import asyncio
            import inspect
            node_id = getattr(node_instance, "id", "?")

            # Sensor nodes have a _process attribute and their stop() is sync
            # but blocks on process.join(). Run in a thread to avoid blocking
            # the event loop.
            if hasattr(node_instance, "_process") and node_instance._process is not None:
                logger.info(f"[LifecycleManager] Running sync stop() in thread for sensor node {node_id!r}")
                loop = asyncio.get_running_loop()
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(None, node_instance.stop),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[LifecycleManager] stop() for sensor node {node_id!r} timed out after 10s — "
                        "force-killing process"
                    )
                    # Last resort: kill the worker process to avoid orphans holding
                    # hardware resources across reloads.
                    proc = getattr(node_instance, "_process", None)
                    if proc is not None and proc.is_alive():
                        proc.kill()
                        proc.join(timeout=2.0)
                    node_instance._process = None
                    node_instance._stop_event = None
                except Exception as exc:
                    logger.warning(
                        f"[LifecycleManager] node {node_id!r} stop() raised {exc!r} — ignoring"
                    )
                return

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
