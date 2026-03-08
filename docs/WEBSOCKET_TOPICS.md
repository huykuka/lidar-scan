# WebSocket Topics - Lifecycle Management & Cleanup

This document covers the WebSocket topic system architecture, lifecycle management, and cleanup mechanisms that ensure robust real-time data streaming.

---

## Overview

The LiDAR standalone system uses WebSocket topics to stream real-time point cloud data from backend DAG nodes to frontend visualization components. Each node registers a unique topic when created and properly cleans up when removed.

---

## Topic Naming Convention

Topics follow a consistent naming pattern:
```
{slugified_node_name}_{node_id_prefix}
```

Examples:
- `front_lidar_abc12345` (from "Front LiDAR" node with ID "abc12345xyz...")
- `crop_filter_def67890` (from "Crop Filter" node with ID "def67890abc...")

---

## Topic Lifecycle

### 1. Registration Phase

When a node is created during configuration load:

```python
# app/services/nodes/managers/config.py
def _register_node_websocket_topic(self, node: Dict[str, Any], node_instance: Any):
    node_name = getattr(node_instance, "name", node["id"])
    safe_name = slugify_topic_prefix(node_name)
    topic = f"{safe_name}_{node['id'][:8]}"
    
    # Register topic with ConnectionManager
    manager.register_topic(topic)
    
    # Store canonical topic on instance for guaranteed cleanup
    node_instance._ws_topic = topic
```

**Key Features:**
- Topic name derived from node display name + ID prefix
- Canonical topic stored as `_ws_topic` attribute on node instance
- Registration creates empty connection list in `ConnectionManager.active_connections`

### 2. Active Phase

During normal operation:
- Clients connect to topics via WebSocket endpoints
- Backend streams binary LIDR-format data to subscribed clients
- Multiple clients can subscribe to the same topic simultaneously

### 3. Cleanup Phase

When nodes are removed or during configuration reload:

```python
# app/services/websocket/manager.py
async def unregister_topic(self, topic: str) -> None:
    # Close all active WebSocket connections gracefully
    connections = self.active_connections.pop(topic, [])
    for ws in connections:
        try:
            await ws.close(code=1001)  # 1001 Going Away
        except Exception:
            pass  # Already closed - ignore
    
    # Cancel all pending interceptor futures
    futures = self._interceptors.pop(topic, [])
    for future in futures:
        if not future.done():
            future.cancel()  # Raises CancelledError in awaiting code
```

---

## Automatic Cleanup Mechanisms

### Single Node Removal

When deleting individual nodes:
1. Node stopped and removed from DAG
2. Stored `_ws_topic` attribute read from node instance
3. Topic unregistered with graceful WebSocket closure
4. Database record removed

### Full Configuration Reload

During `POST /api/v1/nodes/reload`:
1. **Snapshot** all active topics before cleanup
2. **Stop** all nodes and unregister their topics
3. **Orphan Sweep** - detect topics that survived cleanup and force-remove them
4. **Load** new configuration and register new topics

```python
# app/services/nodes/orchestrator.py (reload_config method)
async def reload_config(self, loop=None) -> None:
    async with self._reload_lock:  # Prevent concurrent reloads
        # Snapshot topics before cleanup
        topics_before = set(manager.active_connections.keys())
        
        # Normal node cleanup
        await self._cleanup_all_nodes_async()
        
        # Orphan sweep for topics that survived
        topics_after = set(manager.active_connections.keys())
        orphaned = topics_before - topics_after - SYSTEM_TOPICS
        
        if orphaned:
            logger.warning(f"Sweeping {len(orphaned)} orphaned topics: {orphaned}")
            for topic in orphaned:
                await manager.unregister_topic(topic)
```

---

## WebSocket Protocol Changes

### Topic Removal Notification

When a topic is unregistered, connected clients receive:

| Field | Value |
|-------|-------|
| **Close Code** | `1001` (Going Away) |
| **Close Reason** | "Topic removed" |
| **Protocol** | Standard WebSocket close frame |

Clients handle this via the `WebSocket.onclose` event:

```typescript
// Frontend: MultiWebsocketService
socket.onclose = (event) => {
    if (event.code === 1001) {
        // Topic was intentionally removed - don't reconnect
        this.connections.delete(topic);
        subject.complete();  // Complete the Observable stream
    }
};
```

### API Endpoint Behavior

#### `GET /api/v1/topics`
Returns only topics for active nodes after cleanup.

#### `GET /api/v1/topics/capture?topic={topic}`
If topic is removed while waiting for data:
- Pending requests receive `503 Service Unavailable`
- Not `504 Timeout` (which indicates network issues)

```python
# app/api/v1/websocket.py
@router.get("/topics/capture")
async def capture_frame(topic: str):
    try:
        data = await manager.wait_for_next(topic, timeout=5.0)
        return Response(content=data, media_type="application/octet-stream")
    except asyncio.CancelledError:
        # Topic was removed while waiting
        raise HTTPException(
            status_code=503, 
            detail="Topic was removed while waiting for frame. Please retry."
        )
```

---

## Edge Cases & Error Handling

### Concurrent Reload Prevention

Multiple `POST /api/v1/nodes/reload` requests are serialized:
- First request acquires `asyncio.Lock`
- Subsequent requests wait or return `409 Conflict`
- Prevents state corruption from parallel cleanup

### Failed Node Initialization

If a node partially registers a topic but fails to start:
- Topic may exist in `ConnectionManager` but not in `NodeManager.nodes`
- Orphan sweep during reload detects and removes these topics
- System remains consistent

