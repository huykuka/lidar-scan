# Commit Command Reference

## Name

`commit`

## Description

Enforce standardized commit messages following the project's Conventional Commits standard.

## Usage

```bash
/commit "<type>(<scope>): <description>"
```

### Examples

```bash
# Frontend Feature
/commit "feat(frontend): implement signal-based state management"

# Backend Fix
/commit "fix(backend): correct WebSocket frame fragmentation"

# Documentation Update
/commit "docs(core): update API documentation for DAG nodes"
```

## Agent Guidelines

1. **Phase Commits**: When completing a logical phase in your task list, you MUST use this standard.
2. **Scoping**: Always specify `(frontend)` or `(backend)` depending on your agent role.
3. **Imperative Mood**: Use "add", "fix", "change" instead of "added", "fixed", "changed".

## Reference

This command is defined by the skill at `.opencode/skills/commit/SKILL.md`.
