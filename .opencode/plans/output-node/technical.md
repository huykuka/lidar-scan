# Output Node + Webhook Integration — Technical Design

**Status:** READY FOR PM REVIEW  
**Author:** @architecture  
**Covers:** `output-node` + `output-node-webhook` features (single implementation slice)

---

## 1. Architectural Overview

### 1.1 Position in the DAG

```
[Upstream Node] ──(out → in)──> [OutputNode]
                                     │
                            ┌────────┴────────┐
                            │                 │
                    WebSocket broadcast   Webhook POST
                    (system topic)       (fire-and-forget)
                            │
                    Angular /output/:id
```

The Output Node is a **terminal sink node**. It:
- Accepts exactly **one** input port (`in`).
- Has **no output ports** (does not forward downstream).
- Extracts JSON-serializable metadata from the incoming payload (everything except `points`).
- Broadcasts extracted metadata as a JSON message on the **system WebSocket topic** (`system_status`).
- Optionally fires an HTTP POST to a configured webhook URL (per-instance, async, fire-and-forget).
- `websocket_enabled = False` in `NodeDefinition` — the node does not stream binary LIDR point cloud data and never registers a node-specific WS topic. All comms go through the existing `system_status` system topic.

### 1.2 Why `system_status` Topic

The requirements specify the system topic for metadata broadcast. The existing `system_status` topic is already registered in `SYSTEM_TOPICS` (excluded from `/topics` public listing) and used for node status updates. The Output Node adds a new `type` discriminator field (`"output_node_metadata"`) to co-exist with existing `system_status` message types without a new topic.

> **⚠️ Open Question for PM:** The `system_status` topic currently carries `NodeStatusUpdate` messages. Co-using it for output metadata may create cross-concern coupling. An alternative is a dedicated `output_metadata` system topic. Recommend discussing scope boundary before implementation.

---

## 2. Backend Design

### 2.1 Module Structure

The Output Node lives under the existing `flow_control` module package, following the same sub-package pattern used by `if_condition`.

```
app/modules/flow_control/
├── registry.py          # Existing — import output sub-module registry here
└── output/
    ├── __init__.py
    ├── node.py          # OutputNode class (inherits ModuleNode)
    ├── registry.py      # NodeDefinition + @NodeFactory.register("output_node")
    └── webhook.py       # WebhookSender (async fire-and-forget helper)
```

### 2.2 NodeDefinition (registry.py)

```python
node_schema_registry.register(NodeDefinition(
    type="output_node",
    display_name="Output",
    category="flow_control",
    description="Displays metadata from upstream node on a dedicated page",
    icon="dashboard",
    websocket_enabled=False,   # No LIDR binary streaming; metadata goes via system topic
    properties=[
        PropertySchema(
            name="webhook_enabled",
            label="Enable Webhook",
            type="boolean",
            default=False,
        ),
        PropertySchema(
            name="webhook_url",
            label="Webhook POST URL",
            type="string",
            default="",
            help_text="HTTPS endpoint to receive metadata payloads",
            depends_on={"webhook_enabled": [True]},
        ),
        PropertySchema(
            name="webhook_auth_type",
            label="Authentication Type",
            type="select",
            default="none",
            options=[
                {"label": "None", "value": "none"},
                {"label": "Bearer Token", "value": "bearer"},
                {"label": "Basic Auth", "value": "basic"},
                {"label": "API Key", "value": "api_key"},
            ],
            depends_on={"webhook_enabled": [True]},
        ),
        PropertySchema(
            name="webhook_auth_token",
            label="Bearer Token",
            type="string",
            default="",
            help_text="Bearer token value (stored plaintext in MVP)",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["bearer"]},
        ),
        PropertySchema(
            name="webhook_auth_username",
            label="Username",
            type="string",
            default="",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["basic"]},
        ),
        PropertySchema(
            name="webhook_auth_password",
            label="Password",
            type="string",
            default="",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["basic"]},
        ),
        PropertySchema(
            name="webhook_auth_key_name",
            label="Header Name",
            type="string",
            default="X-API-Key",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["api_key"]},
        ),
        PropertySchema(
            name="webhook_auth_key_value",
            label="Key Value",
            type="string",
            default="",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["api_key"]},
        ),
        PropertySchema(
            name="webhook_custom_headers",
            label="Custom Headers (JSON)",
            type="string",
            default="{}",
            help_text='JSON object of extra headers, e.g. {"X-Source": "lidar"}',
            depends_on={"webhook_enabled": [True]},
        ),
    ],
    inputs=[PortSchema(id="in", label="Input", multiple=False)],
    outputs=[],   # Terminal node — no output ports
))

@NodeFactory.register("output_node")
def build_output_node(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> "OutputNode":
    from app.modules.output.node import OutputNode
    config = node.get("config", {})
    return OutputNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", node["id"]),
        config=config,
    )
```

