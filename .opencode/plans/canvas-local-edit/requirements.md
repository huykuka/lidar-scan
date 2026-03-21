# Canvas Local Editing - Requirements

## Feature Overview

Enable local, client-side editing of the DAG canvas (nodes, connections, positions) without immediate backend
synchronization. Changes accumulate in the frontend until the user explicitly saves, providing a fluid editing
experience with explicit state control.

## User Stories

### As a DAG operator, I want to:

- Add, remove, move, and connect nodes on the canvas **without triggering backend API calls** during editing
- See a **clear visual indicator** when I have unsaved changes (dirty state)
- Click **"Save & Reload"** to commit all local changes to the backend in one atomic operation, then restart the backend
  DAG runtime
- Click **"Sync"** to discard all local edits and pull the latest backend DAG configuration to my canvas, without saving
  anything
- Click **"Reload"** to restart the backend DAG runtime **without** touching the frontend config or discarding local
  edits — useful to force-restart a stuck pipeline
- Be **warned before navigating away** if I have unsaved changes, preventing accidental data loss
- Have the frontend **validate my changes** (cycles, invalid connections, required parameters) before allowing save
- Be **notified if the backend state changed** while I was editing, preventing conflicting overwrites

## Acceptance Criteria

### 1. Local Editing Mode

- [x] All canvas edit actions operate on **local frontend state only**:
  - Adding a new node from the palette
  - Removing/deleting an existing node
  - Moving/dragging a node to a new position
  - Creating a connection between two nodes
  - Removing a connection
  - Editing node configuration/parameters
- [x] No API calls (REST or WebSocket) are made to the backend during any of the above actions
- [x] The canvas updates instantly and smoothly for all local changes (60 FPS maintained)
- [x] Local changes are tracked in a state management structure (Angular Signal-based store)

### 2. Dirty State Indicator

- [x] A **visual indicator** appears when any unsaved changes exist:
  - Badge, icon, or status text near the action buttons
  - Example: "• Unsaved changes" or amber dot indicator
- [x] Indicator disappears when changes are successfully saved or synced (reverted)
- [x] Indicator persists across component re-renders but not page reloads

### 3. Real-Time Frontend Validation

- [x] The frontend validates DAG structure **during editing** (non-blocking warnings):
  - Detects cyclic connections (A → B → C → A)
  - Prevents invalid node-to-node connections based on type compatibility
  - Highlights missing required node parameters
- [x] Validation errors are shown as **warnings** but do not block editing
- [x] Validation is **enforced on save**: invalid configurations block the save operation with clear error messages

### 4. Save & Reload Action

- [x] A **"Save & Reload"** button is visible on the canvas toolbar
- [x] Button is **disabled** when no unsaved changes exist
- [x] Button is **enabled** when dirty state exists
- [x] On click:
  1. **Validates** the entire DAG configuration (cycle detection, connection validity, required parameters)
  2. If validation fails: Shows error dialog with details, cancels save operation
  3. If validation passes:
     - Sends complete DAG configuration to backend API (`PUT /api/v1/dag/config`)
     - Backend **stops current DAG execution**
     - Backend **applies the new configuration**
     - Backend **restarts the DAG pipeline** with updated node graph
     - Frontend receives success confirmation
     - Dirty state indicator clears
     - Canvas refreshes with latest backend state (node IDs, WebSocket topics updated)
- [x] If save fails (network error, backend rejection):
  - Show error notification with reason
  - Local changes remain intact
  - User can retry save or sync (revert)

### 5. Sync Action (Pull Backend Config → Discard Local Edits)

- [x] A **"Sync"** button is visible on the canvas toolbar
- [x] The button is always **enabled** (it is useful even without local edits, to pull in externally changed config)
- [x] On click:
  - If dirty state exists: Shows confirmation dialog: _"You have unsaved changes. Syncing will discard them and load the
    latest backend configuration. Continue?"_
  - If not dirty: Syncs immediately without any prompt
  - If confirmed (or not dirty):
    - Fetches latest DAG configuration from backend API (`GET /api/v1/dag/config`)
    - Replaces entire local canvas state with backend response
    - Dirty state indicator clears
    - Canvas re-renders with backend state
  - If user dismisses the dialog (dirty case): No action, local state remains

### 6. Reload Action (Backend Runtime Restart Only — No Config Sync)

- [x] A **"Reload"** button is visible on the canvas toolbar
- [x] The button is **always enabled** (can be used at any time, with or without unsaved edits)
- [x] Clicking **Reload** does **NOT** discard local edits and does **NOT** pull config from the backend
- [x] On click:
  - Calls `POST /api/v1/nodes/reload` (existing endpoint)
  - Backend restarts the DAG runtime pipeline using its **currently saved** configuration
  - Shows a brief loading indicator on the button during the call
  - On success: shows a toast "DAG runtime reloaded successfully"
  - On failure: shows an error toast with the reason
