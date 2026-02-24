# LiDAR Standalone - Development Guide

## Project Structure

```
lidar-standalone/
├── app/                    # Backend (Python FastAPI)
│   ├── api/v1/             # REST API endpoints (all under /api/v1 prefix)
│   │   ├── lidars.py       # Lidar CRUD + enable/disable + reload + topic_prefix
│   │   ├── fusions.py      # Fusion CRUD + enable/disable
│   │   ├── nodes.py        # Runtime status monitoring (GET /nodes/status)
│   │   ├── system.py       # System status (GET /status)
│   │   └── websocket.py    # WebSocket streaming + topic discovery
│   ├── services/           # Lidar data parsing and WebSocket handling
│   │   ├── lidar/
│   │   │   ├── core/              # Core domain models and utilities
│   │   │   │   ├── sensor_model.py   # LidarSensor model class
│   │   │   │   ├── transformations.py # Point cloud transformation math
│   │   │   │   └── topics.py         # Topic prefix generation & management
│   │   │   ├── protocol/          # Communication protocols
│   │   │   │   └── binary.py         # LIDR binary format encoding/decoding
│   │   │   ├── workers/           # Process workers
│   │   │   │   ├── sick_scan.py      # Worker process for real hardware
│   │   │   │   └── pcd.py            # Worker process for PCD simulation
│   │   │   ├── sensor.py          # LidarService — sensor lifecycle orchestrator
│   │   │   └── fusion.py          # FusionService — multi-sensor fusion
│   │   └── websocket/
│   │       └── manager.py  # WebSocket connection manager
│   ├── repositories/       # SQLite persistence layer
│   │   ├── lidars.py       # Lidar config persistence (enabled, topic_prefix, pose, etc.)
│   │   ├── fusions.py      # Fusion config persistence (enabled, sensor_ids, pipeline)
│   │   └── sqlite.py       # Migrations and DB initialization
│   ├── pipeline/           # Point cloud processing pipelines
│   └── static/             # Built Angular frontend (served at /)
├── web/                    # Modern Angular frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/       # Core singletons (API services, Store architecture, Models)
│   │   │   │   ├── models/           # TS Interfaces (lidar.model.ts, fusion.model.ts)
│   │   │   │   ├── services/         # Global Services
│   │   │   │   │   ├── api/          # Backend API clients
│   │   │   │   │   │   ├── lidar-api.service.ts
│   │   │   │   │   │   ├── fusion-api.service.ts
│   │   │   │   │   │   └── nodes-api.service.ts  # Runtime status polling
│   │   │   │   │   └── stores/       # State Management (SignalsSimpleStoreService)
│   │   │   ├── features/   # Feature modules/components (Settings, Workspaces)
│   │   │   │   ├── settings/
│   │   │   │   │   ├── components/lidar-editor/ # Reactive Lidar Configuration Form
│   │   │   │   │   └── settings.component.*     # Node management UI with runtime status
│   │   │   │   └── workspaces/                  # 3D visualization with Three.js
│   │   │   ├── layout/     # Layout shells (Main, SideNav, Header, Footer)
│   │   │   ├── app.*       # Root component and config
│   │   │   └── ...
│   │   ├── assets/         # Static assets
│   │   ├── environments/   # Environment config (API URLs: /api/v1)
│   │   └── styles/         # Global styles and Tailwind configuration
│   ├── package.json
│   ├── angular.json
│   └── tailwind.config.js
├── config/
│   └── data.db             # SQLite database (gitignored, auto-created on first run)
├── tests/                  # Unit tests (pytest)
│   └── services/
│       └── lidar/
│           ├── test_sensor_model.py    # LidarSensor model tests
│           ├── test_transformations.py # Transformation utilities tests
│           ├── test_topics.py          # Topic management tests
│           └── test_binary_protocol.py # Binary protocol tests
├── pytest.ini              # Pytest configuration
├── requirements.txt        # Python dependencies
└── AGENTS.md               # This file
```