### 2.3 OutputNode (node.py)

```python
class OutputNode(ModuleNode):
    id: str
    name: str
    manager: Any

    def __init__(self, manager, node_id: str, name: str, config: Dict[str, Any]):
        self.manager = manager
        self.id = node_id
        self.name = name
        self._config = config
        self._webhook = WebhookSender.from_config(config)
        # Runtime stats
        self.last_metadata_at: Optional[float] = None
        self.metadata_count: int = 0
        self.error_count: int = 0

    async def on_input(self, payload: Dict[str, Any]) -> None:
        # 1. Extract metadata: strip numpy/binary fields, keep JSON-serializable
        metadata = _extract_metadata(payload)

        # 2. Build system topic message
        message = {
            "type": "output_node_metadata",
            "node_id": self.id,
            "timestamp": payload.get("timestamp") or time.time(),
            "metadata": metadata,
        }

        # 3. Broadcast via system topic (non-blocking, fire-and-forget)
        from app.services.websocket.manager import manager as ws_manager
        asyncio.create_task(ws_manager.broadcast("system_status", message))

        # 4. Webhook delivery (fire-and-forget)
        if self._webhook:
            asyncio.create_task(self._webhook.send(message))

        self.last_metadata_at = time.time()
        self.metadata_count += 1

    def emit_status(self) -> NodeStatusUpdate: ...
```

**`_extract_metadata` logic:**
- Iterates `payload.items()`.
- Excludes keys: `"points"` (numpy array — not serializable), `"node_id"`, `"processed_by"`.
- For each remaining value: if not JSON-serializable (e.g., numpy scalar), cast to Python native type via `item()` or `str()`.
- Returns a `Dict[str, Any]` safe for `json.dumps`.

### 2.4 WebhookSender (webhook.py)

```python
class WebhookSender:
    """Async fire-and-forget HTTP POST to a configured endpoint."""

    def __init__(self, url: str, headers: Dict[str, str], timeout: float = 10.0): ...

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> Optional["WebhookSender"]:
        """Returns None if webhook_enabled is False or url is empty."""
        if not config.get("webhook_enabled"):
            return None
        url = config.get("webhook_url", "").strip()
        if not url:
            return None
        headers = _build_auth_headers(config)
        custom = _parse_custom_headers(config.get("webhook_custom_headers", "{}"))
        headers.update(custom)
        headers["Content-Type"] = "application/json"
        return cls(url=url, headers=headers)

    async def send(self, payload: Dict[str, Any]) -> None:
        """POST payload as JSON. Logs errors; never raises."""
        try:
            body = json.dumps(payload)
            await asyncio.to_thread(self._sync_post, body)
        except Exception as e:
            logger.error(f"Webhook POST failed [{self.url}]: {e}")

    def _sync_post(self, body: str) -> None:
        import httpx
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, content=body, headers=self._headers)
            if resp.status_code >= 400:
                logger.error(f"Webhook [{self._url}] returned {resp.status_code}")
            else:
                logger.debug(f"Webhook [{self._url}] returned {resp.status_code}")
```

**HTTP Client choice:** `httpx` (sync client wrapped in `asyncio.to_thread`). `httpx` is already common in FastAPI ecosystems; if not present, add to `requirements.txt`. Avoids importing `requests` as a second HTTP library.

**Auth header construction:**

| auth_type | Header added |
|---|---|
| `none` | (none) |
| `bearer` | `Authorization: Bearer <token>` |
| `basic` | `Authorization: Basic <base64(user:pass)>` |
| `api_key` | `<key_name>: <key_value>` |

### 2.5 DAG Registration & Discovery

The Output Node lives inside `app/modules/flow_control/output/`. The existing `discover_modules()` mechanism in `app/modules/__init__.py` iterates top-level sub-packages and imports their `registry.py`. Since `flow_control` is already discovered, only the `flow_control/registry.py` needs to be updated to import the new `output` sub-module registry:

```python
# app/modules/flow_control/registry.py  (updated)
from .if_condition import registry as if_condition_registry
from .output import registry as output_registry  # NEW
```

No changes to `discover_modules()` or any other orchestrator code.

### 2.6 Webhook Config Persistence

