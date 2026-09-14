---
name: running-implement-spine
user-invocable: false
description: "Use to generate and run the one dynamic Workflow for a classified implement run — resolves the per-leaf tiers, builds the §4.2.1 spine, records the run intent, runs the completeness gate, and returns one JSON block. Backs the /relay:implement command and the relay:implementing-spec adapter."
---

# running-implement-spine

This skill holds the part of `/relay:implement` that generates and runs the one dynamic
Workflow. `/relay:implement` runs Steps 0 through 2 — flags, the engine question, the
worktree gate, the branch guard, task-kind classification, and the §4.2.1 branch table —
then calls this skill. `relay:implementing-spec` calls this skill too, from the other
entry point named in the design's §4 architecture. The skill holds no spine of its own;
the §4.2.1 branch table in `commands/implement.md` stays the one written authority.

## Inputs

- `kind` — the classified task kind (`feature | script | config-artifact | bugfix | docs`).
- `task` — the task description text.
- `spec_path` (optional) — the spec file path, when the caller has one.
- `engine` — the resolved dispatch engine.
- `agent` — the resolved dispatch agent.
- `verify` (boolean) — whether to append the verify-until-clean tail.
- `rounds` — the verify loop's round cap.
- `axis_source` — provenance of this run's dispatch axis (`flags`, `relay.json`,
  `default`, `prompt`, or a `<a>+<b>` combination — the same vocabulary
  `scripts/parse-engine-agent.sh` exports as `RELAY_AXIS_SOURCE`). `/relay:implement`
  forwards the source printed on its own last axis line. `relay:implementing-spec`
  passes `relay.json` when it read the `.claude/relay.json` pin, else `default`.
- `command` — the name of the caller, recorded as this run's command. `/relay:implement`
  passes `implement`. `relay:implementing-spec` passes `implementing-spec`. Step 3.5
  writes this value, and `scripts/retro-run.sh` prints it back as `RELAY_RETRO_COMMAND`.
- `closes_issue` (optional) — an issue number to close in the commit body.
- `keep_sessions` (boolean, optional, default `false`) — when true, Step 4.5 keeps this
  run's background sessions instead of deleting them. `/relay:implement` forwards its
  `--keep-sessions` flag here. `relay:implementing-spec` passes no such flag, so this
  input defaults to `false` for that caller and needs no edit.
- `worktree` (optional) — the literal absolute path to this run's active worktree, from
  `RELAY_WT_ACTIVE`. Absent means the caller printed no active-worktree line: generate
  dispatches exactly as today. When present, write the literal absolute path into each
  generated dispatch:
  - `acpx`: prefix the dispatch command with `WORKTREE=<literal>` —
    `WORKTREE=<literal> bash skills/dispatching-acpx-agents/acpx-dispatch.sh …`.
  - `bg-sessions`: prefix the dispatch command the same way —
    `WORKTREE=<literal> bash skills/dispatching-bg-agents/bg-dispatch.sh …`.
  - `in-session`, writer roles (`role-class: writer`): pre-fill `WORKTREE_PATH` with the
    literal and `EXPECTED_HEAD` (captured via `git -C <literal> rev-parse HEAD`) in the
    generated `agent()` prompt slots.
  - `in-session`, non-writer roles: nothing.
  - Never emit the literal string `${WORKTREE:-$REPO_ROOT}` when a literal path is
    available; that fallback expression stays in the dispatch scripts themselves as the
    safety net for a caller that supplies nothing.

## Step 3 — Generate one Workflow
This step never runs for a `session-tree` run. `session-tree` is a branch of Step 1 in
`commands/implement.md`, decided before this skill is ever called — that command's own
Step 3, the call into this skill, is itself skipped whenever Step 1 took it, so this
skill is never invoked at all on that path, and Step 3.5 below records no run intent
for it. `relay:implementing-spec` never runs `commands/implement.md`'s Step 1 either,
so the phrase does not apply to it: treat this precondition as always false for that
caller.

