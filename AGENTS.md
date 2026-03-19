# LiDAR Standalone - Architecture & Agent Workflows

## Core Architecture & Technical Context

The `lidar-standalone` project is a high-performance Point Cloud Processing system with integrated performance monitoring.

- **Backend Stack**: Python 3.10+, FastAPI, Open3D, Asyncio.
- **Backend Architecture**: A dynamic Directed Acyclic Graph (DAG) orchestration engine mapping physical data flows entirely through decoupled, pluggable _nodes_ (Modules). Heavy Open3D operations run on threadpools to prevent blocking the async FastAPI event loop.
- **Frontend Stack**: Angular 20 (Signals, Standalone Components exclusively), Tailwind CSS, Synergy UI, Three.js.
- **Frontend Architecture**: Directly manipulates WebGL `BufferGeometry` arrays for 60FPS parsing of 100k+ dense point clouds.
- **Protocols**: Fast binary WebSocket streaming (the `LIDR` protocol) overriding standard HTTP JSON parsing for real-time sensor data. WebSocket topics include automatic cleanup and duplicate prevention during node lifecycle changes.
- **Performance Monitoring**: Low-overhead (<1%) real-time metrics collection covering DAG nodes, Open3D operations, WebSocket performance, and Three.js rendering metrics with Angular dashboard visualization.

CRITICAL: When you need detailed API specifics or rules, use your Read tool on these references:

- Backend Rules: @.opencode/rules/backend.md
- Frontend Rules: @.opencode/rules/frontend.md
- Protocol Specs: @.opencode/rules/protocols.md

## Feature Tracking & Folders

Features are tracked in dedicated subdirectories located in `.opencode/plans/<feature-name>/`.
Each folder contains:

- `requirements.md`: Feature specs and acceptance criteria (BA, PM, Arch).
- `technical.md`: Technical implementation direction, DAG routing, UI logic (Arch, Devs).
- `api-spec.md`: The API contract. Frontend (`@fe-dev`) MUST mock data from this while Backend (`@be-dev`) is working.
- `backend-tasks.md` & `frontend-tasks.md`: Detailed implementation tasks per layer (Devs).
- `qa-tasks.md`: Test plans, TDD checklists, and QA specific tasks (@qa).
- `qa-report.md`: Final test report and coverage results (@qa).
  All Dev and QA agents MUST update checkboxes (`[ ]` to `[x]`) in these files as steps complete.

#### Planning Phase

1. **@ba/@pm**: Define performance requirements and acceptance criteria in `requirements.md`
2. **@architecture**: Design monitoring architecture, data collection points, and dashboard integration in `technical.md`
3. **@architecture**: Define metrics API contracts in `api-spec.md`

#### Development Phase

1. **@be-dev**: Implement backend following tasks in `backend-tasks.md`
2. **@fe-dev**: Build Angular frontend using specifications in `frontend-tasks.md`
3. Both devs MUST mock API data per `api-spec.md` during parallel development

#### QA & Review Phase

1. **@qa**: Validate metrics accuracy, dashboard functionality, and performance overhead requirements
2. **@qa**: Conduct load testing to ensure <1% performance impact
3. **@review**: Code review focusing on monitoring integration and performance impact
4. **@docs**: Update documentation to reflect monitoring capabilities and usage

<!-- gitnexus:start -->

# GitNexus — Code Intelligence

This project is indexed by GitNexus as **lidar-standalone** Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/lidar-standalone/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool             | When to use                   | Command                                                                 |
| ---------------- | ----------------------------- | ----------------------------------------------------------------------- |
| `query`          | Find code by concept          | `gitnexus_query({query: "auth validation"})`                            |
| `context`        | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})`                              |
| `impact`         | Blast radius before editing   | `gitnexus_impact({target: "X", direction: "upstream"})`                 |
| `detect_changes` | Pre-commit scope check        | `gitnexus_detect_changes({scope: "staged"})`                            |
| `rename`         | Safe multi-file rename        | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher`         | Custom graph queries          | `gitnexus_cypher({query: "MATCH ..."})`                                 |

## Impact Risk Levels

| Depth | Meaning                               | Action                |
| ----- | ------------------------------------- | --------------------- |
| d=1   | WILL BREAK — direct callers/importers | MUST update these     |
| d=2   | LIKELY AFFECTED — indirect deps       | Should test           |
| d=3   | MAY NEED TESTING — transitive         | Test if critical path |

## Resources

| Resource                                          | Use for                                  |
| ------------------------------------------------- | ---------------------------------------- |
| `gitnexus://repo/lidar-standalone/context`        | Codebase overview, check index freshness |
| `gitnexus://repo/lidar-standalone/clusters`       | All functional areas                     |
| `gitnexus://repo/lidar-standalone/processes`      | All execution flows                      |
| `gitnexus://repo/lidar-standalone/process/{name}` | Step-by-step execution trace             |

## Self-Check Before Finishing

Before completing any code modification task, verify:

1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task                                         | Read this skill file                                        |
| -------------------------------------------- | ----------------------------------------------------------- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md`       |
| Blast radius / "What breaks if I change X?"  | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?"             | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md`       |
| Rename / extract / split / refactor          | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md`     |
| Tools, resources, schema reference           | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md`           |
| Index, status, clean, wiki CLI commands      | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md`             |

<!-- gitnexus:end -->
