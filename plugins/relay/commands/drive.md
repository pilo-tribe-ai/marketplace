---
description: "Autonomous run-to-done. Drives a long-running, multi-step process to a verified done criterion without a human in the loop — surviving /compact and worktree loss. MAIN owns at most one long-lived process; one dynamic Workflow runs the oracle-gated loop (orient → delegate → verify → branch → record → consecutive-clean-runs → closeout)."
disable-model-invocation: true
argument-hint: "[--resume] [--retro [<runId>|last]] [--fixes-model sonnet|opus|fable] [--verification-model sonnet|opus|fable] [--engine in-session|acpx|smart-routing|bg-sessions] [--agent claude|codex|opencode|hybrid|smart-routing] [--worktree current|<path-without-spaces>|<branch>] <oracle-file>"
allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill
---

# Relay Drive (L3)

## Step 0 — Dependency gate + arg resolution
Run first; any failure aborts the command.

The script prints the two `[relay]` lines below plus a `KEY=value` block, including
`RELAY_DRIVE_ORACLE=` and `RELAY_DRIVE_RESUME=`; read them from printed stdout — this Bash call
is a fresh process, so nothing it exports survives. A missing oracle fails with
`drive: <oracle-file> is required` unless a retro target was given.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" drive "$ARGUMENTS" || exit 1
```

The block is a script because a session isolated in a git worktree refuses an inline Bash
command that carries `source`, `$(…)`, `case` or `if`, and because sourcing `check-deps.sh`
under zsh ends the call silently. `engine=session-tree` is refused here.

`check-deps.sh` blocks if the `superpowers` plugin is missing. `RELAY_DRIVE_ORACLE` is `$ARGUMENTS`
minus the parsed `--engine`/`--agent`/`--retro` flags; `RELAY_DRIVE_RESUME` is `1` on a resume.

`parse-engine-agent.sh` resolves and validates the axis (flags, then the `.claude/relay.json` pin,
then defaults in-session⇒claude, acpx⇒hybrid, smart-routing⇒smart-routing, bg-sessions⇒claude),
exports `RELAY_ENGINE` / `RELAY_AGENT` / `RELAY_AXIS_SOURCE` / `RELAY_IN_SESSION_TIERS`; invalid
input fails loudly.

## Step 0.2 — Retro-only mode
Runs only when Step 0 printed `enabled=1` **with a non-empty target**. Audit that run and stop.
A retro is read-only: do **not** enter a worktree and do **not** generate a Workflow.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<target>"
```

Report the printed block verbatim and stop. Exit `0`: nothing found. Exit `1`: deviations found
(advisory). Exit `2`: too little evidence survives to audit.

## Step 0.25 — Ask when unpinned
Runs only when the Step 0 axis line printed `(source: default)` and `resume=1` was not printed.
Any other source (including `default+flags`) skips this step. If this session
cannot present an interactive question (headless, e.g. `claude -p`), skip this step and keep
the default axis.

Ask exactly one `AskUserQuestion`:

- **Question:** `No dispatch engine is pinned for this repo. How should relay dispatch this run's leaf work?`
- **Option 1 (listed first = default):** label `in-session (default)` — description:
  `Every leaf runs inside this session on the session model. No extra setup, simplest to follow, but all tokens bill to this Claude session and long runs consume this session's context. Tip: pin {"engine": "in-session"} in .claude/relay.json to skip this question permanently.`
- **Option 2:** label `acpx (hybrid)` — description:
  `Delegation-eligible leaves run as external acpx workers (per-role claude/codex split from bindings/presets.yaml). Requires acpx >= 0.12.0 and the codex CLI configured (/relay:setup checks this). Preserves this session's context; codex tokens bill to the codex plan, and each worker pays cold-cache input prices. Tip: pin {"engine": "acpx", "agent": "hybrid"} in .claude/relay.json to skip this question permanently.`
- **Option 3:** label `bg-sessions (claude)` — description:
  `Delegation-eligible leaves run as background Claude sessions. No acpx and no codex CLI needed. The session's context is preserved. Every worker bills to the Claude plan. Tip: pin {"engine": "bg-sessions"} in .claude/relay.json to skip this question permanently.`

`smart-routing` is not offered — it stays flag- and pin-reachable only.

On `in-session (default)`: proceed. On `acpx (hybrid)` or `bg-sessions (claude)`: run one
re-resolution block with the chosen pair (`prompt` is a command-layer provenance value only):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only acpx hybrid --source prompt
```

For `bg-sessions (claude)` run
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only bg-sessions claude --source prompt`
instead. The Workflow injection uses the values from the **last** printed axis line.

## Step 0.5 — Ensure worktree isolation
Runs before the Step 2.5 long-lived-process launch (so the process starts in the right cwd) and
before Workflow generation.

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
printed), then invoke `relay:ensuring-worktree-isolation`, passing both blocks.