Call the `Workflow` tool now. Generate exactly one dynamic Workflow that runs the entire process beginning to end — from the first work-node through the final verify — in a single run. The roles named in Step 2 are leaf bodies: place each as an `agent()` node inside the generated Workflow. The only work that runs in this thread is the Step 1 classification. Running the spine inline forfeits the isolated runtime, native resume, and deterministic phasing that the Workflow substrate provides.

**Tier note.** Resolve the per-leaf tier ladder deterministically — never hand-derive it from `bindings/presets.yaml`:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" --all
```

For every `agent()` role node this Workflow dispatches **in-session**, set `opts.model` and `opts.effort` from that role's printed row. A `model=inherit` row means OMIT `opts.model` so the node inherits the session model — still set that row's `opts.effort`. When in-session tiers are off, every row prints as `inherit` and you set neither opt. Delegated (`delegate-and-watch`) nodes: pin the **outer watcher** `agent()` node from the resolver's `watcher` line — it is a role-independent node-kind constant (the watcher only launches, waits, buckets the exit, and routes; when tiers are off its line prints `inherit` and you set neither opt). The inner worker is unaffected — its model comes from `modalities.*` at acpx dispatch time. A delegated node reaches its worker through `bash "${CLAUDE_PLUGIN_ROOT}/skills/dispatching-acpx-agents/acpx-dispatch.sh"` (see `relay:dispatching-acpx-agents`); do not substitute a single-turn prompt helper for it.

The printed rows already carry the two model overrides. `--fixes-model` and `--verification-model` replace the model of every role that carries the matching `category:` in `bindings/presets.yaml`, and the resolver's header names both values and where each one came from. Transcribe the rows; never re-apply an override by hand. An override changes the model column only — `opts.effort` always comes from the row. With in-session tiers off, the header says both overrides reached no row.

**The `write-plan` node.** The node dispatches through `relay:delegate-leaf` using the node label `write-plan`, the same way the branch table resolves every other kind's role from a label. It runs after `refine-spec` and before `refine-plan`.

- Run the node only when no file under `docs/plans/` matches the spec slug. If a plan is present, skip the node.
- When the run has no spec file at all, skip `write-plan` **and** `refine-plan`, and go straight to `implement`. Do not make an empty spec.
- Fill all six role slots: `SPEC_FILE_PATH`, `SPEC_CONTENT`, `SLUG`, `PLAN_PATH`, `REPO_ROOT`, `TASK_DESCRIPTION`. `SLUG` is the spec filename stem. `PLAN_PATH` is `<REPO_ROOT>/docs/plans/<SLUG>.md`. `SPEC_CONTENT` is the full text of `SPEC_FILE_PATH`.
- The role prints `PLAN_PATH=<path>`. The plan adapter reads a lower-case `plan_path`. Bind them with the literal line `plan_path = PLAN_PATH` before `refine-plan` runs. The case is different, and nothing bound them before.
- If `refine-plan` finds no subject, the adapter returns `SUBJECT_MISSING` and the run stops. An empty plan is not an acceptable plan.

**The `commit` node.** The node runs in the coordinator, not in a leaf. The implementer leaf stays read-only on git: it never runs a git mutation, because recording commits is the parent coordinator's job.

- Message: `<type>(<scope>): <summary>`. The type comes from the kind: `feature` gives `feat`, `bugfix` gives `fix`, `docs` gives `docs`, `script` and `config-artifact` give `chore`.
- Scope: the spec slug. With no spec, use the top directory the diff touches.
- Body: add `Closes #<n>` when the caller supplied `closes_issue`.
- If `git status --short` prints nothing, the node fails and the run reports `error`. A run that changed no file is not a clean run.

**Verify-node guard.** A verify node must separate three cases — no verdict, a verdict that is clean, and a verdict that carries findings. Write the guard so the absent case stays reachable:

> `if (!verdict) { /* unverified — retry or fail */ } else if (!verdict.blocking) { /* clean */ }`
>
> Collapsing them into `if (!verdict || !verdict.blocking) break` reports an unverified run as verified. Likewise, a `try/catch` around `agent()` that returns `null` on a schema miss converts a hard harness failure into a false success — if you catch, re-raise or record the miss as a failure in the returned result, never as an absent field.
>
> Both anti-patterns come from a real failing generated script. It carried a prose output contract *and* a `safeAgent` wrapper added to survive that contract's misses; the wrapper is what made the failure silent. The mitigation caused the silent failure it was added to survive.