## Frontend Stack

- **Angular** - UI framework (utilizing Standalone Components and new Control Flow)
- **Angular Signals** - Reactive state management (`signal`, `computed`, `update`)
- **Three.js** - 3D point cloud rendering (Canvas/WebGL)
- **Tailwind CSS** - Utility-first styling
- **Synergy Design System** (`@synergy-design-system/angular`) - Enterprise UI component library
- **Reactive Forms** - Form handling and strict validation (e.g., Lidar Editor)

## Backend Stack & Architecture

- **FastAPI** - Python web framework for REST endpoints and WebSockets
- **Open3D** - Point cloud processing, transformation, and downsampling pipelines
- **Multiprocessing / Subprocesses** - Hard-isolated workers for lidar ingestion
- **Asyncio** - Event loop for non-blocking WebSocket streaming
- **NumPy** - Efficient array operations and transformations
- **pytest** - Unit testing framework with 126+ tests

### Core Backend Components

1. **API Layer (`app/api/v1/`)**: REST endpoints (all under `/api/v1` prefix) for managing Lidar/Fusion configs, enable/disable controls, runtime status, and topic discovery.
2. **WebSocket Manager (`app/services/websocket/`)**: Broadcasts optimized point cloud binary frames (LIDR format) to connected Angular clients via `/api/v1/ws/{topic}`.
3. **Lidar Service (`app/services/lidar/`)**:
   - **Core Domain (`core/`)**: Sensor models, transformation mathematics, and topic management utilities
     - `sensor_model.py` - LidarSensor class with pose configuration
     - `transformations.py` - 4x4 transformation matrices and point cloud transformations
     - `topics.py` - URL-safe topic prefix generation with collision handling
   - **Protocol (`protocol/`)**: Binary communication format
     - `binary.py` - LIDR format encoding/decoding for efficient WebSocket streaming
   - **Workers (`workers/`)**: Isolated process tasks
     - `sick_scan.py` - Connects to actual hardware (UDP)
     - `pcd.py` - Loads PCD files for simulation
   - **Services**:
     - `sensor.py` - LidarService orchestrator (307 lines, down from 424)
     - `fusion.py` - Multi-sensor point cloud fusion
   - **Dev-friendly**: Gracefully handles missing `sick_scan_api` or invalid PCD paths; surfaces errors in status endpoint instead of crashing.
   - **Runtime tracking**: Process health, last frame timestamps, errors displayed in UI
4. **SQLite Persistence (`app/repositories/`)**: All lidar and fusion configurations (including `enabled`, `topic_prefix`, pose) persisted in `config/data.db`.
5. **Testing (`tests/`)**: Comprehensive unit tests with 126+ test cases covering:
   - Transformation mathematics (33 tests)
   - Binary protocol encoding/decoding (26 tests)
   - Topic generation and collision handling (37 tests)
   - Sensor model initialization and pose management (30 tests)

## State Management Architecture

The application uses a lightweight signal-based store architecture:

1. `SignalsSimpleStoreService<T>`: A generic class providing a `.state` signal, `.select()` for computed slices, and `.set()`/`.setState()` for dispatching changes.
2. **Domain Stores** (e.g., `LidarStoreService`): Extend the simple store to provide domain-specific state (like `lidars`, `selectedLidar`, `isLoading`, `editMode`).
3. **Components**: Inject the specific store via `inject()`, bind properties directly to store selectors, and dispatch updates cleanly without convoluted input/output drilling for global models.

## Backend API Endpoints

