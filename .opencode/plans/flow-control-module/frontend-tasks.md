# Frontend Development Tasks - Flow Control Module

## Overview

Build Angular UI components for the IF condition node, including node card, editor, multi-port rendering, and external state control integration.

**Primary Files:**
- `web/src/app/features/settings/components/nodes/if-condition-*` (NEW COMPONENTS)
- `web/src/app/core/services/api/flow-control-api.service.ts` (NEW SERVICE)
- `web/src/app/features/settings/components/flow-canvas/` (MODIFICATIONS)

**Dependencies:**
- Backend API spec: See `api-spec.md` for endpoint contracts
- Backend mock data: See `api-spec.md` section 12 for mock responses
- Node plugin architecture: See `web/src/app/core/models/node-plugin.model.ts`

---

## Task Checklist

### Phase 1: API Service Layer

- [x] **Task 1.1:** Create `web/src/app/core/services/api/flow-control-api.service.ts`
  - [x] Generate with Angular CLI: `cd web && ng g service core/services/api/flow-control-api`
  - [x] Inject `HttpClient` and `environment`
  - [x] Implement `setExternalState(nodeId: string, value: boolean): Observable<ExternalStateResponse>`
    - [x] POST to `/api/v1/nodes/{nodeId}/flow-control/set`
    - [x] Request body: `{ value }`
    - [x] Return typed response: `ExternalStateResponse`
  - [x] Implement `resetExternalState(nodeId: string): Observable<ExternalStateResponse>`
    - [x] POST to `/api/v1/nodes/{nodeId}/flow-control/reset`
    - [x] Empty request body
  - [x] Add RxJS error handling: `catchError()` with user-friendly messages

- [x] **Task 1.2:** Create TypeScript interfaces
  - [x] File: `web/src/app/core/models/flow-control.model.ts`
  - [x] Define:
    ```typescript
    export interface ExternalStateResponse {
      node_id: string;
      state: boolean;
      timestamp: number;
    }
    
    export interface IfNodeStatus extends NodeStatus {
      expression: string;
      external_state: boolean;
      last_evaluation: boolean | null;
      last_error: string | null;
    }
    
    export interface IfConditionConfig {
      expression: string;
      throttle_ms: number;
    }
    ```

- [x] **Task 1.3:** Write mock service for testing
  - [x] File: `web/src/app/core/services/api/flow-control-api.service.mock.ts`
  - [x] Return mock data from `api-spec.md` section 12
  - [x] Use `of()` to simulate HTTP observables
  - [x] Include delay simulation: `delay(200)`

---

### Phase 2: Node Card Component

- [x] **Task 2.1:** Generate card component
  - [x] CLI: `cd web && ng g component features/settings/components/nodes/if-condition-card --skip-tests`
  - [x] Make standalone component with `standalone: true`
  - [x] Import Synergy UI components

- [x] **Task 2.2:** Implement card template
  - [x] Display shortened expression (max 30 chars, truncate with `...`)
  - [x] Display current condition result as a status badge
  - [x] Display error badge if `last_error` is not null
  - [x] Use Synergy badge component for status indicator
  - [x] Template structure:

    ```html
    <div class="if-card p-2">
      <div class="expression-preview text-xs text-gray-600 mb-1">
        {{ shortExpression() }}
      </div>
      <div class="status-row flex gap-2">
        @if (status()?.last_evaluation === true) {
          <syn-badge variant="success">TRUE</syn-badge>
        } @else if (status()?.last_evaluation === false) {
          <syn-badge variant="neutral">FALSE</syn-badge>
        } @else {
          <syn-badge variant="neutral">—</syn-badge>
        }
      </div>
      @if (status()?.last_error) {
        <syn-badge variant="danger" class="mt-1">Error</syn-badge>
      }
    </div>
    ```

- [x] **Task 2.3:** Implement card component logic
  - [x] Inputs: `node: InputSignal<CanvasNode>`, `status: InputSignal<NodeStatus | null>`
  - [x] Computed signal: `shortExpression()` to truncate long expressions
  - [x] Type guard: cast `status()` to `IfNodeStatus` when accessing IF-specific fields
  - [x] Implement `NodeCardComponent` interface

