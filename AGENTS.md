# LiDAR Standalone - Architecture & Agent Workflows

## Core Architecture & Technical Context

The `lidar-standalone` project is a high-performance Point Cloud Processing system.

- **Backend Stack**: Python 3.10+, FastAPI, Open3D, Asyncio.
- **Backend Architecture**: A dynamic Directed Acyclic Graph (DAG) orchestration engine mapping physical data flows entirely through decoupled, pluggable _nodes_ (Modules). Heavy Open3D operations run on threadpools to prevent blocking the async FastAPI event loop.
- **Frontend Stack**: Angular 20 (Signals, Standalone Components exclusively), Tailwind CSS, Synergy UI, Three.js.
- **Frontend Architecture**: Directly manipulates WebGL `BufferGeometry` arrays for 60FPS parsing of 100k+ dense point clouds.
- **Protocols**: Fast binary WebSocket streaming (the `LIDR` protocol) overriding standard HTTP JSON parsing for real-time sensor data.

CRITICAL: When you need detailed API specifics or rules, use your Read tool on these references:

- Backend Rules: @.opencode/rules/backend.md
- Frontend Rules: @.opencode/rules/frontend.md
- Protocol Specs: @.opencode/rules/protocols.md

## Agent SDLC Workflow

This repository strictly enforces an 8-step SDLC process, utilizing specialized subagents located via `@.opencode/agents/`:

1. **Requirements**: Use `@ba` to scope features with the user.
2. **Architecture**: Use `@arch` to define technical direction, system design, and API contracts.
3. **Planning**: Use `@pm` to break features into tracked tasks (`.opencode/plans/<feature>/`) and construct git worktrees.
4. **Backend Dev**: Use `@be-dev` to implement Python code based on the generated plan.
5. **Frontend Dev**: Use `@fe-dev` to implement Angular 20 UI.
6. **Code Review**: Use `@cr` to review architecturally-compliant components.
7. **Testing & PR**: Use `@qa` to verify automated tests and wrap the feature into a GitHub Pull Request.
8. **Documentation**: Use `@docs` to update technical documentation via `AGENTS.md` and `/docs/`.

## Feature Tracking & Folders

Features are tracked in dedicated subdirectories located in `.opencode/plans/<feature-name>/`.
Each folder contains:

- `requirements.md`: Feature specs and acceptance criteria (BA, PM, Arch).
- `technical.md`: Technical implementation direction, DAG routing, UI logic (Arch, Devs).
- `api-spec.md`: The API contract. Frontend (`@fe-dev`) MUST mock data from this while Backend (`@be-dev`) is working.
  All Dev and QA agents MUST update checkboxes (`[ ]` to `[x]`) in these files as steps complete.
