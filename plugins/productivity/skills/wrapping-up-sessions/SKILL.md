---
name: wrapping-up-sessions
description: >-
  Use when a session's work has LANDED — merged, or intentionally abandoned — and the workspace
  should be cleaned up: "wrap up this session", "tear down the worktree", "close this out".
  Confirms the work reached the default branch, then deletes the local branch and removes the
  worktree it runs in (outside a worktree it returns to the default branch and pulls). Destructive
  — hard-stops on uncommitted work, unpushed commits, or an in-progress merge/rebase. If the PR is
  still open, drive it to green first with a PR-driving skill (e.g. relay:refining-prs).
context: fork
allowed-tools: AskUserQuestion(*), Bash(*), Read(*)
---

# wrapup — tear down a finished work session

Remove this session's workspace: branch gone, worktree gone, the work proven to be on the default
branch first. Every gate in step 2 is a HARD STOP: fail any one and stop, report exactly what
failed, and delete nothing.

**Tear down ONLY the checkout you are running in.** If you are in a worktree, that worktree is the
thing to remove, and you remove it from inside. Never run a command against the main checkout and
never move it to another branch — a different session usually owns it and may sit on its own branch
with its own uncommitted work. Read its path for the report only.

**Branches are shared.** Every worktree of a repository reads one set of refs. Deleting a branch
here deletes it for every other session too, so step 1 refuses to delete the default branch and
step 4 touches no branch but the one you are on.

This skill does NOT drive a PR. Step 3 proves the CHANGES reached the default branch; it does not
prove a PR was approved or closed. Run this skill once you already know the work has landed or is
intentionally abandoned. To drive a PR to merge-ready first, use a PR-driving skill such as
`relay:refining-prs` (if installed).

## 0. How to run the commands

A worktree-isolated session runs behind a guard that inspects every shell command and refuses
anything it cannot prove stays inside this worktree. Write each command in the plainest form:

- **One git command per call.** Chaining sometimes passes and sometimes does not, so do not rely
  on it. Never put a git command inside `$( )`.
- **Paste paths literally into git commands.** `git worktree remove "$WT"` is refused, because the
  guard cannot see where the variable points.
- **Never redirect git to another checkout.** `git -C <main checkout> …` and `cd <main checkout>`
  are both refused, and no step here needs them.
- **A command whose NAME comes from a variable is refused too** — that is why step 3 resolves
  `$CLAUDE_PLUGIN_ROOT` with `echo` first and then pastes the printed path.

A refusal is not a git error, and it is not a reason to stop the skill. It means the command was
written in a form the guard cannot verify. Rewrite it as a single plain command with literal paths
and run it again.

## 1. Identify the workspace

Record all five of these before you touch anything. Step 4 destroys the state some of them read.

- **Branch: `git rev-parse --abbrev-ref HEAD`. Write the name down now.** Step 4 detaches HEAD, and
  after that this command prints `HEAD` and the name is gone.
  - If it ALREADY prints `HEAD`, this session is detached. Go to "Detached HEAD" at the end of this
    step — do not carry `HEAD` forward as a branch name.
- **Default branch:** run `git remote set-head origin -a` FIRST, then read
  `git symbolic-ref --short refs/remotes/origin/HEAD` (strip the `origin/`). The refresh is not
  optional. `symbolic-ref` is a purely local read: if the ref is unset it errors, but if it is
  merely STALE (upstream renamed its default branch) it returns the old name with exit 0 and no
  warning, and a plain `git fetch`/`git pull` will not heal it. Every later step would then target
  the wrong branch. If the refresh and the read both fail, fall back to whichever of `main` or
  `master` appears in `git branch -r` — never assume `main`.
- **Are you in a worktree?** Run this ONE command, which prints two lines:

  ```
  git rev-parse --path-format=absolute --git-dir --git-common-dir
  ```

  The two paths are EQUAL in a main checkout and DIFFERENT in a worktree. Compare these two and
  nothing else. Do not compare `--git-dir` with `--git-common-dir` without `--path-format=absolute`:
  once the working directory is below the repository root, git prints the first absolute and the
  second relative (`../.git`), so they differ as text in a MAIN checkout and the skill would take
  the worktree path against the shared checkout.
