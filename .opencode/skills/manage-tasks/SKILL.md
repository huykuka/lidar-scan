---
name: manage-tasks
description: Creates task tracking folders and feature branches for new features.
license: MIT
compatibility: opencode
metadata:
  audience: pm
---

## What I do

- Take a feature specification from BA and Architect and break it into tracked markdown tasks.
- Create a new feature branch for the feature development to occur in isolation.

## Guidelines

1. **Branches**: Use `git checkout -b <feature-branch-name>` from the current directory.
2. **Task Folders**: Instead of a single file, you MUST generate a dedicated folder for each feature:
   - `mkdir -p .opencode/plans/<feature_name>/`
3. **Task Files**: Inside that folder, you MUST scaffold six files with Markdown task checkboxes (`- [ ]`):
   - `.opencode/plans/<feature_name>/requirements.md` (Checklist for BA/PM acceptance)
   - `.opencode/plans/<feature_name>/technical.md` (Checklist for General Technical implementations)
   - `.opencode/plans/<feature_name>/api-spec.md` (Checklist for Backend payload creation, which Frontend uses to mock)
   - `.opencode/plans/<feature_name>/backend-tasks.md` (Checklist specifically for `@be-dev` execution)
   - `.opencode/plans/<feature_name>/frontend-tasks.md` (Checklist specifically for `@fe-dev` execution)
   - `.opencode/plans/<feature_name>/qa-tasks.md` (Checklist for `@qa` execution and TDD tracking)
4. **Halt**: After creating the branch and tracking files, YOU MUST stop and Ask the user to verify the checklists **before** instructing the Developer agents to begin.
