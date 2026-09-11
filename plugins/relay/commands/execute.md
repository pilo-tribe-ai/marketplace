---
description: "Open-ended composition. Classifies the task to bias soft-zone guidance, then freely composes one dynamic Workflow from the library with no hard floor."
disable-model-invocation: true
argument-hint: "[--engine in-session|acpx|smart-routing|bg-sessions] [--agent claude|codex|opencode|hybrid|smart-routing] [--fixes-model sonnet|opus|fable] [--verification-model sonnet|opus|fable] [--retro [<runId>|last]] [--worktree current|<path-without-spaces>|<branch>] <task>"
allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill
---

# Relay Execute (L3, 100% soft)

## Step 0 — Dependency gate + engine/agent resolution
Run first; any failure aborts the command.

The script prints the two `[relay]` lines below plus a `KEY=value` block; read them from
printed stdout — this Bash call is a fresh process, so nothing it exports survives.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" execute "$ARGUMENTS" || exit 1
```

The block is a script because a session isolated in a git worktree refuses an inline Bash
command that carries `source`, `$(…)`, `case` or `if`, and because sourcing `check-deps.sh`
under zsh ends the call silently. `engine=session-tree` is refused here.

`check-deps.sh` blocks if the `superpowers` plugin is missing. `parse-engine-agent.sh` resolves
and validates the axis (flags, then the `.claude/relay.json` pin, then defaults `in-session`⇒`claude`,
`acpx`⇒`hybrid`, `bg-sessions`⇒`claude`; invariants in-session⇒claude, bg-sessions⇒claude) and exports
`RELAY_ENGINE` / `RELAY_AGENT` / `RELAY_AXIS_SOURCE` / `RELAY_IN_SESSION_TIERS`. Invalid input fails loudly.

## Step 0.2 — Retro-only mode
Runs only when Step 0 printed `enabled=1` **with a non-empty target**. Audit that run and stop:
do **not** enter a worktree, and do **not** generate a Workflow.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<target>"
```

Report the printed block verbatim and stop. Exit `0` means no deviations, `1` means deviations
(advisory), `2` means too little evidence survives to audit.

## Step 0.25 — Ask when unpinned
Runs only when the Step 0 axis line printed `(source: default)`.
If this session cannot present an interactive question (headless run, e.g. `claude -p`), skip
this step and keep the default axis.

Ask exactly one `AskUserQuestion`:

- **Question:** `No dispatch engine is pinned for this repo. How should relay dispatch this run's leaf work?`
- **Option 1 (listed first = default):** label `in-session (default)` — description:
  `Every leaf runs inside this session on the session model. No extra setup; all tokens bill to this Claude session and consume its context.`
- **Option 2:** label `acpx (hybrid)` — description:
  `Delegation-eligible leaves run as external acpx workers (claude/codex split from bindings/presets.yaml). Requires acpx >= 0.12.0 and the codex CLI (/relay:setup checks this). Preserves this session's context; codex tokens bill to the codex plan.`
- **Option 3:** label `bg-sessions (claude)` — description:
  `Delegation-eligible leaves run as background Claude sessions. No acpx or codex CLI needed. Preserves this session's context; workers bill to the Claude plan.`

Each description ends with `Tip: pin {"engine": "<engine>"} in .claude/relay.json to skip this question permanently.` (acpx pins `"agent": "hybrid"` too). `smart-routing` is not offered; it stays flag- and pin-reachable.

On `in-session (default)`: proceed. On `bg-sessions (claude)`: run this re-resolution block
(`prompt` is a command-layer provenance value; the script never emits it):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" --axis-only bg-sessions claude --source prompt
```

On `acpx (hybrid)`: run the same line with `--axis-only acpx hybrid --source prompt`. The
Workflow's literal injection uses the **last** printed axis line.

## Step 0.5 — Ensure worktree isolation
Runs **before** Workflow composition:

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
per-state `AskUserQuestion`, and on **Create** runs `--create` then `EnterWorktree({path: …})`
**exactly once**. Abort on the skill's abort/cancel paths. When `RELAY_WT_ARG` was printed,
the skill instead branches on the `--resolve` block's `RELAY_WT_RESOLVED` value — see
`relay:ensuring-worktree-isolation` for the pre-answered branch table.
If this session cannot present an interactive question (headless run), skip the confirmation
and proceed **in place** — never create, enter, or switch worktrees without an answered confirmation.

## Step 0.55 — Record the active worktree
Runs immediately after the gate skill returns, whether or not `--worktree` was given.
The value crosses to the next step as printed stdout, so read it from this block.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --active || exit 1
```