Webhook settings are **stored inside the node's `config` JSON blob** (same `NodeModel.config_json` field used for all node config). This means:
- No new DB table or migration required.
- Webhook config survives DAG save/reload.
- Updated via the existing `PUT /api/v1/dag/config` atomic save flow (preferred) — the entire DAG config including Output Node config is saved at once.
- Also updatable via a dedicated `PATCH /api/v1/nodes/{node_id}/webhook` endpoint (see Section 4 — API Spec) for live in-place updates without triggering a full DAG reload.

### 2.7 Input Validation (Backend)

A Pydantic model validates webhook config on the `PATCH` endpoint:

```python
class WebhookConfig(BaseModel):
    webhook_enabled: bool = False
    webhook_url: Optional[str] = None
    webhook_auth_type: Literal["none", "bearer", "basic", "api_key"] = "none"
    webhook_auth_token: Optional[str] = None
    webhook_auth_username: Optional[str] = None
    webhook_auth_password: Optional[str] = None
    webhook_auth_key_name: Optional[str] = "X-API-Key"
    webhook_auth_key_value: Optional[str] = None
    webhook_custom_headers: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_url_when_enabled(self) -> "WebhookConfig":
        if self.webhook_enabled:
            if not self.webhook_url or not self.webhook_url.startswith(("http://", "https://")):
                raise ValueError("webhook_url must be a valid HTTP/HTTPS URL when webhook is enabled")
        return self
```

### 2.8 ConfigLoader — Input Port Constraint

The `multiple=False` flag on the `in` PortSchema is a UI-side constraint (prevents drawing multiple edges to the input in the canvas). There is no runtime enforcement in the DAG engine today. The Output Node's `on_input` processes each call independently; receiving two upstream connections would result in interleaved broadcasts (two payloads per cycle, one per source). This is acceptable behavior in MVP — the single-input constraint is enforced by the canvas, not the engine.

> **⚠️ BA Clarification Needed:** Requirements state exactly one input. If hard runtime enforcement is required (rejecting a second edge in `PUT /dag/config`), this adds scope to the DAG config save service. Recommend confirming with BA/PM.

### 2.9 Node Lifecycle on Reload

When `reload_config` is called (e.g., after DAG save):
- The existing `LifecycleManager` tears down and rebuilds all nodes.
- The Output Node's `_webhook` is rebuilt from config on `__init__` — no extra cleanup needed.
- Because `websocket_enabled=False`, `_ws_topic` will be `None`; no WebSocket topic is registered or unregistered for this node.
- The system `system_status` topic remains registered throughout (it is a permanent system topic).

---

## 3. Frontend Design

### 3.1 New Route

```
/output/:nodeId
```

Registered in `app.routes.ts` as a lazy-loaded standalone component:

```typescript
{
  path: 'output/:nodeId',
  loadComponent: () =>
    import('./features/output-node/output-node.component')
      .then(m => m.OutputNodeComponent),
}
```

### 3.2 Feature Structure

```
web/src/app/features/output-node/
├── output-node.component.ts       # Smart component (route container)
├── output-node.component.html
├── output-node.component.css
├── components/
│   ├── metadata-table/
│   │   ├── metadata-table.component.ts    # Dumb/presentational
│   │   └── metadata-table.component.html
│   └── webhook-config/
│       ├── webhook-config.component.ts    # Dumb form (inputs/outputs via signals)
│       └── webhook-config.component.html
└── services/
    └── output-node-api.service.ts         # REST API calls for this feature
```

### 3.3 OutputNodeComponent (Smart)

Responsibilities:
- Reads `:nodeId` from `ActivatedRoute`.
- Calls `OutputNodeApiService.getNode(nodeId)` on init to validate node exists and retrieve current webhook config.
- Subscribes to `system_status` WebSocket via existing `MultiWebsocketService`.
- Filters messages: `msg.type === 'output_node_metadata' && msg.node_id === nodeId`.
- Holds reactive signals:
  - `metadata = signal<Record<string, any> | null>(null)`
  - `connectionStatus = signal<'connecting' | 'connected' | 'disconnected'>('connecting')`
  - `nodeNotFound = signal<boolean>(false)`

### 3.4 WebSocket Subscription Pattern

Uses existing `MultiWebsocketService`. The system topic URL:
```
ws://<host>/api/v1/ws/system_status
```

