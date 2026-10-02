---
name: commit
description:
  Create a well-formed git commit from current changes using session history for
  rationale and summary; use when asked to commit, prepare a commit message, or
  finalize staged work.
---

# Commit

## Goals

- Produce a commit that reflects the actual code changes and the session context.
- Follow `AGENTS.md` commit discipline and the architecture in `PROJECT.md`.
- Include both summary and rationale in the body.

## Commit title convention

Every title must use the project format with a non-empty scope:

```text
<type>(<scope>):<中文描述>
```

Allowed types are `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `perf`,
`build`, `ci`, and `revert`. Use a stable lowercase scope such as `backend`,
`frontend`, `identity`, `docs`, `ci`, or `repo`. Do not use `impl`, an empty
scope, or an unscoped prefix. Do not add a space after the colon. The Chinese
description must be a concise Simplified Chinese verb-object phrase; do not
use an English description.

For behavior changes, reproduce the failure before implementation, then include
the fix, its tests, and corresponding contracts in one independently reviewable
commit.

Do not mix unrelated types in one commit. Split by type when practical.

## Inputs

- Session history for intent and rationale.
- `git status`, `git diff`, and `git diff --staged` for actual changes.
- `AGENTS.md` and `PROJECT.md`.

## Steps

1. Read session history to identify scope, intent, and rationale.
2. Inspect the working tree and staged changes (`git status`, `git diff`, `git diff --staged`).
3. Stage the exact intended paths after confirming scope; preserve unrelated edits.
4. Sanity-check newly added files; flag build artifacts, logs, or temp files before committing.
5. If staging is incomplete or includes unrelated files, fix the index or ask for confirmation.
6. Choose the allowed type and stable non-empty scope that match the staged diff.
7. Write a concise Simplified Chinese description, <= 72 characters. Format: `<type>(<scope>):<中文描述>`.
8. Write the body in Chinese with change summary, rationale, and tests or validation run (or why not run).
9. Wrap body lines at 72 characters.
10. Create the commit message with a here-doc or temp file and use `git commit -F <file>`.
11. Commit only when the message matches the staged changes.

## Output

- A single commit whose message reflects the session and discipline above.

## Template

```
<type>(<scope>):中文主题

变更摘要：
- <变更内容>

变更原因：
- <变更原因>

验证：
- <验证命令或“未运行（原因）”>
```
