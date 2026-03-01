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
2. **Task Folders**: Instead of a single file, you MUST generate a dedicated folder for each feature INSIDE the new worktree:
   - `mkdir -p ../<feature-branch-name>/.opencode/plans/<feature_name>/`
3. **Task Files**: Inside that worktree folder, you MUST scaffold six files with Markdown task checkboxes (`- [ ]`):
   - `../<feature-branch-name>/.opencode/plans/<feature_name>/requirements.md` (Checklist for BA/PM acceptance)
   - `../<feature-branch-name>/.opencode/plans/<feature_name>/technical.md` (Checklist for General Technical implementations)
   - `../<feature-branch-name>/.opencode/plans/<feature_name>/api-spec.md` (Checklist for Backend payload creation, which Frontend uses to mock)
   - `../<feature-branch-name>/.opencode/plans/<feature_name>/backend-tasks.md` (Checklist specifically for `@be-dev` execution)
   - `../<feature-branch-name>/.opencode/plans/<feature_name>/frontend-tasks.md` (Checklist specifically for `@fe-dev` execution)
   - `../<feature-branch-name>/.opencode/plans/<feature_name>/qa-tasks.md` (Checklist for `@qa` execution and TDD tracking)
4. **Halt**: After creating the worktree and tracking files, YOU MUST stop and Ask the user to verify the checklists **before** instructing the Developer agents to begin.