- **Initial run** (`$RELAY_DRIVE_RESUME` is `0`): the skill asks the one per-state
  `AskUserQuestion` (`worktree` / `main` / `stray`); on a **Create** choice it runs `--create` then
  `EnterWorktree({path: …})` **exactly once**. It records `RELAY_DRIVE_WORKSPACE=worktree` (entered
  path) or `RELAY_DRIVE_WORKSPACE=in-place` (recorded branch/checkout) into `loop-state.md`. When
  `RELAY_WT_ARG` was printed, the skill instead branches on the `--resolve` block's
  `RELAY_WT_RESOLVED` value — see `relay:ensuring-worktree-isolation` for the pre-answered branch
  table — and still records `RELAY_DRIVE_WORKSPACE` the same way.
- **Resume** (`$RELAY_DRIVE_RESUME` is `1`): the gate runs **verify-only** — no prompt, create, or
  enter. It reads `RELAY_DRIVE_WORKSPACE` from `loop-state.md` and asserts the cwd matches; a
  mismatch aborts with a clear error.

Abort the command on the skill's abort/cancel paths. If this session
cannot present an interactive question (headless, e.g. `claude -p`), skip the confirmation and
proceed **in place** — never create, enter, or switch worktrees without an answered confirmation.

## Step 0.55 — Record the active worktree
Runs immediately after the gate skill returns, whether or not `--worktree` was given.
The value crosses to the next step as printed stdout, so read it from this block.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --active || exit 1
```

## Step 1 — Classify the task kind
Read the oracle file at `$RELAY_DRIVE_ORACLE`. Run `relay:classifying-task-kind` over the oracle's
contents. Drive's free text is empty after flag-stripping, so classify the oracle contents, not
`$ARGUMENTS`.

The classifier infers one of `feature | script | config-artifact | bugfix | docs`. Surface the
kind to the user. The kind is **advisory**: it biases the soft zone only. The oracle proves done.

## Step 2 — Select the policy (branch on kind)
Each entry shapes an `agent()` node in the Step 3 Workflow — not an action in this thread.

Branch on `kind.value`. For every kind the HARD spine is the oracle-gated loop unchanged:
`orient → delegate → verify → branch → record → consecutive-clean-runs → closeout`. The soft zone
may add lenses; it never removes or reorders the hard spine, and it never substitutes for the
oracle's pass condition.

| kind | soft-zone bias on the delegate + verify nodes |
|---|---|
| `feature` | verification leans on tests the oracle names; a fix cycle may add `relay:panel` when the same step fails its cap |
| `bugfix` | orient reads the failing evidence first; the verify node re-proves the original symptom, not just the suite |
| `script` | verification is the script's own exit code and observable effect |
| `config-artifact` | verification re-reads the written artifact from disk rather than trusting the writing step's report |
| `docs` | verification resolves the references the step introduced; no test-suite lens |

## Step 2.5 — Load the protocol + own the long-lived process
Invoke `relay:driving-to-done` to load the protocol (four invariants, lean orchestrator,
circuit breaker, closeout). If `$RELAY_DRIVE_RESUME` is `1`, read `loop-state.md` first and continue from
the recorded position.

If the oracle declares a **single long-lived process** (dev server, watch build, tunnel), launch it
as a background task in MAIN **now, before generating the Workflow**, and record its task id in
`loop-state.md`. This is the only work MAIN does besides launching the Workflow — a process started
inside a leaf dies with that leaf, so it cannot live there. Otherwise skip this.

## Step 3 — Generate one Workflow
Call the `Workflow` tool now. Generate exactly one dynamic Workflow that drives the oracle to its done
criterion in a single run, over the Step 2 spine. The verify node proves the pass condition from REAL
evidence; on FAIL the branch node diagnoses and fixes, capped ≈3, then must re-prove from step 0.
Done is N consecutive clean runs (N=2) on a freshly-reset, pristine-verified seed, ending in closeout.
Place each leaf step as an `agent()` node inside the Workflow. Only Step 1, Step 2.5, and the
long-lived-process launch run in this thread; an inline loop forfeits the Workflow substrate's
isolation, journal resume, and phasing.

**Tier note.** Resolve the per-leaf tier ladder deterministically — never hand-derive it from `bindings/presets.yaml`:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" --all
```

For every `agent()` role node dispatched **in-session**, set `opts.model` and `opts.effort` from that role's printed row. A `model=inherit` row means OMIT `opts.model` (the node inherits the session model) — still set `opts.effort`. When in-session tiers are off, every row prints `inherit` and you set neither opt. For delegated (`delegate-and-watch`) nodes, pin the **outer watcher** `agent()` node from the resolver's `watcher` line; the inner worker's model comes from `modalities.*` at acpx dispatch time.

The printed rows already carry the two model overrides. `--fixes-model` and `--verification-model` replace the model of every role that carries the matching `category:` in `bindings/presets.yaml`, and the resolver's header names both values and where each one came from. Transcribe the rows; never re-apply an override by hand. An override changes the model column only — `opts.effort` always comes from the row. With in-session tiers off, the header says both overrides reached no row.