- **Worktree path: `git rev-parse --show-toplevel`.** Use THIS in step 4, never `pwd` and never the
  directory you started in. `git worktree remove` accepts only the top level of a worktree and
  fails with "is not a working tree" on a subdirectory — and in step 4 that failure lands after the
  branch is already deleted.
- **Main checkout path:** the FIRST `worktree` line of `git worktree list --porcelain`. For the
  report only. Run nothing against it.

Then branch on what you found:

- **The branch IS the default branch.** There is no work branch to delete, and deleting it would
  break every other session in the repository: their `git rebase <default>`, `git log <default>..`,
  and `git diff <default>` all stop working. So:
  - In a worktree: run step 2, SKIP step 3, and in step 4 path A run ONLY item 1 (classify the
    lock), item 5 (prune) and item 6 (remove the worktree). Do NOT detach and do NOT delete a
    branch.
  - Not in a worktree: there is nothing to tear down. Check `git status --porcelain` is empty
    first — pulling onto a dirty tree can fail or conflict. If it is clean, run
    `git pull origin <default-branch>` then `git fetch --prune origin`; if it is dirty, report the
    changes and stop without pulling. Go to step 5 and report `nothing-to-remove`.
- **Detached HEAD** (`git rev-parse --abbrev-ref HEAD` printed `HEAD`). A previous run of this
  skill probably stopped between detaching and removing the worktree, so the branch is already
  gone. Record the sha with `git rev-parse HEAD`. Apply the first two gates of step 2 only — the
  third cannot run, because a detached HEAD has no upstream, and you must NOT report that as "the
  work exists only locally". Run step 3 with the SHA in place of the branch name; the check accepts
  one. Show the user the verdict and ask once. On a yes, run only item 1 and item 6 of path A.
- **Anything else:** continue to step 2.

## 2. Safety gates (ALL must pass)
- **Working tree clean:** `git status --porcelain` is empty. Any uncommitted or untracked change
  is a HARD STOP — list it and stop.
- **No operation in progress:** check for `MERGE_HEAD`, `rebase-merge`, `rebase-apply`,
  `CHERRY_PICK_HEAD`, or `REVERT_HEAD` in the worktree's git dir. Read the directory printed by
  `git rev-parse --path-format=absolute --git-dir` in step 1 — inside a worktree `.git` is a FILE,
  not a directory, so looking for `<worktree>/.git/MERGE_HEAD` finds nothing even mid-merge.
  Any of them is a HARD STOP. `git status --porcelain` does NOT catch this: a conflict resolved
  in favour of HEAD leaves the tree byte-identical to HEAD, so porcelain prints nothing while the
  merge is still open. Removing the worktree then discards the resolution with no warning and no
  way back — the only path in this skill that destroys unrecoverable work silently.
- **Nothing unpushed:** run `git rev-parse --abbrev-ref @{u}`.
  - **It SUCCEEDS:** `git log @{u}..HEAD --oneline` must be empty. Any commit listed is a HARD STOP.
  - **It ERRORS:** the error alone does not say why, and the two causes need opposite answers. Run
    `git config --get branch.<branch>.merge`, pasting the branch name from step 1.
    - **Empty output** — the branch never had an upstream. HARD STOP: the work exists only locally.
    - **It prints a ref** — the branch WAS pushed, and its remote-tracking ref is gone. A deleted
      remote branch does this, and so does `git fetch --prune` in ANY worktree, because remote
      refs are shared. This skill prunes in step 4, so the next teardown in the same repository
      reaches this state normally. Do NOT report the work as local-only. Instead record that this
      gate could not run, and carry one restriction into step 3: **only exit 0 may continue there.
      Exit 1 and exit 2 become a HARD STOP, not a question** — without a remote ref, a commit made
      after the last push exists nowhere else, and the usual ask would talk the user into deleting
      it.

When this gate passes normally it proves every commit is on the remote, and that is what makes the
deletions in step 4 safe.

## 3. Confirm the work landed

Run this BEFORE you delete or detach anything, and run it every time — not only when something
refuses. Step 4 detaches HEAD, and a detached HEAD sits ON the branch tip, so `git branch -d`
afterwards always succeeds and proves nothing. This check is the only landed-ness evidence the
skill has.

First refresh the ref you are about to compare against:

