---
description: "Use when implementing or reviewing Angular frontend code, Synergy component templates, Tailwind styling, route updates, and frontend tests."
applyTo: "web/src/**/*.{ts,html,scss}"
---
# Frontend Instructions

## Must follow
- Use Angular standalone component patterns and existing Signals conventions.
- Prefer Synergy components where equivalents exist.
- Keep HTTP and websocket integration in service layers; avoid coupling transport logic directly in view-heavy components.
- Preserve Three.js performance-sensitive rendering patterns in workspace viewers.
- Keep Tailwind as the primary styling mechanism and align with existing token usage.

## Styling and UX rules
- Follow existing layout and interaction patterns in `web/src/app/features/`.
- Avoid introducing hardcoded visual constants when a token or utility class already exists.
- Keep templates readable with Angular control-flow syntax (`@if`, `@for`, `@switch`) where already used.

## Integration and quality
- Handle API or stream failure states with visible user feedback and safe fallback behavior.
- Add or update tests relevant to changed components/services.
- Run focused frontend checks relevant to changed code (`corepack pnpm test` and/or build).

## References
- `.opencode/rules/frontend.md`
- `docs/ARCHITECTURE.md`
- `docs/TOOL_REGISTRY.md`