# Canvas Local Edit — Backend Tasks

**Feature:** `canvas-local-edit`  
**Agent:** `@be-dev`  
**References:**
- Requirements: `requirements.md`
- Technical design: `technical.md`
- API contract: `api-spec.md`

**Constraint:** No changes to existing node/edge CRUD endpoints. All work is additive except `app/db/models.py` and `app/db/migrate.py`.

---

## Phase 1 — Database Layer

### 1.1 Add `DagMetaModel` to ORM models
- [ ] Open `app/db/models.py`
- [ ] Add the `DagMetaModel` class after `EdgeModel`:
  ```python
  class DagMetaModel(Base):
      __tablename__ = "dag_meta"
      id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
      config_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
  ```
- [ ] Import `Integer` from sqlalchemy if not already imported

### 1.2 Add migration in `migrate.py`
- [ ] Open `app/db/migrate.py`
- [ ] In `ensure_schema()` after `Base.metadata.create_all()`, add:
  ```python
  # Seed dag_meta row if table is empty
  with engine.begin() as conn:
      conn.execute(text(
          "INSERT OR IGNORE INTO dag_meta (id, config_version) VALUES (1, 0)"
      ))
  ```
- [ ] Verify: Running `ensure_schema()` on an existing DB without a `dag_meta` table creates it and seeds version `0`
- [ ] Verify: Running `ensure_schema()` again is idempotent (no duplicate row)

### 1.3 Add `DagMetaRepository`
- [ ] Create `app/repositories/dag_meta_orm.py`
- [ ] Implement `DagMetaRepository` with:
  - `get_version() -> int` — reads `config_version` from `dag_meta WHERE id=1`
  - `increment_version(session: Session) -> int` — `UPDATE dag_meta SET config_version = config_version + 1 WHERE id=1`, returns new version
  - Both methods accept optional `Session` (same pattern as `NodeRepository`)
- [ ] Export from `app/repositories/__init__.py`

---

## Phase 2 — Pydantic Schemas

### 2.1 Create `app/api/v1/schemas/dag.py`
- [ ] Create the file with:
  ```python
  from typing import Dict, List
  from pydantic import BaseModel
  from app.api.v1.schemas.nodes import NodeRecord
  from app.api.v1.schemas.edges import EdgeRecord

  class DagConfigResponse(BaseModel):
      config_version: int
      nodes: List[NodeRecord]
      edges: List[EdgeRecord]

  class DagConfigSaveRequest(BaseModel):
      base_version: int
      nodes: List[NodeRecord]
      edges: List[EdgeRecord]

  class DagConfigSaveResponse(BaseModel):
      config_version: int
      node_id_map: Dict[str, str]
  ```
- [ ] Add Swagger `model_config = ConfigDict(json_schema_extra={...})` example to `DagConfigSaveRequest`

### 2.2 Add `ConflictResponse` to common schemas
- [ ] Open `app/api/v1/schemas/common.py`
- [ ] Add:
  ```python
  class ConflictResponse(BaseModel):
      detail: str
  ```

---

## Phase 3 — Service Layer

### 3.1 Create `app/api/v1/dag/` package
- [ ] Create `app/api/v1/dag/__init__.py` (empty)
- [ ] Create `app/api/v1/dag/service.py`

### 3.2 Implement `get_dag_config()` in `service.py`
- [ ] Read all nodes via `NodeRepository().list()`
- [ ] Read all edges via `EdgeRepository().list()`
- [ ] Read current version via `DagMetaRepository().get_version()`
- [ ] Return `DagConfigResponse(config_version=..., nodes=..., edges=...)`

### 3.3 Implement `save_dag_config()` in `service.py`
- [ ] **Signature:** `async def save_dag_config(req: DagConfigSaveRequest) -> DagConfigSaveResponse`
- [ ] **Step 1 — Lock:** check `node_manager._reload_lock.locked()`; raise `HTTPException(409, "reload in progress")` if locked
- [ ] **Step 2 — Version check:** read current version; if `current_version != req.base_version` raise `HTTPException(409, f"Version conflict: base_version={req.base_version} but current version is {current_version}. ...")`
- [ ] **Step 3 — Atomic DB transaction** (single `SessionLocal()` instance passed to repos):
  - Get existing node IDs from DB
  - For each node in `req.nodes`:
    - If `node.id` is a "temp" ID (starts with `__new__` or not present in DB): call `repo.upsert(payload)` which generates a new UUID; record `{temp_id: new_id}` in `node_id_map`
    - Otherwise: call `repo.upsert(payload)` with existing ID
  - Delete nodes that are in DB but NOT in `req.nodes`
  - Call `EdgeRepository.save_all(req.edges)` to replace all edges; update any edge `source_node`/`target_node` references using `node_id_map`
  - Call `DagMetaRepository.increment_version(session)` → `new_version`
  - Commit session
