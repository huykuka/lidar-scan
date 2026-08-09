# FE Base Context
_Updated: 2026-08-09_

## Feature map
- recordings: recording library and streamed recording viewer
- workspaces: DAG pipeline editor
- settings: application and sensor settings
- results: processing results
- calibration: calibration workflows
- admin: service-only administration
- logs: log viewer
- host: host diagnostics

## Key files
- Routes: web/src/app/app.routes.ts
- App config: web/src/app/app.config.ts
- Auth service: web/src/app/core/services/auth.service.ts
- Toast service: web/src/app/core/services/toast.service.ts
- Node plugin registry: web/src/app/core/services/node-plugin-registry.service.ts
- Auth interceptor: web/src/app/core/interceptors/auth.interceptor.ts
- Environments: web/src/environments/environment.ts
- Test setup: web/src/test-setup.ts

## Patterns
- API base: environment.apiUrl
- WS factory: environment.wsUrl(topic)
- Auth guard: serviceGuard (admin/service role only)
- Signal pattern: signal() + computed() in services
- Synergy event binding: (syn-change), (syn-input)

## Conventions
- Standalone components import SynergyComponentsModule for existing app compatibility.
- Recording viewer uses angular-three NgtsPointsBuffer and fixed reusable Float32Array.
- Binary LIDR frames parse through core/services/lidr-parser.ts.
