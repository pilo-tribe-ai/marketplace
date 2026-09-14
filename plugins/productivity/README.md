# productivity

Small, model-callable skills for moving work between sessions and agents.

**Version:** 0.10.0

## What's New in v0.10.0

- **`wrapping-up-sessions` can now finish from inside the worktree it is closing.** That is the
  only place it normally runs, and three defects made the teardown unreachable there.
- **It removes the worktree from inside, instead of `cd`-ing to the main checkout first.** A
  worktree-isolated session runs behind a shell guard that refuses `cd <other checkout>` and
  `git -C <other checkout>` alike, so the one removal path the skill offered did not exist from
  where the skill runs. The premise was wrong as well: `git worktree remove` accepts its own path
  and deletes the directory. Step 4 path A now runs in a fixed order — classify the lock,
  `git checkout --detach` to free the branch, `git branch -d`, `git fetch --prune`, verify, and
  remove the worktree **last**, because the remove deletes the directory the shell stands in and
  every later command fails with "Unable to read current working directory".
- **A harness lock is no longer read as a person's lock.** Claude Code locks a worktree itself and
  names the owning session and pid in the reason, so the old "someone locked it deliberately, stop"
  rule fired on the normal case: a session closing its own workspace, which is live by definition.
  Step 4 reads the reason from `git worktree list --porcelain`. A `claude session <name> (pid <N>
  ...)` reason on the worktree you are standing in is this session's own lock and is cleared with
  `git worktree unlock`; on a different worktree the pid decides; any other reason is a person's
  lock and still stops. `remove -f -f` is still never used.
- **The skill tears down only the checkout it runs in, and never touches the main checkout.** Step 3
  used to run `git checkout <default-branch>` and `git pull` there while step 2's clean-tree and
  branch gates inspected only the worktree being removed — so it could drag another session off its
  branch and pull onto its uncommitted work. Making the main checkout out of bounds removes the
  ungated mutation by construction, rather than adding one more gate.
- **The squash-merge check is promoted to its own step and now runs every time.** Detaching HEAD
  puts it ON the branch tip, so `git branch -d` afterwards always succeeds — with an upstream or
  without one — and the "not fully merged" refusal that used to trigger the v0.9.0 check never
  happens in a worktree. The check would have gone dead exactly where it matters. It now runs
  unconditionally in step 3, before anything is detached or deleted: exit 0 continues, exit 1 and
  exit 2 still gather `git ls-remote` evidence and ask. Every run now carries landed-ness evidence,
  not only the runs that hit a refusal.
- **New `scripts/self-teardown-test.sh`** builds real repositories and asserts the four facts the
  new path rests on: `-d` refuses while the branch is checked out here; `--detach` frees it and
  makes `-d` succeed with and without an upstream; `git worktree remove` succeeds on its own path;
  and a locked worktree refuses both `remove` and `remove --force` until `unlock`. It also asserts
  the main checkout keeps its branch and its untracked files throughout.
- **A new step 0 records the shell guard's rules,** because the skill meets them on every run: one
  git command per call, literal absolute paths, and no redirect to another checkout.
- **An adversarial review of the first draft found five more defects, all fixed here.**
  - The worktree test itself was wrong. `git rev-parse --git-dir` prints an absolute path while
    `--git-common-dir` stays relative once the working directory is below the repository root, so
    the two differ as text in a MAIN checkout — and the skill would have taken the worktree path
    against the shared checkout, detaching it and deleting its default branch. The test is now one
    command, `git rev-parse --path-format=absolute --git-dir --git-common-dir`, correct from any
    directory.
  - The worktree path now comes from `git rev-parse --show-toplevel`, not the working directory.
    `git worktree remove` accepts only a worktree's top level, and that failure would otherwise land
    after the branch was already deleted.
  - A worktree checked out on the default branch now keeps it. Refs are shared, so deleting it
    breaks `git rebase <default>`, `git log <default>..HEAD` and `git diff <default>` in every other
    checkout.
  - The lock rule is scoped to the worktree being removed. `git worktree list --porcelain` lists
    every worktree, so a sibling session's harness lock was stopping a teardown it cannot block.
  - Step 2 now tells apart the two states behind an `@{u}` error. `git config --get
    branch.<b>.merge` is empty when no upstream was ever set (still a hard stop) and prints a ref
    when the branch was pushed and its remote-tracking ref was pruned — the ordinary state after a
    merged branch is deleted, and the state this skill's own `fetch --prune` creates for the next
    teardown in the same repository. That case no longer reports the work as local-only.
  - Step 3's own invocation was refused by the guard. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/...`
    builds a command name from a variable, so the skill would have lost its only landed-ness
    evidence. It now resolves the root with `echo` and calls the script by the printed literal path.
