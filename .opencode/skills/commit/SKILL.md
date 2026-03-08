---
name: commit
description: Standardized Git Commit Message Skill
---

# Git Commit Message Standard

To maintain a clean and searchable history, all agents MUST use the Conventional Commits format for every commit.

## Format

```text
<type>(<scope>): <description>
```

- **type**: The category of change (see below)
- **scope**: The functional area (optional but highly recommended)
- **description**: A concise, imperative-mood summary of the change

## Commit Types

| Type       | Description                                                                                            |
| :--------- | :----------------------------------------------------------------------------------------------------- |
| `feat`     | A new feature for the user                                                                             |
| `fix`      | A bug fix for the user                                                                                 |
| `docs`     | Documentation only changes                                                                             |
| `style`    | Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc) |
| `refactor` | A code change that neither fixes a bug nor adds a feature                                              |
| `test`     | Adding missing tests or correcting existing tests                                                      |
| `chore`    | Changes to the build process or auxiliary tools and libraries such as documentation generation         |
| `perf`     | A performance improvement                                                                              |

## Common Scopes

| Scope      | Description                                              |
| :--------- | :------------------------------------------------------- |
| `frontend` | UI implementation, Angular components, CSS, Three.js     |
| `backend`  | FastAPI endpoints, DAG nodes, services, Open3D logic     |
| `core`     | Core orchestrator, protocol handlers, shared library     |
| `docs`     | Project documentation, agent instructions                |
| `config`   | Environment variables, dependencies, tool configurations |

## Examples

- `feat(frontend): add real-time point cloud rendering with Three.js`
- `fix(backend): resolve memory leak in Open3D threadpool`
- `chore(docs): update fe-dev.md instructions for commit standards`
- `test(core): add unit tests for LIDR protocol parser`
- `refactor(frontend): use Angular Signals for performance metrics`
