# Frontend Development Tasks - Node WebSocket Streaming Flag

## Summary
The frontend already has all the necessary code in place! The `websocket_enabled` field exists in the TypeScript models, the computed signal `isWebsocketEnabled()` exists in the component, and the template already uses `@if` guards. This task is purely **verification and testing** to ensure the existing reactive system correctly responds to the backend flag.

---

## Task Breakdown

### 1. Verify TypeScript Model
**File:** `web/src/app/core/models/node.model.ts`

- [x] Confirm `NodeDefinition` interface includes `websocket_enabled: boolean` (line 50)
- [x] No changes needed — model already matches backend schema

**Expected state:**
```typescript
export interface NodeDefinition {
  type: string;
  display_name: string;
  category: string;
  description?: string;
  icon: string;
  websocket_enabled: boolean;  // ✅ Already exists
  properties: PropertySchema[];
  inputs: PortSchema[];
  outputs: PortSchema[];
}
```

---

### 2. Verify Service Layer
**File:** `web/src/app/core/services/node-plugin-registry.service.ts`

- [x] Confirm `loadFromBackend()` fetches definitions from `/nodes/definitions` (line 82-92)
- [x] Confirm `definitionToPlugin()` automatically includes all backend fields (line 26-62)
- [x] No changes needed — service already propagates the field

**Expected behavior:**
- Backend returns `{ type: "calibration", websocket_enabled: false, ... }`
- Service stores it in `this.plugins` map
- Component accesses it via `nodeDefinition()` computed signal

---

### 3. Verify Component Logic
**File:** `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts`

- [x] Confirm `isWebsocketEnabled()` computed signal exists (line 124-128)
- [x] Confirm signal defaults to `true` when definition is missing (backward compat)
- [x] No changes needed — logic already correct

**Expected state:**
```typescript
protected isWebsocketEnabled = computed(() => {
  const def = this.nodeDefinition();
  // Default to true if definition is missing (backward compat)
  return def ? def.websocket_enabled !== false : true;
});
```

**Logic breakdown:**
- If `def` exists and `websocket_enabled === false` → returns `false`
- If `def` exists and `websocket_enabled === true` → returns `true`
- If `def` is missing → returns `true` (safe default)

---

### 4. Verify Template Conditional Rendering
**File:** `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.html`

- [x] Confirm visibility toggle is wrapped in `@if (isNodeEnabled() && isWebsocketEnabled())` (line 101-107)
- [x] Confirm recording controls are wrapped in `@if (isNodeEnabled() && hasOutputPort() && isWebsocketEnabled())` (line 116-118)
- [x] No changes needed — guards already in place

**Expected state:**
```html
<!-- Visibility Toggle -->
@if (isNodeEnabled() && isWebsocketEnabled()) {
  <app-node-visibility-toggle
    [node]="node().data"
    [isPending]="isTogglingVisibility()"
    (visibilityChanged)="onToggleVisibility.emit($event)"
  />
}

<!-- Recording Controls -->
@if (isNodeEnabled() && hasOutputPort() && isWebsocketEnabled()) {
  <app-node-recording-controls [node]="node()" />
}
```

**Behavior:**
- When `websocket_enabled === false` → both controls hidden
- When `websocket_enabled === true` → controls shown (if node is enabled)
- Enable/disable toggle and settings icon → always shown (independent of flag)

---

### 5. Write Frontend Unit Tests
**File:** `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.spec.ts`

- [x] Add test: "should hide visibility toggle when websocket_enabled is false"
- [x] Add test: "should hide recording controls when websocket_enabled is false"
- [x] Add test: "should show visibility toggle when websocket_enabled is true"
- [x] Add test: "should show recording controls when websocket_enabled is true and node has outputs"
- [x] Add test: "should default to showing controls when definition is missing"

