# LiDAR Web Frontend

React + TypeScript dashboard using Vite, Tailwind, React Three Fiber, Zustand, and Synergy Design System.

## Development

```bash
cd web
npm install
npm run dev
```

Create a `.env.local` to override the WebSocket endpoint during development:

```bash
VITE_WS_HOST=ws://localhost:8005/api/v1/ws
```

If `VITE_WS_HOST` is omitted, production defaults to `wss://<host>/ws/<topic>`.

## Testing

```bash
npm run test
```

## Build

```bash
npm run build
```
