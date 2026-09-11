---
description: "Adversarial refinement. Classifies the task, then generates one dynamic Workflow over an improve-loop spine keyed on the refine target (spec | plan | pr | ui). Accepts --target override."
disable-model-invocation: true
argument-hint: "[--engine in-session|acpx|smart-routing|bg-sessions] [--agent claude|codex|opencode|hybrid|smart-routing] [--fixes-model sonnet|opus|fable] [--verification-model sonnet|opus|fable] [--retro [<runId>|last]] [--target spec|plan|pr|ui] [--worktree current|<path-without-spaces>|<branch>]"
allowed-tools: Bash, EnterWorktree, AskUserQuestion, Skill, Workflow
---

# Relay Refine (L3)

## Step 0 — Dependency gate + engine/agent resolution

Run first; failure aborts the command.

The script prints the two `[relay]` lines below plus a `KEY=value` block; read them from
printed stdout — this Bash call is a fresh process, so nothing it exports survives.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" refine "$ARGUMENTS" || exit 1
```

The block is a script because a session isolated in a git worktree refuses an inline Bash
command that carries `source`, `$(…)`, `case` or `if`, and because sourcing `check-deps.sh`
under zsh ends the call silently. `engine=session-tree` is refused here.

Surface the printed axis; Step 3 injects those two values. `parse-engine-agent.sh` resolves
and validates the axis (flags, then the `.claude/relay.json` pin, then defaults; invariants
in-session⇒claude, bg-sessions⇒claude, smart-routing rejects literal workers), exports
`RELAY_ENGINE`/`RELAY_AGENT`/`RELAY_AXIS_SOURCE`; invalid input fails loudly. `check-deps.sh`
blocks if the `superpowers` plugin is missing.

## Step 0.2 — Retro-only mode
Runs only when Step 0 printed `enabled=1` **with a non-empty target**. Audit that run and
stop: do **not** enter a worktree, and do **not** generate a Workflow — a retro is read-only.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<target>"
```

Report the printed block verbatim and stop. Exit `0`: nothing found. Exit `1`: deviations
found (advisory — a retro never fails a command). Exit `2`: too little evidence to audit.
A bare `--retro` with no target runs the command normally and retros this run in Step 5.

## Step 0.25 — Ask when unpinned
Runs only when the Step 0 axis line printed `(source: default)`; any other source skips it.
If this session cannot present an interactive question (headless run, e.g. `claude -p`),
skip it and proceed with the resolved default axis.

Ask exactly one `AskUserQuestion`:

- **Question:** `No dispatch engine is pinned for this repo. How should relay dispatch this run's leaf work?`
- **Option 1 (listed first = default):** label `in-session (default)` — description:
  `Every leaf runs inside this session on the session model. No extra setup, but all tokens bill to this Claude session and long runs consume this session's context.`
- **Option 2:** label `acpx (hybrid)` — description:
  `Delegation-eligible leaves run as external acpx workers (per-role claude/codex split from bindings/presets.yaml). Requires acpx >= 0.12.0 and the codex CLI (/relay:setup checks this). Preserves this session's context; codex tokens bill to the codex plan at cold-cache input prices.`
- **Option 3:** label `bg-sessions (claude)` — description:
  `Delegation-eligible leaves run as background Claude sessions. No acpx or codex CLI needed. Preserves this session's context; every worker bills to the Claude plan.`

Tip: pin `{"engine": "in-session"}`, `{"engine": "acpx", "agent": "hybrid"}`, or
`{"engine": "bg-sessions"}` in `.claude/relay.json` to skip this question. `smart-routing`
is not offered — it stays flag- and pin-reachable only.

On `in-session (default)`: proceed. On either other choice, run one re-resolution block with
that option's pair, so the transcript carries the final axis (`prompt` is a command-layer
provenance value; the script never emits it):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only acpx hybrid --source prompt
```

For `bg-sessions (claude)` run
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only bg-sessions claude --source prompt`
instead. Step 3 injects the values from the **last** printed axis line.

## Step 0.5 — Ensure worktree isolation
Runs after the dependency gate and **before** Workflow generation:

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
`EnterWorktree({path: …})` **exactly once**. Abort the command on its abort/cancel paths.
When `RELAY_WT_ARG` was printed, the skill instead branches on the `--resolve` block's
`RELAY_WT_RESOLVED` value — see `relay:ensuring-worktree-isolation` for the pre-answered
branch table.

**In-place is the recommended option here.** Mark the in-place option **(Recommended)** for
both interactive states (`main` and `stray`) and drop that marker from the Create option;
refinement reads and patches in place.

If this session cannot present an interactive question (headless run, e.g. `claude -p`), skip
the confirmation and proceed **in place** — never create, enter, or switch worktrees without
an answered confirmation.

