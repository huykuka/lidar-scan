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
- [x] Open `app/db/models.py`
- [x] Add the `DagMetaModel` class after `EdgeModel`:
  ```python
  class DagMetaModel(Base):
      __tablename__ = "dag_meta"
      id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
      config_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
  ```
- [x] Import `Integer` from sqlalchemy if not already imported

### 1.2 Add migration in `migrate.py`
- [x] Open `app/db/migrate.py`
- [x] In `ensure_schema()` after `Base.metadata.create_all()`, add:
  ```python
  # Seed dag_meta row if table is empty
  with engine.begin() as conn:
      conn.execute(text(
          "INSERT OR IGNORE INTO dag_meta (id, config_version) VALUES (1, 0)"
      ))
  ```
- [x] Verify: Running `ensure_schema()` on an existing DB without a `dag_meta` table creates it and seeds version `0`
- [x] Verify: Running `ensure_schema()` again is idempotent (no duplicate row)

### 1.3 Add `DagMetaRepository`
- [x] Create `app/repositories/dag_meta_orm.py`
- [x] Implement `DagMetaRepository` with:
  - `get_version() -> int` — reads `config_version` from `dag_meta WHERE id=1`
  - `increment_version(session: Session) -> int` — `UPDATE dag_meta SET config_version = config_version + 1 WHERE id=1`, returns new version
  - Both methods accept optional `Session` (same pattern as `NodeRepository`)
- [x] Export from `app/repositories/__init__.py`

---

## Phase 2 — Pydantic Schemas

### 2.1 Create `app/api/v1/schemas/dag.py`
- [x] Create the file with:
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
- [x] Add Swagger `model_config = ConfigDict(json_schema_extra={...})` example to `DagConfigSaveRequest`

### 2.2 Add `ConflictResponse` to common schemas
- [x] Open `app/api/v1/schemas/common.py`
- [x] Add:
  ```python
  class ConflictResponse(BaseModel):
      detail: str
  ```

---

## Phase 3 — Service Layer

### 3.1 Create `app/api/v1/dag/` package
- [x] Create `app/api/v1/dag/__init__.py` (empty)
- [x] Create `app/api/v1/dag/service.py`

### 3.2 Implement `get_dag_config()` in `service.py`
- [x] Read all nodes via `NodeRepository().list()`
- [x] Read all edges via `EdgeRepository().list()`
- [x] Read current version via `DagMetaRepository().get_version()`
- [x] Return `DagConfigResponse(config_version=..., nodes=..., edges=...)`

### 3.3 Implement `save_dag_config()` in `service.py`
- [x] **Signature:** `async def save_dag_config(req: DagConfigSaveRequest) -> DagConfigSaveResponse`
- [x] **Step 1 — Lock:** check `node_manager._reload_lock.locked()`; raise `HTTPException(409, "reload in progress")` if locked
- [x] **Step 2 — Version check:** read current version; if `current_version != req.base_version` raise `HTTPException(409, f"Version conflict: base_version={req.base_version} but current version is {current_version}. ...")`
- [x] **Step 3 — Atomic DB transaction** (single `SessionLocal()` instance passed to repos):
  - Get existing node IDs from DB
  - For each node in `req.nodes`:
    - If `node.id` is a "temp" ID (starts with `__new__` or not present in DB): call `repo.upsert(payload)` which generates a new UUID; record `{temp_id: new_id}` in `node_id_map`
    - Otherwise: call `repo.upsert(payload)` with existing ID
  - Delete nodes that are in DB but NOT in `req.nodes`
  - Call `EdgeRepository.save_all(req.edges)` to replace all edges; update any edge `source_node`/`target_node` references using `node_id_map`
  - Call `DagMetaRepository.increment_version(session)` → `new_version`
  - Commit session
- [x] **Step 4 — Reload:** call `await node_manager.reload_config()`
- [x] **Step 5 — Return:** `DagConfigSaveResponse(config_version=new_version, node_id_map=node_id_map)`
- [x] Wrap steps 3–4 in `try/except`; on exception: rollback, raise `HTTPException(500, f"Save failed: {str(e)}")`

---

## Phase 4 — Handler (Router)

### 4.1 Create `app/api/v1/dag/handler.py`
- [x] Create `APIRouter(tags=["DAG"])`
- [x] Implement `GET /dag/config` endpoint:
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
- [x] Implement `PUT /dag/config` endpoint:
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
- [x] Open `app/app.py`
- [x] Import the new DAG router
- [x] Add `v1_router.include_router(dag_router, prefix="")` (or equivalent to how other routers are registered)

---

## Phase 5 — Tests

### 5.1 Create `tests/api/test_dag_config.py`

#### `TestGetDagConfig`
- [x] `test_get_returns_empty_dag_for_fresh_db` — empty nodes/edges, version=0
- [x] `test_get_returns_correct_version_and_nodes` — seed DB with 2 nodes + 1 edge, assert response
- [x] `test_version_is_integer` — assert `config_version` is int, not float or string

