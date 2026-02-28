---
name: manage-tasks
description: Creates task tracking folders and git worktrees for new features.
license: MIT
compatibility: opencode
metadata:
  audience: pm
---

## What I do

- Take a feature specification from BA and Architect and break it into tracked markdown tasks.
- Create a new git worktree for the feature development to occur in isolation.

## Guidelines

1. **Worktrees**: Use `git worktree add ../<feature-branch-name> -b <feature-branch-name>`
2. **Task Folders**: Instead of a single file, you MUST generate a dedicated folder for each feature:
   - `mkdir -p .opencode/plans/<feature_name>/`
3. **Task Files**: Inside that folder, you MUST scaffold three files with Markdown task checkboxes (`- [ ]`):
   - `.opencode/plans/<feature_name>/requirements.md` (Checklist for BA/PM acceptance)
   - `.opencode/plans/<feature_name>/technical.md` (Checklist for Developer implementations)
   - `.opencode/plans/<feature_name>/api-spec.md` (Checklist for Backend payload creation, which Frontend uses to mock)
4. **Halt**: After creating the worktree and tracking files, YOU MUST stop and Ask the user to verify the checklists **before** instructing the Developer agents to begin.
