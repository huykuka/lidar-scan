# Output Node - Requirements

## Feature Overview

The **Output Node** is a new DAG node type that displays metadata (not point cloud data) from a single input node in a dedicated Angular page. This node serves as the foundation for future Application Nodes (velocity tracking, field evaluation, vehicle classification) that will process actual point cloud data.

### What It Enables

- **Metadata Visualization**: View real-time metadata from any DAG node in a structured table format
- **Bridge to Application Nodes**: Establishes the architectural pattern for future nodes that analyze point cloud data and display results
- **System Monitoring**: Provides visibility into data flowing through the DAG pipeline without processing overhead
- **Future Extensibility**: The metadata-only MVP can be extended to include point cloud analysis results in subsequent features

### How It Fits in the DAG

The Output Node acts as a **terminal visualization node** in the processing pipeline:

1. Receives metadata payload from exactly one upstream node
2. Broadcasts metadata to frontend via WebSocket (system topic, not node-specific)
3. Displays metadata in a dedicated Angular page accessible by clicking the node in the DAG canvas
4. Does NOT modify or forward data to downstream nodes (terminal node)

**Example Workflows:**
- **LiDAR Sensor Output**: Monitor point_count, intensity_avg, timestamp, sensor_name from live sensor data
- **Processing Node Monitoring**: Track duration_ms, error_count, variance from ICP or filtering operations
- **Calibration Inspection**: Display calibration status, transform matrices, reprojection errors

---

## User Stories

### US1: Real-Time Metadata Monitoring

**As a** point cloud processing engineer,  
**I want to** view live metadata from any DAG node in a dedicated page,  
**So that** I can monitor data quality and processing behavior without examining raw point clouds.

**Acceptance Criteria:**
- Add an Output Node to the DAG and connect it to a LiDAR sensor node
- Click the Output Node in the canvas to open its dedicated page
- See metadata (point_count, timestamp, intensity_avg, etc.) updating in real-time in a table
- Metadata updates within <100ms of being emitted by the source node

---

### US2: Foundation for Application Nodes

**As a** system architect,  
**I want to** establish a reusable pattern for nodes with dedicated visualization pages,  
**So that** future Application Nodes (velocity tracking, classification) can follow the same architecture.

**Acceptance Criteria:**
- Output Node demonstrates:
  - Single-input data collection
  - Dedicated Angular page navigation
  - WebSocket-based real-time updates
  - Clean separation between backend node logic and frontend visualization
- Architecture is documented for reuse by future Application Node implementations

---

### US3: Custom Metadata Flexibility

**As a** DAG operator,  
**I want to** see all metadata fields from the input node automatically,  
**So that** I don't need to reconfigure the Output Node when upstream nodes change their metadata structure.

**Acceptance Criteria:**
- Output Node automatically displays all metadata fields present in input payloads
- Table columns dynamically adjust to metadata structure (no hardcoded field list)
- Handles varying metadata structures gracefully (missing fields show as empty/null)
- Supports nested objects and arrays (displayed as JSON strings in table cells)

---

## Acceptance Criteria

### Functional Requirements

#### F1: Single Input Connection
- [ ] Output Node accepts exactly **one** input connection
- [ ] DAG editor prevents connecting multiple inputs to an Output Node
- [ ] Node configuration validates single-input constraint
- [ ] Example: Connecting `LidarSensor → OutputNode` works. Connecting `LidarSensor → OutputNode` + `FilterNode → OutputNode` is rejected with validation error.

#### F2: Metadata Collection & Broadcasting
- [ ] On receiving input data, Output Node extracts metadata dictionary from payload
- [ ] Metadata is broadcast via WebSocket on the **system topic** (not node-specific topic)
- [ ] WebSocket payload format:
  ```typescript
  {
    type: "output_node_metadata",
    node_id: string,
    timestamp: number,
    metadata: Record<string, any>  // All custom fields from input
  }
  ```
- [ ] Does NOT forward data to downstream nodes (terminal node behavior)
- [ ] Handles missing or malformed metadata gracefully (logs warning, sends empty metadata object)

#### F3: Dedicated Angular Page
- [ ] Each Output Node has a dedicated page at route `/output/{node_id}`
- [ ] Page displays metadata in a **table layout** with columns:
  - **Field Name**: Metadata key
  - **Value**: Metadata value (primitives displayed as-is, objects/arrays as JSON)
  - **Type**: Data type (string, number, boolean, object, array, null)
- [ ] Table rows are automatically generated from metadata fields (no hardcoded schema)
- [ ] Page updates in real-time as new metadata arrives via WebSocket

