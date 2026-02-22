# LiDAR Standalone - Development Guide

## Project Structure

```
lidar-standalone/
├── app/                    # Backend (Python FastAPI)
│   ├── api/v1/             # REST API endpoints
│   ├── services/           # Lidar data parsing and WebSocket handling
│   └── ...
├── web/                    # Modern Angular frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/       # Core singletons (API services, Store architecture, Models)
│   │   │   │   ├── models/           # TS Interfaces (lidar.model.ts)
│   │   │   │   ├── services/         # Global Services (navigation, lidar-api.service)
│   │   │   │   └── services/stores/  # State Management (SignalsSimpleStoreService, lidar-store.service)
│   │   │   ├── features/   # Feature modules/components (Settings, Workspaces)
│   │   │   │   ├── settings/
│   │   │   │   │   ├── components/lidar-editor/ # Reactive Lidar Configuration Form
│   │   │   │   │   └── settings.component.*     # Lidar List and management wrap
│   │   │   │   └── workspaces/
│   │   │   ├── layout/     # Layout shells (Main, SideNav, Header, Footer)
│   │   │   ├── app.*       # Root component and config
│   │   │   └── ...
│   │   ├── assets/         # Static assets
│   │   ├── environments/   # Environment config
│   │   └── styles/         # Global styles and Tailwind configuration
│   ├── package.json
│   ├── angular.json
│   └── tailwind.config.js
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
- **msgpack** - Fast binary serialization (if used for IPC) / Custom binary format for WebSockets

### Core Backend Components

1. **API Layer (`app/api/v1/`)**: REST endpoints for managing Lidar configs, pipelines, and retrieving topics.
2. **WebSocket Manager (`app/services/websocket/`)**: Broadcasts the optimized point cloud binary frames (LIDR format) to connected Angular clients.
3. **Lidar Workers (`app/services/lidar/`)**:
   - Spawns isolated process tasks that connect to actual Hardware (UDP) or load PCD files (Simulation).
   - Passes data through a configurable sequence of `operations` (e.g., Outlier Removal, Voxel Downsampling, Pose Transformation) defined in `PipelineOperation` classes.

## State Management Architecture

The application uses a lightweight signal-based store architecture:

1. `SignalsSimpleStoreService<T>`: A generic class providing a `.state` signal, `.select()` for computed slices, and `.set()`/`.setState()` for dispatching changes.
2. **Domain Stores** (e.g., `LidarStoreService`): Extend the simple store to provide domain-specific state (like `lidars`, `selectedLidar`, `isLoading`, `editMode`).
3. **Components**: Inject the specific store via `inject()`, bind properties directly to store selectors, and dispatch updates cleanly without convoluted input/output drilling for global models.

## Backend API Endpoints

| Endpoint                     | Method    | Description                                                        |
| ---------------------------- | --------- | ------------------------------------------------------------------ |
| `/api/v1/lidars/`            | GET       | Returns `{ lidars: LidarConfig[], available_pipelines: string[] }` |
| `/api/v1/lidars/`            | POST      | Register or Update a Lidar configuration                           |
| `/api/v1/lidars/{sensor_id}` | DELETE    | Remove a Lidar configuration                                       |
| `/api/v1/lidars/reload`      | POST      | Trigger backend service to reload config and network parameters    |
| `/api/v1/status`             | GET       | Returns `{ version: string }`                                      |
| `/api/v1/topics`             | GET       | Returns available WebSocket topics                                 |
| `/ws/{topic}`                | WebSocket | Point cloud binary streaming                                       |

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

## Key Implementation Notes

1. **Synergy Design System**: Use Angular components from `@synergy-design-system/angular` seamlessly with standard structural directives (`*ngIf`, `*ngFor`).
2. **Signals Over RxJS Variables**: Component reactive states rely natively on Angular Signals (`set`, `update`, `computed`) instead of `BehaviorSubject` chains where appropriate.
3. **Data Flows**:
   - Modal forms (like `<app-lidar-editor>`) are encapsulated and driven entirely by ReactiveForms logic, initialized from `LidarStoreService` state on load.
   - The "Save" actions invoke `LidarApiService`, refresh `LidarStoreService`, and subsequently clear the global form flag.
