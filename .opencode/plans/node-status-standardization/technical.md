# Technical Architecture: Node Status Standardization

**Status**: Ready for implementation  
**Assigned to**: @be-dev, @fe-dev  
**Prerequisite**: `api-spec.md` — use as the implementation contract

---

## 1. Overview

Replace the existing `get_status()` polling pattern with a standardized, event-driven
`emit_status()` mechanism. Design constraints:

- Nodes do **not** call WebSocket directly (decoupled via aggregator).
- Status emission must **not** block the async event loop.
- Reuse the existing `system_status` WebSocket topic — no new topics.
- Breaking change: single-phase. `get_status()` is deleted, not deprecated.

---

## 2. Backend Architecture

### 2.1 Status Schema

**File**: `app/services/nodes/status_schema.py` *(new)*

Pure Python dataclasses — no Pydantic dependency to keep imports fast on hot paths.

```python
from dataclasses import dataclass, field
from typing import Any, Literal, Optional
import time

OperationalState = Literal["INITIALIZE", "RUNNING", "STOPPED", "ERROR"]

@dataclass
class ApplicationState:
    label: str              # e.g. "connection_status", "calibrating"
    value: Any              # JSON-serialisable
    color: Optional[str] = None  # "green" | "blue" | "orange" | "red" | "gray"

@dataclass
class NodeStatusUpdate:
    node_id: str
    operational_state: OperationalState
    timestamp: float = field(default_factory=time.time)
    application_state: Optional[ApplicationState] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {
            "node_id": self.node_id,
            "operational_state": self.operational_state,
            "timestamp": self.timestamp,
        }
        if self.application_state:
            d["application_state"] = {
                "label": self.application_state.label,
                "value": self.application_state.value,
                "color": self.application_state.color,
            }
        if self.error_message is not None:
            d["error_message"] = self.error_message
        return d
```

---

### 2.2 ModuleNode Base Class

**File**: `app/services/nodes/base_module.py` *(modified)*

```python
from app.services.nodes.status_schema import NodeStatusUpdate

class ModuleNode(ABC):
    # Injected by NodeManager after construction; nodes push via _notify_status()
    _status_callback: Optional[Callable[[NodeStatusUpdate], None]] = None

    @abstractmethod
    def emit_status(self) -> NodeStatusUpdate:
        """
        Return the current structured status of this node.
        Must not perform I/O. Must be fast (<0.5 ms).
        """
        ...

    def _notify_status(self) -> None:
        """
        Call this at every meaningful state transition.
        Thread-safe: safe to call from Open3D threadpool workers.
        """
        if self._status_callback:
            self._status_callback(self.emit_status())
```

`get_status()` is **removed** from the abstract interface and from all concrete
implementations in the same PR (no shim, no deprecation — per requirements).

---

### 2.3 StatusAggregator Service

**File**: `app/services/status_aggregator.py` *(new, replaces `status_broadcaster.py`)*

```python
import asyncio, time
from typing import Dict, Optional
from app.services.nodes.status_schema import NodeStatusUpdate
from app.services.websocket.manager import manager

class StatusAggregator:
    _RATE_LIMIT_SEC = 0.1   # max 10 updates/node/sec

    def __init__(self):
        self._queue: asyncio.Queue[NodeStatusUpdate] = asyncio.Queue()
        self._snapshot: Dict[str, NodeStatusUpdate] = {}
        self._last_sent: Dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def push(self, update: NodeStatusUpdate) -> None:
        """Thread-safe: nodes call this via _notify_status()."""
        self._queue.put_nowait(update)

    def start(self) -> None:
        manager.register_topic("system_status")
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self._snapshot.clear()
        self._last_sent.clear()

    def get_snapshot(self) -> dict:
        """REST endpoint uses this for a synchronous status dump."""
        return {"nodes": [u.to_dict() for u in self._snapshot.values()]}

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while True:
            update = await self._queue.get()
            try:
                now = time.monotonic()
                if now - self._last_sent.get(update.node_id, 0.0) < self._RATE_LIMIT_SEC:
                    continue   # drop — rate limited
                self._snapshot[update.node_id] = update
                self._last_sent[update.node_id] = now
                payload = {"nodes": [u.to_dict() for u in self._snapshot.values()]}
                asyncio.create_task(manager.broadcast("system_status", payload))
            finally:
                self._queue.task_done()

aggregator = StatusAggregator()
```

**Key properties**:

