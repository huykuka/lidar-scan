---
name: review-pr
description: Verify tests, create GitHub PRs, check comments, and merge.
license: MIT
compatibility: opencode
metadata:
  audience: qa
---

## What I do

- Run the full test suite and linters.
- Create a PR via the GitHub CLI (`gh pr create`).
- Check the PR for user comments (`gh pr view --comments`).
- If the user comments "LGTM", merge the PR (`gh pr merge`).

## Guidelines

1. **Verification**: You run `pytest` for backend and `npm run lint` / `npm run test` for frontend.
2. **Notification**: Once tests pass and you create the PR, notify the user with the PR link and stop execution. Do not merge.
3. **Checking**: When invoked again to check the PR, use `gh pr view <number> --comments`.
4. **Merging**: If and ONLY if there is a comment containing exactly "LGTM" from the user, you may run `gh pr merge --merge`. Otherwise, report the feedback back to the dev agents.