#### F4: Navigation from DAG Canvas
- [ ] Clicking an Output Node in the DAG canvas opens its dedicated page
- [ ] Navigation uses Angular router: `router.navigate(['/output', node_id])`
- [ ] Page includes breadcrumb or back button to return to DAG editor
- [ ] If Output Node is deleted from DAG, navigating to its page shows "Node not found" error

#### F5: Real-Time WebSocket Updates
- [ ] Angular page subscribes to **system topic** WebSocket on page load
- [ ] Filters messages by `type === "output_node_metadata"` and `node_id === current_node_id`
- [ ] Updates table display immediately when new metadata arrives (< 100ms latency)
- [ ] Displays "Waiting for data..." placeholder when no metadata has been received yet
- [ ] Handles WebSocket disconnection gracefully (shows "Disconnected" status, attempts reconnect)

#### F6: Error Handling
- [ ] Missing input connection: Node displays warning in DAG canvas, page shows "No input connected"
- [ ] Malformed metadata: Logs backend error, sends empty metadata object to frontend
- [ ] WebSocket errors: Frontend displays reconnection status, retries connection
- [ ] Invalid node_id in route: Shows 404-style error page with link back to DAG editor

#### F7: Node Registration in DAG Editor
- [ ] Output Node appears in node palette under category: `output` or `visualization`
- [ ] Display name: `Output`
- [ ] Icon: `visibility` or `dashboard` (Material Icons)
- [ ] Node type: `output_node`
- [ ] Registered via `app/modules/output/registry.py`
- [ ] Factory builder: `@NodeFactory.register("output_node")`

---

### Non-Functional Requirements

#### NF1: Performance
- [ ] Metadata collection overhead < 1% of DAG processing time (measured with 100k point clouds)
- [ ] WebSocket broadcast is fire-and-forget (does not block input processing)
- [ ] Frontend table rendering handles up to 100 metadata fields without UI lag
- [ ] No memory leaks during continuous operation (24-hour stress test)

#### NF2: Logging & Observability
- [ ] Logs when Output Node receives metadata at DEBUG level: `"OutputNode {node_id}: Received metadata with {field_count} fields"`
- [ ] Logs WebSocket broadcast errors at ERROR level
- [ ] Node status includes:
  - `connected`: boolean (has input connection)
  - `last_update`: timestamp of most recent metadata
  - `metadata_count`: total number of metadata messages processed
  - `error_count`: number of errors encountered

#### NF3: WebSocket Protocol
- [ ] Uses **system topic** (not individual node topic per existing WebSocket topic cleanup rules)
- [ ] Message type: `output_node_metadata` (distinct from other system messages)
- [ ] Cleanup: When Output Node is deleted, stops broadcasting but does not affect system topic itself
- [ ] Follows existing WebSocket lifecycle: Graceful close with code `1001` when node is removed

#### NF4: UI/UX Guidelines
- [ ] Table uses Synergy UI components (if available) or Tailwind-styled table
- [ ] Read-only display (no editing, filtering, or export in MVP)
- [ ] Responsive design (works on desktop, table scrolls horizontally if too many fields)
- [ ] Loading states: Shows spinner while waiting for first metadata
- [ ] Empty states: Shows helpful message when no metadata available

#### NF5: Testing Requirements
- [ ] Backend unit tests:
  - Output Node creation and registration
  - Metadata extraction from input payloads
  - WebSocket broadcast logic
  - Error handling for malformed metadata
- [ ] Frontend unit tests:
  - Angular page component rendering
  - WebSocket subscription and filtering
  - Table generation from dynamic metadata
- [ ] Integration tests:
  - End-to-end flow: DAG node → Output Node → WebSocket → Angular page
  - Multiple Output Nodes in same DAG (verify correct message filtering)

---

## Out of Scope

### Explicitly NOT Included in This Feature

- **Point Cloud Data Processing**: Output Node does NOT process or visualize point cloud XYZ data. It is metadata-only. Point cloud visualization remains in the existing Three.js workspace.
- **Multiple Input Nodes**: Output Node accepts **exactly one** input. Multi-input aggregation is deferred to future Application Nodes.
- **Interactive Features**: No filtering, sorting, searching, or export functionality in MVP. Table is read-only live display only.
- **Historical Data**: Only displays the **latest** metadata. No buffering of previous frames or time-series history.
- **Data Transformation**: Output Node does NOT modify, aggregate, or compute derived metadata. It passes through fields as-is.
- **Custom Layouts**: Only table view in MVP. No card grids, charts, or JSON tree viewers.
- **Persistent Storage**: Metadata is ephemeral. Does NOT save to database or files.
- **Application Logic**: Output Node is a pure visualization layer. Business logic (velocity tracking, classification) belongs in future Application Nodes.
- **Node-Specific Topics**: Uses system topic for simplicity. Individual node topics are out of scope.

