# productivity

Small, model-callable skills for moving work between sessions and agents.

**Version:** 0.9.0

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
  calls at the `git branch -d` refusal, with `scripts/branch-landed-test.sh` next to it as
  its fixture matrix. Both are plain bash and are called through `${CLAUDE_PLUGIN_ROOT}`,
  because a forked skill runs with the user's repository as its working directory.

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
| `wrapping-up-sessions` | Tear down a finished session's workspace: verify nothing is uncommitted, unpushed, or mid-merge/rebase (hard-stop gates), remove the worktree (`git worktree remove`), delete the local branch, return the working folder to the default branch, and pull latest. Runs in a forked context, so the calling session's folder still points at the removed worktree when it finishes. Destructive — refuses unless every gate passes, and asks before force-deleting a branch git reports as unmerged — but first runs `scripts/branch-landed.sh`, which compares content instead of ancestry and green-lights the delete without asking when it can prove the branch was squash- or rebase-merged. Does not check PR state; run it once the work has landed. |

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