### The verify-until-clean loop — only when `--verify` was passed

Generate this tail only when the `verify` input is true. (`/relay:implement` derives that
input from Step 0's printed `enabled=1`; `relay:implementing-spec` always passes
`verify=true` directly — design §8 step 5. Gate on the `verify` input itself, never on
Step 0 or on any fact only `/relay:implement` produces.) Invoke `relay:verifying-until-clean` to
generate the round nodes and the terminal report node. The skill appends its nodes to this same
Workflow, right after the branch's `verify` node — this skill generates no second `Workflow`,
so exactly one Workflow still runs.

Declare no loop identity here. `relay:verifying-until-clean` takes the engine and nothing else,
and this skill must not rename a node, a session, or the state directory. `/relay:implement --verify` has to produce exactly
what `/relay:implement` followed by `/relay:verify` produces, down to the session names, and a
per-caller name would break that.

**Pass this run's engine to the loop.** `/relay:verify` resolves the same axis with the same
script, so the two paths stay equal only when this tail uses the engine this run resolved. Take
that engine from this skill's own `engine` input — never from `$RELAY_ENGINE`. That variable is
exported by `/relay:implement`'s own Step 0, and `relay:implementing-spec` never runs Step 0 and
exports no such variable; reading it here would make the loop unreachable on that caller's path.
The `engine` input carries the same value for both callers, so set it explicitly before
branching:

```bash
RELAY_ENGINE="<this run's engine input>"
case "$RELAY_ENGINE" in
  in-session|acpx) RELAY_VERIFY_ENGINE="$RELAY_ENGINE" ;;
  *)
    echo "[relay] verify: engine=$RELAY_ENGINE has no verify-loop substrate — the loop runs in-session"
    RELAY_VERIFY_ENGINE="in-session"
    ;;
esac
export RELAY_VERIFY_ENGINE
echo "[relay] verify: loop engine=$RELAY_VERIFY_ENGINE"
```

The substitution is printed, never silent. A hard rejection here would throw away a finished
build over its last step, and the loop is a tail, not the work.

**When the loop engine is `acpx`,** the skill asks the user one question before it generates any
node, because the loop then runs headless child sessions with the approval gate off. Ask it
here too, for the same reason and with the same words: `/relay:verify` asks it under acpx, so a
`--verify` tail that did not ask would make the two paths differ. Do not skip that question, and
do not answer it for the user. When the user does not agree, generate no loop node and report
the run as unverified. The spine keeps whatever result it already earned.

**When the loop engine is `in-session`,** ask nothing. No child process starts, so no approval
gate is turned off. `/relay:verify` asks nothing there either, so the two paths still match.

The report node ends in one of the three terminal states `relay:verifying-until-clean` defines
for `RELAY_VERIFY_RESULT`: `clean`, `findings`, or `unverified`. Before the command reports
completion, name the reason plainly:

- `unverified (acpx unavailable)` — the helper exited `69`. The acpx engine only.
- `unverified (no reply)` — a step recorded `failed:no-reply`, so it invoked nothing or
  answered with an empty file. The in-session engine only.
- `unverified (loop blocked)` — the loop ran and could not reach a verdict.
- `findings` — the loop ran and the branch still carries problems.

A run is reported clean only when the loop's own result reads `clean`. Never report the two
other states as a clean run.

A bare run produces no `RELAY_VERIFY_RESULT` at all, because no loop ran. Report that the loop
did not run. Never read the absence of the loop as a clean result.

Cite only `relay:delegate-leaf`, `relay:delegate-and-watch`, `relay:improve-loop`, `relay:panel`, `relay:parallel-gather`, `relay:verifying-until-clean`, and the language-reference doc.

## Step 3.5 — Record run intent
This step never runs for a `session-tree` run, for the same reason as Step 3 above: that
branch is decided by `commands/implement.md`'s own Step 1, before this skill is ever
called. `session-tree` allocates its own runid through `scripts/bg-manifest.sh` instead,
and this bookkeeping step's script never runs for a session-tree run (spec §Deliverable 3,
Bookkeeping). `relay:implementing-spec` never runs that Step 1 either, so treat this
precondition as always false for that caller too.