```typescript
// In OutputNodeComponent.ngOnInit()
this.wsSubscription = this.wsService
  .connect('system_status', `${environment.wsUrl}/ws/system_status`)
  .pipe(
    map(raw => JSON.parse(raw) as SystemMessage),
    filter(msg =>
      msg.type === 'output_node_metadata' &&
      msg.node_id === this.nodeId
    ),
  )
  .subscribe({
    next: msg => this.metadata.set(msg.metadata),
    error: () => this.connectionStatus.set('disconnected'),
    complete: () => this.connectionStatus.set('disconnected'),
  });
```

On component destroy: call `wsService.disconnect('system_status')` only if this component opened the connection and no other consumer is active. Since `MultiWebsocketService` deduplicates by topic, share the connection — call `disconnect` only on component destroy if `wsService.getActiveTopics()` shows it still connected.

> **Note:** Multiple components may subscribe to `system_status`. The shared `Subject` in `MultiWebsocketService` handles fan-out. Disconnect logic must be defensive.

### 3.5 MetadataTableComponent (Dumb)

Input: `metadata = input<Record<string, any> | null>()`

Renders a Tailwind-styled table:

| Field | Value | Type |
|---|---|---|
| `point_count` | `45000` | `number` |
| `intensity_avg` | `0.72` | `number` |
| `sensor_name` | `"lidar_front"` | `string` |

- `@for` over `Object.entries(metadata())`.
- Value rendering: primitives as-is; objects/arrays as `JSON.stringify(..., null, 2)` in a `<pre>` tag.
- Type column: `typeof value` or `"array"` / `"null"` guards.
- Empty state: `@if (!metadata())` → "Waiting for data..." with spinner.

### 3.6 Webhook Configuration UI

Webhook settings are surfaced in the existing DAG canvas **node configuration drawer** (Settings page), not on the `/output/:nodeId` page. The `OutputNodeComponent` page is read-only visualization only.

In the Settings feature's node-config drawer, a `WebhookConfigComponent` is rendered when `node.type === 'output_node'`:

```
[Enable Webhook] ← syn-switch
  [Webhook URL input]      ← syn-input, type="url"
  [Auth Type dropdown]     ← syn-select
    ↳ Bearer: [Token input, type="password"]
    ↳ Basic:  [Username] [Password, type="password"]
    ↳ API Key: [Header Name] [Key Value, type="password"]
  [Custom Headers]         ← repeating key-value rows
    [Header Key] [Header Value] [Remove ×]
    [+ Add Header]
  [Save] [Cancel]
```

State managed via Angular Signals inside `WebhookConfigComponent`. The component emits a `webhookSaved` output signal on save, which triggers `OutputNodeApiService.updateWebhookConfig(nodeId, config)`.

### 3.7 Navigation from DAG Canvas

The canvas node click handler (in `features/settings/`) must be extended to detect `node.type === 'output_node'` and call `router.navigate(['/output', node.id])`. This is a small change to the existing settings canvas click logic.

> **⚠️ BA Clarification Needed:** Does clicking the Output Node in the canvas open the metadata page, the config drawer, or both (drawer + link to page)? Recommend consistent UX — open config drawer first with a "View Live Data →" button linking to `/output/:id`.

### 3.8 API Service (output-node-api.service.ts)

Placed in `web/src/app/features/output-node/services/`:

```typescript
@Injectable({ providedIn: 'root' })
export class OutputNodeApiService {
  private http = inject(HttpClient);

  getNode(nodeId: string): Promise<NodeConfig> { ... }

  getWebhookConfig(nodeId: string): Promise<WebhookConfig> { ... }

  updateWebhookConfig(nodeId: string, config: WebhookConfig): Promise<void> { ... }
}
```

The `getNode` call reuses the existing `/api/v1/nodes/:id` endpoint. The webhook CRUD uses `PATCH /api/v1/nodes/:nodeId/webhook`.

### 3.9 Models

New TypeScript interfaces in `web/src/app/core/models/`:

```typescript
// output-node.model.ts
export interface OutputNodeMetadataMessage {
  type: 'output_node_metadata';
  node_id: string;
  timestamp: number;
  metadata: Record<string, any>;
}

export interface WebhookConfig {
  webhook_enabled: boolean;
  webhook_url: string;
  webhook_auth_type: 'none' | 'bearer' | 'basic' | 'api_key';
  webhook_auth_token?: string;
  webhook_auth_username?: string;
  webhook_auth_password?: string;
  webhook_auth_key_name?: string;
  webhook_auth_key_value?: string;
  webhook_custom_headers?: Record<string, string>;
}
```

---

## 4. Data / Model Flow

