---
description: "Autonomous end-to-end implementation. Classifies the task into a closed kind from context, then generates one dynamic Workflow over the kind's hard spine (the §4.2.1 branch table); soft zone adds patterns. --engine/--agent select the dispatch family (acpx + claude by default, so delegate-eligible leaves run as watched external workers; --engine in-session keeps every leaf in this session). --verify appends the verify-until-clean loop, making the run equal to /relay:implement followed by /relay:verify."
argument-hint: "[--engine in-session|acpx|smart-routing|bg-sessions|session-tree] [--agent claude|codex|opencode|hybrid|smart-routing] [--fixes-model sonnet|opus|fable] [--verification-model sonnet|opus|fable] [--verify] [--rounds 1-5] [--retro [<runId>|last]] [--keep-sessions] [--worktree current|<path-without-spaces>|<branch>] <task>"
allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill, SendMessage
---

# Relay Implement (L3)

## Step 0 — Dependency gate + engine/agent resolution
Run first; any failure aborts the command.

The script prints the three `[relay]` lines below plus a `KEY=value` block; read them from
printed stdout — this Bash call is a fresh process, so nothing it exports survives.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" implement "$ARGUMENTS" || exit 1
```

The block is a script because a session isolated in a git worktree refuses an inline Bash
command that carries `source`, `$(…)`, `case` or `if`, and because sourcing `check-deps.sh`
under zsh ends the call silently. The same guard also refuses a `${VAR}` reference or an
`ENV=value` prefix on the command line. The harness substitutes `${CLAUDE_PLUGIN_ROOT}` to an
absolute path before the block runs, so the line above is accepted as shipped; a line typed by
hand must use the absolute path.

`check-deps.sh` blocks if the `superpowers` plugin is missing. `parse-engine-agent.sh` resolves
and validates the axis: flags first, then the `.claude/relay.json` pin (`engine`/`agent` keys),
then defaults (`in-session`⇒`claude`, `acpx`⇒`hybrid`, `smart-routing`⇒`smart-routing`,
`bg-sessions`⇒`claude`, `session-tree`⇒`claude`). It enforces the cross-arg invariants
(in-session⇒claude; bg-sessions⇒claude; session-tree⇒claude; smart-routing rejects literal
workers) and exports `RELAY_ENGINE` / `RELAY_AGENT` / `RELAY_AXIS_SOURCE` /
`RELAY_IN_SESSION_TIERS`. Invalid input fails loudly. This command's own default is
`--engine acpx --agent claude` — every delegate-eligible leaf runs as a watched external
Claude worker, so this session keeps its context. `--engine in-session` returns to
self-execution, where Claude runs every leaf itself and no delegation occurs.

## Step 0.2 — Retro-only mode
Runs only when Step 0 printed `enabled=1` **with a non-empty target**. `--retro <runId>` and
`--retro last` are retro-only: audit that run and stop. Skip Step 0.25, do **not** enter a worktree,
and do **not** generate a Workflow — a retro is read-only and must not dirty the branch it audits.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<target>"
```

Report the printed block verbatim and stop. Exit `0`: the checks that could run found nothing.
Exit `1`: deviations were found (advisory — a retro never fails a command). Exit `2`: too
little evidence survives to audit that run. A bare `--retro` with no target is **not** this
mode: it runs the command normally and retros this run at the end.

## Step 0.25 — Ask when unpinned
Runs only when the Step 0 axis line printed `(source: default)` — no flag and no
`.claude/relay.json` pin on either axis. Any other source (including `default+flags`)
skips this step. If this session cannot present an interactive question
(headless/programmatic run, e.g. `claude -p`), skip this step and proceed with the
already-resolved default axis — never block the run waiting for an answer.

Ask exactly one `AskUserQuestion`:

- **Question:** `No dispatch engine is pinned for this repo. How should relay dispatch this run's leaf work?`
- **Option 1 (listed first = default):** label `acpx (default)` — description:
  `Delegation-eligible leaves run as external acpx workers, every one of them Claude. Requires acpx >= 0.12.0 (/relay:setup checks this). Preserves this session's context; each worker pays cold-cache input prices.`
- **Option 2:** label `acpx (hybrid)` — description:
  `The same acpx workers, split per role by bindings/presets.yaml (reasoning roles claude, coding roles codex). Also needs the codex CLI configured. Codex tokens bill to the codex plan.`
- **Option 3:** label `in-session (claude)` — description:
  `Every leaf runs inside this session on the session model. No acpx install needed, simplest to follow, but all tokens bill to this Claude session and long runs consume this session's context.`