- [x] **Task 2.4:** Add Tailwind styling
  - [x] Use utility classes for layout (flex, gap, padding)
  - [x] Responsive design: stack status badge on small screens
  - [x] Error state: red border + icon

---

### Phase 3: Node Editor Component

- [x] **Task 3.1:** Generate editor component
  - [x] CLI: `cd web && ng g component features/settings/components/nodes/if-condition-editor --skip-tests`
  - [x] Make standalone with `standalone: true`
  - [x] Import `ReactiveFormsModule`, Synergy form components

- [x] **Task 3.2:** Implement editor form template
  - [x] Expression input:
    - [x] Use `<syn-textarea>` for multiline expression
    - [x] Rows: 3
    - [x] Placeholder: `point_count > 1000 AND intensity_avg < 200`
    - [x] Help text: `Supports: >, <, ==, !=, >=, <=, AND, OR, NOT, ( )`
    - [x] Real-time validation error display
  - [x] Throttle input:
    - [x] Use `<syn-input type="number">`
    - [x] Min: 0, step: 10
    - [x] Label: `Throttle (ms)`
  - [x] Action buttons:
    - [x] Save button: `<syn-button type="submit">`
    - [x] Cancel button: `<syn-button variant="ghost">`
  - [x] Template structure:

    ```html
    <form [formGroup]="form" (ngSubmit)="onSave()" class="flex flex-col gap-4">
      <syn-textarea
        label="Condition Expression"
        formControlName="expression"
        rows="3"
        placeholder="point_count > 1000 AND intensity_avg < 200"
        helpText="Supports: >, <, ==, !=, >=, <=, AND, OR, NOT, ( )"
        [error]="validationError()"
      />
      
      <syn-input
        label="Throttle (ms)"
        type="number"
        formControlName="throttle_ms"
        min="0"
        step="10"
      />
      
      <div class="flex gap-2 justify-end">
        <syn-button type="button" variant="ghost" (click)="onCancel()">Cancel</syn-button>
        <syn-button type="submit" [disabled]="!form.valid">Save</syn-button>
      </div>
    </form>
    ```

- [x] **Task 3.3:** Implement editor component logic
  - [x] Inject `NodeStoreService`
  - [x] Outputs: `saved = output<void>()`, `cancelled = output<void>()`
  - [x] Initialize form in `ngOnInit()`:
    - [x] Load current node config from store
    - [x] Set default values: `expression: 'true'`, `throttle_ms: 0`
    - [x] Add validators: `expression` required
  - [x] Implement real-time validation:
    - [x] Subscribe to `form.get('expression').valueChanges`
    - [x] Validate allowed characters: `/^[a-z_0-9\s><=!&|()\.]+$/i`
    - [x] Set `validationError` signal with error message
  - [x] Implement `onSave()`:
    - [x] Merge form values into node config
    - [x] Call `nodeStore.updateNode(updatedNode)`
    - [x] Emit `saved.emit()`
  - [x] Implement `onCancel()`: emit `cancelled.emit()`
  - [x] Implement `NodeEditorComponent` interface

- [x] **Task 3.4:** Add expression validation logic
  - [x] Create validation function: `validateExpression(expr: string): string | null`
  - [x] Check allowed characters regex
  - [x] Check balanced parentheses (simple stack-based check)
  - [x] Return error message or `null` if valid
  - [x] Future: Add backend validation call (optional)

