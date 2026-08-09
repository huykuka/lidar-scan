# Frontend Project Rules

This file is loaded automatically by the `fe-dev` agent. Documents exact conventions, file paths, and patterns for this Angular + Three.js + Synergy Design System project.

## Scope (ALL feature modules)

Rules apply to every feature under `web/src/app/features/*` and `web/src/app/plugins/*`.

- Treat examples as patterns, not feature-specific implementations.
- Prefer existing local patterns from the target feature first, then enforce global rules.
- Never copy feature-specific literals (API paths, store keys) from another feature without verifying.

---

## Project layout

```
web/src/
  index.html
  main.ts
  styles.scss
  environments/
    environment.ts          ← apiUrl, staticUrl, wsUrl(topic) — always use these
  app/
    app.ts                  ← root standalone component
    app.html / app.scss
    app.config.ts           ← provideNgtRenderer, provideRouter, provideHttpClient, interceptors
    app.routes.ts           ← root lazy routes (loadComponent)
    core/
      errors/
        global-error.handler.ts
      guards/
        auth.guard.ts       ← serviceGuard (admin/service role only)
        unsaved-changes.guard.ts
      interceptors/
        auth.interceptor.ts          ← attaches Bearer token from AuthService
        http-toast.interceptor.ts    ← auto-toast on 4xx/5xx (no duplicate needed)
      models/
      pipes/
      services/
        auth.service.ts              ← signal-based; isAuthenticated, isAdmin, isService computed()
        toast.service.ts             ← call .success/.error/.warning
        dialog.service.ts
        drawer.service.ts
        navigation.service.ts
        theme.service.ts
        system-status.service.ts     ← polls /api/v1/status
        node-status.service.ts       ← WS node status updates
        node-plugin-registry.service.ts ← register frontend node UI plugins
        point-cloud-data.service.ts
        shape-layer.service.ts
        multi-websocket.service.ts   ← manages multiple WS topics
        lidr-parser.ts               ← binary LIDR frame parser
        pcd-parser.service.ts        ← PCD format parser
        signals-simple-store.service.ts
        split-layout-store.service.ts
        app-init.service.ts          ← init() via provideAppInitializer
        api/                         ← one file per backend domain
          nodes-api.service.ts
          edges-api.service.ts
          dag-api.service.ts
          recording-api.service.ts
          results-api.service.ts
          calibration-api.service.ts
          config-api.service.ts
          config-transfer.service.ts
          flow-control-api.service.ts
          fusion-api.service.ts
          host-api.service.ts
          lidar-api.service.ts
          lidar-profiles-api.service.ts
          visionary-profiles-api.service.ts
          logs-api.service.ts
          plugins-api.service.ts
          topic-api.service.ts
          admin-api.service.ts
        stores/
          workspace-store.service.ts
          node-store.service.ts
          recording-store.service.ts
          logs-store.service.ts
          calibration-store.service.ts
          fusion-store.service.ts
          lidar-store.service.ts
    layout/
      components/
      loading-screen/
      main-layout/
    features/                        ← lazy-loaded page components (loadComponent in app.routes.ts)
      workspaces/                    ← default route, DAG pipeline editor
      settings/
      recordings/
      results/
      calibration/
      admin/                         ← node-definitions page (serviceGuard)
      logs/
      host/
    plugins/                         ← frontend node UI plugin system
      application/
      calibration/
      flow-control/
      fusion/
      operation/
      pcd-injection/
      playback/
      sensor/
      shared/
      form/
    shared/
      components/
      validators/
  assets/
  tailwind.config.js
  angular.json
  tsconfig.json / tsconfig.app.json / tsconfig.spec.json
  vitest.config.ts
```

---

## Key patterns

### Auth

```ts
// auth.service.ts — signal-based
readonly isAuthenticated = computed(() => this.currentUser() !== null);
readonly isAdmin = computed(() => ROLE_LEVELS[role] >= ROLE_LEVELS['admin']);
readonly isService = computed(() => role === 'service');
readonly canEdit = this.isAdmin;

// In component
authService = inject(AuthService);
// template: @if (authService.isAdmin()) { ... }
```

No RBAC service — use `AuthService` signals directly. Never check localStorage for role.

### HTTP / API services

```ts
// Inject HttpClient directly; use environment.apiUrl
private http = inject(HttpClient);
private apiUrl = environment.apiUrl;

getNodes() {
  return this.http.get<Node[]>(`${this.apiUrl}/nodes`);
}
```

No `AbstractApiService` base class — inject `HttpClient` directly in each API service.

### WebSocket

```ts
// environment.wsUrl produces correct ws:// or wss:// URL
const url = environment.wsUrl('node-status');
// Use MultiWebSocketService for managed multi-topic connections
```

### Toast notifications

```ts
private toast = inject(ToastService);

this.toast.success('Recording started');
this.toast.error('Connection failed');
```

HTTP errors (4xx/5xx) auto-toast via `http-toast.interceptor.ts` — no duplication needed.

### Synergy Design System — mandatory component mapping