**Verify-node guard.** A verify node must separate three cases — no verdict, a verdict that is clean, and a verdict that carries findings. Write the guard so the absent case stays reachable:

> `if (!verdict) { /* unverified — retry or fail */ } else if (!verdict.blocking) { /* clean */ }`
>
> Collapsing them into `if (!verdict || !verdict.blocking) break` reports an unverified run as verified. Likewise, a `try/catch` around `agent()` that returns `null` on a schema miss converts a hard harness failure into a false success — if you catch, re-raise or record the miss as a failure in the returned result, never as an absent field. (Both anti-patterns are from a real failed run.)

Cite only `relay:delegate-leaf`, `relay:delegate-and-watch`, `relay:improve-loop`, `relay:staged-run`
and the language-reference doc.

**Worktree injection.** When Step 0.55 printed `RELAY_WT_ACTIVE=<value>`, classify each
oracle-loop leaf against the loop documented at the `## The loop (generated as one dynamic
Workflow)` heading in `skills/driving-to-done/SKILL.md` (Orient → Delegate → Verify → Branch
→ Record) plus the closeout step at that file's `## Closeout (the done criterion's tail)`
section, and inject the literal `RELAY_WT_ACTIVE` value (with `EXPECTED_HEAD` captured via
`git -C <literal> rev-parse HEAD`) only on the writer leaves:

- `orient` — reader, no injection.
- `verify` — reader ("confirm from REAL evidence in the envelope"), no injection.
- `delegate` — writer; inject the literal into `{{WORKTREE_PATH}}` at generation time. This
  applies whether `delegate` runs as `relay:delegate-and-watch` (acpx / smart-routing /
  bg-sessions) or as `relay:delegate-leaf` (the default in-session engine) — its landing-verify
  sub-step reads `{{WORKTREE_PATH}}` from this same generator's slot substitution.
- `branch` — writer for the composed FAIL-path fixer prompt; inject the literal.
- `record` — writes local state files (`loop-state.md`, `decision-log.md`) at MAIN's cwd, no
  injection.
- `closeout` — writer for the reconciled oracle + final summary that lands in the workspace;
  inject the literal.

## Step 3.5 — Record run intent
Runs **immediately after the `Workflow` tool returns** — `run_id` exists only then, in the tool
*result*.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/record-run-intent.sh" \
  --run-id "<runId>" --command drive --task-kind "<kind>" \
  --spine "" \
  --gates "" \
  --axis-source "<the source printed on the last Step 0 axis line>"
```

No role is skippable on this command, so pass `--gates ""`. Do not add axis values or task text —
the script already persists them, and a second copy can drift.

This is advisory bookkeeping. If it fails, report the reason and continue.

## Step 4 — Verify run completeness
Before reporting completion, confirm: exactly one `Workflow` run was launched, and no spine role
(`relay:delegate-leaf`, `relay:improve-loop`, `relay:staged-run`) was invoked directly in this thread.
If any ran inline, stop and re-issue the work as a single Workflow.

That check proves shape only. Then run the completeness gate with the `runId` from the `Workflow` tool result:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/verify-run-completeness.sh" <runId>
```

Branch on the exit code:

- `0` COMPLETE — proceed.
- `1` INCOMPLETE — do not report success. Name each dead node and the phase output it was to produce, then re-run those nodes or escalate.
- `2` INDETERMINATE — report that completeness could not be verified. Never treat it as a pass.

## Step 5 — Retro this run (only when `--retro` was passed with no target)
Skip this step entirely when Step 0 printed `enabled=0`.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<runId>"
```

Report the printed block verbatim. The retro is advisory and strictly read-only: it re-runs
nothing, writes no file, and never fails the command (exit codes as in Step 0.2). It runs
**outside** the Workflow by construction: a retro node would itself be an `agent({schema})` node,
subject to the failure mode it detects.

Read its `SILENT` line against the gate you just ran. Dead nodes with `attempt == 1` mean
**the completeness gate did not fire** — the gate needs attention, not just this run.

## Delegation wiring note
When `$RELAY_ENGINE` is `acpx` or `smart-routing` and a role's `delegate_eligible` is `true` in `bindings/presets.yaml`, substitute `relay:delegate-and-watch` for the in-session dispatch at that node (worker per `$RELAY_AGENT`). When `$RELAY_ENGINE` is `bg-sessions`, substitute the same way — the watcher's leg is `relay:dispatching-bg-agents` instead of the acpx driver. When `$RELAY_ENGINE` is `in-session`, leave the in-session dispatch in place.

## Closeout note
When the Workflow completes, MAIN updates memory and tears down the process it launched in Step
2.5. The Workflow's closeout step commits the durable artifacts (`loop-state.md`,
`decision-log.md`, `blocked-items.md`, the reconciled oracle, the final summary) onto the current
branch.
