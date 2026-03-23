# Output Node — Frontend Tasks

**Assignee:** @fe-dev  
**Feature Branch:** `feature/output-node`  
**References:** `technical.md`, `api-spec.md`  
**Constraint:** Work ONLY inside the `/web/` folder. Use Angular CLI for all scaffolding.  
**Mock Rule:** Use `api-spec.md §4` mock data for ALL API calls until `@be-dev` endpoints are live.  
**Note:** All checkboxes MUST be updated (`[ ]` → `[x]`) as steps complete.

---

## Phase 1 — Models & API Service

- [x] **F1.1** Add `OutputNodeMetadataMessage` and `WebhookConfig` interfaces to `web/src/app/core/models/output-node.model.ts`:
  ```typescript
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
    webhook_auth_token?: string | null;
    webhook_auth_username?: string | null;
    webhook_auth_password?: string | null;
    webhook_auth_key_name?: string | null;
    webhook_auth_key_value?: string | null;
    webhook_custom_headers?: Record<string, string> | null;
  }
  ```
- [x] **F1.2** Export new model from `web/src/app/core/models/index.ts`
- [x] **F1.3** Scaffold API service:
  ```bash
  cd web && ng g service features/output-node/services/output-node-api
  ```
- [x] **F1.4** Implement `OutputNodeApiService`:
  - `getNode(nodeId: string): Promise<NodeConfig>` → `GET /api/v1/nodes/:nodeId`
  - `getWebhookConfig(nodeId: string): Promise<WebhookConfig>` → `GET /api/v1/nodes/:nodeId/webhook`
  - `updateWebhookConfig(nodeId: string, config: WebhookConfig): Promise<{ status: string; node_id: string }>` → `PATCH /api/v1/nodes/:nodeId/webhook`
  - Use `inject(HttpClient)` and `firstValueFrom()`
  - Use `environment.apiUrl` base
- [x] **F1.5** Create mock implementation in `web/src/app/core/mocks/` for use in tests:
  - `MockOutputNodeApiService` returning static data from `api-spec.md §4`

---

## Phase 2 — Feature Scaffolding

- [x] **F2.1** Scaffold smart container component:
  ```bash
  cd web && ng g component features/output-node/output-node --standalone
  ```
- [x] **F2.2** Scaffold `MetadataTableComponent` (dumb/presentational):
  ```bash
  cd web && ng g component features/output-node/components/metadata-table --standalone
  ```
- [x] **F2.3** Scaffold `WebhookConfigComponent` (dumb form):
  ```bash
  cd web && ng g component features/output-node/components/webhook-config --standalone
  ```
- [x] **F2.4** Add lazy route to `web/src/app/app.routes.ts`:
  ```typescript
  {
    path: 'output/:nodeId',
    loadComponent: () =>
      import('./features/output-node/output-node.component')
        .then(m => m.OutputNodeComponent),
  }
  ```
  Place route BEFORE the `**` wildcard.

---

## Phase 3 — MetadataTableComponent

- [x] **F3.1** Define signal inputs:
  - `metadata = input<Record<string, any> | null>(null)`
- [x] **F3.2** Implement template with `@if`/`@for`:
  - `@if (!metadata())` → empty state: "Waiting for data..." + spinner (Synergy `syn-spinner` or Tailwind `animate-spin`)
  - `@if (metadata())` → render Tailwind table with columns: **Field**, **Value**, **Type**
  - `@for (entry of entries(); track entry[0])` where `entries = computed(() => Object.entries(metadata() ?? {}))`
  - Value rendering:
    - Primitives: render as string
    - Objects/arrays: `JSON.stringify(value, null, 2)` inside `<pre class="font-mono text-xs">` with horizontal overflow scroll
    - `null`/`undefined`: render `—` (em dash)
  - Type column: `typeof value === 'object' && Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value`
- [x] **F3.3** Style with Tailwind: alternating row colors, sticky header, horizontal scroll on table wrapper
- [x] **F3.4** Write component unit test: `metadata-table.component.spec.ts`
  - `it('renders empty state when metadata is null')`
  - `it('renders all fields from metadata object')`
  - `it('renders nested objects as JSON')`
  - `it('renders null value as em dash')`

---

## Phase 4 — OutputNodeComponent (Smart Container)

- [x] **F4.1** Inject `ActivatedRoute`, `Router`, `MultiWebsocketService`, `OutputNodeApiService`
- [x] **F4.2** Define signals:
  - `metadata = signal<Record<string, any> | null>(null)`
  - `connectionStatus = signal<'connecting' | 'connected' | 'disconnected'>('connecting')`
  - `nodeNotFound = signal<boolean>(false)`
  - `nodeName = signal<string>('')`
- [x] **F4.3** Implement `ngOnInit()`:
  - Extract `nodeId` from `ActivatedRoute.snapshot.params['nodeId']`
  - Call `OutputNodeApiService.getNode(nodeId)`:
    - On success: `nodeName.set(node.name)`
    - On 404: `nodeNotFound.set(true)`, return (skip WS)
  - Connect WebSocket:
    ```typescript
    this.wsSub = this.wsService
      .connect('system_status', `${environment.wsUrl}/ws/system_status`)
      .pipe(
        map(raw => JSON.parse(raw as string)),
        filter(msg => msg.type === 'output_node_metadata' && msg.node_id === nodeId),
      )
      .subscribe({
        next: msg => {
          this.connectionStatus.set('connected');
          this.metadata.set(msg.metadata);
        },
        error: () => this.connectionStatus.set('disconnected'),
        complete: () => this.connectionStatus.set('disconnected'),
      });
  ```
- [x] **F4.4** Implement `ngOnDestroy()`:
  - `this.wsSub?.unsubscribe()`
  - Do NOT call `wsService.disconnect('system_status')` — other components may share the topic
