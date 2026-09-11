---
name: ensuring-worktree-isolation
description: >-
  Use as the Step 0.5 preflight of relay's source-modifying L3 commands (implement,
  refine, execute, drive) — guarantees an isolated, up-to-date workspace before any
  Workflow runs. Reads worktree-preflight.sh --classify, branches on the printed state
  (worktree / main / stray / not-git), drives the per-state AskUserQuestion confirmation,
  creates a fresh worktree off origin/<default> or HEAD when chosen, and enters it via
  EnterWorktree({path}) exactly once. Self-contained — does not delegate to
  superpowers:using-git-worktrees.
user-invocable: false
---

# ensuring-worktree-isolation

This skill is the Step 0.5 worktree-isolation gate. It runs in MAIN, after the command's
dependency/arg gate and before the command generates its Workflow. Its one job: make sure
the session is in an isolated, confirmed-correct, up-to-date workspace, so the Step 1+
Workflow never runs against a dirty `main` checkout by accident.

It owns the full confirm / create / enter state machine. It does not delegate to
`superpowers:using-git-worktrees`: that skill lacks the confirm-existing-worktree,
pull-latest-from-default, and `EnterWorktree({path})` flow this gate requires.

## One model: the flag is a pre-answered gate

The four source-modifying L3 commands accept an optional `--worktree <value>` flag. When
the user gives it, the value pre-answers this gate — the run should not stop to ask a
question it already has the answer to. When the user omits it, this gate runs exactly as
it did before the flag existed.

Value grammar — a value is one of three shapes:

- `current` — the primary checkout or worktree the session is already in.
- a path — a value that names a directory that IS a linked worktree of this repository.
- a branch — anything else: the value is tried as a branch name. A directory that exists
  on disk but is NOT a linked worktree of this repository is still tried as a branch name.
  Existence alone does not make a value a path; only being a linked worktree does.

A value that matches neither a linked worktree nor a branch resolves to `missing`.

## The Bash↔Claude seam

State crosses the boundary as printed stdout, never env vars (env does not persist across
Bash calls — same convention as `check-deps.sh`). The script prints a `KEY=value` block;
you read it and make the tool calls bash cannot (`AskUserQuestion`, `EnterWorktree`).