```
git fetch origin <default-branch>
```

This fetch is not optional. Nothing earlier in the skill fetched, and a local default branch that
has not yet seen the squash commit reads as "never merged" — wrong in the dangerous direction. If
the fetch FAILS, stop and report that. A check against a stale ref is not evidence, and a report
that says NOT-CONTAINED when the real cause was an unreachable remote misleads.

Then run the equivalence check. The script lives in the plugin, not in the user's repository, so
resolve its directory first and paste the result:

```
echo "$CLAUDE_PLUGIN_ROOT"
```

Then call the script by the printed absolute path, with no `bash` prefix and no variable:

```
<printed path>/scripts/branch-landed.sh origin/<default-branch> <branch>
```

Two plain commands, because the guard refuses a command whose name is built from a variable — the
one-liner `bash "${CLAUDE_PLUGIN_ROOT}/scripts/branch-landed.sh" …` is rejected before it runs.
If `echo` prints nothing, say so and stop: without the plugin root there is no check, and a missing
check is not a pass.

**Read the EXIT CODE — never parse the text.**

Ancestry alone cannot answer this question. A squash merge rewrites the branch into one new commit,
so not one of the original commits stays an ancestor of the default branch. The check compares
CONTENT instead: whether every commit has an equivalent patch upstream (a rebase or cherry-pick
merge), and then whether the branch's whole diff is upstream as one squashed patch.

- **Exit 0 — CONTAINED.** The changes are already on the default branch. Go to step 4 and do NOT
  ask. Keep the script's one evidence line: it names the squash commit, so your report cites a sha
  and not only a verdict.
- **Exit 1 — NOT-CONTAINED.** No content match. Gather evidence and ask, below.
- **Exit 2 — INCONCLUSIVE.** A git call failed, or the two histories have no merge base. Treat it
  exactly like exit 1 — an absent answer is not a negative answer.

If step 2's unpushed gate could not run (the upstream was gone), exit 1 and exit 2 are a HARD STOP
here instead of a question. Only CONTAINED may continue.

Two properties of the check to carry into your report:
- CONTAINED is one-way proof. It proves the work landed; NOT-CONTAINED does NOT prove the work did
  not land. The check compares patch identity, which includes the diff context lines, so a default
  branch that edited the SAME lines before the squash landed shifts that context and reads
  NOT-CONTAINED for a branch that truly merged. Conflict resolution during the merge does the same.
  That is why exit 1 asks instead of refusing.
- A branch that was squash-merged and then REVERTED reads CONTAINED. That is correct for the
  question asked — the changes did land, and the revert is a separate later act. Nothing is lost
  either way, because the step-2 gate already proved every commit is on the remote.

**On exit 1 or exit 2, gather evidence and ask.** Run `git ls-remote --heads origin <branch>` and
read it in this order:
- **Exit code nonzero** (128 on an unreachable remote, bad auth, wrong remote name): the result is
  INCONCLUSIVE, not evidence. Stop and report — an unreachable remote prints nothing on stdout,
  exactly like a deleted branch, and inferring "gone" from it would delete unmerged work on a
  transient network blip.
- **Exit 0 with a ref line:** the branch still exists on the remote — a signal the work may NOT
  have landed.
- **Exit 0 with empty output:** the remote branch is gone, which usually means a completed merge
  with auto-delete.

Show the user both results — the equivalence verdict and the remote-branch state — and get explicit
confirmation before you continue to step 4. This is the one place the skill asks.

## 4. Tear down the checkout you are in

Take path A if step 1 found a worktree, path B if it did not. Skip this whole step if step 1
already reported there was nothing to tear down.

### Path A — you are in a worktree: remove it from inside

You CAN remove the worktree you are standing in. `git worktree remove` accepts its own path and
deletes the directory. Do not `cd` anywhere first.

Do NOT call **ExitWorktree**. It only acts on a worktree that `EnterWorktree` created in the same
session, and it is a silent no-op for every other worktree — including one made by `git worktree
add`, one inherited from an earlier session, and this fork. `git worktree remove` is the path.

Run these IN ORDER. The remove is last because it deletes the directory the shell is standing in:
every command after it fails with "Unable to read current working directory".

