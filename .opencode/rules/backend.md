# Backend Project Rules

This file is loaded automatically by the `be-dev` agent. Documents exact conventions, file paths, and patterns for this Python + FastAPI + SQLite project.

---

## Project layout

```
app/
  app.py                    ← FastAPI app factory, CORS middleware, static mounts
  api/
    v1/                     ← all routers, prefix /api/v1
      __init__.py           ← includes all sub-routers
      auth/                 ← JWT login/logout
      dag/                  ← DAG metadata (handler.py + service.py)
      edges/                ← pipeline edge CRUD
      nodes/                ← node CRUD + status
      recordings/           ← recording start/stop/list
      results/router.py     ← result storage queries
      calibration/          ← calibration management
      lidar/                ← LiDAR profile management
      logs/                 ← log streaming
      flow_control/         ← pipeline flow ops
      config/               ← system config CRUD
      host/                 ← host system info
      system/               ← health, version, status
      websocket/            ← WS upgrade endpoints
      assets/               ← static asset endpoints
      pcd_injection/        ← manual PCD data injection
  core/
    config.py               ← pydantic BaseSettings (settings singleton)
    lifespan.py             ← FastAPI lifespan (engine init, plugin discovery, startup/shutdown)
    logging.py              ← get_logger() — stdlib logging with JSON support
    openapi.py              ← OpenAPI tag list
  db/
    models.py               ← SQLAlchemy ORM models (NodeModel, EdgeModel, RecordingModel, …)
    session.py              ← engine init, SessionLocal, WAL pragmas, get_engine(), init_engine()
    migrate.py              ← ensure_schema() — creates/alters tables from ORM
  modules/                  ← domain logic (no HTTP/ORM concerns)
    application/            ← app-level processing (truck_bin_detection lives in plugins now)
    calibration/
    flow_control/
    fusion/
    lidar/
    pcd_injection/
    pipeline/
    playback/
    visionary/
  plugins/
    __init__.py             ← auto-discovery: scans installed/, calls registry.py per plugin
    installed/              ← one folder per plugin
      <name>/
        registry.py         ← NodeFactory.register() + node_schema_registry.register()
        node.py             ← ModuleNode subclass (TruckBinDetectionNode, etc.)
        utils/              ← plugin-private helpers
  repositories/             ← DB access layer (ORM queries only, no business logic)
  schemas/                  ← Pydantic request/response models
    status.py               ← NodeStatusUpdate, ApplicationState, OperationalState
    pose.py
    results.py
  services/
    nodes/                  ← node orchestration
      node_factory.py       ← NodeFactory.create() + @NodeFactory.register()
      base_module.py        ← ModuleNode abstract base
      orchestrator.py       ← pipeline DAG orchestrator
      schema.py             ← NodeDefinition, PortSchema, PropertySchema, node_schema_registry
      managers/             ← NodeManager, config hasher, floor calibration
    websocket/              ← WS connection manager
    shared/
    results_storage.py
    status_aggregator.py    ← notify_status_change()
    host_monitor.py
tests/
  conftest.py               ← TestClient fixture, tmp SQLite DB, monkeypatch
  unit/
  integration/
  api/
  pipeline/
  repositories/
  services/
  modules/
  schemas/
  fixtures/
main.py                     ← uvicorn entrypoint
pyproject.toml              ← deps (fastapi, sqlalchemy, open3d-cpu, numpy, …)
pytest.ini                  ← testpaths=tests, addopts=-v --strict-markers
```

---

## Key patterns

### FastAPI app and lifespan

```python
# app/app.py — app factory
from fastapi import FastAPI
app = FastAPI(lifespan=lifespan)

# app/core/lifespan.py — startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()          # SQLite + WAL
    ensure_schema()        # ORM → tables
    # plugin discovery, node manager init
    yield
    # cleanup
```

### DB session dependency

```python
from app.db.session import SessionLocal

def get_session():
    with SessionLocal() as session:
        yield session

# In router:
@router.get("/nodes")
def list_nodes(session: Session = Depends(get_session)):
    ...
```

