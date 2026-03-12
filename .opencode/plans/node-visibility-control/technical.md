# Technical Specification — Node Visibility Control

**Feature:** `node-visibility-control`  
**Author:** @architecture  
**Date:** 2026-03-12  
**Status:** Approved for Implementation

---

## 1. Overview & Design Goals

This feature adds a first-class `visible` boolean field to every DAG node, controlling whether the node's WebSocket topic is registered and actively streaming point cloud data to the frontend. Invisible nodes continue all backend processing (DAG routing, Open3D operations, recording) — only the WebSocket broadcast and frontend rendering are suppressed.

### Design Principles

1. **Additive change only**: `visible` is a new column/field alongside `enabled`. The two flags are orthogonal. `enabled=false` means the node's DAG instance is not created; `visible=false` means the node runs but doesn't stream.
2. **Leverage existing cleanup infrastructure**: The existing `ConnectionManager.unregister_topic()` / `LifecycleManager._unregister_node_websocket_topic_async()` pipeline (from `websocket-topic-cleanup`) is the canonical path for teardown. Visibility changes reuse this pipeline, not a custom path.
3. **Atomic DB update**: Visibility is a single-column write with no cascade effects on other node properties.
4. **Protected system topics**: The `SYSTEM_TOPICS` set in `manager.py` blocks visibility changes on critical infrastructure topics.
5. **UI optimism with rollback**: The frontend applies the toggle visually in <100ms before the API call returns, rolling back on error.

---

## 2. Database Layer

### 2.1 Schema Change — `NodeModel`

**File:** `app/db/models.py`

Add a `visible` column to `NodeModel`. New nodes default to `True`. This must be additive — existing rows without the column get the default value via migration.

```python
class NodeModel(Base):
    __tablename__ = "nodes"
    # ... existing columns ...
    visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
```

**Serialization** — `to_dict()` must include the new field:

```python
def to_dict(self) -> dict:
    return {
        # ... existing fields ...
        "visible": self.visible,
    }
```

### 2.2 Migration

**File:** `app/db/migrate.py`

`ensure_schema()` must add the `visible` column to existing `nodes` tables using an `ALTER TABLE` guard:

```python
with engine.begin() as conn:
    cols = _table_cols(conn, "nodes")
    if "visible" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE nodes ADD COLUMN visible INTEGER NOT NULL DEFAULT 1"
        )
```

This is additive and idempotent — calling it multiple times is safe.

---

## 3. Repository Layer

### 3.1 `NodeRepository`

**File:** `app/repositories/node_orm.py`

#### `upsert()` change

When creating/updating a node, read and persist the `visible` field:

```python
visible = data.get("visible", True)
# For existing records:
existing.visible = data.get("visible", existing.visible)
# For new records:
node = NodeModel(..., visible=visible)
```

#### New method: `set_visible()`

```python
def set_visible(self, node_id: str, visible: bool) -> None:
    """Toggle node visible state — atomic single-column update."""
    session = self._get_session()
    try:
        node = session.query(NodeModel).filter(NodeModel.id == node_id).first()
        if not node:
            raise ValueError(f"Node {node_id} not found")
        node.visible = visible
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if self._should_close():
            session.close()
```

---

## 4. DAG Orchestrator Layer

### 4.1 ConfigLoader — Conditional Topic Registration

**File:** `app/services/nodes/managers/config.py`

`_register_node_websocket_topic()` must respect the `visible` flag. When `visible=False`, the topic is **not registered** in `ConnectionManager` and `node_instance._ws_topic` is set to `None`.

```python
def _register_node_websocket_topic(self, node: Dict[str, Any], node_instance: Any):
    node_name = getattr(node_instance, "name", node["id"])
    safe_name = slugify_topic_prefix(node_name)
    topic = f"{safe_name}_{node['id'][:8]}"

    if node.get("visible", True):
        manager.register_topic(topic)
        node_instance._ws_topic = topic
        logger.debug(f"Registered WS topic '{topic}' for node {node['id']}")
    else:
        node_instance._ws_topic = None  # Explicitly absent; prevents stale cleanup
        logger.debug(f"Node {node['id']} is invisible — WS topic '{topic}' not registered")
```