- [x] **Task 3.5:** Add "External Control URLs" section to the editor form
  - [x] **Behaviour rules:**
    - [x] When `editMode === false` (node not yet saved): render the section with a grey/disabled appearance and the text "Available after saving the node" — no URLs, no copy buttons
    - [x] When `editMode === true` (node already registered, `node.id` is present): render two read-only URL rows with copy buttons
  - [x] **Computed signals** inside the editor component:

    ```typescript
    private nodeStore = inject(NodeStoreService);
    private env = inject(ENVIRONMENT);           // or read from environment.apiUrl

    protected isEditMode = computed(() => this.nodeStore.select('editMode')());
    protected nodeId     = computed(() => this.nodeStore.selectedNode()?.id ?? null);

    protected setUrl = computed(() =>
      this.nodeId()
        ? `${this.env.apiUrl}/api/v1/nodes/${this.nodeId()}/flow-control/set`
        : null
    );
    protected resetUrl = computed(() =>
      this.nodeId()
        ? `${this.env.apiUrl}/api/v1/nodes/${this.nodeId()}/flow-control/reset`
        : null
    );
    ```
  - [x] **Template** — append inside the `<form>` after the throttle field, before the action buttons:

    ```html
    <!-- External Control URLs -->
    <div class="flex flex-col gap-2">
      <span class="text-xs font-semibold text-syn-color-neutral-700">External Control URLs</span>

      @if (!isEditMode()) {
        <!-- Pre-save placeholder -->
        <p class="text-xs text-syn-color-neutral-400 italic">
          Available after saving the node.
        </p>
      } @else {
        <!-- Set URL -->
        <div class="flex items-center gap-2">
          <syn-input
            label="Set (POST)"
            [value]="setUrl()"
            readonly
            size="small"
            class="flex-1 font-mono text-xs"
          />
          <syn-icon-button
            name="content_copy"
            label="Copy set URL"
            size="small"
            (click)="copyToClipboard(setUrl()!)"
          />
        </div>

        <!-- Reset URL -->
        <div class="flex items-center gap-2">
          <syn-input
            label="Reset (POST)"
            [value]="resetUrl()"
            readonly
            size="small"
            class="flex-1 font-mono text-xs"
          />
          <syn-icon-button
            name="content_copy"
            label="Copy reset URL"
            size="small"
            (click)="copyToClipboard(resetUrl()!)"
          />
        </div>

        <p class="text-xs text-syn-color-neutral-400">
          Call these endpoints from any external system to control routing.
          POST body for set: <code>{"value": true}</code>
        </p>
      }
    </div>
    ```
  - [x] **`copyToClipboard()` helper** in the component class:

    ```typescript
    protected copyToClipboard(text: string): void {
      navigator.clipboard.writeText(text).then(() => {
        this.toast.success('URL copied to clipboard.');
      });
    }
    ```
    - [x] Inject `ToastService` for the success feedback
  - [x] The two `syn-input` fields must be `readonly` — user cannot edit them, only copy
  - [x] No API calls are made from this section — it is display-only

---

### Phase 4: Node Plugin Registration

- [x] **Task 4.1:** Register IF node plugin
  - [x] File: `web/src/app/core/services/node-plugin-registry.service.ts`
  - [x] Add registration in constructor or initialization:

    ```typescript
    this.register({
      type: 'if_condition',
      category: 'flow_control',
      displayName: 'Conditional If',
      description: 'Routes data based on boolean expression',
      icon: 'call_split',
      style: {
        color: '#9c27b0',
        backgroundColor: '#f3e5f5'
      },
      ports: {
        inputs: [
          { id: 'in', label: 'Input', dataType: 'pointcloud' }
        ],
        outputs: [
          { id: 'true', label: 'True', dataType: 'pointcloud' },
          { id: 'false', label: 'False', dataType: 'pointcloud' }
        ]
      },
      cardComponent: IfConditionCardComponent,
      editorComponent: IfConditionEditorComponent,
      createInstance: () => ({
        type: 'if_condition',
        name: 'If Condition',
        config: {
          expression: 'true',
          throttle_ms: 0
        }
      })
    });
    ```

- [x] **Task 4.2:** Import components in registry
  - [x] Add imports at top of `node-plugin-registry.service.ts`:
    ```typescript
    import { IfConditionCardComponent } from '@features/settings/components/nodes/if-condition-card/if-condition-card.component';
    import { IfConditionEditorComponent } from '@features/settings/components/nodes/if-condition-editor/if-condition-editor.component';
    ```

---

### Phase 5: Multi-Port Canvas Rendering

> **Context:** The current canvas is entirely port-unaware. Every node has exactly one hardcoded
> output dot and one hardcoded input dot. The changes below are surgical — all existing single-port
> nodes must continue to work identically after this phase.

- [x] **Task 5.1:** Extend `pendingConnection` in `FlowCanvasDragService` to carry the source port ID
  - [x] File: `web/src/app/features/settings/components/flow-canvas/flow-canvas-drag.ts`
  - [x] Change the `pendingConnection` signal shape (line 16-20):
    ```typescript
    // Before:
    readonly pendingConnection = signal<{
      fromNodeId: string;
      cursorX: number;
      cursorY: number;
    } | null>(null);

    // After:
    readonly pendingConnection = signal<{
      fromNodeId: string;
      fromPortId: string;   // e.g. "out", "true", "false"
      fromPortIndex: number; // 0-based index within outputs array
      cursorX: number;
      cursorY: number;
    } | null>(null);
    ```
  - [x] Update `startConnectionDrag()` signature to accept `fromPortId: string` and `fromPortIndex: number`