| Endpoint                             | Method    | Description                                                        |
| ------------------------------------ | --------- | ------------------------------------------------------------------ |
| `/api/v1/lidars/`                    | GET       | Returns `{ lidars: LidarConfig[], available_pipelines: string[] }` |
| `/api/v1/lidars/`                    | POST      | Register or Update a Lidar configuration                           |
| `/api/v1/lidars/{sensor_id}`         | DELETE    | Remove a Lidar configuration                                       |
| `/api/v1/lidars/{id}/enabled`        | POST      | Enable/disable a lidar (`?enabled=true` or `false`)                |
| `/api/v1/lidars/{id}/topic_prefix`   | POST      | Update topic prefix (`?topic_prefix=...`)                          |
| `/api/v1/lidars/reload`              | POST      | Trigger backend service to reload config and restart all nodes     |
| `/api/v1/fusions/`                   | GET       | Returns `{ fusions: FusionConfig[] }`                              |
| `/api/v1/fusions/`                   | POST      | Register or Update a Fusion configuration                          |
| `/api/v1/fusions/{id}`               | DELETE    | Remove a Fusion configuration                                      |
| `/api/v1/fusions/{id}/enabled`       | POST      | Enable/disable a fusion (`?enabled=true` or `false`)               |
| `/api/v1/status`                     | GET       | Returns system status `{ version: string, is_running: bool }`      |
| `/api/v1/nodes/status`               | GET       | **Runtime status** of all nodes (process health, frame age, errors)|
| `/api/v1/topics`                     | GET       | Returns available WebSocket topics                                 |
| `/api/v1/ws/{topic}`                 | WebSocket | Point cloud binary streaming                                       |

## WebSocket Binary Frame Format (LIDR)

```
Offset | Size | Type    | Description
-------|------|---------|------------
0      | 4    | char[4] | Magic "LIDR"
4      | 4    | uint32  | Version
8      | 8    | float64 | Timestamp
16     | 4    | uint32  | Point count
20     | N*12 | float32 | Points (x, y, z) * count
```

## Development Commands

```bash
# Install dependencies
cd web && npm install

# Start dev server
npm run start

# Build for production
npm run build
```

## Flow Canvas & Node System

The Settings page features a **Node-RED style flow canvas** for visual node configuration:

### Canvas Features
- **Drag-and-drop**: Nodes can be dragged from the palette onto the canvas
- **Visual connections**: Bezier curves show data flow from sensors to fusions
- **Real-time status**: Node cards display runtime health with color-coded badges
- **Pan & Zoom**: Canvas supports panning (Shift+drag or middle mouse) and zooming (mouse wheel)
- **Auto layout**: Automatically arrange nodes in a clean grid
- **Persistent positions**: Node positions saved to localStorage

### Canvas Architecture
- **Location**: `web/src/app/features/settings/components/flow-canvas/`
- **Reactive updates**: Uses Angular `effect()` to watch store changes and auto-update when nodes are added/removed
- **Connection calculation**: SVG bezier curves calculated from node positions with output ports (right side of sensors) to input ports (left side of fusions)
- **Node state management**: Canvas reads from `LidarStoreService` and `FusionStoreService` signals

### Node Plugin System

The canvas supports extensible node types through a plugin architecture:

#### Core Plugin Components

1. **`NodePlugin` interface** (`web/src/app/core/models/node-plugin.model.ts`):
```typescript
interface NodePlugin {
  type: string;              // Unique identifier (e.g., 'sensor', 'transform')
  displayName: string;       // UI label
  description: string;       // Short description for palette
  icon: string;             // Material icon name
  category: 'source' | 'processing' | 'sink' | 'utility';
  style: NodeStyle;         // Visual styling (colors, borders)
  ports: NodePorts;         // Input/output port configuration
  config?: NodeConfigSchema; // Optional configuration schema
}
```

2. **`NodePluginRegistry` service** (`web/src/app/core/services/node-plugin-registry.service.ts`):
   - Singleton service managing all registered plugins
   - Built-in plugins: `sensor` and `fusion`
   - Methods: `register()`, `getAll()`, `getByType()`, `unregister()`

#### Creating New Plugins

**Step 1**: Define your plugin in `web/src/app/plugins/`:

