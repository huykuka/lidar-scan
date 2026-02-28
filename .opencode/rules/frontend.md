# Frontend Architecture & Best Practices

## Tech Stack

Angular 20, Synergy Design System, Tailwind CSS, Three.js, RxJS/Signals.

## Core Architecture

1. **Component Style**: Use Angular 20 Standalone Components strictly. Modules (`NgModule`) are deprecated in this codebase.
2. **State Management**: Use **Angular Signals** (`signal()`, `computed()`, `effect()`, `input()`, `output()`) for reactive logic and component communication. Reserve RxJS strictly for HTTP streams and WebSocket subscriptions.
3. **Control Flow**: Use the Angular template syntax (`@if`, `@for`, `@switch`).
4. **Three.js Visualizer (`features/workspaces/`)**: Directly mutate WebGL `BufferGeometry` array attributes in-place. Do not destroy and recreate geometries on every frame update, as it ruins 60FPS performance on 100k+ point clouds.

## Guidelines & Restrictions

- **CLI Usage**: You MUST use the Angular CLI for scaffolding components and services (e.g., `cd web && ng g component <name>`).
- **Styling**: Enforce Tailwind CSS for styling. Do NOT write custom CSS unless absolutely necessary. If custom CSS is required in `.scss`, use `ng-deep` sparingly and ensure it is properly scoped to the component class.
- **Directory Constraint**: You MUST ONLY operate within the `/web/` folder. Do not touch backend files.
- **Separation of Concerns**: Smart Components handle state/API calls. Dumb/Presentation components only receive `@Input()` (or Signal `input()`) and emit `@Output()` (or Signal `output()`).
- **API Services**: Centralize all REST API calls in `core/services/api/`. Do not inject `HttpClient` directly into feature components.