Classify first:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --classify
```

Read the printed block:

```
RELAY_WT_STATE=<worktree|main|stray|not-git>
RELAY_WT_BRANCH=<current branch or DETACHED>
RELAY_WT_DEFAULT=<default branch, e.g. main>
RELAY_WT_REPO_ROOT=<toplevel>
RELAY_WT_WORKTREE_ROOT=<path if in a linked worktree, else empty>
```

A `not-git` state makes the script return non-zero. The `|| exit` on the source line has
already aborted the command, so this skill does nothing in that case.

## Pre-answered gate — reading `RELAY_WT_ARG`

The calling command's Step 0 prints `RELAY_WT_ARG=<value>` on its own stdout when the user
gave `--worktree <value>`; it prints nothing when the flag was absent. The calling command's
Step 0.5 then also runs `worktree-preflight.sh --resolve "<value>"` and passes both printed
blocks — the `--classify` block and the `--resolve` block — to this skill as plain
substituted text in the invocation. This skill never reads an environment variable for
either value; both arrive as printed stdout, substituted into the calling text, per the
same Bash↔Claude seam described above.

When `RELAY_WT_ARG` is absent, skip straight to the state machine below, unchanged.

When `RELAY_WT_ARG` is present, read the `--resolve` block:

```
RELAY_WT_RESOLVED=<current|path|branch|missing>
RELAY_WT_TARGET=<absolute path (current/path/branch) or the value verbatim (missing)>
RELAY_WT_TARGET_BRANCH=<branch at target, DETACHED, or empty on missing>
```

Branch on `RELAY_WT_RESOLVED`, instead of running the interactive state machine below:

| `RELAY_WT_RESOLVED` | Action |
|---|---|
| `current` | Proceed. No create, no enter. |
| `path` or `branch` | If `RELAY_WT_TARGET` equals the current toplevel (`RELAY_WT_REPO_ROOT`), proceed with no create/enter. Otherwise call `EnterWorktree({path: RELAY_WT_TARGET})` exactly once, then proceed. |
| `missing`, interactive session | Ask today's Create / Proceed in place / Cancel question (below), with the flag pre-committing the destination: Create → run `worktree-preflight.sh --create <base> --at <value>` (where `<value>` is the literal `--worktree` value), then `EnterWorktree({path: RELAY_WT_CREATED_PATH})` exactly once; Proceed in place → no create, no enter; Cancel → abort the command with: `[relay] error: cancelled at the --worktree <value> create prompt`. |
| `missing`, headless session | Abort the command with: `[relay] error: worktree-missing: <value> is not a worktree or a checked-out branch of this repository`. Do not ask a question in a headless session — there is no one to answer it. |

The rule that decides interactive vs. headless above is the same rule this skill already
uses elsewhere in this file (see "Drive autonomy" below) — there is no new detection site
and no new printed key for it.

The enter-exactly-once invariant below is unchanged by the flag: at most one
`EnterWorktree` call per run, whether the flag was given or not.

## The state machine (no `--worktree` flag given)

Branch on `RELAY_WT_STATE`. Each state has exactly one `AskUserQuestion` confirmation and a
small set of on-accept actions. `<task>` is the user's task phrase; `<default>` is
`RELAY_WT_DEFAULT`. Never call `EnterWorktree` on an undefined path: only the Create branch
below calls it, and only after `RELAY_WT_CREATED_PATH` was printed.

### State `worktree` — already isolated, confirm it is the right one

You are already inside a linked worktree (`RELAY_WT_WORKTREE_ROOT` is set) — whether it was
created under `.claude/worktrees/` by relay or hand-made elsewhere with `git worktree add`.
The only question is whether it is the correct workspace for this task.

- `AskUserQuestion`: "In linked worktree `<RELAY_WT_BRANCH>` at `<RELAY_WT_WORKTREE_ROOT>` —
  correct workspace for <task>?" → Yes / No.
- Yes → proceed. Do not create or enter anything. The Step 1+ Workflow runs here.
- No → abort the command with guidance: "Switch to the right worktree or to `main`, then
  re-run." Do not auto-switch — the user picks the workspace.

### States `main` and `stray` — in the primary checkout, offer a fresh worktree

The two states differ only in the base ref and the question text:

| State | Meaning | `<base>` | `AskUserQuestion` |
|---|---|---|---|
| `main` | on the default branch | `origin/<default>` | "On `main`. Create a fresh isolated worktree off `origin/<default>`? (recommended) / Proceed on main in place / Cancel." |
| `stray` | non-default branch or detached HEAD | `HEAD` | "On branch `<RELAY_WT_BRANCH>` (not main, not a worktree). Create a worktree from current HEAD (preserves your work)? (recommended) / Proceed here in place / Cancel." |

`stray` branches from current HEAD, not `origin/<default>`, so the user's work-in-progress
is preserved.

- Create (recommended) →
  1. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --create "<base>" "<slug>"`
     — this runs `git fetch origin <default>` (the pull-latest requirement; it never
     mutates the user's checked-out branch), creates `.claude/worktrees/<name>` on a fresh
     `relay/<slug>` branch, reads any primary-checkout `.claude/relay.json` `bootstrap`
     command, runs it in the new worktree with output on stderr, and prints
     `RELAY_WT_CREATED_PATH=<absolute path>` plus `RELAY_WT_BOOTSTRAP=<ran|skipped>`.
     A cold bootstrap can take minutes, so invoke `--create` with the longest timeout the
     calling tool allows. Relay imposes no internal timeout.
  2. On failure — if `--create` returns non-zero or prints no `RELAY_WT_CREATED_PATH` line
     (e.g. `git worktree add` failed, or the bootstrap command failed), do not call
     `EnterWorktree`. Abort the command and surface the script's stderr message to the user.
  3. Read `RELAY_WT_CREATED_PATH`, then call `EnterWorktree({path: RELAY_WT_CREATED_PATH})`.
  4. Proceed — the session cwd is now the new worktree.
- Proceed in place → continue on the current branch/checkout. The gate offers isolation but
  does not force it; this is the user's explicit choice — no auto-stash.
- Cancel → abort the command.

### State `not-git`

The script already returned non-zero and the command aborted before this skill ran. No
action.

## The load-bearing invariant: enter EXACTLY ONCE, never re-switch

Call `EnterWorktree` exactly once per run and never re-switch afterward: `ExitWorktree`
will not remove a worktree entered via the `path` form, and previously visited worktrees
become non-writable after a further switch, so the Step 1+ Workflow runs in that single
entered worktree.

Worktree creation uses `git worktree add` (via `--create`, a deterministic base ref) rather
than `EnterWorktree({name})`: the latter's base is governed by the global `worktree.baseRef`
setting and cannot be chosen per-call. Create with the explicit base, then enter via the
path form.

## Drive autonomy — `--resume` verify-only mode

`/relay:drive` runs confirm-at-launch-then-headless: this gate runs before the Workflow, so
the human is present for the one confirmation and the headless loop never re-prompts.

- Initial run: after resolving the workspace, record the chosen mode into `loop-state.md` —
  `RELAY_DRIVE_WORKSPACE=worktree` (with the entered worktree path) or
  `RELAY_DRIVE_WORKSPACE=in-place` (with the recorded branch/checkout). A drive run may
  legitimately not be in a worktree (the "proceed in place" options).
- `--resume`: the gate runs verify-only — it does not prompt or create. It reads
  `RELAY_DRIVE_WORKSPACE` from `loop-state.md` and asserts the current cwd matches the
  recorded mode (`worktree` → that recorded worktree; `in-place` → the recorded
  branch/checkout), then proceeds.
- Only a genuine mismatch (the worktree is gone, or the user resumed from a different
  place) prints a clear error and aborts.

## After the gate

Once the gate has proceeded — already isolated, entered a new worktree, or staying in place
by explicit choice — control returns to the command, which generates its Step 1+ Workflow in
the resolved cwd. The gate does not run again this session.

Calm imperatives only. Read the printed state, ask the one question for that state, and make
the single tool call the accepted answer requires.