```
Upstream Node
    │  payload: { points: ndarray, timestamp: float, node_id: str, ...metadata_fields }
    ▼
OutputNode.on_input(payload)
    │
    ├─ _extract_metadata(payload)
    │     removes: 'points', 'node_id', 'processed_by'
    │     coerces: numpy scalars → Python native types
    │     returns: { "point_count": 45000, "timestamp": 1234.56, ... }
    │
    ├─ asyncio.create_task(ws_manager.broadcast("system_status", {
    │       "type": "output_node_metadata",
    │       "node_id": self.id,
    │       "timestamp": ...,
    │       "metadata": { ... }
    │   }))
    │
    └─ asyncio.create_task(webhook_sender.send({ same payload }))  [if enabled]


WebSocket
    │  JSON text frame → system_status topic
    ▼
MultiWebsocketService (Angular)
    │  Subject.next(raw)
    ▼
OutputNodeComponent subscription
    │  filter by type + node_id
    ▼
metadata signal.set(msg.metadata)
    │
    ▼
MetadataTableComponent re-renders
```

---

## 5. Error Handling Strategy

| Layer | Scenario | Handling |
|---|---|---|
| `OutputNode.on_input` | `_extract_metadata` raises | Catch, log ERROR, broadcast empty `metadata: {}` |
| `OutputNode.on_input` | WS broadcast raises | `asyncio.create_task` swallows; log in `broadcast()` |
| `WebhookSender.send` | `httpx` timeout | Caught in `send()`, logged ERROR, no re-raise |
| `WebhookSender.send` | Non-2xx HTTP response | Logged ERROR, no retry |
| `WebhookSender.send` | Invalid URL at runtime | Caught, logged ERROR |
| `WebhookConfig` Pydantic | Invalid URL on save | 400 HTTPException from route handler |
| Angular `OutputNodeComponent` | WS disconnection (non-1001) | `connectionStatus.set('disconnected')`, show reconnect status |
| Angular `OutputNodeComponent` | Node not found (404 from API) | `nodeNotFound.set(true)`, show error page with back link |
| Angular `WebhookConfigComponent` | Invalid URL input | Inline validation error, Save button disabled |

---

## 6. Uncertainties & Required BA/PM Input

| # | Question | Impact | Priority |
|---|---|---|---|
| U1 | Should `output_node_metadata` use the existing `system_status` topic or a new dedicated `output_metadata` system topic? | Affects `manager.py`, frontend subscription, possible interference with existing status messages | **High** |
| U2 | Hard runtime enforcement of single-input constraint (reject second edge in PUT /dag/config)? | Adds scope to DAG save service validation | **Medium** |
| U3 | Should clicking an Output Node in the canvas open the config drawer, the `/output/:id` page, or a drawer with a link? | UX consistency with existing nodes | **Medium** |
| U4 | Should the `/output/:id` page be accessible from the main nav sidebar or only from the canvas click? | Nav structure, sidebar component changes | **Low** |
| U5 | Is `httpx` already in `requirements.txt`, or must it be added? If not, is `requests` acceptable? | Dependency management | **Low** |
| U6 | Should webhook credentials eventually be encrypted (e.g., Fernet)? If yes, define migration path now. | Security architecture | **Low (post-MVP)** |

---

## 7. Impact on Existing Code

The following existing symbols are **touched** by this feature:

| File | Change | Risk |
|---|---|---|
| `app/modules/flow_control/registry.py` | Add import of `output` sub-module registry | Low — additive only |
| `app/modules/flow_control/output/` (new) | New sub-package with OutputNode, WebhookSender, registry | None — additive |
| `app/db/migrate.py` | No schema change required (webhook config is in `config_json` blob) | None |
| `web/src/app/app.routes.ts` | Add `/output/:nodeId` lazy route | Low |
| `web/src/app/layout/main-layout/` | Possibly add "Output" to sidebar nav | Low |
| `web/src/app/features/settings/` | Canvas click handler to navigate on `output_node` type | Low |
| `app/api/v1/` | New `output/` router module | Low — additive |
| `app/api/v1/__init__.py` or router aggregator | Register new output router | Low |

No changes to `ModuleNode`, `DataRouter`, `ConnectionManager`, `NodeFactory`, or any existing node modules.

---

## 8. Dependencies

- **Backend:** `httpx` (add to `requirements.txt` if not present)
- **Frontend:** No new npm packages required
- **DB:** No migration required
- **Protocol:** No changes to LIDR binary protocol; uses existing JSON broadcast path in `ws_manager.broadcast()`