- [ ] **Step 4 — Reload:** call `await node_manager.reload_config()`
- [ ] **Step 5 — Return:** `DagConfigSaveResponse(config_version=new_version, node_id_map=node_id_map)`
- [ ] Wrap steps 3–4 in `try/except`; on exception: rollback, raise `HTTPException(500, f"Save failed: {str(e)}")`

---

## Phase 4 — Handler (Router)

### 4.1 Create `app/api/v1/dag/handler.py`
- [ ] Create `APIRouter(tags=["DAG"])`
- [ ] Implement `GET /dag/config` endpoint:
  ```python
  @router.get(
      "/dag/config",
      response_model=DagConfigResponse,
      summary="Get DAG Configuration",
      description="Returns all nodes, edges, and current config_version for optimistic locking.",
      tags=["DAG"],
  )
  async def dag_config_get_endpoint():
      return await get_dag_config()
  ```
- [ ] Implement `PUT /dag/config` endpoint:
  ```python
  @router.put(
      "/dag/config",
      response_model=DagConfigSaveResponse,
      responses={
          409: {"description": "Version conflict or reload in progress"},
          422: {"description": "Invalid DAG configuration"},
          500: {"description": "Save or reload failure"},
      },
      summary="Save DAG Configuration",
      description=(
          "Atomically replaces all nodes and edges, increments config_version, "
          "and triggers a DAG reload. Rejects 409 if base_version is stale."
      ),
      tags=["DAG"],
  )
  async def dag_config_save_endpoint(req: DagConfigSaveRequest):
      return await save_dag_config(req)
  ```

### 4.2 Register router in `app/app.py`
- [ ] Open `app/app.py`
- [ ] Import the new DAG router
- [ ] Add `v1_router.include_router(dag_router, prefix="")` (or equivalent to how other routers are registered)

---

## Phase 5 — Tests

### 5.1 Create `tests/api/test_dag_config.py`

#### `TestGetDagConfig`
- [ ] `test_get_returns_empty_dag_for_fresh_db` — empty nodes/edges, version=0
- [ ] `test_get_returns_correct_version_and_nodes` — seed DB with 2 nodes + 1 edge, assert response
- [ ] `test_version_is_integer` — assert `config_version` is int, not float or string

#### `TestSaveDagConfig`
- [ ] `test_save_success_increments_version` — PUT with `base_version=0`, assert response `config_version=1`
- [ ] `test_save_replaces_nodes` — PUT with 1 node; assert DB has only that node
- [ ] `test_save_replaces_edges` — PUT with 0 edges after seeding 2 edges; assert DB has 0 edges
- [ ] `test_save_assigns_new_id_for_temp_nodes` — PUT node with id `__new__abc`, assert `node_id_map` key present, new ID in DB
- [ ] `test_save_409_on_version_conflict` — GET version=0, manually set DB version to 1, PUT with `base_version=0` → 409
- [ ] `test_save_409_on_reload_in_progress` — mock `_reload_lock.locked()` → True → 409
- [ ] `test_save_triggers_reload` — mock `node_manager.reload_config`; assert called once on success
- [ ] `test_save_does_not_increment_on_db_error` — mock `repo.upsert` to throw; assert version unchanged, 500 returned
- [ ] `test_save_422_on_missing_node_name` — PUT with node missing `name` field → 422

### 5.2 Create `tests/repositories/test_dag_meta_orm.py`
- [ ] `test_get_version_returns_0_for_fresh_db`
- [ ] `test_increment_version_returns_new_value`
- [ ] `test_increment_version_is_atomic` — two calls return sequential values

### 5.3 Migration test
- [ ] In `tests/` (or existing migration test file): verify `dag_meta` table exists and has 1 row after `ensure_schema()`
- [ ] Verify `ensure_schema()` is idempotent on second run

---

## Dependency Notes

- **Does not depend on frontend work** — backend can be developed and tested independently
- `NodeRepository`, `EdgeRepository` are used as-is; no changes to their signatures required
- `node_manager.reload_config()` is already `async` and is called identically to the existing `POST /nodes/reload` handler
- Type hints must be strict (`Dict`, `List`, `Optional` from `typing`) per `backend.md`
- Pydantic V2 models required per `backend.md`
