---
name: wrapping-up-sessions
description: >-
  Use when a session's work has LANDED — merged, or intentionally abandoned — and the workspace
  should be cleaned up: "wrap up this session", "tear down the worktree", "close this out".
  Removes the worktree, deletes the local branch, returns the working folder to the default
  branch, and pulls latest. Destructive and does NOT verify that anything merged — hard-stops on
  uncommitted work, unpushed commits, or an in-progress merge/rebase. If the PR is still open,
  drive it to green first with a PR-driving skill (e.g. relay:refining-prs, if installed).
context: fork
allowed-tools: AskUserQuestion(*), Bash(*), Read(*)
---

# wrapup — tear down a finished work session

Return the workspace to a clean default-branch state — worktree gone, branch gone, latest pulled.
This deletes a worktree and a branch, so every gate in step 2 is a HARD STOP: fail any one and
stop, report exactly what failed, and delete nothing.

This skill does NOT check whether a PR merged. Run it only once you already know the work has
landed or is intentionally abandoned — nothing here will catch a still-open PR, and the gates
below pass trivially for unmerged work. To drive a PR to merge-ready first, use a PR-driving skill such as `relay:refining-prs` (if installed).

## 1. Identify the workspace
- Branch: `git rev-parse --abbrev-ref HEAD`.
- Default branch: run `git remote set-head origin -a` FIRST, then read
  `git symbolic-ref --short refs/remotes/origin/HEAD` (strip the `origin/`). The refresh is not
  optional. `symbolic-ref` is a purely local read: if the ref is unset it errors, but if it is
  merely STALE (upstream renamed its default branch) it returns the old name with exit 0 and no
  warning, and a plain `git fetch`/`git pull` will not heal it. Every later step would then target
  the wrong branch. If the refresh and the read both fail, fall back to whichever of `main` or
  `master` appears in `git branch -r` — never assume `main`.
- Worktree check: `git rev-parse --git-common-dir` differs from `--git-dir`. Capture the worktree
  path, and the main checkout path from the FIRST line of `git worktree list` (the main working
  tree is always listed first).
- If already on the default branch and not in a worktree, there is nothing to tear down. Skip
  step 3's teardown, but still check `git status --porcelain` is empty first — pulling onto a
  dirty tree can fail or conflict, and nothing should mutate the default branch unchecked. If it
  is clean, run `git pull origin <default-branch>` and `git fetch --prune origin`; if it is dirty,
  report the changes and stop without pulling. Either way go to step 4 and report that there was
  nothing to remove.

## 2. Safety gates (ALL must pass)
- **Working tree clean:** `git status --porcelain` is empty. Any uncommitted or untracked change
  is a HARD STOP — list it and stop.
- **No operation in progress:** check for `MERGE_HEAD`, `rebase-merge`, `rebase-apply`,
  `CHERRY_PICK_HEAD`, or `REVERT_HEAD` in the worktree's git dir (`git rev-parse --git-dir`).
  Any of them is a HARD STOP. `git status --porcelain` does NOT catch this: a conflict resolved
  in favour of HEAD leaves the tree byte-identical to HEAD, so porcelain prints nothing while the
  merge is still open. Removing the worktree then discards the resolution with no warning and no
  way back — the only path in this skill that destroys unrecoverable work silently.
- **Nothing unpushed:** run `git rev-parse --abbrev-ref @{u}` first. If it ERRORS, the branch has
  no upstream — HARD STOP, the work exists only locally (do not read the error as an inconclusive
  tool failure). If it succeeds, `git log @{u}..HEAD --oneline` must be empty; any commit listed
  is a HARD STOP.

State what you're about to remove (branch name, worktree path) and proceed. Do not ask for
confirmation beyond this — the gates ARE the safety. The single exception is the force-delete in
step 3, and only when the equivalence check there cannot confirm the work landed.

## 3. Tear down and return to the default branch
Skip this whole step if step 1 found no worktree AND you are already on the default branch.

- **Remove the worktree** (skip if not in one). You cannot remove the worktree you're standing in,
  so `cd` to the main checkout captured in step 1 first, then run `git worktree remove <path>`.

  Do NOT call **ExitWorktree** here, even if the tool is offered. It acts only on the context that
  calls it — this skill runs in a forked context, so that is the fork and not the session you are
  closing. `git worktree remove` is the only path. Two consequences. Nothing moves you back to the
  main checkout for you — the `cd` above is the only thing that does it. And the folder the PARENT
  session sits in does not move either: once the worktree is gone, that session points at a
  directory that no longer exists. This is harmless only because step 4 ends by telling the user
  to close that session, so say it in the closing report.

  Add `--force` only when the sole obstacle is the cwd, never to discard real changes — it drops
  uncommitted working-tree state but never commits, which survive in the shared object database.
  A LOCKED worktree refuses even one `--force` and needs `-f -f`; treat hitting that as a signal
  someone locked it deliberately, and stop rather than double-forcing.

- **Confirm where you are.** `git rev-parse --show-toplevel` must now report the main checkout.
  Do not run the next bullet until it does.