## Step 1 — Classify (advisory)
Run `relay:classifying-task-kind` over `$ARGUMENTS` minus the parsed `--engine`/`--agent`/`--retro` flags and minus `--worktree` with its value; the composed task text is that same string. The kind is advisory: it only biases which patterns the soft zone weights. It keys NO hard floor.

## Step 2 — Compose freely
Call the `Workflow` tool now. Generate exactly one dynamic Workflow that runs the entire process in a single run. Each composed library pattern is a leaf body: place it as an `agent()` node inside the Workflow. The only work in this thread is the Step 1 classification; inline composition forfeits the isolated runtime, native resume, and deterministic phasing.

**Tier note.** Resolve the per-leaf tier ladder deterministically — never hand-derive it from `bindings/presets.yaml`:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" --all
```

For every `agent()` role node dispatched **in-session**, set `opts.model` and `opts.effort` from that role's printed row. A `model=inherit` row means OMIT `opts.model` but still set `opts.effort`. When tiers are off, every row prints `inherit` and you set neither opt. Delegated (`delegate-and-watch`) nodes: pin the **outer watcher** `agent()` node from the resolver's `watcher` line (a role-independent constant); the inner worker's model comes from `modalities.*` at acpx dispatch time.

The printed rows already carry the two model overrides. `--fixes-model` and `--verification-model` replace the model of every role that carries the matching `category:` in `bindings/presets.yaml`, and the resolver's header names both values and where each one came from. Transcribe the rows; never re-apply an override by hand. An override changes the model column only — `opts.effort` always comes from the row. With in-session tiers off, the header says both overrides reached no row.

**Verify-node guard.** A verify node must separate three cases — no verdict, a clean verdict, and a verdict with findings. Keep the absent case reachable:

> `if (!verdict) { /* unverified — retry or fail */ } else if (!verdict.blocking) { /* clean */ }`
>
> Collapsing them into `if (!verdict || !verdict.blocking) break` reports an unverified run as verified. Likewise, a `try/catch` around `agent()` that returns `null` on a schema miss turns a hard harness failure into a false success — if you catch, re-raise or record the miss as a failure in the returned result, never as an absent field. (Both anti-patterns are from a real failed run.)

Cite only the L2 skills (`relay:panel`, `relay:delegate-leaf`, `relay:delegate-and-watch`, `relay:improve-loop`, `relay:brainstorm-decide`, `relay:parallel-gather`, `relay:staged-run`) and the language-reference doc.

**Worktree injection.** When Step 0.55 printed `RELAY_WT_ACTIVE=<value>`: for each `agent()`
node whose role file declares `role-class: writer`, put the literal `RELAY_WT_ACTIVE` value
in the `WORKTREE_PATH` slot and capture `EXPECTED_HEAD` with `git -C <literal> rev-parse
HEAD`. Composed nodes that are not writer roles get nothing.

## Step 3.5 — Record run intent
Runs **immediately after the `Workflow` tool returns** — `run_id` exists only in the tool *result*.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/record-run-intent.sh" \
  --run-id "<runId>" --command execute --task-kind "<kind>" \
  --spine "" \
  --gates "" \
  --axis-source "<the source printed on the last Step 0 axis line>"
```

No role is skippable on this command, so pass `--gates ""`. Do not add axis values or task text — the script already persists them, and a second copy can drift. This is advisory bookkeeping: if it fails, report the reason and continue.

## Step 4 — Verify run completeness
Before reporting completion, confirm: exactly one `Workflow` run was launched, and no composed library pattern (`relay:delegate-leaf`, `relay:panel`, `relay:improve-loop`) was invoked directly in this thread. If any ran inline, stop and re-issue the work as a single Workflow.

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

Report the printed block verbatim; exit codes as in Step 0.2. The retro is advisory and strictly read-only: it re-runs nothing, writes no file, and never fails the command. It runs **outside** the Workflow by construction: a retro node inside the script would itself be an `agent({schema})` node, subject to the failure mode it detects.

Read its `SILENT` line against the gate you just ran. Dead nodes with `attempt == 1` mean **the completeness gate did not fire** — the gate needs attention, not just this run.

## Delegation wiring note
When `$RELAY_ENGINE` resolves to `acpx` or `smart-routing` and a role's `delegate_eligible` is `true` in `bindings/presets.yaml`, substitute `relay:delegate-and-watch` for the in-session dispatch at that node (worker per `$RELAY_AGENT`). For `bg-sessions`, substitute the same way with `relay:dispatching-bg-agents` as the watcher's leg. For `in-session`, keep the in-session dispatch.