> **Note**: The derived topic string is not stored when `visible=False` because there is nothing to clean up. The `LifecycleManager` teardown handles `None` safely — see §4.3.

### 4.2 DataRouter — Broadcast Gate

**File:** `app/services/nodes/managers/routing.py`

`_broadcast_to_websocket()` must short-circuit if the node has no registered topic (i.e., `_ws_topic is None`):

```python
async def _broadcast_to_websocket(self, source_id: str, topic: str, payload: Dict[str, Any]):
    # Guard: invisible nodes have no registered topic
    if topic is None:
        return
    if "points" not in payload or not manager.has_subscribers(topic):
        return
    # ... existing broadcast logic ...
```

The `_get_node_topic()` call in `forward_data()` must be updated to return `None` when the node is invisible:

```python
def _get_node_topic(self, source_id: str, source_node: Any) -> Optional[str]:
    # Return None if node has no registered WS topic (invisible)
    if hasattr(source_node, "_ws_topic"):
        return source_node._ws_topic  # Could be None for invisible nodes
    # Legacy fallback for nodes without _ws_topic
    node_name = getattr(source_node, "name", source_id)
    safe_name = slugify_topic_prefix(node_name)
    return f"{safe_name}_{source_id[:8]}"
```

> **Critical invariant**: `_record_node_data()` and `_forward_to_downstream_nodes()` are **not gated** by visibility. Recording and DAG routing continue unaffected regardless of visibility state.

### 4.3 LifecycleManager — Safe Teardown for None Topic

**File:** `app/services/nodes/managers/lifecycle.py`

`_unregister_node_websocket_topic_async()` must handle `_ws_topic = None` gracefully:

```python
async def _unregister_node_websocket_topic_async(self, node_id: str, node_instance: Any) -> None:
    if hasattr(node_instance, "_ws_topic"):
        topic = node_instance._ws_topic
        if topic is None:
            # Node was invisible — no topic was registered, nothing to clean up
            return
    else:
        # Legacy fallback
        node_name = getattr(node_instance, "name", node_id)
        safe_name = slugify_topic_prefix(node_name)
        topic = f"{safe_name}_{node_id[:8]}"
    await manager.unregister_topic(topic)
```

### 4.4 NodeManager — New `set_node_visible()` Method

**File:** `app/services/nodes/orchestrator.py`

This is the runtime orchestration method that processes a visibility toggle. It is the single point of authority for in-memory state changes.

```python
async def set_node_visible(self, node_id: str, visible: bool) -> None:
    """
    Toggle a node's visibility state at runtime.

    When hiding (visible=False):
      1. Unregisters the WebSocket topic (sends 1001 Going Away to clients).
      2. Clears _ws_topic on the node instance.

    When showing (visible=True):
      1. Derives the canonical topic name.
      2. Registers the topic in ConnectionManager.
      3. Stores _ws_topic on the node instance.

    Nodes not in self.nodes (disabled/not-running) are skipped silently.
    Recording and DAG routing are NOT affected.
    """
    node_instance = self.nodes.get(node_id)
    if not node_instance:
        # Node not in running DAG — DB was already updated by the caller
        logger.debug(f"set_node_visible: node {node_id} not in running nodes, skipping runtime update")
        return

    if not visible:
        # Tear down WebSocket topic if currently registered
        if getattr(node_instance, "_ws_topic", None):
            await self._lifecycle_manager._unregister_node_websocket_topic_async(node_id, node_instance)
        node_instance._ws_topic = None
        logger.info(f"Node {node_id} hidden — WS topic unregistered")
    else:
        # Re-register WebSocket topic
        node_name = getattr(node_instance, "name", node_id)
        safe_name = slugify_topic_prefix(node_name)
        from app.services.shared.topics import slugify_topic_prefix
        topic = f"{safe_name}_{node_id[:8]}"
        websocket_manager.register_topic(topic)
        node_instance._ws_topic = topic
        logger.info(f"Node {node_id} shown — WS topic '{topic}' registered")
```