- **Option 4:** label `bg-sessions (claude)` — description:
  `Delegation-eligible leaves run as background Claude sessions. No acpx and no codex CLI needed. The session's context is preserved. Every worker bills to the Claude plan.`

End each description with: `Tip: pin {"engine": "<engine>"} in .claude/relay.json to skip this
question permanently.` (for the two acpx options: `{"engine": "acpx", "agent": "claude"}` and
`{"engine": "acpx", "agent": "hybrid"}`). `smart-routing` and
`session-tree` are not offered — both stay flag- and pin-reachable only.

On `acpx (default)`: proceed — the Step 0 resolution already holds. On any other answer, run
one re-resolution block so the transcript carries the final axis with honest provenance
(`prompt` is a command-layer provenance value only; the script never emits it).

On `acpx (hybrid)`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only acpx hybrid --source prompt
```

On `in-session (claude)`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only in-session claude --source prompt
```

On `bg-sessions (claude)`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only bg-sessions claude --source prompt
```

The later literal injection into the Workflow uses the values from the **last** printed
axis line.

## Step 0.5 — Ensure worktree isolation
Runs after the dependency gate and **before** Workflow generation. Classify the git state,
then hand off to the gate skill:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --classify || exit 1
```

When Step 0 printed `RELAY_WT_ARG=<value>`, also run the resolver beside the classifier.
Substitute the printed value into the command as a literal, in place of `<value>`. The
shell variable `$_worktree` is not available here: Step 0 ran in a different Bash call, and
state crosses that boundary as printed stdout only. Let the block print — the gate skill
reads the `RELAY_WT_*` lines from this output:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --resolve "<value>" || exit 1
```

Read the printed `RELAY_WT_*` block (and the `--resolve` block, when `RELAY_WT_ARG` was
printed), then invoke `relay:ensuring-worktree-isolation`, passing both blocks. It owns
the confirm / create / enter state machine (`worktree` / `main` / `stray`), asks the one
per-state `AskUserQuestion`, and on a **Create** choice runs `--create` then
`EnterWorktree({path: …})` **exactly once**, so the Step 1+ Workflow runs in the isolated
worktree. Abort the command on the skill's abort/cancel paths. When `RELAY_WT_ARG` was
printed, the skill instead branches on the `--resolve` block's `RELAY_WT_RESOLVED` value —
see `relay:ensuring-worktree-isolation` for the pre-answered branch table.

If this session cannot present an interactive question (headless/programmatic run, e.g.
`claude -p`), skip the gate's confirmation and proceed **in place** in the current checkout —
never create, enter, or switch worktrees without an answered confirmation.

## Step 0.55 — Record the active worktree
Runs immediately after the gate skill returns, whether or not `--worktree` was given.
The value crosses to the next step as printed stdout, so read it from this block.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --active || exit 1
```

## Step 0.6 — Branch guard, only when `--verify` was passed
Skip this step entirely when Step 0 printed `enabled=0`. It runs **after** Step 0.5, so it reads
the branch this run actually lands on.