| Native HTML | Use instead |
|---|---|
| `<input>` | `<syn-input>` |
| `<button>` | `<syn-button>` |
| `<select>` | `<syn-select>` |
| `<textarea>` | `<syn-textarea>` |
| `<dialog>` / modal | `<syn-dialog>` |
| `<table>` | `<syn-table>` |
| Card / panel | `<syn-card>` |
| Nav/sidebar | `<syn-nav-item>`, `<syn-side-nav>` |
| Notification | `<syn-alert>` |
| Tabs | `<syn-tab-group>`, `<syn-tab>` |
| Checkbox | `<syn-checkbox>` |
| Radio | `<syn-radio>`, `<syn-radio-group>` |
| Switch/toggle | `<syn-switch>` |
| Badge/tag | `<syn-badge>` |
| Icon | `<syn-icon>` |

### Synergy event binding

```html
<!-- WRONG -->
<syn-input (change)="onFoo($event)">

<!-- CORRECT -->
<syn-input (syn-change)="onFoo($event)">
<syn-input (syn-input)="onSearch($event)">
<syn-input (syn-blur)="onBlur($event)">
```

Always look up Synergy component API via MCP before writing markup.

### Signal-based state (MANDATORY for new code)

```ts
// services: signal() + computed()
readonly items = signal<Item[]>([]);
readonly count = computed(() => this.items().length);

// components: inject signals, use in template directly
items = inject(NodeStoreService).items;
// template: @for (item of items(); track item.id) { ... }
```

Avoid `BehaviorSubject` for new code unless wrapping an existing RxJS stream.

### Reactive patterns

```ts
// Prefer async pipe for observables still in use
items$ = this.api.getItems();
// template: @for (item of items$ | async; track item.id) { ... }

// Imperative subscriptions — always unsubscribe
this.api.save(data).pipe(takeUntilDestroyed()).subscribe(...);
```

### Tailwind — only CSS mechanism allowed

```html
<!-- CORRECT -->
<div class="flex items-center gap-4 px-6 py-3 rounded-lg">

<!-- WRONG -->
<div style="display:flex; padding: 12px">
```

In `.scss` files only:

```scss
// 1 — @apply Tailwind utilities
.my-element { @apply flex items-center gap-4; }

// 2 — Synergy CSS variable reference
:host { background: var(--syn-color-neutral-50); }
```

### Synergy color scheme (MANDATORY)

Never use hardcoded hex or Tailwind palette colors (`bg-blue-500`). Use Synergy tokens:

```html
<!-- CORRECT -->
<div class="bg-[var(--syn-color-primary-600)] text-[var(--syn-color-neutral-0)]">
<span class="text-[var(--syn-color-danger-600)]">Error</span>

<!-- WRONG -->
<div class="bg-blue-600 text-white">
```

| Group | Tokens | Use for |
|---|---|---|
| `--syn-color-primary-*` | 50–950 | brand, CTAs, links |
| `--syn-color-neutral-*` | 0–950 | backgrounds, borders, text |
| `--syn-color-danger-*` | 50–950 | errors, destructive actions |
| `--syn-color-warning-*` | 50–950 | warnings |
| `--syn-color-success-*` | 50–950 | success states |
| `--syn-color-surface-*` | raised/sunken/overlay | card/panel surfaces |

Use `mcp_synergy_desig_token-info` to verify exact token names.

### Tailwind class order

```
Layout (flex/grid/block/hidden)
→ Spacing (p-*, m-*, gap-*)
→ Sizing (w-*, h-*)
→ Typography (text-*, font-*, leading-*)
→ Visuals (bg-[var(--syn-...)], border-[var(--syn-...)], rounded-*, shadow-*)
→ States (hover:, focus:, disabled:)
```

### Component file structure (MANDATORY)

Three separate files — no inline template or styles:

```
<name>.component.ts      ← class only
<name>.component.html    ← all markup
<name>.component.scss    ← Tailwind @apply or CSS vars only
```

```ts
// CORRECT
@Component({
  standalone: true,
  selector: 'app-my-component',
  templateUrl: './my-component.component.html',
  styleUrl: './my-component.component.scss',
})

// WRONG — never inline
@Component({ template: `<div>...</div>` })
```

### 3D rendering (angular-three)

```ts
// app.config.ts already provides NgtRenderer
import { provideNgtRenderer } from 'angular-three/dom';

// Use NgtCanvas + NGT bindings in templates
// Never touch Three.js DOM or renderer directly
```

### Frontend plugin system

```ts
// Register a node UI plugin
const registry = inject(NodePluginRegistry);
registry.register({
  type: 'my_node_type',
  component: MyNodeFormComponent,
  // ...
});
// Done in app.config.ts via APP_INITIALIZER or provideAppInitializer
```

### New feature checklist

1. `web/src/app/features/<name>/<name>.component.ts/html/scss` — standalone component
2. Route entry in `app.routes.ts` using `loadComponent`
3. API service in `core/services/api/<name>-api.service.ts`
4. Store service in `core/services/stores/<name>-store.service.ts` (if stateful)
5. `serviceGuard` on route if admin-only
6. Unit tests: `<name>.component.spec.ts`, `<name>-api.service.spec.ts`

### Environment / API base URL

```ts
import { environment } from '@env/environment';
// environment.apiUrl    ← REST base
// environment.wsUrl(topic) ← WebSocket URL factory
// environment.staticUrl ← static file base
// Never hardcode localhost or port
```

### Commands (run inside web/)

```bash
# Dev server
npm start

# Build
npm run build

# Tests
npm test
```

### Token storage

Tokens managed exclusively by `AuthService` via `localStorage` keys `auth_token` / `auth_user`.
Never read/write these keys outside `AuthService`.