**Test implementation:**
```typescript
describe('FlowCanvasNodeComponent - websocket_enabled behavior', () => {
  let component: FlowCanvasNodeComponent;
  let fixture: ComponentFixture<FlowCanvasNodeComponent>;
  let nodeStore: NodeStoreService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FlowCanvasNodeComponent],
      providers: [NodeStoreService]
    }).compileComponents();

    fixture = TestBed.createComponent(FlowCanvasNodeComponent);
    component = fixture.componentInstance;
    nodeStore = TestBed.inject(NodeStoreService);
  });

  it('should hide visibility toggle when websocket_enabled is false', () => {
    // Arrange: Mock node definition with websocket_enabled=false
    const mockDefinition: NodeDefinition = {
      type: 'calibration',
      display_name: 'ICP Calibration',
      category: 'calibration',
      icon: 'tune',
      websocket_enabled: false,
      properties: [],
      inputs: [],
      outputs: []
    };
    nodeStore.set('nodeDefinitions', [mockDefinition]);

    // Act: Set node data and detect changes
    const node: CanvasNode = {
      id: 'cal-1',
      data: { 
        id: 'cal-1',
        type: 'calibration', 
        name: 'Test Calibration',
        category: 'calibration',
        enabled: true, 
        config: {},
        x: 0,
        y: 0
      },
      position: { x: 0, y: 0 }
    };
    component.node.set(node);
    fixture.detectChanges();

    // Assert: Visibility toggle should not be rendered
    const visibilityToggle = fixture.debugElement.query(
      By.css('app-node-visibility-toggle')
    );
    expect(visibilityToggle).toBeNull();
  });

  it('should hide recording controls when websocket_enabled is false', () => {
    // Similar setup as above
    const mockDefinition: NodeDefinition = {
      type: 'if_condition',
      display_name: 'If Condition',
      category: 'flow_control',
      icon: 'call_split',
      websocket_enabled: false,
      properties: [],
      inputs: [{ id: 'in', label: 'Input', data_type: 'pointcloud', multiple: false }],
      outputs: [{ id: 'out', label: 'Output', data_type: 'pointcloud', multiple: false }]
    };
    nodeStore.set('nodeDefinitions', [mockDefinition]);

    const node: CanvasNode = {
      id: 'if-1',
      data: {
        id: 'if-1',
        type: 'if_condition',
        name: 'Test If',
        category: 'flow_control',
        enabled: true,
        config: {},
        x: 0,
        y: 0
      },
      position: { x: 0, y: 0 }
    };
    component.node.set(node);
    fixture.detectChanges();

    // Assert: Recording controls should not be rendered
    const recordingControls = fixture.debugElement.query(
      By.css('app-node-recording-controls')
    );
    expect(recordingControls).toBeNull();
  });

  it('should show visibility toggle when websocket_enabled is true', () => {
    // Arrange: Mock sensor node definition
    const mockDefinition: NodeDefinition = {
      type: 'sensor',
      display_name: 'LiDAR Sensor',
      category: 'sensor',
      icon: 'sensors',
      websocket_enabled: true,
      properties: [],
      inputs: [],
      outputs: [{ id: 'out', label: 'Output', data_type: 'pointcloud', multiple: false }]
    };
    nodeStore.set('nodeDefinitions', [mockDefinition]);

    const node: CanvasNode = {
      id: 'sen-1',
      data: {
        id: 'sen-1',
        type: 'sensor',
        name: 'Test Sensor',
        category: 'sensor',
        enabled: true,
        config: {},
        x: 0,
        y: 0
      },
      position: { x: 0, y: 0 }
    };
    component.node.set(node);
    fixture.detectChanges();

    // Assert: Visibility toggle SHOULD be rendered
    const visibilityToggle = fixture.debugElement.query(
      By.css('app-node-visibility-toggle')
    );
    expect(visibilityToggle).not.toBeNull();
  });

  it('should show recording controls when websocket_enabled is true and node has outputs', () => {
    // Same setup as above
    const mockDefinition: NodeDefinition = {
      type: 'sensor',
      display_name: 'LiDAR Sensor',
      category: 'sensor',
      icon: 'sensors',
      websocket_enabled: true,
      properties: [],
      inputs: [],
      outputs: [{ id: 'out', label: 'Output', data_type: 'pointcloud', multiple: false }]
    };
    nodeStore.set('nodeDefinitions', [mockDefinition]);

    const node: CanvasNode = {
      id: 'sen-1',
      data: {
        id: 'sen-1',
        type: 'sensor',
        name: 'Test Sensor',
        category: 'sensor',
        enabled: true,
        config: {},
        x: 0,
        y: 0
      },
      position: { x: 0, y: 0 }
    };
    component.node.set(node);
    fixture.detectChanges();

    // Assert: Recording controls SHOULD be rendered
    const recordingControls = fixture.debugElement.query(
      By.css('app-node-recording-controls')
    );
    expect(recordingControls).not.toBeNull();
  });

  it('should default to showing controls when definition is missing', () => {
    // Arrange: No definition registered for this type
    nodeStore.set('nodeDefinitions', []);

    const node: CanvasNode = {
      id: 'unknown-1',
      data: {
        id: 'unknown-1',
        type: 'unknown_type',
        name: 'Unknown Node',
        category: 'unknown',
        enabled: true,
        config: {},
        x: 0,
        y: 0
      },
      position: { x: 0, y: 0 }
    };
    component.node.set(node);
    fixture.detectChanges();

    // Assert: Controls should be shown (safe default)
    const visibilityToggle = fixture.debugElement.query(
      By.css('app-node-visibility-toggle')
    );
    expect(visibilityToggle).not.toBeNull();
  });
});
```