- **Step 1 recognises a detached HEAD** as a half-finished teardown and resumes from it, instead of
  reading `HEAD` as a branch name and reporting the work as local-only.
- The step-2 hard-stop gates and `branch-landed.sh` itself are unchanged.

## What's New in v0.9.0

- **`wrapping-up-sessions` proves a squash merge instead of asking about it.** A squash merge
  rewrites a branch into one new commit, so not one of the original commits stays an ancestor of
  the default branch, and `git branch -d` refuses with "not fully merged" — the same words it uses
  for a branch that never merged at all. The skill used to treat that refusal as unresolvable and
  always stopped to ask.
- **Step 3 now runs a content-equivalence check, `scripts/branch-landed.sh`,** and green-lights
  the delete when the check confirms the changes are already on the default branch. Two arms:
  `git cherry` compares every branch commit against the upstream patch-ids (this catches a rebase
  merge or a cherry-pick); when commits remain, the script synthesizes a throw-away commit holding
  the branch's whole tree on top of the merge base and asks `git cherry` whether that one squashed
  patch is upstream (this catches a squash merge).
- **The verdict is the exit code:** 0 CONTAINED, 1 NOT-CONTAINED, 2 INCONCLUSIVE. On CONTAINED the
  one evidence line names the actual squash commit, so the report cites a sha and not only a
  verdict.
- **Exit 1 and exit 2 both keep the old ask.** They fall through to the `git ls-remote` evidence
  and the confirmation prompt — an absent answer is never read as a negative answer.
- **A `git fetch origin <default-branch>` now runs before the check.** The only pull in the skill
  runs after the deletion, so a local default branch that has not yet seen the squash commit would
  read as never merged.
- **Two properties are stated in the skill body.** CONTAINED is one-way proof: patch-id includes
  the diff context lines, so a default branch that edited the same lines before the squash landed
  reads NOT-CONTAINED for a branch that truly merged — which is why exit 1 asks rather than
  refuses. And a squash that was later reverted reads CONTAINED, which answers the question asked
  and is safe, because the step-2 gate already proved every commit is on the remote.
- **`scripts/branch-landed-test.sh` ships the 13-case fixture matrix.** Every case is checked to be
  reachable through a real `git branch -d` refusal, and the detector is also proven against a real
  GitHub squash merge in this repository. The step-2 hard-stop gates are untouched.

## What's New in v0.8.0

- **`wrapping-up-sessions` runs in a forked context (`context: fork`).** The teardown transcript —
  gate checks, git plumbing, verification reads — stays out of the calling session, which is the
  session the skill exists to close.
- **Its frontmatter `name:` is now the bare `wrapping-up-sessions`.** The harness already prefixes
  a plugin skill, so the qualified `productivity:wrapping-up-sessions` form was redundant and
  risked registering under a name no dispatch site resolves. `handoff` in this same plugin already
  used the bare form.
- **`allowed-tools` is now stated:** `AskUserQuestion`, `Bash`, `Read` — the skill is git plumbing
  plus the one force-delete confirmation.
- **The skill no longer calls `ExitWorktree`.** That tool acts only on the context that calls it,
  which from a fork is the fork and not the session being closed. `git worktree remove` is now the
  only removal path, not a fallback.
- **One behavior follows:** the calling session's folder still points at the removed worktree when
  the skill finishes. Step 4 reports that fact next to the safe-to-close signal. Every other
  teardown step acts on the shared checkout and lands the same way from a fork.

## What's New in v0.7.0

- **`handoff` renders the document in the reply.** It no longer saves the handoff document
  to the OS temp directory — the rendered text is the deliverable, and the user carries it
  into the next session. This means the skill is no longer a byte-verbatim copy of its
  [mattpocock/skills](https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md)
  upstream; it is now adapted from it.