```typescript
// example: web/src/app/plugins/transform-plugin.ts
import { NodePlugin } from '../core/models/node-plugin.model';

export const TransformNodePlugin: NodePlugin = {
  type: 'transform',
  displayName: 'Transform',
  description: 'Apply transformations to point clouds',
  icon: 'rotate_90_degrees_ccw',
  category: 'processing',
  style: {
    backgroundColor: '#fef3c7',
    color: '#f59e0b',
    borderColor: '#fbbf24',
  },
  ports: {
    inputs: [{ id: 'input', label: 'Points In', type: 'pointcloud' }],
    outputs: [{ id: 'output', label: 'Points Out', type: 'pointcloud' }],
  },
  config: {
    fields: [
      { name: 'rotation', type: 'number', label: 'Rotation (degrees)', default: 0 },
      { name: 'scale', type: 'number', label: 'Scale Factor', default: 1.0 },
    ],
  },
};
```

**Step 2**: Register plugin in `app.config.ts`:

```typescript
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { TransformNodePlugin } from './plugins/transform-plugin';

export const appConfig: ApplicationConfig = {
  providers: [
    // ... other providers
    {
      provide: APP_INITIALIZER,
      useFactory: (registry: NodePluginRegistry) => () => {
        registry.register(TransformNodePlugin);
      },
      deps: [NodePluginRegistry],
      multi: true,
    },
  ],
};
```

**Step 3**: The plugin automatically appears in the palette and can be dragged onto the canvas.

#### Plugin Categories

- **source**: Data producers (sensors, file readers)
- **processing**: Data transformers (filters, fusion, downsampling)
- **sink**: Data consumers (recorders, publishers)
- **utility**: Helper nodes (debug, monitoring)

#### Current Plugin Status

**Implemented (Frontend Only)**:
- Plugin palette displays all registered plugins dynamically
- Drag-and-drop from palette to canvas works
- Visual distinction by category colors

**Backend Integration Needed**:
- Custom plugins currently show a warning toast when dropped
- To make custom plugins functional, backend API endpoints need to be extended to support generic node types
- Currently only `sensor` and `fusion` types are persisted and executed

#### Future Plugin Enhancements

1. **Backend Support**: Extend `/api/v1/nodes` to support generic node types with plugin metadata
2. **Connection Validation**: Enforce port type compatibility when connecting nodes
3. **Node Configuration UI**: Auto-generate config forms from `NodeConfigSchema`
4. **Plugin Marketplace**: Allow importing/exporting plugin definitions
5. **Custom Node Rendering**: Support custom templates per plugin type

## 3D Visualization System (Workspaces)

The Workspaces view provides real-time 3D visualization of point cloud streams with advanced controls and multi-topic support.

### Architecture Overview

**Location**: `web/src/app/features/workspaces/`

**Component Structure**:
```
workspaces/
├── workspaces.component.*              # Main container (283 lines)
└── components/
    ├── point-cloud/                    # Three.js renderer (340 lines)
    ├── workspace-controls/             # Topic & control panel (87 lines, 145 HTML)
    ├── workspace-view-controls/        # Camera presets & view controls (115 lines)
    └── workspace-telemetry/            # HUD stats display (93 lines)
```

### Multi-Topic Point Cloud Streaming

The visualization system supports **viewing multiple LiDAR/fusion streams simultaneously** with independent colors and controls.

#### State Management

**`WorkspaceStoreService`** (`web/src/app/core/services/stores/workspace-store.service.ts`):

```typescript
interface TopicConfig {
  topic: string;       // WebSocket topic name
  color: string;       // Hex color (e.g., '#3b82f6')
  enabled: boolean;    // Show/hide toggle
}

interface WorkspaceState {
  selectedTopics: TopicConfig[];  // Multi-topic array
  availableTopics: string[];      // From backend /api/v1/topics
  // ... other state
}

// 8 predefined colors that cycle automatically
const DEFAULT_TOPIC_COLORS = [
  '#3b82f6', // blue
  '#10b981', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#f97316', // orange
];
```