| Property | Value |
|---|---|
| Push mechanism | `asyncio.Queue.put_nowait()` — O(1), no awaiting |
| Event loop blocking | None — queue consumer runs in `create_task` |
| Rate limit | 100 ms per `node_id` (max 10 updates/node/sec) |
| Broadcast | Fire-and-forget `create_task` per the existing WebSocket pattern |
| Late-join snapshot | `get_snapshot()` returns full current state |

---

### 2.4 NodeManager Integration

**File**: `app/services/nodes/instance.py` (or wherever nodes are instantiated)

After creating each node, inject the callback before starting it:

```python
from app.services.status_aggregator import aggregator
node._status_callback = aggregator.push
```

Aggregator lifecycle is tied to the DAG start/stop:

```python
# DAG start
aggregator.start()
# ... start nodes ...

# DAG stop
# ... stop nodes ...
aggregator.stop()
```

---

### 2.5 Node Implementation Requirements

All five nodes below must:
1. Remove `get_status()`.
2. Add `emit_status() -> NodeStatusUpdate`.
3. Call `self._notify_status()` at **each** of the listed trigger points.

#### LidarSensor (`app/modules/lidar/sensor.py`)

| Trigger | `operational_state` | `application_state` |
|---|---|---|
| `start()` called, process spawned | `INITIALIZE` | `{label:"connection_status", value:"starting", color:"orange"}` |
| First UDP frame received | `RUNNING` | `{label:"connection_status", value:"connected", color:"green"}` |
| Connection exception in worker loop | `ERROR` + `error_message` | `{label:"connection_status", value:"disconnected", color:"red"}` |
| `stop()` called | `STOPPED` | `{label:"connection_status", value:"disconnected", color:"red"}` |

`emit_status()` must read `manager.node_runtime_status[self.id]` to derive current
`connection_status` — this dict is already maintained by the worker.

#### CalibrationNode (`app/modules/calibration/calibration_node.py`)

| Trigger | `operational_state` | `application_state` |
|---|---|---|
| `enable()` | `RUNNING` | `{label:"calibrating", value:false, color:"gray"}` |
| Calibration computation starts | `RUNNING` | `{label:"calibrating", value:true, color:"blue"}` |
| Calibration computation finishes | `RUNNING` | `{label:"calibrating", value:false, color:"gray"}` |
| `disable()` | `STOPPED` | `{label:"calibrating", value:false, color:"gray"}` |

#### IfConditionNode (`app/modules/flow_control/if_condition/node.py`)

| Trigger | `operational_state` | `application_state` |
|---|---|---|
| Node initialised (`__init__`) | `RUNNING` | `{label:"condition", value:null, color:"gray"}` |
| Condition evaluates → true | `RUNNING` | `{label:"condition", value:"true", color:"green"}` |
| Condition evaluates → false | `RUNNING` | `{label:"condition", value:"false", color:"red"}` |
| Evaluation exception | `ERROR` + `error_message` | *(same as last)* |

#### OperationNode (`app/modules/pipeline/operation_node.py`)

| Trigger | `operational_state` | `application_state` |
|---|---|---|
| `enable()` | `RUNNING` | `{label:"processing", value:true, color:"blue"}` |
| `disable()` | `STOPPED` | `{label:"processing", value:false, color:"gray"}` |
| Exception in `on_input` | `ERROR` + `error_message` | `{label:"processing", value:false, color:"gray"}` |

#### FusionService (`app/modules/fusion/service.py`)

| Trigger | `operational_state` | `application_state` |
|---|---|---|
| `enable()` | `RUNNING` | `{label:"fusing", value:len(sensor_ids), color:"blue"}` |
| `disable()` | `STOPPED` | `{label:"fusing", value:0, color:"gray"}` |
| Exception in `on_input` | `ERROR` + `error_message` | `{label:"fusing", value:0, color:"gray"}` |

---

### 2.6 REST API Migration

**`app/api/v1/nodes/service.py`** and **`app/api/v1/system/service.py`**: remove all
`get_status()` calls. Replace the status-gathering block with:

```python
from app.services.status_aggregator import aggregator
return aggregator.get_snapshot()
```

---

### 2.7 File Manifest

**New files**

| File | Purpose |
|---|---|
| `app/services/nodes/status_schema.py` | `NodeStatusUpdate`, `ApplicationState` dataclasses |
| `app/services/status_aggregator.py` | Aggregator + rate limiter; module-level `aggregator` singleton |