---

## Success Metrics

### Quantitative
- [ ] Output Node successfully displays metadata from at least 3 different source node types (LiDAR, filter, calibration)
- [ ] WebSocket latency < 100ms from backend emit to frontend table update
- [ ] Metadata collection overhead < 1% in performance tests with 100k point clouds
- [ ] Zero memory leaks in 24-hour continuous operation test
- [ ] Unit test coverage > 80% for backend and frontend code

### Qualitative
- [ ] Operators can inspect metadata from any DAG node within 2 clicks (add Output Node, click to open page)
- [ ] Developers can reuse Output Node architecture pattern for future Application Nodes
- [ ] Table display is intuitive and works with any metadata structure (no configuration needed)
- [ ] WebSocket updates feel instant and responsive in UI

---

## Technical Constraints

### Performance
- Metadata extraction must not block the async FastAPI event loop
- WebSocket broadcast must be fire-and-forget (no awaiting client acknowledgment)
- Frontend table must handle dynamic schema without triggering excessive re-renders

### Architecture
- Reuse existing `websocket_manager` system topic infrastructure
- Follow DAG orchestrator's decoupled design (node does not call WebSocket directly)
- Maintain compatibility with existing node lifecycle (creation, deletion, reconfiguration)

### Data Integrity
- No sensitive data (credentials, file paths) in metadata (general best practice, no specific restrictions)
- Metadata values must be JSON-serializable (no numpy arrays, binary buffers)
- Handle missing or null fields gracefully (no crashes on incomplete metadata)

### UI/UX
- Angular 20 Standalone Components with Signals for reactive state
- Tailwind CSS for styling (Synergy UI if components available)
- Responsive table layout (horizontal scroll if needed)

---

## Dependencies & Prerequisites

### Backend
- FastAPI, existing DAG orchestrator (`app/services/nodes/`)
- WebSocket manager with system topic support (`app/services/websocket/manager.py`)
- ModuleNode base class for pluggable node implementation

### Frontend
- Angular 20 (Signals, Standalone Components)
- Tailwind CSS / Synergy UI
- WebSocket service for system topic subscription
- Angular Router for `/output/{node_id}` page routing

### Protocol
- WebSocket system topic for metadata broadcast
- JSON-serializable metadata payloads
- Follows existing topic lifecycle and cleanup rules

---

## Open Questions (Resolved)

1. **Q:** What metadata fields should be displayed?  
   **A:** All custom metadata fields automatically (dynamic schema).

2. **Q:** Read-only or interactive?  
   **A:** Read-only live display (no filtering, export in MVP).

3. **Q:** UI layout?  
   **A:** Table view with Field Name, Value, Type columns.

4. **Q:** Multiple Output Nodes?  
   **A:** Yes, each with dedicated route `/output/{node_id}`.

5. **Q:** Real-time updates?  
   **A:** WebSocket (system topic) real-time push.

6. **Q:** Multiple inputs?  
   **A:** No. Exactly **one** input connection only.

7. **Q:** WebSocket topic strategy?  
   **A:** System topic (shared, not node-specific).

8. **Q:** Navigation?  
   **A:** Click Output Node in DAG canvas to open page.

9. **Q:** Metadata structure handling?  
   **A:** Display all fields automatically, no filtering.

10. **Q:** Data retention?  
    **A:** Latest metadata only, no buffering/history.

---

## Next Steps for Architecture & Planning

1. **@architecture**: Design backend Output Node module structure (inherit from `ModuleNode`, metadata extraction logic)
2. **@architecture**: Define WebSocket message format and system topic integration in `api-spec.md`
3. **@architecture**: Specify Angular page routing, component structure, and WebSocket subscription logic in `technical.md`
4. **@architecture**: Document single-input validation in DAG editor
5. **@be-dev** & **@fe-dev**: Review `technical.md` for implementation task breakdown
6. **@qa**: Define test scenarios in `qa-tasks.md` (metadata extraction, WebSocket filtering, table rendering, error handling)

---

**Document Status:** ✅ READY FOR ARCHITECTURE REVIEW  
**Next Phase:** Architecture to produce `technical.md` and `api-spec.md`