**Helper Methods**:
- `addTopic(topic, color?)` - Add new topic with auto-assigned color
- `removeTopic(topic)` - Remove topic from visualization
- `toggleTopicEnabled(topic)` - Show/hide without removing
- `updateTopicColor(topic, color)` - Change point cloud color
- **Persistence**: Selections auto-save to `localStorage` via Angular `effect()`
- **Validation**: On load, filters out stale topics (deleted sensors/fusions)

#### Multi-WebSocket Management

**`MultiWebsocketService`** (`web/src/app/core/services/multi-websocket.service.ts`):

- Manages **multiple simultaneous WebSocket connections** (one per topic)
- Each connection subscribes to `/api/v1/ws/{topic}`
- Returns `Observable<{ topic: string, data: ArrayBuffer }>` with topic identifier
- Independent lifecycle: `connect(topic)`, `disconnect(topic)`, `disconnectAll()`

**Connection Sync Pattern** (`workspaces.component.ts`):

```typescript
private syncWebSocketConnections() {
  const currentTopics = new Set(this.wsSubscriptions.keys());
  const desiredTopics = new Set(
    this.selectedTopics().filter(t => t.enabled).map(t => t.topic)
  );

  // Connect new topics
  for (const topic of desiredTopics) {
    if (!currentTopics.has(topic)) {
      this.connectToTopic(topic);
    }
  }

  // Disconnect removed topics
  for (const topic of currentTopics) {
    if (!desiredTopics.has(topic)) {
      this.disconnectFromTopic(topic);
    }
  }
}
```

Triggered reactively via Angular `effect()` watching `selectedTopics` signal.

#### Point Cloud Rendering Architecture

**`PointCloudComponent`** (`point-cloud.component.ts`) - Manages Three.js scene:

**Data Structure**:
```typescript
private pointClouds = new Map<string, {
  pointsObj: THREE.Points,           // Scene object
  geometry: THREE.BufferGeometry,    // Point positions
  material: THREE.PointsMaterial,    // Color & rendering
  lastCount: number                  // For efficient updates
}>();
```

**Key Methods**:

1. **`addOrUpdatePointCloud(topic: string, color: string)`**
   - Creates new Three.js `Points` object if topic is new
   - Updates material color if topic already exists
   - Each topic gets independent Three.js objects added to scene

2. **`removePointCloud(topic: string)`**
   - Removes Three.js objects from scene
   - Disposes geometry and material to prevent memory leaks
   - Deletes from `pointClouds` map

3. **`updatePointsForTopic(topic: string, points: Float32Array, count: number)`**
   - Updates specific topic's point positions
   - Efficient buffer updates (only resizes if count changes)
   - Marks geometry attributes as needing update

4. **`getTotalPointCount(): number`**
   - Aggregates point counts across all active topics
   - Used for HUD display

**Backwards Compatibility**: Legacy `updatePoints()` method still supported for single-topic mode.

### Camera View Presets

Quick navigation buttons for common viewpoints:

**Available Presets** (all in `point-cloud.component.ts`):

1. **`setTopView()`** - Orthographic top-down view (looking down Z-axis)
2. **`setFrontView()`** - Front elevation view (looking along Y-axis)
3. **`setSideView()`** - Side elevation view (looking along X-axis)
4. **`setIsometricView()`** - 45° isometric perspective
5. **`fitToPoints()`** - Auto-zoom to fit all point clouds in view (calculates bounding box across all topics)

**Implementation Pattern**:
```typescript
setTopView() {
  this.camera.position.set(0, 0, 50);
  this.camera.lookAt(0, 0, 0);
  this.camera.up.set(0, 1, 0);
  this.controls.update();
}
```

**UI Integration**: Buttons in `workspace-view-controls.component` emit events bound to these methods in parent component.

