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

## Data Recording Subsystem

The recording system operates **independently from WebSocket streaming** by intercepting node outputs directly at the DAG orchestrator level.

1. **Node-Based Recording**: Recording targets nodes by their `node_id`, not WebSocket topics.
2. **DAG-Level Interception**: When any node calls `manager.forward_data(node_id, payload)`, the orchestrator checks `recorder.is_recording(node_id)` and writes the full N-dimensional point cloud data directly to disk before WebSocket broadcast occurs.
3. **Format**: Records complete numpy arrays into ZIP/PCD archives via the `RecordingService` singleton.