- **`dispatch-background-sessions` forks the current session.** Instead of composing a
  self-contained prompt and writing it to a prompt file, the skill launches the background
  session with `claude --bg --name <name> --resume "$CLAUDE_CODE_SESSION_ID"
  --fork-session "<directive>"`. The fork inherits the parent conversation's full context,
  so the prompt shrinks to a short directive: a role reset (do the one item; do not
  re-dispatch), the work item, the areas other sessions own, a parent pointer, standing
  constraints, and a report-before-editing first action. The directive is
  passed via a quoted heredoc (no prompt file, no escaping). If `$CLAUDE_CODE_SESSION_ID`
  is empty the skill stops rather than falling back to `--continue`, which can fork a
  different conversation. The launch-verify step (`claude logs` after ~15s) and the
  one-item-per-dispatch rule are kept.

## What's New in v0.6.0

- **Retired two skills: `wrapping-up-prs` and `designating-session-for-planning`.** Both
  duplicated more actively-developed skills elsewhere in the ecosystem and carried a
  disproportionate maintenance surface. `wrapping-up-prs` (a ~550-line embedded Workflow with
  Sonar Web API details, per-role model plans, and force-with-lease semantics) overlapped
  `pr-flow:getting-prs-merged`, `pr-flow:getting-prs-approved`, and `relay:refining-prs`;
  `designating-session-for-planning` was a thin read-only planning prompt already covered by
  `superpowers:brainstorming` + `superpowers:writing-plans` and relay's planning skills. To drive
  a PR to merge-ready, use `relay:refining-prs`.
- **`productivity` now ships exactly three skills:** `handoff`, `dispatch-background-sessions`,
  and `wrapping-up-sessions` — the set of things nothing else in the ecosystem does.

## What's New in v0.5.0

- **`wrapping-up-sessions` is now purely a workspace-teardown skill.** It no longer resolves or
  verifies a PR — no `gh pr view`, no merged-state gate, no PR-number argument. Run it once the
  work has already landed and it returns the workspace to a clean default-branch state: exit and
  remove the worktree, delete the local branch, check out the default branch, `git pull`, and
  `git fetch --prune` to drop the stale remote-tracking ref.
- **The local safety gates are kept and extended.** A dirty working tree, unpushed commits, a
  branch with no upstream, or an in-progress merge/rebase are all hard stops — those are what
  actually protect against destroying work. Because nothing verifies merge state any more, the
  skill also asks for explicit confirmation before force-deleting a branch git reports as
  unmerged, instead of assuming a squash merge. To drive a PR to merge-ready first, use
  `relay:refining-prs`.

## What's New in v0.4.0

- **`dispatch-background-sessions` links the child back to its parent.** At dispatch time the
  skill captures the parent's `$CLAUDE_CODE_SESSION_ID` and embeds it in the composed prompt as
  a **Parent session** block, so the dispatched session has a durable pointer home (for
  hand-back or escalation) and you can return to the originating session with
  `claude --resume <id>`.
- **Broader trigger.** The skill description now matches direct asks like "dispatch a new
  claude session" or "start a background session to do X", not only work-item phrasings.

## What's New in v0.3.0

- **`dispatch-background-sessions` is now a single call.** Instead of starting an idle
  session and printing a prompt to paste in, the skill writes the composed prompt to a
  prompt file in the OS temp directory, launches the background session with
  `claude --bg --name <name> "<prompt>"` so it starts working on the item immediately,
  verifies via `claude logs` that the session picked up the work, and reports the prompt
  file path as the manual fallback.
- **New skill: `wrapping-up-prs`.** Drives an open PR to merge-ready with minimal human
  input — resolves conflicts, fixes failing checks (CI and Sonar quality gates), and loops
  until the PR is mergeable or only awaiting human approval. It never merges. This completes
  the command-center loop: designate → dispatch → wrap up PR → wrap up session.

## What's New in v0.2.0

- **Three new command-center skills**
  - `designating-session-for-planning` — a **read-only** command center that scopes work into a
    prioritized, parallelizable inventory of single-PR-sized items, then stops before implementing.
  - `dispatch-background-sessions` — composes a self-contained, evidence-grounded prompt for one
    work item, starts an idle background session via `claude --bg`, and prints the prompt to paste in.
  - `wrapping-up-sessions` — verifies nothing is uncommitted/unpushed, then tears down the worktree
    and local branch, returns the working folder to the default branch, and pulls latest.
- Skills use qualified names (`productivity:<slug>`), keeping the 0-agent architecture.

## What's New in v0.1.0

- **Initial release.** Ships the verbatim `handoff` skill (copied from
  [mattpocock/skills](https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md))
  to compact the current conversation into a handoff document for the next
  agent.
- Skill-only, 0-agent plugin — no commands, no hooks, no Python.