1. **Classify the lock, before you change anything.** Run `git worktree list --porcelain`. It lists
   EVERY worktree in the repository. Find the block whose `worktree` line is the path you captured
   in step 1, and read ONLY the `locked <reason>` line inside that block. No such line means no
   lock — go to item 2.
   - The reason reads `claude session <name> (pid <N> start <date>)` → the harness wrote it for the
     session that works here, and you are the session closing it. Run
     `git worktree unlock <worktree path>` and continue.
   - The reason is any other text → a person locked it on purpose. STOP and report the reason.
   - `locked` lines on OTHER worktrees are report material only. They never block
     `git worktree remove <your own path>`, so never stop for one and never unlock one.
   - Never use `remove -f -f`. A single `--force` does not override a lock either, so reaching for
     force only hides the question of who owns the lock.
2. **Free the branch:** `git checkout --detach`. `git branch -d` refuses while the branch is checked
   out here, and this is the only way to release it from inside. The worktree is about to be
   deleted, so the detached state costs nothing. **Skip this and item 3 entirely if step 1 found you
   on the default branch.**
3. **Delete the branch:** `git branch -d <branch>`. Paste the name you wrote down in step 1.
   **This succeeds because HEAD now sits on the branch tip — it is not evidence the work merged.**
   Step 3 is the evidence. If it still refuses, the branch is checked out in ANOTHER worktree: say
   which one and stop, because `-D` will not override that either.
4. **Verify now, while you still have a working directory:** `git branch --list <branch>` must be
   empty. Everything after item 6 is unverifiable, so check here.
5. **Prune the remote-tracking ref:** `git fetch --prune origin`. If it fails, the only cost is a
   stale ref — note it and carry on.
6. **Remove the worktree, LAST:** `git worktree remove <worktree path>`. Paste the top-level path
   from step 1. Exit 0 IS the proof the directory is gone; you cannot check afterwards.

**Run no command after the remove.** The working directory no longer exists. Write the report from
what you already recorded.

### Path B — you are not in a worktree

1. `git checkout <default-branch>`.
2. `git branch -d <branch>`. Here a refusal is real, because HEAD is on the default branch. Step 3
   already answered whether the work landed: on exit 0 run `git branch -D <branch>`; on exit 1 or 2
   you already asked the user.
3. `git pull origin <default-branch>`.
4. `git fetch --prune origin` to drop the stale remote-tracking ref. This must stay a SEPARATE
   command: `git pull --prune origin <default-branch>` does NOT prune the deleted branch, because a
   refspec on the command line limits pruning to refs matching that refspec.

If the branch is already gone by the time you reach it, that is SUCCESS, not a failure to escalate.

## 5. Verify and close

Say which path you took: **`self-removal`** (path A), **`return-to-default`** (path B), or
**`nothing-to-remove`** (the step-1 early exit).

Confirm with evidence, not assumption:
- Path A: `git branch --list <branch>` was empty at item 4, and `git worktree remove` exited 0.
  If step 1 found you on the default branch, say `self-removal, no branch deleted` and drop the
  branch evidence line — keeping that branch was the correct outcome.
- Path B: `git branch --list <branch>` is empty, `git worktree list` no longer shows the path,
  `git rev-parse --abbrev-ref HEAD` is the default branch, and `git status` reports up to date.

**If any check fails, teardown is incomplete.** Say exactly what is left over (a surviving branch,
an un-removed worktree, a checkout stuck on the wrong branch) and do NOT tell the user the session
is safe to close — a dangling worktree that everyone stops tracking is the failure this skill exists
to prevent. Stop there and let them decide.

Distinguish which half failed. The branch delete and the worktree removal are irreversible; the
checkout and pull in path B are not. On path A, if the branch is gone but the removal failed, say
so: the worktree is still on disk with a detached HEAD, the commits survive on the remote, and only
the removal needs finishing. Say that re-running this skill will report a detached HEAD and pick up
from there.

Report a one-line summary and the landed-ness evidence line from step 3. On path A, add that the
CALLING session's folder no longer exists, because you just deleted it — that session cannot run
another command and should be closed. Then tell the user it is safe to close: if backgrounded,
`claude stop <id>`; otherwise exit. (You cannot self-terminate the process; do not pretend to.)
State plainly that the main checkout was not touched.
