---
name: land
description:
  Merge an explicitly authorized HotKey pull request after checking its current
  head, conflicts, review findings, and configured CI.
---

# Land

## Scope

Use this workflow only when the user asks to merge or land a pull request.
Direct main pushes use the push workflow. Follow `AGENTS.md` and the actual
`.github/PULL_REQUEST_TEMPLATE.md`; the repository has no local review watcher
or automatic Codex Review workflow.

## Steps

1. Resolve the PR in the configured repository and attach it to the chat.
2. Inspect the current PR head, base, mergeability, CI, and review findings.
   Fetch the branch before editing; preserve unrelated local changes.
3. Resolve applicable findings within the authorized scope and run the checks
   required by `AGENTS.md`. Do not mark review feedback resolved without evidence.
4. If the PR conflicts with main, integrate current origin/main, resolve the
   conflicts, and rerun affected checks. Publish using the configured remote.
5. Wait for the configured checks on the current head. Use bounded waits and
   report progress; do not wait for an assumed review bot or removed helper.
   If checks are absent or unavailable, report that limitation accurately.
6. Confirm no blocking review finding remains and the head has not changed,
   then merge using the authorized method. Do not bypass branch protection or
   delete remote branches unless separately authorized.
7. Confirm the PR is merged and report its URL, merge SHA, and actual CI result.

## Commands

Use the explicit repository to avoid a global GH_REPO selecting another project.

```sh
gh pr view <pr> --repo StephenQiu30/hotkey-server --json number,url,headRefOid,baseRefName,mergeable,reviewDecision,statusCheckRollup
gh pr checks <pr> --repo StephenQiu30/hotkey-server
gh run view <run-id> --repo StephenQiu30/hotkey-server --log-failed
gh pr merge <pr> --repo StephenQiu30/hotkey-server --squash --match-head-commit <verified-head-sha>
```

The example merge uses squash. Use a different method when requested by the user.
GitHub comments or review requests require explicit authorization to send them.