## Step 0.55 — Record the active worktree
Runs immediately after the gate skill returns, whether or not `--worktree` was given.
The value crosses to the next step as printed stdout, so read it from this block.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --active || exit 1
```

## Step 1 — Classify the task kind

Run `relay:classifying-task-kind` over `$ARGUMENTS` minus the parsed `--engine`/`--agent`/`--retro` flags and minus `--worktree` with its value. It infers one of `feature | script | config-artifact | bugfix | docs` from context. Surface the kind. It feeds `--task-kind` in Step 3.5.

## Step 2 — Select the policy (branch on TARGET, not kind)
Each entry below defines an `agent()` node in the Workflow you generate in Step 3 — not an action to perform in this thread.

Resolve the refine target from `--target` in `$ARGUMENTS` minus the parsed `--engine`/`--agent`/`--retro` flags (`spec | plan | pr | ui`). Branch on the target. For every target the HARD spine is `relay:improve-loop` over that target's critic/fixer:

- `spec` → the `relay:refining-specs` critic
- `plan` → the `relay:refining-plans` critic
- `pr`   → the `relay:refining-prs` critic
- `ui`   → the `relay:refining-ui` critic/fixer — the worker is the UI generator, the critic is the UI evaluation panel, and the loop converges under the scored `convergence_mode`, not the binary verdict of spec/plan/pr

The closed-enum kind check from §4.2.1 does NOT run here (target axis, not kind axis).

## Step 3 — Generate one Workflow
Call the `Workflow` tool now. Generate exactly one dynamic Workflow that runs the entire process in a single run. The roles named in Step 2 are leaf bodies: place each as an `agent()` node inside the generated Workflow. The only work that runs in this thread is the Step 1 classification. Running the spine inline forfeits the isolated runtime, native resume, and deterministic phasing of the Workflow substrate.

Each Bash call is a fresh process, so the Step 0 exports do not survive to a later tool call.
Put the **literal values** of `RELAY_ENGINE` and `RELAY_AGENT` captured in Step 0 in the
prompt of every `agent()` node that invokes `relay:refining-specs`, `relay:refining-plans`,
`relay:refining-prs`, or `relay:refining-ui` (alongside the adapter slug). All four shims take
the axis — omitting it from `relay:refining-ui` silently falls back to `in-session`/`claude`.

**Tier note.** Resolve the per-leaf tier ladder deterministically — never hand-derive it from `bindings/presets.yaml`:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" --all
```

For every `agent()` role node dispatched **in-session**, set `opts.model` and `opts.effort` from that role's printed row. A `model=inherit` row means OMIT `opts.model` — still set `opts.effort`. When in-session tiers are off, every row prints `inherit` and you set neither opt. Delegated (`delegate-and-watch`) nodes: pin the **outer watcher** `agent()` node from the resolver's `watcher` line, a role-independent constant. The inner worker's model comes from `modalities.*` at acpx dispatch time.

The printed rows already carry the two model overrides. `--fixes-model` and `--verification-model` replace the model of every role that carries the matching `category:` in `bindings/presets.yaml`, and the resolver's header names both values and where each one came from. Transcribe the rows; never re-apply an override by hand. An override changes the model column only — `opts.effort` always comes from the row. With in-session tiers off, the header says both overrides reached no row.

**Verify-node guard.** A verify node must separate three cases — no verdict, a clean verdict, and a verdict with findings. Keep the absent case reachable:

> `if (!verdict) { /* unverified — retry or fail */ } else if (!verdict.blocking) { /* clean */ }`
>
> Collapsing them into `if (!verdict || !verdict.blocking) break` reports an unverified run as verified. Likewise, a `try/catch` around `agent()` that returns `null` on a schema miss converts a hard harness failure into a false success — if you catch, re-raise or record the miss as a failure in the returned result, never as an absent field.
>
> (Both anti-patterns are from a real failed run.)

Cite only `relay:improve-loop`, `relay:delegate-and-watch` and the language-reference doc.

**Worktree injection.** When Step 0.55 printed `RELAY_WT_ACTIVE=<value>`, forward it into
each `relay:refining-specs`, `relay:refining-plans`, `relay:refining-prs`, or
`relay:refining-ui` shim's config alongside its `subject_adapter` field, as a new optional
`worktree: <literal>` config key.

## Step 3.5 — Record run intent
Runs **immediately after the `Workflow` tool returns** — `run_id` exists only then, in the
tool *result*.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/record-run-intent.sh" \
  --run-id "<runId>" --command refine --task-kind "<kind>" \
  --spine "<the Step 2 spine for the resolved target, as the agent() node LABELS, comma-separated>" \
  --gates "" \
  --axis-source "<the source printed on the last Step 0 axis line>"
```

No role is skippable on this command, so pass `--gates ""`.

`--spine` takes **node labels, not skill names.** The retro compares each recorded role
against the labels of the agent nodes that ran, so `relay:improve-loop` verbatim matches
nothing and reports a false SPINE deviation. `intended_spine` snapshots the spine at run time.

Do not add axis values or task text — the script already persists them, and a second copy can drift.

This is advisory bookkeeping. If it fails, report the reason and continue.

## Step 4 — Verify run completeness
Before reporting completion, confirm: exactly one `Workflow` run was launched, and no spine role (`relay:improve-loop`, `relay:refining-specs`) was invoked directly in this thread. If any ran inline, stop and re-issue the work as a single Workflow.

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
nothing, writes no file, and never fails the command — exit codes as in Step 0.2.

It runs **outside** the Workflow by construction: a retro node would itself be an
`agent({schema})` node, subject to the failure mode it exists to detect.

Read its `SILENT` line against the gate you just ran. If the retro names dead nodes whose
`attempt == 1`, **the completeness gate did not fire** — a signal that the gate needs attention.

## Delegation wiring note
The refining shim receives the resolved literal `RELAY_ENGINE` and `RELAY_AGENT` values and
decides each later leaf dispatch. When the engine is `acpx` or `smart-routing` and a role's
`delegate_eligible` is `true` in `bindings/presets.yaml`, it substitutes
`relay:delegate-and-watch` for the in-session dispatch (the worker is selected by the resolved
agent). When the engine is `bg-sessions`, it substitutes `relay:delegate-and-watch` the same
way, with `relay:dispatching-bg-agents` as the watcher's leg. With `in-session`, it leaves the
in-session dispatch in place.
