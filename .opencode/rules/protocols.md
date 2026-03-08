# Network Protocols & Subsystems

## WebSocket Binary Frame Format (LIDR)

Point cloud nodes do not send slow JSON arrays over network protocols. They pack memory blocks directly onto binary buffers decoded synchronously by standard DataViews on the client.

| Offset | Size  | Type    | Description               |
| ------ | ----- | ------- | ------------------------- |
| 0      | 4     | char[4] | Magic "LIDR"              |
| 4      | 4     | uint32  | Version                   |
| 8      | 8     | float64 | Timestamp                 |
| 16     | 4     | uint32  | Point count               |
| 20     | N\*12 | float32 | Points (x, y, z) \* count |

## WebSocket Topic Lifecycle & Cleanup

WebSocket topics are managed through a complete lifecycle to ensure clean resource management and prevent ghost connections:

### Topic Registration
- Each DAG node registers a unique WebSocket topic when created: `{slugified_name}_{node_id_prefix}`
- Topics are stored canonically on node instances as `_ws_topic` attribute to guarantee cleanup consistency
- Registration creates connection tracking structures in `ConnectionManager.active_connections`

### Topic Cleanup Protocol
- **Graceful Disconnect**: Clients receive WebSocket close frame with code `1001 Going Away` when topics are removed
- **Future Cancellation**: Pending interceptor futures are cancelled to prevent memory leaks
- **Orphan Sweep**: Configuration reloads detect and clean up topics from failed node initializations
- **Concurrent Protection**: Re-entrant locks prevent parallel reload operations from corrupting topic state

### Client Handling
Frontend clients must handle `WebSocket.onclose` events with code `1001` as intentional topic removal (not network failure). The recommended pattern:

```typescript
socket.onclose = (event) => {
    if (event.code === 1001) {
        // Topic removed - complete stream, don't reconnect
        this.connections.delete(topic);
        subject.complete();
    } else {
        // Network error - attempt reconnection
        this.scheduleReconnect(topic);
    }
};
```

## Data Recording Subsystem

The recording system operates **independently from WebSocket streaming** by intercepting node outputs directly at the DAG orchestrator level.

1. **Node-Based Recording**: Recording targets nodes by their `node_id`, not WebSocket topics.
2. **DAG-Level Interception**: When any node calls `manager.forward_data(node_id, payload)`, the orchestrator checks `recorder.is_recording(node_id)` and writes the full N-dimensional point cloud data directly to disk before WebSocket broadcast occurs.
3. **Format**: Records complete numpy arrays into ZIP/PCD archives via the `RecordingService` singleton.
