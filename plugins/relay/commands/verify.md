---
description: "Repeat simplify, code-review, and /verify over the current branch until it verifies clean or the round cap is spent. Reports one of three terminal states: clean, findings, or unverified."
argument-hint: "[--rounds 1-5] [--engine in-session|acpx] [--agent claude]"
allowed-tools: Bash, AskUserQuestion, Workflow, Skill
---

# Relay Verify (L3)

Repeat `/simplify` → `/code-review medium --fix` → `/verify` → fix over the branch you are
on, until `/verify` reports a clean verdict or the round cap is spent.

`--engine` picks how each step reaches its command. The default is `acpx`: every step runs
as one turn of a headless child Claude session, so this session keeps its context. That child
runs with the approval gate off, so the default path asks for agreement once at Step 1 before
it generates any node. `--engine in-session` starts each command with `SlashCommand` from this
session and starts no child process, so it asks nothing and needs no acpx install.

The check step reads only the verdict line that `relay:verifying-until-clean` states, because
`/verify` resolves to whatever the repository defines and may prescribe no report format.

## Step 0 — dependency gate and argument parse

The script prints the two `[relay]` lines below plus a `KEY=value` block, including
`RELAY_VERIFY_ENGINE=`; read them from printed stdout — this Bash call is a fresh process, so
nothing it exports survives.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" verify "$ARGUMENTS" || exit 1
```

The block is a script because a session isolated in a git worktree refuses an inline Bash
command that carries `source`, `$(…)`, `case` or `if`, and because sourcing `check-deps.sh`
under zsh ends the call silently.

The default is 3 rounds. The bound runs from 1 to 5. An out-of-range `RELAY_VERIFY_ROUNDS`
fails here too; it is never clamped.

`parse-engine-agent.sh` resolves and validates the axis, exports
RELAY_ENGINE/RELAY_AGENT/RELAY_AXIS_SOURCE, and fails loudly on invalid input. An engine pin
in `.claude/relay.json` behaves here as it does for `/relay:implement`.

The agent axis is inert here, and its default is `claude`. No role is dispatched, so there is
no worker to choose; every step is a Claude step under either engine. The axis is still
validated, so `--agent codex` with `--engine in-session` fails here with the same message as
every other command.

The script rejects every engine except `in-session` and `acpx` — the message is
`is not supported by /relay:verify (supported: in-session | acpx)` — and exports
`RELAY_VERIFY_ENGINE` for the loop to use.

## Step 0.5 — branch guard

The loop edits files and commits them, so it refuses the default branch.
`worktree-preflight.sh --branch-guard verify` reads the `RELAY_WT_STATE` / `RELAY_WT_BRANCH`
block and refuses the default branch and a detached `HEAD`, printing that block and, on a
refusal, `verify: refusing to run on the default branch. This loop edits files and commits
them. Create a branch first.` (or the detached-HEAD equivalent).

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --branch-guard verify || exit 1
```

The `not-git` state makes the script return non-zero, which `|| exit 1` catches. This
command never creates or enters a worktree; it verifies the branch you are on, in place.

## Step 1 — generate the loop

Invoke `relay:verifying-until-clean` to generate the round nodes and the terminal report node,
appended to this command's single Workflow.

Pass `$RELAY_VERIFY_ENGINE` to the skill. The engine picks the node shape, and nothing else.

When the engine is `acpx`, the skill asks the user one question before it generates any
node, because the loop then runs headless child sessions with the approval gate off. Do not
skip that question, and do not answer it for the user. When the user does not agree, generate
no node and report the run as unverified.

When the engine is `in-session`, there is no question to ask: no child process starts, so
no approval gate is turned off.

Declare no loop identity here. The skill owns the one identity, so `/relay:implement --verify`
and this command produce the same nodes, session names, and state directory.

## What contains the child

Under `acpx`, each helper runs the child with `--approve-all` and `--cwd "$worktree"`. Neither
is a security boundary. See `relay:verifying-until-clean` for the full containment note.
Under `in-session`, every step runs under this session's own permission mode.

Cite only `relay:verifying-until-clean`.
