# Frontend Tasks: Environment Filtering Node

References:
- Requirements: `.opencode/plans/environment-filtering/requirements.md`
- API Spec: `.opencode/plans/environment-filtering/api-spec.md`
- Frontend Rules: `.opencode/rules/frontend.md`

---

## Scope

The environment filtering node exposes **no new frontend UI panels** (per `requirements.md § Out of Scope`). All parameter tuning is via DAG JSON config. Frontend work is limited to ensuring the new node type renders correctly in the flow canvas palette and status is displayed.

---

## Phase 1 — Node Type Registration (Auto)

- [ ] Verify the Angular flow canvas palette auto-discovers `"environment_filtering"` from `GET /api/v1/nodes/schema` — no code change needed if canvas dynamically renders all registered node definitions
- [ ] Confirm `icon: "layers_clear"` resolves correctly in Synergy icon set
- [ ] Smoke-test: drag `Environment Filtering` node onto canvas, connect to upstream node, verify no JS errors

## Phase 2 — Status Display

- [ ] Verify `planes_filtered` badge renders correctly on the node card (numeric value)
- [ ] Verify `color="orange"` warning state renders visually distinct from `color="blue"` active state
- [ ] Verify `color="red"` ERROR state shows error tooltip or message

## Phase 3 — Config Panel (Existing Generic Panel)

- [ ] Verify the generic property panel renders all **14** properties from `api-spec.md § 3` **(UPDATED: was 13)**
- [ ] Verify `voxel_downsample_size` renders as a bounded number input with `min=0.0`, `max=1.0`, `step=0.005`, default `0.01` **(NEW)**
- [ ] Verify `number` type fields with `min`/`max`/`step` render as sliders or bounded number inputs
- [ ] Verify default values are pre-populated when node is first dropped onto canvas

## Phase 4 — WebSocket Streaming

- [ ] Verify filtered point cloud streams correctly via LIDR binary protocol from this node
- [ ] Verify WS close code `1001` on node removal is handled gracefully (no reconnect loop)

---

## Mock Data (for parallel development)

When mocking `GET /api/v1/nodes/schema`, ensure the `environment_filtering` entry includes `voxel_downsample_size` in the properties array:

```json
{
  "name": "voxel_downsample_size",
  "label": "Voxel Downsample Size (m)",
  "type": "number",
  "default": 0.01,
  "min": 0.0,
  "max": 1.0,
  "step": 0.005,
  "help_text": "Reduce point cloud density before plane detection..."
}
```

---

## Dependencies

- Backend `Phase 3` (registry.py) must be deployed before frontend integration testing
- Mock the `GET /api/v1/nodes/schema` response using **updated** `api-spec.md § 3` shapes (14 properties) during parallel development
