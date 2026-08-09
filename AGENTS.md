# Agent Instructions

## Project

**LiDAR Studio** — real-time LiDAR point cloud processing and 3D visualisation.

- **Backend**: Python 3.12 · FastAPI · SQLAlchemy · SQLite (`app/`)
- **Frontend**: Angular 20 · angular-three/Three.js · Tailwind · Synergy Design System (`web/`)
- **Processing nodes**: plugin architecture — builtin (`app/modules/`) or extension (`app/plugins/installed/`)
- **Transport**: REST `/api/v1/` + binary WebSocket LIDR protocol
- **Package manager (BE)**: `uv` — use `uv run <cmd>`, never `python` directly
- **Package manager (FE)**: `npm` — run inside `web/`

## Before starting any work

1. Read `README.md` for quick-start and local dev setup.
2. Read `.opencode/rules/backend.md` (BE work) and/or `.opencode/rules/frontend.md` (FE work).
3. For new processing nodes, read `app/plugins/installed/README.md` — plugin contract checklist.

## Agent system

This repo uses a multi-agent OpenCode setup. Agents are in `.opencode/agents/`:

| Agent | Role |
|---|---|
| `master` | Orchestrator — classifies request, clarifies, plans, delegates. Never writes code. |
| `plan-reviewer` | Reviews master's plan before delegation. Blocks on missing contracts or vague AC. |
| `be-dev` | Backend developer — FastAPI, SQLAlchemy, plugins, tests. |
| `be-reviewer` | Reviews BE implementation. Dispatches fixes back to `@be-dev`. |
| `fe-dev` | Frontend developer — Angular, Three.js, Synergy, tests. |
| `fe-reviewer` | Reviews FE implementation. Dispatches fixes back to `@fe-dev`. |

Flow for new features:
```
master §0 classify → §1 clarify → §2 plan → @plan-reviewer → §3 parallel delegate
  ├── @be-dev → @be-reviewer (fix loop) → ✅ report master
  └── @fe-dev → @fe-reviewer (fix loop) → ✅ report master
```

Bug fixes skip plan-reviewer and go straight to targeted delegation.

## Key commands

```bash
# Backend dev server
uv run uvicorn main:app --reload --port 8005

# Backend tests
uv run pytest

# Frontend dev server (inside web/)
pnpm start

# Frontend tests (inside web/)
pnpm test

# Pack a plugin for upload
bash scripts/pack_plugin.sh app/plugins/installed/<name>

# Upload plugin to running instance
curl -X POST http://localhost:8005/api/v1/nodes/plugins/upload \
     -F "file=@plugin_packages/<name>.zip"
```

## Plugin development

New processing nodes go in one of two places — master always clarifies which:

- **Builtin** (`app/modules/<category>/`): ships with app, requires redeploy
- **Extension plugin** (`app/plugins/installed/<name>/`): hot-loadable via upload API

See `app/plugins/installed/README.md` and `.opencode/skills/be-add-feature/SKILL.md` for the full blueprint.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **lidar-scan** (9113 symbols, 19149 relationships, 175 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/lidar-scan/context` | Codebase overview, check index freshness |
| `gitnexus://repo/lidar-scan/clusters` | All functional areas |
| `gitnexus://repo/lidar-scan/processes` | All execution flows |
| `gitnexus://repo/lidar-scan/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