**Modified files**

| File | Key change |
|---|---|
| `app/services/nodes/base_module.py` | Remove `get_status()`, add `emit_status()` + `_notify_status()` |
| `app/services/nodes/instance.py` | Inject `_status_callback` + start/stop aggregator |
| `app/modules/lidar/sensor.py` | Replace `get_status()` → `emit_status()` + `_notify_status()` calls |
| `app/modules/calibration/calibration_node.py` | Same |
| `app/modules/flow_control/if_condition/node.py` | Same |
| `app/modules/pipeline/operation_node.py` | Same |
| `app/modules/fusion/service.py` | Same |
| `app/api/v1/nodes/service.py` | Use `aggregator.get_snapshot()` |
| `app/api/v1/system/service.py` | Use `aggregator.get_snapshot()` |

**Deleted files**

| File | Reason |
|---|---|
| `app/services/status_broadcaster.py` | Replaced by `status_aggregator.py` |

---

## 3. Frontend Architecture

### 3.1 New TypeScript Models

**File**: `web/src/app/core/models/node-status.model.ts` *(new)*

Full schema in `api-spec.md`. Key interfaces:

```typescript
export type OperationalState = 'INITIALIZE' | 'RUNNING' | 'STOPPED' | 'ERROR';

export interface ApplicationState {
  label: string;
  value: any;
  color?: 'green' | 'blue' | 'orange' | 'red' | 'gray';
}

export interface NodeStatusUpdate {
  node_id: string;
  operational_state: OperationalState;
  application_state?: ApplicationState;
  error_message?: string;
  timestamp: number;
}

export interface NodesStatusResponse {
  nodes: NodeStatusUpdate[];
}
```

Old `NodeStatus`, `LidarNodeStatus`, `FusionNodeStatus` in `node.model.ts` are removed
and replaced with the above — same breaking-change boundary.

---

### 3.2 StatusWebSocketService

**File**: `web/src/app/core/services/status-websocket.service.ts` *(modified)*

- Signal type: `signal<NodesStatusResponse | null>(null)` — shape is now `NodeStatusUpdate[]`.
- Add **50 ms debounce** to prevent excess Angular change-detection cycles:

```typescript
private _pending: NodesStatusResponse | null = null;
private _debounceId: ReturnType<typeof setTimeout> | null = null;

onmessage = (ev) => {
  this._pending = JSON.parse(ev.data);
  if (!this._debounceId) {
    this._debounceId = setTimeout(() => {
      if (this._pending) this.status.set(this._pending);
      this._pending = null;
      this._debounceId = null;
    }, 50);
  }
};
```

---

### 3.3 NodeStoreService — Status Map

**File**: `web/src/app/core/services/stores/node-store.service.ts` *(modified)*

```typescript
nodeStatusMap = computed<Map<string, NodeStatusUpdate>>(() => {
  const statuses = this.statusWebSocket.status()?.nodes ?? [];
  return new Map(statuses.map(s => [s.node_id, s]));
});
```

Provides O(1) status lookup by `node_id` for the flow canvas.

---

### 3.4 FlowCanvasNodeComponent

**File**: `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts` *(modified)*

Input signal type changes to `NodeStatusUpdate | null`.

**New computed signals** (replace all old status helpers):

```typescript
protected readonly badgeColorMap: Record<string, string> = {
  green: '#16a34a', blue: '#2563eb', orange: '#d97706',
  red: '#dc2626',  gray: '#6b7280',
};

protected operationalIcon = computed(() => {
  switch (this.status()?.operational_state) {
    case 'INITIALIZE': return { icon: 'hourglass_empty', css: 'text-syn-color-warning-600 animate-pulse' };
    case 'RUNNING':    return { icon: 'play_circle',     css: 'text-syn-color-success-600' };
    case 'STOPPED':    return { icon: 'pause_circle',    css: 'text-syn-color-neutral-400' };
    case 'ERROR':      return { icon: 'error',           css: 'text-syn-color-danger-600' };
    default:           return { icon: 'radio_button_unchecked', css: 'text-syn-color-neutral-300' };
  }
});

protected appBadge = computed(() => {
  const a = this.status()?.application_state;
  if (!a) return null;
  return { text: `${a.label}: ${a.value}`, color: this.badgeColorMap[a.color ?? 'gray'] };
});

protected errorText = computed(() =>
  this.status()?.operational_state === 'ERROR'
    ? (this.status()?.error_message ?? null)
    : null
);
```

