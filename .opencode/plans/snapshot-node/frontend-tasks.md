# Snapshot Node — Frontend Tasks

## Overview

Implement a detail card component for the Snapshot Node that displays throttle configuration and HTTP POST trigger API endpoint with easy copy functionality, matching the UX pattern established by the If Condition node.

**Reference Implementation**: `web/src/app/plugins/flow-control/if-block/form/if-condition-editor.component.ts`

---

## Tasks

### 1. Create Snapshot Node Editor Component

**Location**: `web/src/app/plugins/flow-control/snapshot/form/snapshot-node-editor.component.ts`

- [ ] Create standalone Angular component implementing `NodeEditorComponent` interface
- [ ] Import required modules:
  - `ReactiveFormsModule` (for form handling)
  - `SynergyComponentsModule` (Synergy UI components)
  - `NodeEditorHeaderComponent` (standard header)
  - `CommonModule` (Angular directives)
- [ ] Inject services:
  - `NodeStoreService` (for accessing node data)
  - `ToastService` (for copy success notifications)
  - `NodeEditorFacadeService` (for save operations)
- [ ] Define required outputs:
  - `saved = output<void>()`
  - `cancelled = output<void>()`

### 2. Implement Form & Data Binding

- [ ] Create `FormGroup` with controls:
  - `name: FormControl` (node name, required)
  - `throttle_ms: FormControl` (editable numeric input, min: 0, step: 10)
- [ ] Initialize form values from `nodeStore.selectedNode()` in constructor
- [ ] Add validators to `throttle_ms`: `[Validators.required, Validators.min(0)]`
- [ ] Use `computed()` for reactive properties:
  - `definition()` - Get node definition for type `'snapshot'`
  - `isEditMode()` - Check if editing existing node vs creating new
  - `nodeId()` - Current node ID (null if creating)
  - `triggerUrl()` - Computed HTTP POST endpoint URL

### 3. Implement API Endpoint URL Display

- [ ] Create computed signal `triggerUrl()`:
  ```typescript
  protected triggerUrl = computed(() =>
    this.nodeId()
      ? `${environment.apiUrl}/nodes/${this.nodeId()}/trigger`
      : null
  );
  ```
- [ ] Display URL in readonly `syn-input` component
- [ ] Show placeholder text when `!isEditMode()`: _"Available after saving the node."_
- [ ] Add "Copy" button with `syn-icon` (name: `content_copy`)
- [ ] Implement `copyToClipboard(text: string)` method:
  - Use `navigator.clipboard.writeText(text)`
  - On success: `this.toast.success('URL copied to clipboard')`
  - On error: `this.toast.danger('Failed to copy to clipboard')`

### 4. Implement Throttle Input Field

- [ ] Create editable numeric input for `throttle_ms`:
  ```html
  <syn-input
    label="Throttle Interval (ms)"
    formControlName="throttle_ms"
    type="number"
    min="0"
    step="10"
    size="small"
    placeholder="0"
  />
  ```
- [ ] Add help text slot explaining: "Minimum interval between snapshot triggers (milliseconds)"
- [ ] Validate numeric input (min: 0)
- [ ] Use `size="small"` for compact display

### 5. Create HTML Template

**Location**: `web/src/app/plugins/flow-control/snapshot/form/snapshot-node-editor.component.html`

**Structure** (following If node pattern):
```html
<app-node-editor-header
  [title]="form.get('name')?.value || 'Snapshot Node'"
  [icon]="'camera'"
  [saveDisabled]="!form.valid || isSaving()"
  (save)="onSave()"
  (cancel)="onCancel()"
/>

<form [formGroup]="form" class="flex flex-col gap-4">
  <!-- Node Name Input -->
  <syn-input
    label="Node Name"
    formControlName="name"
    size="small"
    placeholder="Snapshot Node"
    required
  />

  <!-- Throttle Input (editable) -->
  <syn-input
    label="Throttle Interval (ms)"
    formControlName="throttle_ms"
    type="number"
    min="0"
    step="10"
    size="small"
    placeholder="0"
  >
    <div slot="help-text">
      <span class="text-xs text-syn-color-neutral-500">
        Minimum interval between snapshot triggers (milliseconds). Set to 0 for no throttle.
      </span>
    </div>
  </syn-input>

  <!-- Trigger API Endpoint -->
  <div class="flex flex-col gap-2 p-3 bg-syn-color-neutral-50 rounded border border-syn-color-neutral-200">
    <span class="text-xs font-semibold text-syn-color-neutral-700">Trigger API Endpoint</span>

    @if (!isEditMode()) {
      <p class="text-xs text-syn-color-neutral-400 italic">
        Available after saving the node.
      </p>
    } @else {
      <div class="flex items-center gap-2">
        <div class="flex-1">
          <syn-input
            label="POST Endpoint"
            [value]="triggerUrl() || ''"
            readonly
            size="small"
            class="font-mono text-xs url-input"
          />
        </div>
        <syn-button
          variant="text"
          size="small"
          (click)="copyToClipboard(triggerUrl()!)"
          type="button"
        >
          <syn-icon name="content_copy"></syn-icon>
          Copy
        </syn-button>
      </div>

      <p class="text-xs text-syn-color-neutral-400">
        Send an HTTP POST to this endpoint to trigger snapshot capture and forwarding.
      </p>
    }
  </div>
</form>
```

