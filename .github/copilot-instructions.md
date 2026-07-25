# LiDAR Standalone - Copilot Instructions

## Scope
- Monorepo with Python backend in `app/` and Angular frontend in `web/`.
- Prefer scoped changes: only touch files required by the task.

## Architecture
- Backend: FastAPI + Pydantic + SQLAlchemy + Open3D processing.
- Frontend: Angular standalone components + Signals + Three.js + Tailwind + Synergy.
- Realtime: Binary WebSocket streaming with the `LIDR` frame protocol.
- Workflow: Harness-guided process and capability checks via `scripts/bin/harness-cli`.

## Build and test
- Backend:
  - Install: `uv sync`
  - Run app: `uv run python main.py`
  - Test: `uv run pytest`
- Frontend:
  - Install: `cd web && corepack pnpm install`
  - Start: `cd web && corepack pnpm start`
  - Build: `cd web && corepack pnpm build`
  - Test: `cd web && corepack pnpm test`

## Critical conventions
- Reuse existing module boundaries and pipeline/orchestrator patterns.
- Keep heavy CPU-bound processing off the event loop (`asyncio.to_thread` or existing worker patterns).
- Keep API validation in Pydantic models and raise API-layer `HTTPException` for client errors.
- Preserve binary websocket and topic lifecycle conventions for stream safety and cleanup.
- For frontend UI, prefer Synergy components where equivalents exist.
- Keep Angular services responsible for HTTP calls; avoid pushing network logic into components.

## Harness-first workflow
- Before optional external tools, check capability availability:
  - `scripts/bin/harness-cli query tools --capability <name> --status present`
- Use clean skip behavior when a capability is absent.

## Detailed rules
- Backend implementation rules: see `.opencode/rules/backend.md`.
- Frontend implementation rules: see `.opencode/rules/frontend.md`.
- Protocol and streaming references: see `.opencode/rules/protocols.md`.
- High-level process guidance: see `AGENTS.md` and `docs/HARNESS.md`.