`/relay:verify` refuses the default branch and refuses a detached HEAD, because its loop commits
every round. The `--verify` tail runs the same loop, so it refuses the same two states (the
same-paths invariant, Step 2).

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --branch-guard || exit 1
```

The guard reads the printed `RELAY_WT_*` block and refuses `main` and a detached `HEAD`
because commits on a detached `HEAD` are on no branch.

## Step 1 — Classify the task kind

**`session-tree` branch — terminal.** When `$RELAY_ENGINE` resolves to `session-tree`,
this command generates **no Workflow**. Invoke `relay:orchestrating-session-trees` in the
current (MAIN) session (`Skill` is already in `allowed-tools`). When Step 0.55 printed
`RELAY_WT_ACTIVE=<value>`, append a `worktree: <value>` line to the calling text of that
invocation; when it printed nothing, omit the line and behavior is unchanged. Report the
skill's result and **end the command turn here**. Do not fall through to Step 2. Every
other engine value continues below.

Run `relay:classifying-task-kind` over the task text (`$ARGUMENTS` minus the parsed `--engine`/`--agent`
flags, minus `--verify`, minus `--rounds` with its value, minus `--keep-sessions`, minus `--retro` with its optional target, **and minus `--worktree` with its value**). It infers one of `feature | script | config-artifact | bugfix | docs` from context. Surface it.
Leaving the literal `--retro` or `--verify` in the text pollutes what the classifier reads.

## Step 2 — Select the policy (branch on kind — §4.2.1 branch table)
Skip this step when Step 1 took the `session-tree` branch.

Each entry below defines an `agent()` node in the Workflow you generate in the next step — not an action to perform in this thread.
Branch on `kind.value`:
- `feature` → refine-spec → write-plan (conditional) → refine-plan → `relay:delegate-leaf`(implement) → commit → verify
- `bugfix`  → diagnose → `relay:delegate-leaf`(fix) → commit → verify
- `script`  → `relay:delegate-leaf`(write) → commit → verify
- `config-artifact` → `relay:delegate-leaf`(generate) → commit → verify
- `docs`    → `relay:delegate-leaf`(write) → commit → verify

Every branch ends at `verify`. When Step 0 printed `enabled=1`, and only then, append one further
phase — `verify-loop` — after `verify`. Soft zone may add `relay:improve-loop`, `relay:panel`,
`relay:parallel-gather`; it never adds or removes the `verify-loop` phase.

A bare run appends nothing after `verify`: no `/simplify`, no `/code-review medium --fix`. This is
the same-paths invariant: `/relay:implement --verify` must equal `/relay:implement`
followed by `/relay:verify`, and a bare run that polished the branch first would break it.

The flag is the only gate, and there is no availability gate. This command never probes acpx and
never drops the loop because acpx is missing; acpx preflight belongs to `/relay:setup`. A
missing acpx surfaces as the helper's exit `69`, which the loop reports as
`unverified (acpx unavailable)` — never as a quiet skip.

## Step 3 — Run the spine
Skip this step when Step 1 took the `session-tree` branch — it generates no Workflow.

Invoke `relay:running-implement-spine`. Pass all twelve inputs: `kind` (Step 1's value), `task`
(the task text), `spec_path` (when the run has one), `engine` and `agent` (the
`$RELAY_ENGINE` / `$RELAY_AGENT` axis Step 0 resolved), `verify` (the boolean Step 0
printed), `rounds` (the round cap Step 0 resolved), `axis_source` (the source on the last
printed axis line — Step 0's, or Step 0.25's when it re-asked),
`command` (the literal `implement`, so the run intent names this command as the caller),
`closes_issue` (when the caller supplied one), `keep_sessions` (the `RELAY_KEEP_SESSIONS`
boolean Step 0 printed), and `worktree` (the literal value Step 0.55 printed as
`RELAY_WT_ACTIVE`, when it printed one). The skill resolves the per-leaf tiers, generates and runs the one
dynamic Workflow over the §4.2.1 branch table above, records the run intent, and runs the
completeness gate. When `verify` is true it appends the `relay:verifying-until-clean` loop
after the branch's `verify` node (same-paths invariant).

The skill prints one fenced JSON block as its last output:
`{"status": "ok", "run_id": "wf_...", "branch": "...", "commit": "abc1234"}`. Step 5 reads
`run_id` from this block, not from the `Workflow` tool result. A `status` other than `ok`
stops the run: report the block's `reason` field verbatim, and never report a non-`ok`
status as a clean run.

## Step 5 — Retro this run (only when `--retro` was passed with no target)
Skip this step when Step 1 took the `session-tree` branch — there is no `runId` to retro.
Otherwise, skip it when Step 0 printed `enabled=0`.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<runId>"
```

Report the printed block verbatim. The retro is advisory and strictly read-only: it re-runs
nothing, writes no file, and never fails the command — exit `1` reports deviations, it does
not signal failure.

It runs **outside** the Workflow by construction: a retro node inside the script would be an
`agent({schema})` node, subject to the same failure mode it exists to detect.

Read its `SILENT` line against the gate the spine ran. If the retro names dead nodes whose
`attempt == 1`, **the completeness gate did not fire** — the gate needs attention, not only
this run.

## Delegation wiring note
When `$RELAY_ENGINE` resolves to `acpx` or `smart-routing` and a role's `delegate_eligible` is `true` in `bindings/presets.yaml`, substitute `relay:delegate-and-watch` for `relay:delegate-leaf` at that delegation step (the worker is selected per `$RELAY_AGENT`). When `$RELAY_ENGINE` resolves to `bg-sessions` and a role's `delegate_eligible` is `true`, substitute `relay:delegate-and-watch` the same way — its watcher's leg is `relay:dispatching-bg-agents` instead of the acpx driver. When `$RELAY_ENGINE` is `in-session` leave `relay:delegate-leaf` in place.