> **Thread safety**: This method must only be called from within the async FastAPI event loop. It is not protected by `_reload_lock` because it is a lightweight, single-node, non-destructive operation. Concurrent `set_node_visible` calls on the same node are unlikely at 1 node-toggle level and are handled idempotently by `register_topic`/`unregister_topic`.

### 4.5 `reload_config()` — Preserve Visibility State

**File:** `app/services/nodes/managers/config.py`

`ConfigLoader.load_from_database()` already fetches the full node dict from the DB. Because `visible` is now persisted in the DB and loaded into `node_data`, the flow is automatic: `_register_node_websocket_topic()` reads `node.get("visible", True)` from the already-loaded dict.

**No changes needed** to `reload_config()` itself — visibility state is preserved through the DB persistence layer.

### 4.6 DAG Config Import/Export

**File:** `app/api/v1/config/` (config import handler)

When importing a DAG configuration from a file, the `visible` field in the JSON must be honoured. The `upsert()` repository method already reads `visible` from the dict, so as long as the import handler passes the full node dict including `visible`, persistence is automatic.

**Export**: `GET /api/v1/config` — the config export handler must include `visible` in each node's output dict (since `to_dict()` now includes it, this is automatic).

---

## 5. API Layer

### 5.1 Pydantic Schema Updates

**File:** `app/api/v1/schemas/nodes.py`

`NodeRecord` must include the `visible` field:

```python
class NodeRecord(BaseModel):
    id: str
    name: str
    type: str
    category: str
    enabled: bool
    visible: bool = True   # NEW
    config: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None
```

`NodeStatusItem` must also include `visible`:

```python
class NodeStatusItem(BaseModel):
    # ... existing fields ...
    visible: bool = True   # NEW
```

### 5.2 DTO Updates

**File:** `app/api/v1/nodes/service.py`

`NodeCreateUpdate` must include `visible`:

```python
class NodeCreateUpdate(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    category: str
    enabled: bool = True
    visible: bool = True   # NEW
    config: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None
```

New DTO for the visibility toggle endpoint:

```python
class NodeVisibilityToggle(BaseModel):
    visible: bool
```

### 5.3 New Endpoint: `PUT /api/v1/nodes/{node_id}/visible`

**File:** `app/api/v1/nodes/handler.py` and `service.py`

```python
# handler.py
@router.put(
    "/nodes/{node_id}/visible",
    response_model=StatusResponse,
    responses={
        400: {"description": "Cannot change visibility of system topics"},
        404: {"description": "Node not found"},
    },
    summary="Set Node Visibility",
    description="Toggle node visible state. Invisible nodes stop WebSocket streaming but continue processing.",
)
async def node_visibility_endpoint(node_id: str, req: NodeVisibilityToggle):
    return await set_node_visible(node_id, req)
```

```python
# service.py
async def set_node_visible(node_id: str, req: NodeVisibilityToggle):
    """Toggle node visible state with WebSocket topic lifecycle management."""
    repo = NodeRepository()
    
    # 1. Validate node exists
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # 2. Guard: prevent visibility changes on system topics
    from app.services.websocket.manager import SYSTEM_TOPICS
    node_instance = node_manager.nodes.get(node_id)
    if node_instance:
        topic = getattr(node_instance, "_ws_topic", None)
        # Derive topic name for the check even if not currently registered
        if not topic:
            from app.services.shared.topics import slugify_topic_prefix
            node_name = getattr(node_instance, "name", node_id)
            topic = f"{slugify_topic_prefix(node_name)}_{node_id[:8]}"
        if topic in SYSTEM_TOPICS:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change visibility of system topic '{topic}'"
            )
    
    # 3. Persist to DB first (atomic)
    repo.set_visible(node_id, req.visible)
    
    # 4. Apply runtime change to running DAG
    await node_manager.set_node_visible(node_id, req.visible)
    
    return {"status": "success"}
```

### 5.4 Updated `get_nodes_status()` service

The status handler must include `visible` from both the DB record and runtime state:

```python
# In get_nodes_status():
status["visible"] = cnfg.get("visible", True)
```