## Overview

`productivity` bundles lightweight prompt skills that help you wrap up work in
one session and hand it cleanly to a fresh agent in the next. v0.7.0 ships three
skills: `handoff`, `dispatch-background-sessions`, and `wrapping-up-sessions` — a
small command-center loop for delegating and tearing down work across sessions.

## Architecture

This is a **skill-only, 0-agent** plugin. There are no agents, commands, hooks,
or Python packages. It contains:

- A plugin-root umbrella `SKILL.md` (`productivity:productivity`) that surfaces
  the toolbox so the model knows the skill names when the user's phrasing is
  generic.
- `skills/handoff/SKILL.md` — the handoff skill, adapted from the upstream
  [mattpocock/skills](https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md)
  source (since v0.7.0 it renders the document in the reply instead of writing a file).
- `skills/{dispatch-background-sessions,wrapping-up-sessions}/SKILL.md`
  — qualified-name (`productivity:<slug>`) command-center skills for dispatching and
  tearing down work across sessions.
- `scripts/branch-landed.sh` — the squash-merge equivalence check `wrapping-up-sessions`
  runs in step 3, before it deletes anything, with `scripts/branch-landed-test.sh` next to it
  as its fixture matrix. It is plain bash and is called through `${CLAUDE_PLUGIN_ROOT}`,
  because a forked skill runs with the user's repository as its working directory.
- `scripts/self-teardown-test.sh` — the fixture behind step 4 path A. It proves a worktree can
  be removed from inside itself, and that the main checkout survives the teardown untouched.

The `handoff` skill keeps its upstream (unqualified) name and `argument-hint`
verbatim; the two workflow skills use qualified names.

## Quickstart

1. Add the marketplace and install the plugin:

   ```
   /plugin marketplace add ai-advanced-futures/claude-code-dev-plugins
   /plugin install productivity@claude-code-dev-plugins
   ```

2. Invoke a skill by intent — for example "write a handoff doc" / "compact this
   conversation" (`handoff`), "dispatch this to a background session"
   (`dispatch-background-sessions`), or "wrap up and tear down this worktree"
   (`wrapping-up-sessions`).

## Skills

| Skill | Description |
|-------|-------------|
| `handoff` | Compact the current conversation into a handoff document for another agent to pick up. Renders the document directly in the reply (no file written), includes a "suggested skills" section, references existing artifacts (PRDs, plans, ADRs, commits) by path instead of duplicating them, and redacts secrets. Accepts an optional argument describing what the next session will focus on. |
| `dispatch-background-sessions` | Hand ONE scoped work item to a separate background session in a single call: derive a session name, compose a short directive (role reset, work item, the areas other sessions own, parent pointer, standing constraints, first action), launch the session as a fork of the current one via `claude --bg --name <name> --resume "$CLAUDE_CODE_SESSION_ID" --fork-session "<directive>"` so it starts with full conversation context and begins working immediately, and verify via `claude logs` that the work was picked up. Accepts the work-item description. |
| `wrapping-up-sessions` | Tear down a finished session's workspace: verify nothing is uncommitted, unpushed, or mid-merge/rebase (hard-stop gates), confirm the work reached the default branch with `scripts/branch-landed.sh`, then delete the local branch and remove the worktree **from inside it**. Outside a worktree it returns to the default branch and pulls. It tears down only the checkout it runs in and never touches the main checkout. Runs in a forked context; on a worktree teardown the calling session's folder no longer exists when it finishes, so that session should be closed. Destructive — refuses unless every gate passes, and asks only when the equivalence check cannot prove the work landed. Does not check PR state; run it once the work has landed. |

## Configuration

No configuration is required. The plugin ships no settings, environment
variables, or hooks, and its skills write no files — `handoff` renders its
document in the reply, and `dispatch-background-sessions` passes its directive
to the forked session inline.

## Integration

- **mission-control.** `release.json` declares a `mission_control_integration`
  block (`dpo_reporting_protocol: inline_handoff`, `preferred_invocation`,
  `done_signal: DONE: productivity`, `yolo_safe: true`). It sets
  `supports_automated_mode: false` — the `handoff` skill emits no DONE signal
  and renders its document in the reply rather than at a deterministic path, so
  the plugin is not an autonomous DPO.
- **Provenance.** The `handoff` skill is adapted from
  [mattpocock/skills](https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md)
  (verbatim through v0.6.0; since v0.7.0 it renders inline instead of writing a
  file).