- [x] **Task 5.2:** Extend `portDragStart` output and update node template to loop over ports
  - [x] File: `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts`
  - [x] Add `NodePluginRegistry` injection and `outputPorts` computed signal:
    ```typescript
    private pluginRegistry = inject(NodePluginRegistry);

    protected outputPorts = computed(() => {
      const def = this.pluginRegistry.get(this.node().data.type);
      return def?.ports?.outputs ?? [{ id: 'out', label: 'Output', dataType: 'pointcloud' }];
    });
    ```
  - [x] Change `portDragStart` output (line 32) to include `portId` and `portIndex`:
    ```typescript
    // Before:
    portDragStart = output<{ nodeId: string; portType: 'input' | 'output'; event: MouseEvent }>();

    // After:
    portDragStart = output<{ nodeId: string; portType: 'input' | 'output'; portId: string; portIndex: number; event: MouseEvent }>();
    ```
  - [x] Add helper to compute Y offset per port (used by template and by `calculatePath()`):
    ```typescript
    getOutputPortY(portIndex: number, totalPorts: number): number {
      const HEADER_Y = 16;    // matches existing hardcoded top-4 = 16px
      const SPACING = 28;     // px between port dots
      if (totalPorts === 1) return HEADER_Y;
      const totalHeight = (totalPorts - 1) * SPACING;
      return HEADER_Y + portIndex * SPACING - totalHeight / 2 + totalHeight / 2;
      // simplifies to: HEADER_Y + portIndex * SPACING for top-anchored layout
    }
    ```

  - [x] File: `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.html`
  - [x] Replace the hardcoded single output port `div` (lines 18-29) with a `@for` loop:
    ```html
    <!-- Output Ports — one dot per port, vertically stacked -->
    @for (port of outputPorts(); track port.id; let i = $index) {
      <div
        (mousedown)="
          $event.stopPropagation();
          portDragStart.emit({ nodeId: node().id, portType: 'output', portId: port.id, portIndex: i, event: $event })
        "
        (mouseup)="$event.stopPropagation()"
        [style.top.px]="getOutputPortY(i, outputPorts().length)"
        [title]="port.label + ' — drag to connect'"
        class="absolute right-0 translate-x-full -translate-y-1/2 w-3 h-3 rounded-sm border-2 border-white shadow-sm z-20 cursor-crosshair transition-all hover:scale-125 after:absolute after:-inset-4 after:content-['']"
        [class.bg-syn-color-success-600]="port.id === 'true'"
        [class.bg-syn-color-warning-600]="port.id === 'false'"
        [class.bg-syn-color-primary-600]="port.id !== 'true' && port.id !== 'false'"
      ></div>
    }
    ```
  - [x] Keep the input port dot (lines 9-16) unchanged — it is already correct

- [x] **Task 5.3:** Update `pendingPath` calculation to use actual port Y
  - [x] File: `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts`
  - [x] In `onPortDragStart()` (line 232), pass `portId` and `portIndex` through to `drag.startConnectionDrag()`:
    ```typescript
    onPortDragStart(event: { nodeId: string; portType: 'input' | 'output'; portId: string; portIndex: number; event: MouseEvent }) {
      if (event.portType !== 'output') return;
      this.drag.startConnectionDrag(event.nodeId, event.portId, event.portIndex);
    }
    ```
  - [x] In `onCanvasMouseMove()` (line 153-163), replace the hardcoded `fromY = fromNode.position.y + 16` with port-aware Y:
    ```typescript
    // Before:
    const fromY = fromNode.position.y + 16;

    // After:
    const portIndex = pending.fromPortIndex;
    const totalPorts = /* look up outputPorts count for fromNode.type */
      this.pluginRegistry.get(fromNode.type)?.ports?.outputs?.length ?? 1;
    const fromY = fromNode.position.y + this.getOutputPortY(portIndex, totalPorts);
    ```
  - [x] Extract `getOutputPortY(portIndex, totalPorts)` as a private method (same formula as in node component):
    ```typescript
    private getOutputPortY(portIndex: number, totalPorts: number): number {
      const HEADER_Y = 16;
      const SPACING = 28;
      return HEADER_Y + portIndex * SPACING;
    }
    ```