---

## 6. WebSocket Protocol Flow

### 6.1 Hide Flow (visible → false)

```
PUT /api/v1/nodes/{node_id}/visible  { "visible": false }
    │
    ▼ service.set_node_visible()
    ├── repo.set_visible(node_id, False)       ← DB committed
    │
    └── node_manager.set_node_visible(node_id, False)
            │
            └── LifecycleManager._unregister_node_websocket_topic_async()
                    │
                    └── ConnectionManager.unregister_topic(topic)
                            ├── ws.close(code=1001)  for each active client
                            │       └── Client MultiWebsocketService.onclose(1001)
                            │               └── subject.complete()
                            │               └── connections.delete(topic)
                            │
                            └── future.cancel()  for each pending interceptor
                    │
                    └── node_instance._ws_topic = None
```

After this flow:
- The topic no longer appears in `GET /api/v1/topics`
- `DataRouter._broadcast_to_websocket()` short-circuits on `topic is None`
- Recording continues via `_record_node_data()` (not gated by topic)

### 6.2 Show Flow (false → visible)

```
PUT /api/v1/nodes/{node_id}/visible  { "visible": true }
    │
    ▼ service.set_node_visible()
    ├── repo.set_visible(node_id, True)        ← DB committed
    │
    └── node_manager.set_node_visible(node_id, True)
            │
            └── Derive topic: slugify(name)_id[:8]
            └── ConnectionManager.register_topic(topic)   ← topic appears in /topics
            └── node_instance._ws_topic = topic
```

After this flow:
- The topic appears in `GET /api/v1/topics`
- `DataRouter._broadcast_to_websocket()` resumes broadcasting for subscribers
- Frontend `WorkspacesComponent` detects topic list change via `system_status` poll
  and refreshes available topics

### 6.3 System Status Broadcast Integration

`status_broadcaster.py` broadcasts node status every 500ms over the `system_status` WebSocket. The broadcaster must include `visible` in each node's status payload. This triggers the frontend `StatusWebSocketService` → `effect()` → `refreshTopics()` chain, which naturally removes invisible-node topics from the workspace topic picker.

---

## 7. Frontend Architecture

### 7.1 Data Model Update

**File:** `web/src/app/core/models/node.model.ts`

```typescript
export interface NodeConfig {
  id: string;
  name: string;
  type: string;
  category: string;
  enabled: boolean;
  visible: boolean;      // NEW — defaults to true
  config: Record<string, any>;
  x: number;
  y: number;
}

export interface NodeStatus {
  // ... existing fields ...
  visible: boolean;     // NEW
}
```

### 7.2 API Service Update

**File:** `web/src/app/core/services/api/nodes-api.service.ts`

Add the visibility toggle method:

```typescript
async setNodeVisible(id: string, visible: boolean): Promise<any> {
  return await firstValueFrom(
    this.http.put(`${environment.apiUrl}/nodes/${id}/visible`, { visible })
  );
}
```

### 7.3 State Store Update

**File:** `web/src/app/core/services/stores/node-store.service.ts`

No structural changes needed. The `nodes` array already holds `NodeConfig[]`. Once `NodeConfig` gains `visible`, the Signal reactivity propagates automatically. A computed selector for visible nodes is useful:

```typescript
visibleNodes = computed(() => this.nodes().filter(n => n.visible !== false));
```

### 7.4 Visibility Toggle Logic — Smart Component

The visibility toggle is a **Smart Component concern** (state + API call). The recommended home is the **Settings feature**, specifically the `dynamic-node-editor` or a new `node-list-item` component in `features/settings/components/`.

#### Toggle Handler Pattern

```typescript
// In the smart component:
protected async toggleNodeVisibility(node: NodeConfig): Promise<void> {
  const newVisible = !node.visible;

  // 1. Optimistic UI update (<100ms)
  const nodes = this.nodeStore.getValue('nodes');
  this.nodeStore.set('nodes', nodes.map(n =>
    n.id === node.id ? { ...n, visible: newVisible } : n
  ));

  // 2. API call
  try {
    await this.nodesApi.setNodeVisible(node.id, newVisible);
  } catch (err) {
    // 3. Rollback on error
    this.nodeStore.set('nodes', nodes);
    this.toast.danger('Failed to update node visibility.');
  }
}
```

