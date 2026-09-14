---
description: "Standalone problem diagnosis. Classifies the task, then generates one dynamic Workflow whose hard spine inspects then reaches a panel verdict; soft zone adds lenses."
disable-model-invocation: true
argument-hint: "[--retro [<runId>|last]] <problem>"
allowed-tools: Bash, AskUserQuestion(*), Workflow, Skill
---

# Relay Diagnose (L3)

Generate one dynamic Workflow that diagnoses the problem in `$ARGUMENTS`.

## Step 0 — Retro flag
This command has no engine/agent axis. Lift `--retro` out of `$ARGUMENTS` before Step 1. The
script prints the one `[relay] retro:` line plus `RELAY_RETRO=` / `RELAY_RETRO_TARGET=`, runs
no dependency gate, and resolves no axis; read them from printed stdout — this Bash call is a
fresh process, so nothing it exports survives.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" diagnose "$ARGUMENTS" || exit 1
```

## Step 0.2 — Retro-only mode
Runs only when Step 0 printed `enabled=1` **with a non-empty target**. Do **not** enter a worktree, and do **not** generate a Workflow — a retro is read-only.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<target>"
```

Report the printed block verbatim and stop. Exit `0`: clean. `1`: deviations (advisory — a retro never fails a command). `2`: too little evidence to audit. A bare `--retro` with no target runs the command normally and retros this run in Step 5.

## Step 1 — Classify the task kind
Run `relay:classifying-task-kind` over `$ARGUMENTS` minus `--retro` and its target. It infers one of `feature | script | config-artifact | bugfix | docs` from context. Surface the kind to the user.

## Step 2 — Select the policy (branch on kind)
Branch on `kind.value`. For every kind the HARD spine is `relay:delegate-leaf` (inspect phase) → `relay:panel` (verdict). The soft zone may add lenses (e.g. `relay:parallel-gather`) per each pattern's when-to-use signal; it never removes the hard spine.

## Step 3 — Generate one Workflow
Call the `Workflow` tool now. Generate exactly one dynamic Workflow that runs the whole process in a single run. Place each Step 2 role as an `agent()` node inside it. Only the Step 1 classification runs in this thread.

**Tier note.** Run the resolver; never hand-derive tiers from `bindings/presets.yaml`:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" --all
```

Set each `agent()` node's `opts.model` and `opts.effort` from its printed row. A `model=inherit` row means OMIT `opts.model`; still set `opts.effort`. With tiers off every row prints `inherit`; set neither. This command never delegates, so the **outer watcher** line does not apply.

**Verify-node guard.** Keep the no-verdict case its own branch:

> `if (!verdict) { /* unverified — retry or fail */ } else if (!verdict.blocking) { /* clean */ }`
>
> Collapsing them into `if (!verdict || !verdict.blocking) break` reports an unverified run as verified. A `try/catch` around `agent()` that returns `null` on a schema miss turns a hard harness failure into a false success — if you catch, re-raise or record the miss as a failure in the result, never as an absent field. (Both anti-patterns are from a real failed run.)

Cite only `relay:panel`, `relay:delegate-leaf`, `relay:parallel-gather` and the language-reference doc.

## Step 3.5 — Record run intent
Runs **immediately after the `Workflow` tool returns** (`run_id` is in the tool result).

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/record-run-intent.sh" \
  --run-id "<runId>" --command diagnose --task-kind "<kind>" \
  --spine "inspect,verdict" \
  --gates "" \
  --axis-source in-session
```

No role is skippable on this command, so pass `--gates ""`. Do not add axis values or task text — the script already persists them, and a second copy can drift. This is advisory bookkeeping: on failure, report the reason and continue.

## Step 4 — Verify run completeness
Before reporting completion, confirm: exactly one `Workflow` run was launched, and no spine role (`relay:panel`, `relay:delegate-leaf`, `relay:parallel-gather`) was invoked directly in this thread. If any ran inline, stop and re-issue the work as a single Workflow.

That check proves shape only. Then run the completeness gate with the `runId` from the `Workflow` tool result:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/verify-run-completeness.sh" <runId>
```

Branch on the exit code:

- `0` COMPLETE — proceed.
- `1` INCOMPLETE — do not report success. Name each dead node and the phase output it was to produce, then re-run those nodes or escalate.
- `2` INDETERMINATE — report that completeness could not be verified. Never treat it as a pass.

## Step 5 — Retro this run (only when `--retro` was passed with no target)
Skip this step when Step 0 printed `enabled=0`.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" "<runId>"
```

Report the printed block verbatim. The retro is advisory and strictly read-only: it never fails the command (exit codes as in Step 0.2).

It runs **outside** the Workflow by construction: a retro node inside the script would itself be an `agent({schema})` node, open to the failure it exists to detect.

Read its `SILENT` line against the gate you just ran. Dead nodes with `attempt == 1` mean **the completeness gate did not fire** — the highest-value finding a retro can produce.