Runs **immediately after the `Workflow` tool returns** — `run_id` exists only then, and it is
returned in the tool *result*, never echoed back from the input.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/record-run-intent.sh" \
  --run-id "<runId>" --command "<this run's command input>" --task-kind "<kind>" \
  --spine "<the Step 2 branch row for this kind, as the agent() node LABELS, comma-separated>" \
  --gates "<verify-loop=false unless the verify input is true; add write-plan=false when the write-plan node was skipped>" \
  --axis-source "<this run's axis_source input>"
```

`--command` takes the `command` **input**, never the literal word `implement`. This skill
has two entry points, and the record must name the one that ran. A hardcoded `implement`
records every `apk`-driven run through `relay:implementing-spec` as a `/relay:implement`
run, so `scripts/retro-run.sh` prints `RELAY_RETRO_COMMAND=implement` for a run that
command never started, and the audit trail names the wrong caller. This is the same class
of gap that `engine`, `axis_source` and `--gates` closed when the spine got its second
caller: a value that was correct while one caller existed, and became a lie when the
second one arrived.

`--gates` keys on **node labels** — the same strings recorded in `--spine`. The retro
suppresses a role by looking that role up in `gates`, so a key naming anything else
matches no role and suppresses nothing. Record a gate only for a spine role this run
deliberately did not dispatch. A setting that changes *how* a node runs rather than
*whether* it runs is not a gate: with delegation off every spine role still dispatches
(`relay:delegate-leaf` stands in for `relay:delegate-and-watch`), and C4 AXIS already
reports on delegation wiring from the script's own consts.

`verify-loop` is the one skippable role in this spine. Key the gate on the `verify` **input**
this skill received, never on a flag: `/relay:implement` sets that input from `--verify`, but
`relay:implementing-spec` passes no flags at all and always sets `verify=true`. When `verify`
is true the loop dispatches, so the value is `""`. When `verify` is false it does not, so the
value is `verify-loop=false`. A literal reader that looked for `--verify` on the adapter path
would record `verify-loop=false` for a run whose loop did dispatch, and corrupt the retro.

Record that gate. It is not optional bookkeeping. `scripts/retro-run.sh` matches an intended role
against the joined node labels as a **substring**, and a bare run produces no label containing
`verify-loop`. Omit the gate and every bare run reports a `SPINE` deviation that describes a
healthy run. The gate makes the retro drop the role from its expected set instead.

`--spine` takes **node labels, not skill names.** The retro compares each recorded role
against the labels of the agent nodes that actually ran, so recording the branch row
verbatim — `relay:delegate-leaf(implement)` — matches nothing and makes a perfectly healthy
run report a SPINE deviation. For `feature` the correct value is
`refine-spec,write-plan,refine-plan,implement,commit,verify,verify-loop` for both a bare run and a `--verify`
run: the recorded spine is the same, and only the `--gates` value differs — a bare run gates
`verify-loop` off, a `--verify` run leaves it empty. Recording `verify-loop` here is what makes
the gate above load-bearing: `retro-run.sh` suppresses a role only when it is in the recorded
spine, so a bare run that dropped `verify-loop` from the spine would make `verify-loop=false`
suppress nothing. The other kinds drop the leading refine roles the same way. Whatever label you
gave the node is what goes in.

Record `write-plan` in `--spine` on every `feature` run, whether the node ran or not, because
`retro-run.sh` suppresses a role only when that role is in the recorded spine.

Record only what no artifact preserves. The runId is the join key; `kind` and the command
identity appear nowhere else (`workflowName` is free text); `intended_spine` snapshots the
§4.2.1 row **at run time**, so a later retro of this run does not diff it against a table
that has since changed. Do **not** add the axis values or the task text — both are already
persisted as `const ENGINE` / `const AGENT` / `const TASK` in the script, and a second copy
can disagree with the first.

This is advisory bookkeeping. If it fails, report the reason and continue — the run already
succeeded, and a later retro simply degrades its spine-coverage check to "unknown".

## Step 4 — Verify run completeness
This step never runs for a `session-tree` run, for the same reason as Step 3 above: that
branch is decided by `commands/implement.md`'s own Step 1, before this skill is ever
called, so this step's "exactly one `Workflow` run was launched" check does not run and
must not fire its "stop and re-issue the work as a single Workflow" branch against a run
that generated no Workflow by design. `relay:implementing-spec` never runs that Step 1
either, so treat this precondition as always false for that caller too.

Before reporting completion, confirm: exactly one `Workflow` run was launched, and no spine role (`relay:delegate-leaf`, `relay:improve-loop`, `relay:panel`) was invoked directly in this thread. If any ran inline, stop and re-issue the work as a single Workflow.

That check proves shape only — one run, nothing inline. It never proves that every node produced output. Then run the completeness gate, passing the `runId` from the `Workflow` tool result:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/verify-run-completeness.sh" <runId>
```