### Auth dependency

```python
from app.api.v1.auth import get_current_user
# UserRole: 'user' | 'admin' | 'service'

@router.post("/nodes")
def create_node(user = Depends(get_current_user)):
    ...
```

### ORM models

```python
# app/db/models.py
class NodeModel(Base):
    __tablename__ = "nodes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    config_json: Mapped[str] = mapped_column("config", String, default="{}")
    # config is a JSON string — parse with json.loads(model.config_json)
```

### Schema migration

```python
# app/db/migrate.py
from app.db.migrate import ensure_schema
# Adds new columns/tables derived from ORM models.
# Never ALTER tables manually.
# Call ensure_schema() in lifespan startup.
```

### Pydantic schemas

```python
# app/schemas/ or inline in router file
from pydantic import BaseModel

class NodeCreate(BaseModel):
    name: str
    type: str
    config: dict = {}

# Response uses model_validate / model_dump
```

### NodeFactory + plugin registry

```python
# app/services/nodes/node_factory.py
@NodeFactory.register("my_node_type")
def build_my_node(node, service_context, edges):
    from app.plugins.installed.my_plugin.node import MyNode  # always relative to plugin
    return MyNode(manager=service_context, node_id=node["id"], ...)
```

**CRITICAL**: plugin node classes live in `app.plugins.installed.<name>.node`.
Never import from `app.modules.application.<name>.node` — that path does not exist.

### ModuleNode interface

```python
# app/services/nodes/base_module.py
class ModuleNode:
    async def on_input(self, payload: dict) -> None: ...
    def emit_status(self) -> NodeStatusUpdate: ...
    def start(self, data_queue=None, runtime_status=None) -> None: ...
    def stop(self) -> None: ...
```

### Error handling

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="Node not found")
raise HTTPException(status_code=403, detail="Forbidden")
raise HTTPException(status_code=400, detail="Invalid input")
raise HTTPException(status_code=422, detail="Unprocessable")
```

### Status notifications

```python
from app.services.status_aggregator import notify_status_change
notify_status_change(self.id)  # triggers WS push to frontend
```

### Async / CPU-heavy work

```python
# detect() < 1 ms → run directly on event loop (no thread overhead)
result = self._detector.detect(points)

# > 1 ms CPU work → offload
result = await asyncio.to_thread(heavy_fn, args)
```

### Testing

```python
# tests/conftest.py — TestClient with tmp SQLite
@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.db.migrate import ensure_schema
    from app.db.session import init_engine
    from app.app import app
    init_engine(db_path=tmp_path / "test.db")
    ensure_schema()
    yield TestClient(app)
```

- Test files: `tests/<layer>/test_<name>.py`
- Run: `uv run pytest`
- Use `monkeypatch` to swap DB path. Never touch production DB in tests.

### New plugin checklist

1. `app/plugins/installed/<name>/__init__.py`
2. `app/plugins/installed/<name>/node.py` — `class MyNode(ModuleNode)`
3. `app/plugins/installed/<name>/registry.py` — `node_schema_registry.register(NodeDefinition(...))` + `@NodeFactory.register("type")`
4. `app/plugins/installed/<name>/utils/` — private helpers
5. Plugin auto-discovered at startup via `app/plugins/__init__.py`

### New API router checklist

1. `app/api/v1/<domain>/router.py` (or `__init__.py`)
2. Pydantic schemas in `app/schemas/` or domain subfolder
3. Repository methods in `app/repositories/`
4. Include router in `app/api/v1/__init__.py`
5. Write tests in `tests/api/test_<domain>.py`

### Commands

```bash
# Install deps
uv sync

# Dev server
uv run uvicorn main:app --reload --port 8005

# Tests
uv run pytest

# Specific test file
uv run pytest tests/api/test_nodes.py -v

# Lint (if ruff configured)
uv run ruff check app/
```

### UTC datetime rule

All stored timestamps use Python `datetime.datetime.utcnow()` or SQLAlchemy `func.now()`.
Never store naive local datetimes.