#### `TestSaveDagConfig`
- [x] `test_save_success_increments_version` — PUT with `base_version=0`, assert response `config_version=1`
- [x] `test_save_replaces_nodes` — PUT with 1 node; assert DB has only that node
- [x] `test_save_replaces_edges` — PUT with 0 edges after seeding 2 edges; assert DB has 0 edges
- [x] `test_save_assigns_new_id_for_temp_nodes` — PUT node with id `__new__abc`, assert `node_id_map` key present, new ID in DB
- [x] `test_save_409_on_version_conflict` — GET version=0, manually set DB version to 1, PUT with `base_version=0` → 409
- [x] `test_save_409_on_reload_in_progress` — mock `_reload_lock.locked()` → True → 409
- [x] `test_save_triggers_reload` — mock `node_manager.reload_config`; assert called once on success
- [x] `test_save_does_not_increment_on_db_error` — mock `repo.upsert` to throw; assert version unchanged, 500 returned
- [x] `test_save_422_on_missing_node_name` — PUT with node missing `name` field → 422

### 5.2 Create `tests/repositories/test_dag_meta_orm.py`
- [x] `test_get_version_returns_0_for_fresh_db`
- [x] `test_increment_version_returns_new_value`
- [x] `test_increment_version_is_atomic` — two calls return sequential values

### 5.3 Migration test
- [x] In `tests/` (or existing migration test file): verify `dag_meta` table exists and has 1 row after `ensure_schema()`
- [x] Verify `ensure_schema()` is idempotent on second run

---

## Phase 6 — Dead Code Removal (canvas-local-edit no longer uses per-node/edge CRUD)

> All canvas save/create/delete operations are now routed exclusively through `PUT /api/v1/dag/config`.
> The following per-node/per-edge mutation endpoints and their service functions are no longer called
> by any active frontend code or workflow and must be removed.

### 6.1 Remove edge mutation endpoints & service functions

#### `app/api/v1/edges/handler.py`
- [x] Delete `POST /edges` — `edge_create_endpoint`
- [x] Delete `DELETE /edges/{edge_id}` — `edge_delete_endpoint`
- [x] Delete `POST /edges/bulk` — `edges_bulk_endpoint`
- [x] Remove imports for `create_edge`, `delete_edge`, `save_edges_bulk`, `EdgeCreateUpdate` from handler

#### `app/api/v1/edges/service.py`
- [x] Delete `async def create_edge(edge: EdgeCreateUpdate)` function
- [x] Delete `async def delete_edge(edge_id: str)` function
- [x] Delete `async def save_edges_bulk(edges: List[EdgeCreateUpdate])` function
- [x] Delete `class EdgeCreateUpdate(BaseModel)` (no longer used by any handler)
- [x] Clean up unused imports (`uuid`, `List` from `typing` if no longer needed)

### 6.2 Remove node mutation endpoint & service function

#### `app/api/v1/nodes/handler.py`
- [x] Delete `POST /nodes` — `node_upsert_endpoint`
- [x] Delete `DELETE /nodes/{node_id}` — `node_delete_endpoint`
- [x] Remove `upsert_node`, `delete_node`, `NodeCreateUpdate` from handler imports

#### `app/api/v1/nodes/service.py`
- [x] Delete `async def upsert_node(req: NodeCreateUpdate)` function
- [x] Delete `async def delete_node(node_id: str)` function
- [x] Delete `class NodeCreateUpdate(BaseModel)` (no longer used by any handler)
- [x] Clean up unused imports (`Pose` from `app.schemas.pose`, `EdgeRepository` if only used by `delete_node`)

### 6.3 Update Swagger tag description in `app/app.py`
- [x] Update `"Nodes"` OpenAPI tag description to remove mention of CRUD/create/delete
- [x] Update `"Edges"` OpenAPI tag description to reflect read-only status (list only)

### 6.4 Update test files to remove calls to deleted endpoints

#### `tests/api/test_dag_config.py`
- [x] Replace `client.post("/api/v1/nodes", ...)` seeding calls in `test_get_returns_correct_version_and_nodes` with equivalent `PUT /dag/config` seeding
- [x] Replace `client.post("/api/v1/nodes", ...)` and `client.post("/api/v1/edges", ...)` seeding in `test_save_replaces_nodes`, `test_save_replaces_edges` with `PUT /dag/config` seeding
- [x] Verify all tests in `test_dag_config.py` still pass

### 6.5 Atomic PUT ghost/stale record validation
- [x] Confirm `save_dag_config()` in `app/api/v1/dag/service.py` deletes all DB nodes NOT present in `req.nodes` (existing `ids_to_delete` logic)
- [x] Confirm `EdgeRepository.save_all()` performs a full replace (delete-all then insert), so no stale edges can persist
- [x] Add a targeted regression test: `test_no_ghost_records_after_put` — PUT with N nodes then PUT with N-1 nodes, assert DB has exactly N-1 nodes and 0 dangling edges

### 6.6 Final verification
- [x] Run `pytest tests/api/test_dag_config.py tests/api/test_nodes_pose.py tests/api/test_config.py tests/repositories/ tests/test_dag_meta_migration.py` — all pass
- [x] Confirm `GET /api/v1/edges`, `GET /api/v1/nodes`, `GET /api/v1/nodes/{id}`, `PUT /nodes/{id}/visible`, `PUT /nodes/{id}/enabled`, `POST /nodes/reload`, `GET /nodes/status/all` still respond correctly

---

## Dependency Notes

- **Does not depend on frontend work** — backend can be developed and tested independently
- `NodeRepository`, `EdgeRepository` are used as-is; no changes to their signatures required
- `node_manager.reload_config()` is already `async` and is called identically to the existing `POST /nodes/reload` handler
- Type hints must be strict (`Dict`, `List`, `Optional` from `typing`) per `backend.md`
- Pydantic V2 models required per `backend.md`