- [x] **Task 5.4:** Update `Connection` interface and `updateConnections()` to track port metadata
  - [x] File: `web/src/app/features/settings/components/flow-canvas/connections/flow-canvas-connections.component.ts`
  - [x] Extend `Connection` interface (line 4-9):
    ```typescript
    export interface Connection {
      id?: string;
      from: string;
      fromPortId: string;    // NEW: e.g. "out", "true", "false"
      fromPortIndex: number; // NEW: 0-based index for Y calculation
      to: string;
      toPortId: string;      // NEW: e.g. "in"
      path?: string;
      color?: string;        // NEW: "#4caf50" for true, "#f97316" for false
    }
    ```
  - [x] File: `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts`
  - [x] Update `updateConnections()` (line 520-544) to read `source_port` from edge and compute correct Y:
    ```typescript
    private updateConnections(): void {
      const connections: Connection[] = [];
      const nodeMap = new Map(this.canvasNodes().map((n) => [n.id, n]));

      this.edges().forEach((edge) => {
        const sourceNode = nodeMap.get(edge.source_node);
        const targetNode = nodeMap.get(edge.target_node);
        if (!sourceNode || !targetNode) return;

        const sourcePortId = edge.source_port ?? 'out';
        const sourcePorts = this.pluginRegistry.get(sourceNode.data.type)?.ports?.outputs ?? [];
        const portIndex = sourcePorts.findIndex((p) => p.id === sourcePortId);
        const fromPortIndex = portIndex >= 0 ? portIndex : 0;
        const totalPorts = Math.max(sourcePorts.length, 1);

        const path = this.calculatePath(sourceNode, targetNode, fromPortIndex, totalPorts);
        const color = sourcePortId === 'true' ? '#16a34a'
                    : sourcePortId === 'false' ? '#ea580c'
                    : undefined;

        connections.push({
          id: edge.id,
          from: edge.source_node,
          fromPortId: sourcePortId,
          fromPortIndex,
          to: edge.target_node,
          toPortId: edge.target_port ?? 'in',
          path,
          color,
        });
      });

      this.connections.set(connections);
    }
    ```
  - [x] Update `calculatePath()` (line 546-558) to accept port Y instead of hardcoding `+ 16`:
    ```typescript
    private calculatePath(
      fromNode: CanvasNode,
      toNode: CanvasNode,
      fromPortIndex: number,
      totalOutputPorts: number,
    ): string {
      const fromX = fromNode.position.x + 192 + 6;
      const fromY = fromNode.position.y + this.getOutputPortY(fromPortIndex, totalOutputPorts);
      const toX = toNode.position.x - 6;
      const toY = toNode.position.y + 16; // input port is always single, stays at header center

      const cp = Math.max(Math.abs(toX - fromX) * 0.5, 40);
      return `M ${fromX} ${fromY} C ${fromX + cp} ${fromY}, ${toX - cp} ${toY}, ${toX} ${toY}`;
    }
    ```

- [x] **Task 5.5:** Pass `color` through connections SVG renderer
  - [x] File: `web/src/app/features/settings/components/flow-canvas/connections/flow-canvas-connections.component.html`
  - [x] Bind `color` on each path so true-port edges render green, false-port edges render orange
  - [x] Existing single-port edges (no `color`) fall back to the current default stroke color

- [x] **Task 5.6:** Update `onPortDrop()` to send port IDs to the backend
  - [x] File: `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts`
  - [x] In `onPortDrop()` (line 238), read `fromPortId` from `pendingConnection` and pass it:
    ```typescript
    async onPortDrop(event: { nodeId: string; portType: 'input' | 'output'; portId: string }) {
      const pending = this.drag.pendingConnection();
      if (!pending || event.portType !== 'input') {
        this.drag.cancelConnectionDrag();
        return;
      }
      // ...duplicate/self-loop checks unchanged...
      await this.edgesApi.createEdge({
        source_node: pending.fromNodeId,
        source_port: pending.fromPortId,   // NEW
        target_node: event.nodeId,
        target_port: event.portId,         // NEW ("in")
      });
    }
    ```
  - [x] Note: `portDrop` output on the node component only carries the node-level input port today.
    Update `portDrop` output in `flow-canvas-node.component.ts` to also emit `portId`:
    ```typescript
    // Before:
    portDrop = output<{ nodeId: string; portType: 'input' | 'output' }>();
    // After:
    portDrop = output<{ nodeId: string; portType: 'input' | 'output'; portId: string }>();
    ```
    And in the input port `mouseup` handler in the template, emit `portId: 'in'` (or look up from plugin definition).