- [x] Local unsaved edits are **fully preserved** before, during, and after the Reload action

### 7. Navigation Guard & Unsaved Changes Warning

- [x] If user tries to **navigate away** from canvas page with unsaved changes:
  - Angular Dialog Service shows custom confirmation modal
  - Modal message: "You have unsaved changes. Do you want to save before leaving?"
  - Options: "Save & Leave", "Discard & Leave", "Stay"
- [x] If user tries to **refresh/close browser tab** with unsaved changes:
  - Browser's native `beforeunload` confirmation dialog appears
  - Message: "Changes you made may not be saved."
- [x] Navigation guard is removed after successful save or sync (revert)

### 8. Backend State Conflict Detection

- [x] Before sending save request, frontend includes a **state version/timestamp** from last backend fetch
- [x] Backend checks if its current state version matches the frontend's base version
- [x] If backend state has changed (mismatch):
  - Backend responds with `409 Conflict` error
  - Frontend shows error dialog: "The DAG configuration was modified by another user or process. Your changes cannot be
    saved. Please sync to fetch the latest state and reapply your changes."
  - User must click "Sync" to fetch latest backend state
  - Local unsaved changes remain visible (but blocked from saving)
- [x] If no conflict: Save proceeds normally

### 9. Edge Cases & Error Handling

- [ ] **WebSocket reconnection during editing**: Local changes are preserved; WebSocket topics re-subscribe on save
- [ ] **Backend DAG execution failure after save**: User receives clear error notification, can sync to previous config
- [ ] **Partial save failure** (e.g., some nodes fail initialization): Backend rolls back entire configuration change;
  frontend shows detailed error
- [ ] **Network timeout during save**: User receives timeout error; can retry or sync (revert)
- [ ] **Multiple clients editing simultaneously**: Last one to save gets conflict error (409)

## Out of Scope

### Explicitly NOT Included

- **Undo/redo stack**: Single "sync all" action only (no granular undo/redo for individual operations)
- **Auto-save to localStorage**: Changes are lost on page reload if not explicitly saved
- **Real-time collaborative editing**: No multi-user presence, locking, or operational transforms
- **Incremental save**: Cannot save individual nodes — must save entire DAG configuration
- **Change preview/diff view**: No visual comparison of before/after states
- **Save without reload**: Backend must always restart DAG on save (no hot-reload)
- **Conflict resolution UI**: No merge/rebase interface — user must manually reapply changes after sync

## Technical Notes

### Frontend State Management

- Use Angular Signals to track:
  - `localDagState: WritableSignal<DagConfig>` — current edited state
  - `savedDagState: WritableSignal<DagConfig>` — last known backend state
  - `isDirty: Signal<boolean>` — computed comparison of local vs saved
- Deep object comparison required for accurate dirty detection

### API Contract Requirements

- **GET /api/v1/dag/config**: ✅ IMPLEMENTED — Returns full DAG configuration + config_version (used by **Sync**)
- **PUT /api/v1/dag/config**: ✅ IMPLEMENTED — Accepts full DAG configuration + base_version, responds with success/conflict (used by **Save & Reload**). Atomic DB transaction + `reload_config()` trigger. Returns 409 on version conflict or reload in progress.
- **POST /api/v1/nodes/reload**: ✅ ALREADY EXISTS — Triggers backend DAG runtime restart (used by **Reload**)
- Backend must support atomic "stop → apply → restart" transaction for the PUT path

### Validation Rules

- Cycle detection: Use topological sort or DFS to detect cycles in directed graph
- Connection validity: Check node output type matches target node input type
- Required parameters: Validate all `required: true` node parameters are non-empty

### Toolbar Button Summary

| Button | Always Visible | Enabled When | Backend Call | Discards Local Edits |
|---|---|---|---|---|
| **Reload** | ✅ | Always | `POST /nodes/reload` | ❌ Never |
| **Sync** | ✅ | Always | `GET /dag/config` | ✅ Yes (with confirm if dirty) |
| **Save & Reload** | ✅ | Only when `isDirty` | `PUT /dag/config` | N/A (persists them) |

## Success Metrics

- [ ] Zero API calls during canvas editing actions (measured via browser DevTools Network tab)
- [ ] Dirty state indicator appears within 100ms of any edit action
- [ ] Save operation completes within 3 seconds for DAGs with <50 nodes
- [ ] Validation feedback appears within 500ms of invalid operation
- [ ] Navigation guard prevents 100% of accidental data loss scenarios (tested via E2E)
- [ ] Conflict detection catches 100% of concurrent edit scenarios (tested via integration tests)
- [ ] Reload button does NOT mutate local frontend state under any condition (verified via unit test)
- [ ] Sync button correctly prompts when dirty and skips prompt when clean (verified via E2E)