### 7.5 New Presentation Component: `NodeVisibilityToggleComponent`

**Scaffold with:** `cd web && ng g component features/settings/components/node-visibility-toggle`

This is a **dumb/presentation component** receiving a `NodeConfig` via Signal `input()` and emitting a `visibilityChanged` output. It renders a Synergy UI eye icon button.

```typescript
@Component({
  selector: 'app-node-visibility-toggle',
  standalone: true,
  imports: [SynergyComponentsModule],
  template: `
    <syn-icon-button
      [name]="node().visible !== false ? 'visibility' : 'visibility_off'"
      [class]="node().visible !== false ? 'text-white' : 'opacity-40'"
      [title]="node().visible !== false ? 'Hide node' : 'Show node'"
      (click)="onToggle()"
    />
  `
})
export class NodeVisibilityToggleComponent {
  node = input.required<NodeConfig>();
  visibilityChanged = output<boolean>();

  protected onToggle(): void {
    this.visibilityChanged.emit(!this.node().visible);
  }
}
```

### 7.6 Workspace Topic Selector — Invisible Node Filtering

**File:** `web/src/app/core/services/api/topic-api.service.ts` (no change needed)

The backend `GET /api/v1/topics` already returns only registered topics. Since invisible nodes' topics are unregistered on the backend, they will naturally disappear from the topic list. The `WorkspacesComponent.refreshTopics()` pattern — already triggered by `system_status` changes — handles cleanup of removed topics from `selectedTopics`.

**Additional guard** in `WorkspaceControlsComponent` for display clarity:

```typescript
// Filter topics shown in the workspace topic selector
// (backend filtering is primary; this is a UI-side safety net)
protected availableTopics = computed(() => {
  const all = this.topics();
  const selected = this.selectedTopics().map(t => t.topic);
  return all.filter(t => !selected.includes(t));
  // Note: invisible topics won't appear in `all` because the backend
  // already removed them from /api/v1/topics
});
```

### 7.7 Three.js Rendering — Removal on Visibility Change

When a node is hidden, the backend sends `1001 Going Away` to the WebSocket client. The `MultiWebsocketService.onclose(1001)` handler calls `subject.complete()`. In `WorkspacesComponent`, the subscription's `complete()` callback already handles this:

```typescript
// Existing code in WorkspacesComponent.connectToTopic():
complete: () => {
  this.wsSubscriptions.delete(topic);
  this.frameCountPerTopic.delete(topic);
  this.pointCloud()?.removePointCloud(topic);   // ← removes from Three.js scene
  this.workspaceStore.removeTopic(topic);        // ← removes from selected topics
},
```

`PointCloudComponent.removePointCloud()` already:
1. Calls `this.scene.remove(cloud.pointsObj)` — removes from WebGL render tree
2. Calls `cloud.geometry.dispose()` — frees GPU buffer memory
3. Calls `cloud.material.dispose()` — frees GPU shader program reference
4. Deletes the entry from `this.pointClouds` Map

**No changes required to Three.js rendering code** — the existing `complete()` path handles cleanup correctly and without memory leaks.

### 7.8 Node List Dimming

Invisible nodes in settings lists are visually dimmed to indicate hidden state. Use Tailwind conditional classes:

```html
<!-- In the node list item template -->
<div [class]="node.visible !== false ? '' : 'opacity-50 grayscale'">
  <!-- node content -->
</div>
```

---

## 8. Edge Case Handling

### EC-1: Rapid Toggle (Multiple clicks before API returns)

**Risk**: User clicks hide → show → hide rapidly; race condition in API calls.

**Mitigation**: The smart component sets a `isTogglingVisibility = signal(false)` guard. The eye button is disabled (`[disabled]="isTogglingVisibility()"`) while the API call is in flight. Pattern:

