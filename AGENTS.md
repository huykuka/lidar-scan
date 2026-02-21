# LiDAR Standalone - Development Guide

## Project Structure

```
lidar-standalone/
├── app/                    # Backend (Python FastAPI)
│   ├── static/             # Legacy vanilla JS frontend
│   │   ├── index.html
│   │   └── js/main.js
│   └── ...
├── web/                    # New React frontend
│   ├── src/
│   │   ├── main.tsx        # Entry point
│   │   ├── App.tsx         # Main app with R3F Canvas
│   │   ├── index.css       # Tailwind imports
│   │   ├── state/
│   │   │   └── useLidarStore.ts    # Zustand store
│   │   ├── lib/
│   │   │   └── frames.ts           # Binary LIDR frame parser
│   │   ├── hooks/
│   │   │   ├── useLidarStream.ts   # WebSocket connection
│   │   │   ├── useTopics.ts        # Topics API fetch
│   │   │   ├── useStatus.ts        # Version/status fetch
│   │   │   └── useMemoizedCloud.ts # R3F geometry memoization
│   │   ├── components/
│   │   │   ├── TopicPanel.tsx      # Control panel with dropdown
│   │   │   ├── PointCloud.tsx      # R3F point cloud renderer
│   │   │   └── Hud.tsx             # Status overlay
│   │   └── layout/
│   │       └── Layout.tsx          # Grid layout wrapper
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   └── tailwind.config.js
└── AGENTS.md               # This file
```

## Frontend Stack

- **Vite** + **TypeScript** - Build tooling
- **React 18** - UI framework
- **React Three Fiber** (`@react-three/fiber`, `@react-three/drei`) - 3D rendering
- **Zustand** - State management
- **Tailwind CSS** - Styling
- **Synergy Design System** (`@synergy-design-system/react`) - UI components
- **Vitest** + **Testing Library** - Unit testing

## Backend API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Returns `{ version: string }` |
| `/topics` | GET | Returns `{ topics: string[] }` - available WebSocket topics |
| `/lidars` | GET/POST | CRUD for lidar configurations |
| `/ws/{topic}` | WebSocket | Point cloud streaming |

## WebSocket Protocol

### Connection URL
- **Development**: Use `VITE_WS_HOST` env variable (e.g., `ws://localhost:8000/ws`)
- **Production**: `${protocol}//${window.location.host}/ws/${topic}`

### Binary Frame Format (LIDR)

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
npm run dev

# Run tests
npm test

# Build for production
npm run build
```

## Environment Variables

Create `.env.local` in `web/` directory:

```env
# API host for development
# WebSocket URL is automatically derived (http->ws, https->wss)
VITE_API_HOST=http://localhost:8004
```

## Key Implementation Notes

1. **Synergy Design System**: Use React components from `@synergy-design-system/react`, not raw web components
2. **React 18 required**: R3F v8 has peer dependency on React 18 (not React 19)
3. **Topic selection**: Dropdown populated from `/topics` API, auto-selects first topic
4. **WebSocket reconnection**: Handled automatically when topic changes
5. **Point cloud rotation**: Applied `-90°` rotation on X and Z axes to convert Z-up to Y-up coordinate system