**Signals removed**: `statusBadge()`, `getFrameAge()`, `isFrameStale()`,
`getStatusColorClass()`, `ifStateIcon()`, `ifStatus`.

---

### 3.5 HTML Template Changes

**File**: `flow-canvas-node.component.html` *(modified)*

Three isolated changes to the existing template:

**1 — Header: replace the status dot with the operational icon**

```html
<!-- REMOVE this block: -->
<div class="w-2.5 h-2.5 rounded-full ..." ...></div>

<!-- ADD before the node name span: -->
<syn-icon
  [name]="operationalIcon().icon"
  [class]="operationalIcon().css + ' text-[14px] shrink-0'"
  [title]="status()?.operational_state ?? 'Unknown'"
/>
```

**2 — Body: passive error display** (insert before the Node Actions Bar `<div>`)

```html
@if (errorText()) {
  <div class="px-2 py-1 bg-syn-color-danger-50 border-t border-syn-color-danger-100
              text-[10px] text-syn-color-danger-700 leading-tight">
    <div class="flex items-start gap-1">
      <syn-icon name="error" class="shrink-0 text-xs mt-0.5" />
      <span class="break-words line-clamp-2">{{ errorText() }}</span>
    </div>
  </div>
}
```

**3 — Bottom-right badge: application state (Node-RED style)** (sibling of the outer `<div>`)

```html
@if (appBadge()) {
  <div class="absolute -bottom-3 right-1 flex items-center gap-1
              bg-white border rounded-full px-1.5 py-0.5 shadow-sm text-[9px] font-mono z-10">
    <span class="truncate max-w-[80px]">{{ appBadge()!.text }}</span>
    <div class="w-2 h-2 rounded-full shrink-0"
         [style.background-color]="appBadge()!.color"></div>
  </div>
}
```

The outer host `<div>` already uses `relative` via the existing class list — the badge
absolute-positions off it cleanly.

---

### 3.6 Frontend File Manifest

**New files**

| File | Purpose |
|---|---|
| `web/src/app/core/models/node-status.model.ts` | `NodeStatusUpdate`, `ApplicationState`, `NodesStatusResponse` |

**Modified files**

| File | Key change |
|---|---|
| `web/src/app/core/models/node.model.ts` | Remove old `NodeStatus`, `LidarNodeStatus`, `FusionNodeStatus` |
| `web/src/app/core/services/status-websocket.service.ts` | New schema type + 50 ms debounce |
| `web/src/app/core/services/stores/node-store.service.ts` | Add `nodeStatusMap` computed |
| `flow-canvas.component.ts` | Use `nodeStatusMap().get(id)` for status lookup |
| `flow-canvas-node.component.ts` | New signals, remove old helpers |
| `flow-canvas-node.component.html` | Operational icon, error body, app-state badge |

---

## 4. End-to-End Status Data Flow

```
[Node state change]
  ↓  self._notify_status()          [synchronous; O(1)]
  ↓  aggregator.push(update)        [put_nowait on asyncio.Queue]
  ↓  StatusAggregator._run()        [async consumer loop]
  ↓  rate-limit check (100 ms/node)
  ↓  update _snapshot dict
  ↓  create_task(manager.broadcast) [fire-and-forget]
  ↓  WS send_json to all clients
  ↓  StatusWebSocketService.onmessage
  ↓  50 ms debounce
  ↓  status signal set
  ↓  nodeStatusMap recomputes (computed signal)
  ↓  FlowCanvasNodeComponent re-renders
       operationalIcon / appBadge / errorText
```

---

## 5. Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Rate limiting strategy | Per-node 100 ms debounce | Prevents individual fast nodes from saturating WS; simple |
| Aggregation mechanism | `asyncio.Queue` consumer | Native, zero-dep, correct back-pressure; thread-safe `put_nowait` |
| Icon library | Synergy UI `syn-icon` (Material Icons) | Already used; `hourglass_empty`, `play_circle`, `pause_circle`, `error` all available |
| Badge colors | Semantic strings on wire, CSS hex map in frontend | Backend stays framework-agnostic; frontend centralises styling |
| Backward compat | None — full breaking change in one PR | Required by spec; avoids dual-format complexity |
| Frontend debounce | 50 ms timeout (no RxJS) | Signal-native, avoids extra RxJS imports; matches RxJS debounceTime(50) behaviour |