---

### 6. Run Frontend Tests

- [ ] Run unit tests: `cd web && npm test -- flow-canvas-node.component.spec`
- [ ] Verify all new tests pass
- [ ] Check test coverage for the component

**Testing commands:**
```bash
cd /home/thaiqu/Projects/personnal/lidar-standalone/web

# Run specific component tests
npm test -- --include="**/flow-canvas-node.component.spec.ts"

# Run with coverage
npm test -- --include="**/flow-canvas-node.component.spec.ts" --code-coverage

# Run all tests to ensure no regressions
npm test
```

---

### 7. Manual Integration Testing

- [ ] Start backend with updated registries: `python main.py`
- [ ] Start frontend: `cd web && npm start`
- [ ] Navigate to Settings page (`/settings`)
- [ ] Drag "LiDAR Sensor" onto canvas → verify visibility/recording controls appear
- [ ] Drag "ICP Calibration" onto canvas → verify NO visibility/recording controls
- [ ] Enable/disable nodes → verify controls show/hide correctly
- [ ] Open node editor → verify all node types still configurable

**Expected behavior:**

| Node Type | Enable Toggle | Settings Icon | Visibility Toggle | Recording Button |
|-----------|---------------|---------------|-------------------|------------------|
| Sensor | ✅ | ✅ | ✅ | ✅ |
| Fusion | ✅ | ✅ | ✅ | ✅ |
| Crop/Filter | ✅ | ✅ | ✅ | ✅ |
| Calibration | ✅ | ✅ | ❌ | ❌ |
| If Condition | ✅ | ✅ | ❌ | ❌ |

---

### 8. Verify Backward Compatibility

- [ ] Test scenario: Backend running old code (no `websocket_enabled` field)
- [ ] Expected: Frontend defaults to showing controls (safe fallback)
- [ ] Verify no console errors or TypeScript warnings

**Rollback test:**
```typescript
// Simulate backend returning old schema (no websocket_enabled field)
const oldDefinition = {
  type: 'sensor',
  display_name: 'LiDAR Sensor',
  category: 'sensor',
  // websocket_enabled field is missing
};

// Component should handle gracefully:
// isWebsocketEnabled() → returns true (default)
// Controls should be visible
```

---

## Testing Commands

```bash
# Install dependencies
cd /home/thaiqu/Projects/personnal/lidar-standalone/web
npm install

# Run frontend tests
npm test

# Run specific test file
npm test -- --include="**/flow-canvas-node.component.spec.ts"

# Run with coverage
npm test -- --code-coverage

# Start dev server for manual testing
npm start
```

---

## Dependencies

**Blocked by:** 
- Backend development (needs `/nodes/definitions` to return `websocket_enabled` field)

**Blocks:**
- QA E2E testing (needs fully integrated frontend + backend)

---

## References

- **Model file:** `web/src/app/core/models/node.model.ts` (line 50 - `websocket_enabled` field)
- **Component logic:** `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts` (line 124-128)
- **Template:** `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.html` (line 101-118)
- **Technical design:** `.opencode/plans/node-websocket-flag/technical.md`
- **API spec:** `.opencode/plans/node-websocket-flag/api-spec.md`

---

## Estimated Effort

- **Code verification:** ~15 minutes (no changes needed!)
- **Unit tests:** ~1 hour (write comprehensive test suite)
- **Manual testing:** ~30 minutes (verify UI behavior)
- **Total:** ~1.75 hours
