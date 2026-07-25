---
description: "Use when implementing or reviewing Python backend code, FastAPI APIs, Pydantic schemas, Open3D processing nodes, persistence, and backend tests."
applyTo: "app/**/*.py"
---
# Backend Instructions

## Must follow
- Keep backend changes within existing boundaries under `app/` (`api`, `services`, `modules`, `repositories`, `schemas`, `core`).
- Validate request payloads with Pydantic models at API boundaries.
- Raise `HTTPException` in API/service layers for explicit client-facing failures.
- Keep CPU-heavy processing off the asyncio event loop (`asyncio.to_thread` or existing process workers).
- Preserve websocket binary frame compatibility and topic lifecycle cleanup patterns.
- Keep data path and static file conventions aligned with existing `/data/` usage.

## Data and API rules
- Preserve response contracts for existing endpoints unless change is explicitly requested.
- Keep point-cloud transfer over binary websocket paths; do not introduce large JSON payload transfers for XYZ frames.
- Reuse existing repository/service abstractions instead of inline persistence logic.
- Avoid introducing global mutable state without synchronization and lifecycle ownership.

## Quality bar
- Add or update `pytest` coverage for changed services/routes.
- Run focused backend tests before completion (`uv run pytest` scoped when possible).

## References
- `.opencode/rules/backend.md`
- `.opencode/rules/protocols.md`
- `docs/ARCHITECTURE.md`