```typescript
protected isTogglingVisibility = signal(false);

protected async toggleNodeVisibility(node: NodeConfig): Promise<void> {
  if (this.isTogglingVisibility()) return;
  this.isTogglingVisibility.set(true);
  // ... optimistic update + API call ...
  this.isTogglingVisibility.set(false);
}
```

### EC-2: Disabled Nodes (enabled=false)

**Scenario**: `set_node_visible()` is called for a node that is `enabled=false` (no runtime instance in `node_manager.nodes`).

**Handling**: `node_manager.set_node_visible()` checks `self.nodes.get(node_id)` first. If the node is not in the running DAG, only the DB update happens — no WebSocket operations are performed. When the node is re-enabled later, `ConfigLoader._register_node_websocket_topic()` reads the `visible` flag from the DB and decides whether to register the topic.

### EC-3: System Topic Protection

**Scenario**: `PUT /nodes/{node_id}/visible` called for a node whose derived topic is in `SYSTEM_TOPICS`.

**Handling**: The service layer derives the topic name and compares against `SYSTEM_TOPICS`. Returns `400 Bad Request` with `"Cannot change visibility of system topic '{topic}'"`.

### EC-4: Node Reload While Invisible

**Scenario**: `POST /nodes/reload` called while some nodes have `visible=false`.

**Handling**: `reload_config()` fully tears down all nodes and topics, then calls `load_config()`. `_register_node_websocket_topic()` reads `visible` from the DB-loaded node dict. Invisible nodes simply don't get their topic registered — the reload naturally preserves the visibility state.

### EC-5: Config Import with `visible` Field

**Scenario**: A DAG config JSON file is imported; some nodes have `visible: false`.

**Handling**: The `upsert()` repository method reads `visible` from the dict. If the imported config includes `visible: false`, it is persisted. If the field is absent (older config format), it defaults to `True` (via `data.get("visible", True)`).

### EC-6: Concurrent Visibility Toggles on Different Nodes

**Scenario**: 10 nodes are hidden simultaneously via parallel API calls.

**Handling**: Each `set_node_visible()` call operates on a different node instance and different WebSocket topic. `ConnectionManager.unregister_topic()` is idempotent. No shared lock is needed — operations are independent.

### EC-7: WebSocket Client Reconnects After 1001

**Scenario**: A buggy client ignores `code=1001` and immediately reconnects to a now-invisible node's topic.

**Handling**: The topic is no longer in `ConnectionManager.active_connections`. The WebSocket upgrade handler (`GET /api/v1/websocket/{topic}`) will accept the connection (it calls `manager.connect()` which creates a new entry). However, the `DataRouter` won't broadcast to it because `node_instance._ws_topic is None`. The client will be connected but receive no data — an acceptable state. The topic will be swept on the next `reload_config()` orphan sweep.

### EC-8: Visibility Change During Active Recording

**Scenario**: Node is hidden while recording is active.

**Handling**: By design, recording bypasses WebSocket entirely (DAG-level interception in `_record_node_data()`). The recording continues uninterrupted. This fulfills requirement AC-19 and AC-22.

---

## 9. Performance Considerations

### 9.1 Visibility Toggle Overhead

A single visibility toggle involves:
- 1 SQLite single-column `UPDATE` (microseconds)
- 1 `ConnectionManager.unregister_topic()` call (O(active_clients) WebSocket closes, typically 0-3)
- 1 topic map dict entry add/remove

Total overhead: **<1ms** per toggle. Well within the 1-second AC-23 requirement.

### 9.2 Batch Visibility Operations (50 nodes)

For 50 concurrent nodes toggled simultaneously:
- 50 parallel API requests, each atomic DB write
- 50 parallel `unregister_topic()` calls — each operates on a separate dict key, no lock contention
- Estimated total: **<100ms** for 50 nodes with typical client counts

### 9.3 DAG Routing Performance

The `_get_node_topic()` method change adds a single `hasattr()` + attribute read per forward cycle. The `_broadcast_to_websocket()` short-circuit on `None` topic exits in the first check. **No meaningful performance impact** on the data path.

### 9.4 Memory Impact