- [x] **Task 5.7:** Edge validation — allow multiple edges from IF node's different output ports
  - [x] File: `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts`
  - [x] Update the duplicate-edge check in `onPortDrop()` (line 254):
    ```typescript
    // Before: blocks any second edge from same source node
    const exists = this.edges().some(
      (e) => e.source_node === sourceId && e.target_node === targetId,
    );

    // After: only block if same source node + same source port + same target
    const exists = this.edges().some(
      (e) =>
        e.source_node === sourceId &&
        (e.source_port ?? 'out') === pending.fromPortId &&
        e.target_node === targetId,
    );
    ```
  - [x] This allows `if_node.true → nodeA` and `if_node.false → nodeB` to coexist

---

### Phase 6: External State Control UI

> **Decision:** External state is controlled by third-party systems via the two REST URLs, not via
> in-app toggle buttons. The editor exposes these URLs as read-only copyable fields (Task 3.5).
> No toggle UI is needed inside the app.

- [x] **Task 6.1:** Add `external_state` live indicator to the node card (lightweight, read-only)
  - [x] File: `if-condition-card.component.ts`
  - [x] If `status()?.external_state === true`, render a small badge "Ext: ON" with `variant="primary"`
  - [x] This gives live visibility that an external system has activated the gate, without exposing controls
  - [x] Template addition (inside the card, after the evaluation badge):

    ```html
    @if (ifStatus()?.external_state) {
      <syn-badge variant="primary" size="small">Ext: ON</syn-badge>
    }
    ```
  - [x] Add typed computed signal:

    ```typescript
    protected ifStatus = computed(() => this.status() as IfNodeStatus | null);
    ```

- [x] **Task 6.2:** Verify `ToastService` is available in the editor component scope
  - [x] `ToastService` is `providedIn: 'root'` — inject directly, no provider changes needed
  - [x] Confirm `navigator.clipboard` is available in the target browser environment (HTTPS or localhost)

---

### Phase 7: Testing & Validation

- [ ] **Task 7.1:** Write unit tests for IfConditionCardComponent
  - [ ] File: `if-condition-card.component.spec.ts`
  - [ ] Test expression truncation: long expression → shows `...`
  - [ ] Test status badge: `last_evaluation=true` → shows green "TRUE" badge
  - [ ] Test status badge: `last_evaluation=false` → shows neutral "FALSE" badge
  - [ ] Test status badge: `last_evaluation=null` → shows neutral "—" badge
  - [ ] Test error badge: status with `last_error` → shows red badge

- [ ] **Task 7.2:** Write unit tests for IfConditionEditorComponent
  - [ ] File: `if-condition-editor.component.spec.ts`
  - [ ] Test form initialization: loads config from store
  - [ ] Test validation: invalid characters → shows error
  - [ ] Test save action: emits `saved` event, calls store update
  - [ ] Test cancel action: emits `cancelled` event
  - [ ] Test URL section — creation mode (`editMode=false`): URLs section shows placeholder text, no copy buttons rendered
  - [ ] Test URL section — edit mode (`editMode=true`, `node.id='if_abc'`): two `syn-input` fields rendered with correct URLs
  - [ ] Test copy button: clicking copies correct URL to clipboard (mock `navigator.clipboard`)

- [ ] **Task 7.3:** Write unit tests for FlowControlApiService
  - [ ] File: `flow-control-api.service.spec.ts`
  - [ ] Mock `HttpClient` with `HttpClientTestingModule`
  - [ ] Test `setExternalState()`: verifies POST request
  - [ ] Test `resetExternalState()`: verifies POST request
  - [ ] Test error handling: HTTP error → returns error observable

