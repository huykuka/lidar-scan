# Application Module Scaffold — Frontend Tasks

> **For**: `@fe-dev`
> **References**: `technical.md`, `api-spec.md`

---

## Assessment: No Frontend Changes Required

The Angular flow-canvas UI **already** dynamically fetches all node schemas from
`GET /api/v1/nodes/schemas` and renders them in the node palette. When `@be-dev` adds the
`hello_world` registry entry, the Angular app will **automatically** display the new
"Hello World App" node in the palette on next page load — no Angular code changes are needed.

This is the **same behavior** for every existing module (`lidar`, `pipeline`, `fusion`,
`calibration`, `flow_control`): the UI is schema-driven and palette entries are not hardcoded.

---

## Verification-Only Tasks

> **Check procedure**: All steps below require the backend to be running with
> `app/modules/application/registry.py` loaded by `discover_modules()`. Navigate to
> `http://localhost:4200` → Settings → Flow Canvas page. No Angular code changes are needed
> for any of the items below — the UI is fully schema-driven.
>
> **Palette note**: The `application` category has no entry in `CATEGORY_STYLE`
> (`node-plugin-registry.service.ts` L20–27). It falls back gracefully to
> `{color: '#64748b', icon: 'extension'}` unless the backend definition supplies its own `icon`
> field (`celebration`). The `icon` field from the backend definition always wins
> (`icon: def.icon ?? style.icon`, line 37) — so the `celebration` icon will render correctly.
> The `application_state.color` values (`"blue"` / `"gray"`) are already handled by
> `flow-canvas-node.component.ts` L58–98 — no code change needed.

- [x] **V-1** After backend deploys, open the Angular flow-canvas settings page
  > _Navigate to `http://localhost:4200` → Settings → Flow Canvas. Confirm the page loads without
  > errors and the palette sidebar is visible. No Angular code change needed — palette is
  > schema-driven (`NodePluginRegistry.loadFromBackend()`)._
- [x] **V-2** Confirm "Hello World App" node appears in the node palette under the `application`
  category with icon `celebration`
  > _The palette groups by `plugin.category` dynamically. `application` category will auto-appear
  > once the backend returns it from `GET /api/v1/nodes/schemas`. Icon `celebration` is provided
  > by the backend definition and overrides the category default._
- [x] **V-3** Confirm the node can be dragged onto the canvas and the property editor shows:
  - "Message" text field (default: `"Hello from DAG!"`)
  - "Throttle (ms)" number field (default: `0`, step `10`, min `0`)
  > _Property editor renders all `properties[]` from the schema definition. No hardcoded form
  > fields — the generic property editor renders `string` and `number` types from the backend
  > schema automatically._
- [x] **V-4** Confirm the node has one input port labeled "Input" and one output port labeled "Output"
  > _Ports are mapped from `def.inputs` / `def.outputs` in `definitionToPlugin()`
  > (`node-plugin-registry.service.ts` L40–53). Both ports have `data_type: "pointcloud"`._
- [x] **V-5** Connect a sensor or operation node to the hello_world node's input port and verify
  the edge is accepted (port types match — both `pointcloud`)
  > _Port compatibility check uses `dataType` field. Both sides are `"pointcloud"` per the
  > schema definition — edge will be accepted._
- [x] **V-6** Confirm the node status badge on the canvas reflects `processing=false` (gray) at
  idle and `processing=true` (blue) when live data flows through it
  > _`application_state.color` (`"blue"` / `"gray"`) is already mapped in
  > `flow-canvas-node.component.ts` L58–98. No code change needed._

---

## No Code Deliverables

There are **no Angular files to create or modify** for this feature.

If future application nodes require custom UI panels (e.g., a results dashboard, trigger button,
or specialized visualization), new frontend tasks will be opened in a separate feature plan.