- Invisible nodes hold no `active_connections` entry — they consume zero per-topic memory in `ConnectionManager`.
- `PointCloudComponent.removePointCloud()` properly disposes GPU buffers — no WebGL memory leaks.

---

## 10. DAG Component Dependency Diagram

```
PUT /api/v1/nodes/{node_id}/visible
    │
    ▼ [app/api/v1/nodes/service.py] set_node_visible()
    │
    ├─▶ [app/repositories/node_orm.py] NodeRepository.set_visible()
    │           └── SQLite: UPDATE nodes SET visible=? WHERE id=?
    │
    └─▶ [app/services/nodes/orchestrator.py] NodeManager.set_node_visible()
                │
                ├─[hide]─▶ [lifecycle.py] _unregister_node_websocket_topic_async()
                │               └─▶ [websocket/manager.py] ConnectionManager.unregister_topic()
                │                       ├── ws.close(1001)  ──▶  Client: subject.complete()
                │                       │                              └── scene.remove(pointsObj)
                │                       └── future.cancel()
                │
                └─[show]─▶ [websocket/manager.py] ConnectionManager.register_topic()
                                └── node_instance._ws_topic = topic
                                └── topic appears in GET /api/v1/topics
                                └── Client: WorkspacesComponent.refreshTopics()


[config.py] ConfigLoader._register_node_websocket_topic()
    │  (called during load_config / reload_config)
    ├── if visible=True  → register_topic(topic); instance._ws_topic = topic
    └── if visible=False → instance._ws_topic = None  (no-op, no topic registered)

[routing.py] DataRouter.forward_data()
    │
    ├── _get_node_topic() → returns instance._ws_topic (may be None)
    ├── _broadcast_to_websocket()  ← short-circuits if topic is None
    ├── _record_node_data()        ← NOT gated by visibility (recording continues)
    └── _forward_to_downstream_nodes()  ← NOT gated by visibility (DAG routing continues)
```

---

## 11. Files Changed Summary

### Backend

| File | Change Type | Description |
|---|---|---|
| `app/db/models.py` | Modify | Add `visible` column to `NodeModel`, update `to_dict()` |
| `app/db/migrate.py` | Modify | Add `ALTER TABLE nodes ADD COLUMN visible` migration |
| `app/repositories/node_orm.py` | Modify | Read/write `visible` in `upsert()`, add `set_visible()` |
| `app/api/v1/schemas/nodes.py` | Modify | Add `visible: bool` to `NodeRecord`, `NodeStatusItem` |
| `app/api/v1/nodes/service.py` | Modify | Add `NodeVisibilityToggle` DTO, `set_node_visible()` service function |
| `app/api/v1/nodes/handler.py` | Modify | Register `PUT /nodes/{node_id}/visible` endpoint |
| `app/services/nodes/orchestrator.py` | Modify | Add `set_node_visible()` method |
| `app/services/nodes/managers/config.py` | Modify | Gate topic registration on `visible` flag |
| `app/services/nodes/managers/routing.py` | Modify | Use `_ws_topic` attribute; short-circuit broadcast on `None` |
| `app/services/nodes/managers/lifecycle.py` | Modify | Handle `_ws_topic = None` in teardown |
| `app/services/status_broadcaster.py` | Modify | Include `visible` in node status broadcast payload |

### Frontend

| File | Change Type | Description |
|---|---|---|
| `web/src/app/core/models/node.model.ts` | Modify | Add `visible` to `NodeConfig`, `NodeStatus` |
| `web/src/app/core/services/api/nodes-api.service.ts` | Modify | Add `setNodeVisible()` method |
| `web/src/app/core/services/stores/node-store.service.ts` | Modify | Add `visibleNodes` computed selector |
| `web/src/app/features/settings/components/node-visibility-toggle/` | New | Presentation component with eye icon toggle |
| `web/src/app/features/settings/components/` (node list parent) | Modify | Wire up `NodeVisibilityToggleComponent`, optimistic toggle handler |

### Database

| Action | Description |
|---|---|
| Migration | `ALTER TABLE nodes ADD COLUMN visible INTEGER NOT NULL DEFAULT 1` |