Branch on the exit code:

- `0` COMPLETE — proceed.
- `1` INCOMPLETE — do not report success. Name each dead node and the phase output it was to produce, then re-run those nodes or escalate.
- `2` INDETERMINATE — report that completeness could not be verified. Never treat it as a pass.

A `0` here proves shape only. It does not turn a non-clean `verify-loop` result into a success —
report the loop's own result (`clean`, `findings`, or `unverified`), never the gate's exit code,
as the run's outcome. On a bare run there is no loop result to report, and a `0` here says
nothing about whether the branch verifies. Say that the loop did not run.


## Step 4.5 — Clean up the run's background sessions

Runs only when the `engine` input is `bg-sessions`. `session-tree` never reaches this
skill — that branch is terminal in `commands/implement.md` Step 1 — and every other
engine launched no background session, so there is nothing to clean up.

Resolve the run's status **before** running the cleanup, so a failed run keeps its
sessions readable for debugging: `--outcome clean` when the run is about to report
`status: ok`, `--outcome failed` otherwise. `--runid` is the Workflow `run_id`
(`wf_...`) from Step 3.5 — `scripts/bg-cleanup.sh` normalizes it itself. Pass `--keep`
when the `keep_sessions` input is true.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/bg-cleanup.sh" --runid "<run_id>" --outcome "<clean|failed>" [--keep]
```

The cleanup never changes the JSON `status` this skill prints in `## Output` — it is
advisory: it never turns an `ok` run into a failure and never turns a failed run into
`ok`. It must never run silently. Branch on the exit code and always print something
from this table:

| Exit | Spine behavior |
|---|---|
| `0` | Report the final `RELAY_BG_CLEANUP=` line. Done. |
| `1` | At least one session did not stop. Send the pinned finish-and-stop message (`docs/bg-dispatch-contract.md` §Spawn authority) via `SendMessage` to each printed `RELAY_BG_STOP_REQUIRED=` name, then re-run the identical `bg-cleanup.sh` command. At most two re-runs. If a session still does not read `stopped`, name it in the run's report and continue. If `SendMessage` is genuinely unavailable in this session, say so in the report and name the sessions — never report them as stopped. |
| `2` | A usage error here is a relay bug, not a run failure. Report the stderr line verbatim and continue. Never retry — the arguments will not change on a retry. |
| `3` | Zero sessions were recorded for this runid. Say so plainly (`no background session was recorded for this run`) and continue. This is legal for a `bg-sessions` run whose leaves all fell through to in-session dispatch — it is not a failure and not a clean deletion. |

## Output

The last thing this skill prints is one fenced JSON block, and nothing after it:

```json
{"status": "ok", "run_id": "wf_...", "branch": "...", "commit": "abc1234"}
```

`status` is `ok`, `blocked`, or `error`. Print `ok` only when the run finished, the
`commit` node made a commit, and — when the caller asked for `verify` — the loop reported
`clean`. On any other value, add a `reason` field that states the cause in plain words:
`findings`, `unverified (acpx unavailable)`, `unverified (no reply)`,
`unverified (loop blocked)`, or the failing node's name. Never print `ok` for a run that
made no commit.