### UI Components & Controls

#### Workspace Controls Panel

**Location**: `workspace-controls.component.*`

**Features**:
- **Topic Dropdown**: Shows only unselected topics (filtered via `computed` signal)
- **Auto-add on Selection**: Selecting a topic immediately adds it (no button needed)
- **Active Topics List**: Per-topic controls displayed as cards:
  - **Color Picker**: `<input type="color">` bound to `updateTopicColor()`
  - **Download Button**: `syn-icon-button` with "download" icon → `onCapturePcd(topic)`
  - **Show/Hide Toggle**: `syn-icon-button` with visibility icon → `toggleTopicEnabled(topic)`
  - **Remove Button**: `syn-icon-button` with close icon → `removeTopic(topic)`
- **Tooltips**: All action buttons have descriptive tooltips
- **Success Message**: Shown when all available topics are selected
- **Legacy Mode**: Backwards-compatible single-topic section (hidden when multi-topic active)

#### Telemetry HUD

**Location**: `workspace-telemetry.component.*`

**Display**:
- **Active Topics Count**: Badge showing `(3)` enabled topics
- **Topic List**: Color-coded dots matching point cloud colors
  - Dot styling: `ring-2 ring-white/30` for visibility
  - Topic names next to each dot
- **Empty State**: Message when no topics selected
- **Computed Signals**: `enabledTopics()` filters hidden topics
- **FPS & Point Count**: Aggregated across all active streams

#### View Controls

**Location**: `workspace-view-controls.component.*`

**Camera Preset Buttons**:
- Top View
- Front View
- Side View
- Isometric View
- Fit to Points

**Other Controls**:
- Grid toggle
- Axes helper toggle
- Point size slider
- Render quality settings

### Lifecycle & ViewChild Management

**Critical Pattern** for Angular `@ViewChild` components:

```typescript
export class WorkspacesComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('pointCloud') pointCloud!: PointCloudComponent;
  private viewInitialized = false;

  constructor() {
    // DON'T access pointCloud here - it's undefined!
    
    effect(() => {
      // Guard with viewInitialized flag
      if (this.viewInitialized) {
        this.syncWebSocketConnections();
      }
    });
  }

  ngAfterViewInit() {
    // NOW pointCloud is available
    this.viewInitialized = true;
    this.initWorkspace(); // Manual sync on first load
  }
}
```

**Why This Matters**: Angular `@ViewChild` components are **not available until `ngAfterViewInit()`**. Accessing them earlier (in constructor or `ngOnInit`) causes point clouds to not render when navigating back to the page.

### Persistence & Validation

**Auto-Persistence**:
- `WorkspaceStoreService` uses `effect()` to watch state changes
- Automatically saves `selectedTopics` to `localStorage` on any modification
- Key: `workspace_state_v1`

**Stale Topic Validation** (on page load):
```typescript
initWorkspace() {
  const availableSet = new Set(this.availableTopics());
  const validTopics = this.selectedTopics().filter(t => 
    availableSet.has(t.topic)
  );
  
  if (validTopics.length !== this.selectedTopics().length) {
    // Some topics were deleted - update state
    this.workspaceStore.set({ selectedTopics: validTopics });
  }
}
```

Prevents errors from deleted sensors/fusions that were previously selected.

### WebSocket Binary Protocol

Point cloud data streams via WebSocket in **LIDR binary format** (see "WebSocket Binary Frame Format" section above).

**Decoding in Frontend**:
```typescript
private decodePointCloud(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  const magic = String.fromCharCode(...new Uint8Array(buffer, 0, 4));
  const version = view.getUint32(4, true);
  const timestamp = view.getFloat64(8, true);
  const count = view.getUint32(16, true);
  
  const points = new Float32Array(buffer, 20, count * 3);
  return { points, count, timestamp };
}
```

### Performance Considerations