### System Topic Protection

Core system topics (e.g., `system_status`) are never swept:
```python
SYSTEM_TOPICS = {'system_status', 'health_check'}
orphaned = topics_before - topics_after - SYSTEM_TOPICS
```

### WebSocket Close Errors

Individual connection close failures don't abort cleanup:
```python
for ws in connections:
    try:
        await ws.close(code=1001)
    except Exception:
        pass  # Log at DEBUG level, continue with other connections
```

---

## Manual Testing Guide

### 1. Topic Inspection

View currently registered topics:
```bash
curl http://localhost:8000/api/v1/topics
```

Expected response:
```json
{
  "topics": ["front_lidar_abc12345", "crop_filter_def67890"],
  "description": {
    "raw_points": "Stream of raw point cloud data",
    "processed_points": "Stream of preprocessed data"
  }
}
```

### 2. Single Node Cleanup Test

```bash
# Create a test node
curl -X POST http://localhost:8000/api/v1/nodes \
  -H "Content-Type: application/json" \
  -d '{"type": "sensor", "name": "Test Sensor", "config": {}}'

# Note the node ID from response
# Check topic appears in /api/v1/topics

# Delete the node
curl -X DELETE http://localhost:8000/api/v1/nodes/{node_id}

# Verify topic removed from /api/v1/topics
# Check WebSocket clients received close frame (1001)
```

### 3. Full Reload Test

```bash
# Connect WebSocket clients to active topics
# Trigger full reload
curl -X POST http://localhost:8000/api/v1/nodes/reload

# Verify all clients disconnected gracefully
# Check logs for "orphaned topic" messages
# Confirm new topics registered after reload
```

### 4. Browser DevTools Monitoring

1. Open DevTools → Network tab → WebSocket filter
2. Connect to topic via `/ws/{topic}` endpoint
3. Trigger node removal or reload
4. Look for close frame with code `1001`

### 5. Backend Log Analysis

Search application logs for cleanup events:
```bash
grep -E "(unregister topic|orphaned topic)" logs/app.log
```

Expected entries:
```
INFO: Unregistering WebSocket topic: front_lidar_abc12345
WARNING: Sweeping 2 orphaned topics: {'old_sensor_xyz98765', 'dead_filter_123abc'}
```

---

## Performance Considerations

### Async Operations

Topic cleanup is fully async to prevent blocking:
- WebSocket close operations run in parallel via `asyncio.gather()`
- Future cancellation is immediate (no network I/O)
- `reload_config()` uses `await asyncio.sleep()` not `time.sleep()`

### Memory Management

Proper cleanup prevents memory leaks:
- Uncancelled futures accumulate in `_interceptors`
- Stale WebSocket objects hold connection state
- Topic dictionaries grow without cleanup

### Concurrent Safety

Re-entrant locks prevent race conditions:
- Only one reload can execute at a time
- Node removal during reload is queued safely
- Connection lists are modified atomically

---

## Troubleshooting

### Ghost Topics Remain After Reload

**Symptoms:** 
- Topics appear in `GET /api/v1/topics` for non-existent nodes
- WebSocket connections time out

**Diagnosis:**
1. Check if orphan sweep ran: `grep "orphaned topic" logs/`
2. Verify `_ws_topic` stored on node instances
3. Check for concurrent reload conflicts

**Resolution:**
- Manual cleanup: restart application
- Fix root cause: ensure `_ws_topic` attribute is set during registration

### WebSocket Clients Not Disconnecting

**Symptoms:**
- Clients remain connected to removed topics
- Frontend shows active connections to dead topics

**Diagnosis:**
1. Check DevTools for close frames with code `1001`
2. Verify `unregister_topic()` is being called
3. Look for WebSocket close exceptions in logs

**Resolution:**
- Check `ConnectionManager.unregister_topic()` implementation
- Verify all call sites use `await` for async version

### 503 Errors on Topic Capture

**Symptoms:**
- `/api/v1/topics/capture` returns 503 during normal operation
- Intermittent capture failures

**Diagnosis:**
1. Check if topic removal occurred during capture
2. Verify timing of reload vs capture requests
3. Look for `CancelledError` in logs

**Resolution:**
- Normal behavior during reload - clients should retry
- Consider adding exponential backoff in client code

---

## File Reference

### Core Implementation
- `app/services/websocket/manager.py` - ConnectionManager with async cleanup
- `app/services/nodes/managers/lifecycle.py` - Node removal and topic teardown
- `app/services/nodes/orchestrator.py` - Reload orchestration and orphan sweep

### API Endpoints
- `app/api/v1/nodes.py` - Node CRUD operations
- `app/api/v1/websocket.py` - Topic endpoints and capture
- `app/api/v1/config.py` - Configuration import with auto-reload

### Frontend Integration
- `web/src/app/core/services/multi-websocket.service.ts` - Client connection management
- Browser DevTools - WebSocket monitoring and close frame inspection

---

## Related Documentation

- **LIDR Protocol**: `.opencode/rules/protocols.md` - Binary frame format
- **Execution Flow**: `docs/EXECUTION_FLOW.md` - Node lifecycle and DAG operations
- **Performance Monitoring**: `AGENTS.md` - Metrics collection for WebSocket performance
- **Technical Specification**: `.opencode/plans/websocket-topic-cleanup/technical.md` - Detailed implementation

---

*Last Updated: 2026-03-08*