- [x] **F4.5** Implement template (`output-node.component.html`):
  - `@if (nodeNotFound())` → 404 error card with "Node not found" + back button linking to `/settings`
  - `@if (!nodeNotFound())`:
    - Page header: "Output Node — {{ nodeName() }}" with back button
    - Connection status badge: `connecting` / `connected` / `disconnected` (color-coded)
    - `<app-metadata-table [metadata]="metadata()" />`
- [x] **F4.6** Write component unit tests: `output-node.component.spec.ts`
  - `it('shows 404 error when node not found')`
  - `it('shows connecting status initially')`
  - `it('shows connected status after first WS message')`
  - `it('shows disconnected status on WS error')`
  - `it('passes filtered metadata to metadata-table')`
  - `it('ignores WS messages from different node_id')`
  - `it('unsubscribes on destroy')`

---

## Phase 5 — WebhookConfigComponent (DAG Settings Drawer)

- [x] **F5.1** Define signal inputs and outputs:
  - `config = input<WebhookConfig>(defaultWebhookConfig)`
  - `nodeId = input<string>('')`
  - `webhookSaved = output<WebhookConfig>()`
- [x] **F5.2** Create internal form state signals:
  - `formState = signal<WebhookConfig>({...})` initialized from `config()` via `effect()`
  - `urlValidationError = computed<string | null>(() => validateUrl(formState().webhook_url, formState().webhook_enabled))`
  - `urlWarning = computed<string | null>(() => ...)` — HTTP URL warning
  - `isDirty = computed<boolean>(() => JSON.stringify(formState()) !== JSON.stringify(config()))`
  - `isSaving = signal<boolean>(false)`
- [x] **F5.3** Implement template:
  - `syn-switch` for "Enable Webhook" toggle
  - `@if (formState().webhook_enabled)`:
    - URL input (`syn-input`) with inline validation error / warning below
    - Auth type `syn-select` dropdown
    - `@switch (formState().webhook_auth_type)`:
      - `@case ('bearer')`: password-masked token input
      - `@case ('basic')`: username + password inputs
      - `@case ('api_key')`: header name + key value (password-masked) inputs
    - Custom headers section: `@for` rows with key/value inputs + remove button, plus "Add Header" button
  - Save button (disabled when `urlValidationError() !== null || isSaving()`)
  - Cancel button
- [x] **F5.4** URL validation helper (pure function, tested independently):
  ```typescript
  function validateWebhookUrl(url: string, enabled: boolean): string | null
  function warnWebhookUrl(url: string, enabled: boolean): string | null
  ```
  - Error: empty when enabled, invalid format
  - Warning: HTTP (not HTTPS) URL
- [x] **F5.5** Implement save handler:
  - Validate → if error, do not call API
  - `isSaving.set(true)`
  - Call `OutputNodeApiService.updateWebhookConfig(nodeId(), formState())`
  - On success: `webhookSaved.emit(formState()); isSaving.set(false)`
  - On error: show toast error message, `isSaving.set(false)`
- [x] **F5.6** Implement cancel handler: reset `formState` from `config()` input
- [x] **F5.7** Write component unit tests: `webhook-config.component.spec.ts`
  - `it('hides webhook fields when toggle is off')`
  - `it('shows bearer token input when auth_type is bearer')`
  - `it('shows username+password when auth_type is basic')`
  - `it('shows header name+value when auth_type is api_key')`
  - `it('shows validation error for empty URL when enabled')`
  - `it('shows warning for http URL')`
  - `it('disables save button when url is invalid')`
  - `it('calls updateWebhookConfig on save')`
  - `it('does not call API when validation error present')`
  - `it('resets form on cancel')`
  - `it('masks password fields')`
- [x] **F5.8** Write unit tests for URL validation helper: `webhook-url-validator.spec.ts`

---

## Phase 6 — Canvas Navigation Integration

- [ ] **F6.1** Locate the Output Node click handler in `web/src/app/features/settings/` (the node canvas click logic)
- [ ] **F6.2** Add navigation: when a node with `type === 'output_node'` is clicked in the canvas, call `router.navigate(['/output', node.id])`
  - Keep existing behavior for all other node types unchanged
  - Recommendation: open config drawer AND show a "View Live Data →" link button inside the drawer pointing to `/output/:id`
- [ ] **F6.3** Integrate `WebhookConfigComponent` into the Output Node's config drawer section in the Settings feature:
  - Render `<app-webhook-config [config]="webhookConfig()" [nodeId]="node.id" (webhookSaved)="onWebhookSaved($event)" />` when drawer is for an `output_node`
  - Load current webhook config via `OutputNodeApiService.getWebhookConfig(nodeId)` when drawer opens

---

## Phase 7 — Sidebar Navigation (Optional / Low Priority)

- [ ] **F7.1** Confirm with PM whether Output Node pages should appear in the sidebar nav
- [ ] **F7.2** If required: add dynamic "Output Nodes" section in sidebar, listing all `output_node` type nodes fetched from `GET /api/v1/nodes` filtered by `type === 'output_node'`

---

## Edge Cases to Handle

- WS message arrives before node metadata is loaded → show metadata immediately, back-fill node name async
- `metadata` object contains very deeply nested structures → `JSON.stringify` handles gracefully; table cell shows truncated JSON with horizontal scroll
- User navigates away mid-save in webhook config → `isDirty` signal triggers unsaved-changes guard (verify `canDeactivate` guard covers feature route)
- Auth type dropdown changed → clear previous credential fields in `formState` (don't leak stale credentials)
- `webhook_custom_headers` is null from API → treat as empty object `{}`
- Two Output Node pages open simultaneously in different tabs → both subscribe independently to `system_status` topic; each filters by own `node_id`
