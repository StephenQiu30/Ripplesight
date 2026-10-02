---
name: push
description:
  Push authorized HotKey changes to the configured origin and target branch;
  create or update a pull request only when requested by the user.
---

# Push

## Scope

Follow `AGENTS.md` for commit format and validation, and `PROJECT.md` for
architecture. Preserve unrelated work and use the existing origin URL.
A request to push to main authorizes a direct push to main; it does not require
creating a pull request.

## Steps

1. Inspect the branch, worktree, staged changes, configured remote, and current
   remote head. Confirm the target matches the user's request.
2. Commit the exact authorized paths with a Chinese message in the required
   `type(scope):description` format. Keep each commit independently reviewable.
3. Run checks appropriate to the actual change. Backend checks use uv, Ruff,
   mypy, and pytest. Frontend checks use pnpm, ESLint, TypeScript, Vitest,
   Prettier, and the production build. Contract and database changes follow
   their real OpenAPI and isolated PostgreSQL checks in `AGENTS.md`.
4. Fetch origin and inspect divergence. If the remote advanced, integrate it
   without overwriting unrelated work and rerun affected checks.
5. Push normally to the authorized branch. Do not force-push main or change
   remotes to bypass authentication, permission, or branch protection failures.
6. Confirm the remote SHA matches the local commit. Inspect CI runs for that
   exact SHA and report failures or unfinished checks accurately.
7. If the user requested a pull request, use the actual template at
   `.github/PULL_REQUEST_TEMPLATE.md`. Keep its title and body aligned with the
   final scope and validation, then attach the resulting PR to the chat.

## Commands

Pass the repository explicitly to gh so a global GH_REPO cannot select another
project. Resolve it from the configured origin; for this repository it is
`StephenQiu30/hotkey-server`.

```sh
git status --short --branch
git remote -v
git fetch origin
git rev-list --left-right --count HEAD...origin/main
git push origin HEAD:main
git ls-remote origin refs/heads/main
gh run list --repo StephenQiu30/hotkey-server --branch main --commit <sha>
```

The main push commands above apply only when main is the authorized target.
For a requested PR, use `gh pr create` or `gh pr edit` with an explicit repo and
write multiline bodies to a temporary file for `--body-file`.
