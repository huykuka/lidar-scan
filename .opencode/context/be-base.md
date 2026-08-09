# BE Base Context
_Updated: 2026-08-09_

## Router map
- `app/api/v1/` includes domain routers under `/api/v1`.
- `websocket` serves topic and recording WebSockets.

## Key files
- App factory: `app/app.py`
- Settings: `app/core/config.py`
- Lifespan: `app/core/lifespan.py`
- ORM models: `app/db/models.py`
- DB session: `app/db/session.py`
- Migration: `app/db/migrate.py`
- Node factory: `app/services/nodes/node_factory.py`
- Test client: `tests/conftest.py`

## Patterns
- Recording ZIP access uses `RecordingReader`.
- API routers included from `app/api/v1/__init__.py`.