**Efficient Updates**:
- Buffer geometry only reallocated if point count changes
- Uses `bufferAttribute.needsUpdate = true` for in-place updates
- Three.js renderer capped at 60 FPS via `requestAnimationFrame()`

**Memory Management**:
- Explicit disposal of geometries/materials when removing topics
- WebSocket subscriptions properly unsubscribed in `ngOnDestroy()`

**FPS Calculation**:
```typescript
private frameCount = new Map<string, number>();
private lastFpsUpdate = Date.now();

// Update per-topic frame count
this.frameCount.set(topic, (this.frameCount.get(topic) || 0) + 1);

// Calculate aggregate FPS every second
const elapsed = now - this.lastFpsUpdate;
if (elapsed >= 1000) {
  const totalFrames = Array.from(this.frameCount.values())
    .reduce((sum, count) => sum + count, 0);
  this.fps = Math.round(totalFrames / (elapsed / 1000));
}
```

### Key Files Reference

| File | Purpose | Lines |
|------|---------|-------|
| `workspaces.component.ts` | Main orchestrator with WebSocket sync | 283 |
| `point-cloud.component.ts` | Three.js scene & multi-topic rendering | 340 |
| `workspace-controls.component.ts` | Topic selection & per-topic actions | 87 |
| `workspace-controls.component.html` | Control panel UI template | 145 |
| `workspace-view-controls.component.ts` | Camera presets & view toggles | 115 |
| `workspace-telemetry.component.ts` | HUD stats with multi-topic display | 93 |
| `workspace-store.service.ts` | State management & persistence | 144 |
| `multi-websocket.service.ts` | Multi-connection WebSocket manager | 102 |

### Common Patterns

**Adding a New Camera Preset**:
1. Add method to `PointCloudComponent` (e.g., `setCustomView()`)
2. Add output event to `WorkspaceViewControlsComponent`
3. Add button to view controls template with event binding
4. Bind event in `workspaces.component.html`: `(onCustomView)="pointCloud.setCustomView()"`

**Adding Per-Topic Action**:
1. Add method to `WorkspaceStoreService` (e.g., `downloadPcd(topic)`)
2. Add button to active topics list in `workspace-controls.component.html`
3. Bind click to method: `(click)="onCustomAction(config.topic)"`

## Key Implementation Notes

1. **Synergy Design System**: Use Angular components from `@synergy-design-system/angular` seamlessly with standard structural directives (`*ngIf`, `*ngFor`).
2. **Signals Over RxJS Variables**: Component reactive states rely natively on Angular Signals (`set`, `update`, `computed`, `effect`) instead of `BehaviorSubject` chains where appropriate.
3. **Data Flows**:
   - Modal forms (like `<app-lidar-editor>`) are encapsulated and driven entirely by ReactiveForms logic, initialized from `LidarStoreService` state on load.
   - The "Save" actions invoke `LidarApiService`, refresh `LidarStoreService`, and subsequently clear the global form flag.
   - Canvas components use `effect()` to reactively update when stores change (e.g., when nodes are added/edited).
4. **Runtime Status Monitoring**:
   - Settings page polls `/api/v1/nodes/status` every 2 seconds to display real-time node health.
   - Status badges show: Running (green), Stale (yellow), Starting (yellow), Stopped (gray), Error (red).
   - Loading overlays with `syn-spinner` appear when toggling node enable/disable.
5. **Topic Naming**:
   - Each lidar has a persisted `topic_prefix` field (auto-generated from `name`, slugified, collision-safe).
   - WebSocket topics: `{topic_prefix}_raw_points` and `{topic_prefix}_processed_points`.
   - Fusion topics: custom topic name (e.g., `fused_points`).
6. **ViewChild Lifecycle**: Always guard `@ViewChild` component access with a `viewInitialized` flag set in `ngAfterViewInit()`. Accessing ViewChild components before this lifecycle hook causes rendering issues (point clouds won't display when navigating back to page).