- **Delete the branch:** `git branch -d <branch>`. Two distinct reasons it can refuse:
  - *The branch is still checked out in a worktree* — the previous bullet did not actually remove
    it. `-D` will NOT override this. Go back and remove the worktree, don't escalate the flag.
  - *Git reports the branch is not fully merged.* **Do not reflexively escalate to `-D`.** This
    refusal looks exactly the same whether the branch was squash- or rebase-merged (safe to
    delete) or was never merged at all (deleting it destroys the only local copy). Ancestry
    cannot separate the two: a squash merge rewrites the branch into one new commit, so not one
    of the original commits stays an ancestor of the default branch, and `-d` refuses a landed
    branch and an abandoned branch with the same words.

    Compare the CONTENT instead. First refresh the ref you are about to compare against:

    ```
    git fetch origin <default-branch>
    ```

    This fetch is not optional. Nothing earlier in the skill fetched, and the `git pull` two
    bullets below runs only AFTER the deletion. A local default branch that has not yet seen the
    squash commit reads as "never merged", which is the wrong answer in the dangerous direction.
    If the fetch FAILS, stop and report that — a check against a stale ref is not evidence, and a
    report that says NOT-CONTAINED when the real cause was an unreachable remote misleads.

    Then run the equivalence check and read its EXIT CODE — never parse its text:

    ```
    bash "${CLAUDE_PLUGIN_ROOT}/scripts/branch-landed.sh" origin/<default-branch> <branch>
    ```

    (The fork's working directory is the user's repository, so plugin-relative paths do not
    resolve. `${CLAUDE_PLUGIN_ROOT}` is the only form that works.)

    - **Exit 0 — CONTAINED.** The branch's changes are already on the default branch, as a
      squash commit or as re-applied patches. This is the green light: print the script's one
      evidence line, run `git branch -D <branch>`, and do NOT ask. The evidence line names the
      squash commit, so the report cites a sha and not only a verdict.
    - **Exit 1 — NOT-CONTAINED.** No content match. Go to the ask below.
    - **Exit 2 — INCONCLUSIVE.** A git call failed, or the two histories have no merge base.
      Treat it exactly like exit 1 — an absent answer is not a negative answer.

    Two properties of the check to carry into your report:
    - CONTAINED is one-way proof. It proves the work landed; NOT-CONTAINED does NOT prove the
      work did not land. The check compares patch identity, which includes the diff context
      lines, so a default branch that edited the SAME lines before the squash landed shifts that
      context and reads NOT-CONTAINED for a branch that truly merged. Conflict resolution during
      the merge does the same. That is why exit 1 asks instead of refusing.
    - A branch that was squash-merged and then REVERTED reads CONTAINED. That is correct for the
      question asked — the changes did land, and the revert is a separate later act. Nothing is
      lost either way, because the step-2 gate already proved every commit is on the remote.

    **On exit 1 or exit 2, gather evidence and ask.** Run `git ls-remote --heads origin <branch>`
    and read it in this order:
    - **Exit code nonzero** (128 on an unreachable remote, bad auth, wrong remote name): the
      result is INCONCLUSIVE, not evidence. Stop and report — an unreachable remote prints
      nothing on stdout, exactly like a deleted branch, and inferring "gone" from it would
      force-delete unmerged work on a transient network blip.
    - **Exit 0 with a ref line:** the branch still exists on the remote — a signal the work may
      NOT have landed.
    - **Exit 0 with empty output:** the remote branch is gone, which usually means a completed
      merge with auto-delete.

    Show the user both results — the equivalence verdict and the remote-branch state — and get
    explicit confirmation before running `git branch -D <branch>`. This is the one place the
    skill asks, and it now covers only what the check cannot prove.

  If the branch is already gone by the time you reach this bullet, that is SUCCESS, not a failure
  to escalate.
- `git checkout <default-branch>`, then `git pull origin <default-branch>`.
- `git fetch --prune origin` to drop the stale remote-tracking ref. This must stay a SEPARATE
  command: `git pull --prune origin <default-branch>` does NOT prune the deleted branch, because
  a refspec on the command line limits pruning to refs matching that refspec. Do not merge these
  two into one call.

## 4. Verify and close
Confirm with evidence, don't assume:
- `git worktree list` no longer shows the removed path.
- `git branch --list <branch>` is empty.
- `git rev-parse --abbrev-ref HEAD` is the default branch and `git status` reports up to date.

**If any check fails, teardown is incomplete.** Say exactly what is left over (an un-removed
worktree, a surviving branch, a checkout stuck on the wrong branch) and do NOT tell the user the
session is safe to close — a dangling worktree that everyone stops tracking is the failure this
skill exists to prevent. Stop there and let them decide.

Distinguish which half failed. The deletions in step 3 are irreversible; the checkout and pull
that follow them are not. If the branch and worktree are gone but the resync failed (network,
conflict on the default branch), say so plainly — the teardown DID happen and re-running the
skill will not repeat it; only the return-to-default part needs finishing.

Only when every check passes: report a one-line summary, say that the calling session's folder
still points at the removed worktree, then tell the user it's safe to close this session — if
backgrounded, `claude stop <id>`; otherwise exit. (You cannot self-terminate the process; do not
pretend to.) Report the same way on the step-1 early exit, noting that there was nothing to tear
down.