- [ ] **Task 7.4:** Integration test: Node creation workflow
  - [ ] E2E test (Cypress/Playwright):
    1. Drag IF node from palette to canvas
    2. Verify node appears with default config
    3. Click node → open editor
    4. Change expression → save
    5. Verify node config updated via API

- [ ] **Task 7.5:** Integration test: Dual-port edge creation
  - [ ] E2E test:
    1. Create IF node
    2. Create downstream node 1
    3. Connect IF node's `true` port → downstream 1
    4. Create downstream node 2
    5. Connect IF node's `false` port → downstream 2
    6. Verify both edges created with correct `source_port` metadata

---

### Phase 8: Documentation & Cleanup

- [ ] **Task 8.1:** Add JSDoc comments to all components and services
  - [ ] Document component inputs, outputs, signals
  - [ ] Document service methods with param/return types

- [ ] **Task 8.2:** Update frontend README
  - [ ] Document flow control module structure
  - [ ] Provide usage examples (how to create IF node, configure expression)

- [ ] **Task 8.3:** Run linter and fix warnings
  - [ ] CLI: `cd web && npm run lint`
  - [ ] Fix all ESLint warnings
  - [ ] Ensure no unused imports

- [ ] **Task 8.4:** Visual QA check
  - [ ] Verify card appearance matches design
  - [ ] Verify editor form layout is clean and accessible
  - [ ] Verify multi-port rendering aligns correctly
  - [ ] Verify edge colors (green/orange) are distinct
  - [ ] Test responsive design: mobile/tablet views

---

## Dependencies & Blockers

### External Dependencies
- **Backend API:** Must implement endpoints in `api-spec.md`
- **Mock Data:** Use mock service (Task 1.3) until backend ready

### Internal Dependencies
- **Node Plugin System:** Must support multi-port definitions
- **Flow Canvas:** Must handle port-specific edge routing

### Blockers
- **Backend API not ready:** Use mock service for parallel development
- **Synergy UI components:** Verify `syn-textarea`, `syn-badge` are available

---

## Testing Requirements

### Unit Test Coverage
- [ ] IfConditionCardComponent: 80%+
- [ ] IfConditionEditorComponent: 80%+
- [ ] FlowControlApiService: 90%+

### Integration Test Coverage
- [ ] Node creation workflow (E2E)
- [ ] Dual-port edge creation (E2E)
- [ ] External state control (E2E, if implemented)

### Manual Testing
- [ ] Drag-and-drop IF node from palette
- [ ] Configure expression with validation
- [ ] Create edges from both output ports
- [ ] Verify evaluation badge updates in real-time (mock status updates)

---

## Definition of Done

- [ ] All tasks checked off
- [ ] All unit tests passing (`npm run test`)
- [ ] Linter clean (`npm run lint`)
- [ ] Components render correctly in dev environment
- [ ] Mock API service allows parallel development
- [ ] Code reviewed by @review agent
- [ ] Visual QA approved by @qa agent
- [ ] Integration tests pass against backend (post-backend completion)

---

## Estimated Effort

- **Phase 1 (API Service):** 2 hours
- **Phase 2 (Card Component):** 3 hours
- **Phase 3 (Editor Component):** 5 hours
- **Phase 4 (Plugin Registration):** 1 hour
- **Phase 5 (Multi-Port Rendering):** 6 hours
- **Phase 6 (External State UI):** 1 hour (card badge + clipboard verification only)
- **Phase 7 (Testing):** 4 hours
- **Phase 8 (Documentation):** 2 hours

**Total:** ~24 hours (3 days for 1 developer)

---

## Notes for Frontend Developer

1. **Angular 20 Standards:** Use standalone components, signals, `@if/@for` syntax exclusively.
2. **Synergy UI:** Use Synergy components for all form inputs and badges.
3. **Tailwind CSS:** Use utility classes, avoid custom CSS unless absolutely necessary.
4. **Mock First:** Develop against mock API service to unblock backend dependency.
5. **Multi-Port Challenge:** Pay special attention to port positioning and edge routing logic.
6. **Accessibility:** Ensure form inputs have proper labels and ARIA attributes.

---

**Document Status:** ✅ READY FOR FRONTEND DEVELOPMENT  
**Coordination:** See `backend-tasks.md` for parallel backend development