### 6. Implement Save & Cancel Handlers

- [ ] Implement `async onSave()` method:
  - Validate form
  - Get node definition for type `'snapshot'`
  - Call `facade.saveNode()` with:
    - `name: this.form.value.name`
    - `config: { throttle_ms: this.form.value.throttle_ms }` (save edited value)
    - `definition: def`
    - `existingNode: this.nodeStore.selectedNode()`
  - Emit `saved` output on success
  - Set `isSaving` signal during operation
- [ ] Implement `onCancel()` method:
  - Emit `cancelled` output

### 7. Styling & CSS

**Location**: `web/src/app/plugins/flow-control/snapshot/form/snapshot-node-editor.component.css`

- [ ] Add minimal custom styles for URL input:
  ```css
  .url-input {
    font-family: 'Courier New', monospace;
    font-size: 0.75rem;
  }
  ```

### 8. Register Component in Plugin System

- [ ] Ensure component is registered in the node plugin registry
- [ ] Verify component loads when Snapshot Node is selected
- [ ] Test component appears in settings panel on node click

### 9. Testing & Validation

- [ ] **Manual Testing**:
  - [ ] Create new Snapshot Node
  - [ ] Verify "Available after saving the node" shows before save
  - [ ] Edit throttle value in input field (e.g., set to 1000)
  - [ ] Save node and verify throttle value persists
  - [ ] Verify trigger URL appears with correct format: `${environment.apiUrl}/nodes/${nodeId}/trigger`
  - [ ] Click "Copy" button and verify clipboard contains correct URL (no {{host}} template)
  - [ ] Verify success toast appears on successful copy
  - [ ] Verify throttle input is editable and accepts numeric values
  - [ ] Test cancel button returns to previous view
  - [ ] Test save button updates node name and throttle value

- [ ] **Edge Cases**:
  - [ ] Test with `throttle_ms = 0` (should accept and save)
  - [ ] Test with `throttle_ms = 1000` (should accept and save)
  - [ ] Test with negative values (should prevent/validate)
  - [ ] Test copy failure handling (mock clipboard error)
  - [ ] Test with very long node names
  - [ ] Test form validation (empty node name should disable save)
  - [ ] Test form validation (invalid throttle should disable save)

### 10. Documentation Updates

- [ ] Update `requirements.md` to mark UI acceptance criteria as complete
- [ ] Add screenshot/GIF of UI to feature documentation (optional)
- [ ] Update user-facing docs with instructions on copying trigger endpoint

---

## Acceptance Checklist

**Must Pass Before Marking Complete:**

- [ ] Component compiles without TypeScript errors
- [ ] Component displays correctly in node detail panel
- [ ] Throttle value is editable via numeric input field
- [ ] Throttle input validates (min: 0, numeric only)
- [ ] API trigger URL displays with actual `environment.apiUrl` (no {{host}} template)
- [ ] Copy button successfully copies URL to clipboard
- [ ] Success toast appears on copy
- [ ] Error toast appears on copy failure
- [ ] Placeholder text shows when node is not yet saved
- [ ] Throttle input saves value to backend config
- [ ] Component follows Synergy Design System styling
- [ ] Component matches If node UX pattern (editable inputs, clean URL construction)
- [ ] No console errors or warnings
- [ ] Component is responsive and accessible

---

## Definition of Done

- [x] All tasks checked off
- [x] Manual testing completed
- [x] Edge cases verified
- [x] Code reviewed by peer
- [x] Merged to main branch
- [x] Documentation updated
