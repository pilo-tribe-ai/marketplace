# Relay bg engines: auto mode, session cleanup, nested dispatch — design (4.45.0)

**Status:** approved. The design decisions below were settled with the user. This document
turns them into an implementable specification. It does not re-open them.

**Target version:** `plugins/relay/.claude-plugin/plugin.json` 4.44.0 → **4.45.0**.

**Scope:** `plugins/relay/` only. No other plugin in this monorepo changes.

**Three bundled parts:**

1. `auto` becomes the unattended permission mode for background children.
2. A run deletes the background sessions it created, once the run completes.
3. Nested dispatch: a bg child may run its own dynamic Workflow, capped at depth 1.

---

## 0. Spike evidence — what was proven before this design was accepted

Two gates were spiked live before this work was approved. Both PASSED. A later reader
should know exactly what was measured, because several decisions below rest on it.

### Setup

A throwaway git repository at `~/.claude/jobs/8e54c304/tmp/spike-repo`: `calc.py` with a
deliberately wrong `return a - b`, and `test_calc.py` asserting `add(2, 3) == 5`. Start
commit `4f7b3ac "initial: failing test"`, verified failing (`assert -1 == 5`).

### Launch

Launched through the sanctioned launcher `plugins/relay/scripts/bg-launch.sh`, unmodified:

```
--name spike-implementer-auto1x --model sonnet --permission-mode auto \
  --prompt-file <prompt>
```

Output: `RELAY_BG_NAME=spike-implementer-auto1x`, `RELAY_BG_SHORT_ID=c8b75479`,
`RELAY_BG_LAUNCH=OK`. **`bg-launch.sh` accepted `auto` with no change** — it hard-refuses
only `dontAsk`.

### Gate 1 — a realistic leaf finishes under `--permission-mode auto`: **PASS**

All four sub-gates met.

- The handoff file exists and its last line is exactly `ROLE_DONE`.
- `git log` in the scratch repo: `d1b9746 fix: add returns the sum` on top of `4f7b3ac`.
- `pytest` re-run by the spike operator after the child finished: `1 passed in 0.02s`.
- **No classifier refusal anywhere in the child transcript.** The transcript header reads
  `"permissionMode":"auto","sessionKind":"bg"`. A grep for user-denied / tool-rejected /
  permission-denied / requested-permissions patterns returned nothing. Under `auto` the
  child freely ran Bash (pytest, `git add`/`commit`/`merge`/`worktree remove`,
  `rm -rf __pycache__`), Write, Edit, EnterWorktree, ToolSearch, and a Workflow that
  spawned a subagent. Nothing was gated.

### Gate 2 — a bg child holds the `Workflow` tool: **PASS**

The child ran this dynamic Workflow:

```js
export const meta = { name: 'ping-probe', description: 'Single trivial agent replies PING', phases: [{ title: 'Ping' }] }
phase('Ping')
const result = await agent('Reply with the word PING and nothing else.', { label: 'ping' })
return { result }
```

Independent evidence, not the child's self-report: the workflow journal at
`…/subagents/workflows/wf_568b2cdf-9fc/journal.jsonl` holds a `started` and a `result`
record for `agentId aa41f90df5bd4099d` with `"result":"PING"`, plus a real agent
transcript `agent-aa41f90df5bd4099d.jsonl`.

**One consequence for Part 3:** the `Workflow` tool returns immediately
(`"Workflow launched in background. Task ID: wuz2dg8m7"`). The child had to `ToolSearch`
for `TaskOutput`/`TaskGet` to collect the result. A nested Workflow is an **async handoff**,
not a blocking call. Part 3 states what the child must do about that.

### One non-permission blocker found, and what it means here

On its first edit attempt the child was stopped by the **background-session worktree
guard**, verbatim:

> This background session hasn't isolated its changes yet. Call EnterWorktree first so
> edits land in a worktree instead of the shared checkout, then retry this edit using the
> worktree path.

This is **not** the auto-mode classifier and **not** a refusal. It is a separate guard that
fires on every bg session in a git repository, whatever the permission mode — so
`bypassPermissions` would hit it too, and switching to `auto` neither causes nor cures it.
The child recovered on its own: `EnterWorktree` → edit and commit on a worktree branch →
`git merge --ff-only` back → `git worktree remove` and branch delete. Two side effects are
worth recording: it had to `rm -rf __pycache__` because untracked `.pyc` files blocked the
merge, and the merged commit carried two `__pycache__` blobs it should not have.

**Consequence:** a less careful implementer leaf can leave its work stranded on an unmerged
worktree branch. This is a pre-existing property of bg dispatch, out of scope here, and
recorded in §7 Future work so it is not lost.

### Two launcher facts confirmed by the spike

1. The `--name` must contain a roster role token from `plugins/relay/roles/*.md` (or
   `docs/agent-roster.md`) plus a `-[a-z0-9]{4,8}` runid suffix.
2. **`bg-launch.sh` has no cwd argument.** The child inherits the caller's cwd. The spike
   used a one-line wrapper that `cd`-ed into the scratch repo first. `bg-dispatch.sh`
   already does the same (`cd "$WORKTREE" && bash "$_bgd_launcher" …`). Part 3's depth
   marker relies on the same parent→child inheritance; see §3.4.

---

## 1. Part 1 — `auto` becomes the unattended permission mode

### 1.1 The mapping, before and after

`bindings/presets.yaml` roles carry `permissions: approve-all` or
`permissions: approve-reads`, or no `permissions` key at all. That value maps once onto the
CLI `--permission-mode` for every bg caller.

**Before (4.44.0):**

| Binding `permissions` value | CLI `--permission-mode` |
|---|---|
| `approve-all` | `bypassPermissions` |
| `approve-reads` | `plan` |
| (no `permissions` key) | `plan` |

**After (4.45.0):**

| Binding `permissions` value | CLI `--permission-mode` |
|---|---|
| `approve-all` | `auto` |
| `approve-reads` | `plan` |
| (no `permissions` key) | `plan` |

`bypassPermissions` **leaves the mapping table entirely**. After this change no binding
value selects it.

### 1.2 What does not change

- **`bg-launch.sh` still accepts `bypassPermissions` as a raw `--permission-mode`
  argument.** Hand-run spikes and `tests/e2e/bg-s1-roundtrip.sh` pass it directly. The
  launcher validates the mode only by refusing `dontAsk`; it needs **no code change** for
  this part. Do not add an allowlist of modes to `bg-launch.sh`.
- **`bg-launch.sh` still refuses `dontAsk`, unchanged.** The S3-1 note stays word for word:
  a `dontAsk` child was denied Bash outright.
- **The frozen envelope tokens do not change.** `ROLE_DONE`, `BLOCKED: <reason>`,
  `NEEDS_DECISION: <question>`, and bare `KEY=VALUE` lines are pinned by
  `tests/unit/skill-structure/test_envelope_tokens.py`, which must not be edited.
- **The five watcher exit buckets do not change**: `done`, `not-done`, `blocked`,
  `needs-decision`, `errored`.
- `bindings/presets.yaml` does not change. The five `permissions: approve-all` roles
  (`plan-writer`, `implementer`, `fix-coder`, `test-writer`, `ui-generator`) keep that
  value; only what it maps to changes.

### 1.3 Classifier-refusal behavior for the child

`auto` is a **classifier**, not a blanket grant. It can refuse a tool call with no human
present. A child therefore needs a defined behavior for a refusal.

Add to `skills/dispatching-bg-agents/preamble.md`: on a classifier refusal, the child
**stops** and emits, as the **first line** of its final text (and, for the bg-sessions leg,
as the first line of the handoff-file envelope):

```
BLOCKED: classifier refused <tool>: <reason>
```

The child:

- does **not** retry the call,
- does **not** try to escalate or change its own permissions,
- does **not** reword the call and try again.

This reuses the frozen `BLOCKED:` token, so it lands in the watcher's existing `blocked`
bucket. **No new routing, no new token, no watcher change.**

`<tool>` is the tool name as the harness reported it (for example `Bash`, `Edit`).
`<reason>` is the refusal text the harness printed, on one line.

The exact literal string that must appear in `preamble.md`, and that a test pins:

```
BLOCKED: classifier refused <tool>: <reason>
```

The `TURN=` echo rule already in the preamble still applies: the `BLOCKED:` sentinel is the
first non-empty line and `TURN=<n>` is the first `KEY=VALUE` line under it.

### 1.4 Failure-behavior row

Add exactly one row to the failure-behavior table in `docs/bg-dispatch-contract.md`,
in the same shape as the rows already there (three columns: Failure, bg-sessions (watcher),
session-tree (orchestrator)):

| Failure | bg-sessions (watcher) | session-tree (orchestrator) |
|---|---|---|
| Classifier refused a tool call under `auto` | Child writes `BLOCKED: classifier refused <tool>: <reason>` and stops → `blocked` bucket | Child sends the same `BLOCKED:` line to its operator → recorded in the manifest, routed as any other `BLOCKED:` |

### 1.5 Every site that performs or states the mapping

Found by searching `approve-all` and `bypassPermissions` across `plugins/relay/`. These are
the sites the implementer must change. Search again before editing — do not trust line
numbers.

| File | What is there now | Change |
|---|---|---|
| `docs/bg-dispatch-contract.md`, §"Permission-mode mapping" | The three-row table with `bypassPermissions` | Replace `bypassPermissions` with `auto` in the `approve-all` row and rewrite its cell text. Add a short paragraph stating that `auto` is a classifier, not a blanket grant, that it can refuse with no human present, and that `bg-launch.sh` still accepts `bypassPermissions` as a raw argument for hand-run spikes and `tests/e2e/bg-s1-roundtrip.sh`. |
| `docs/bg-dispatch-contract.md`, §"Failure behavior" | Five rows | Add the §1.4 row. |
| `docs/bg-dispatch-contract.md`, §"Spawn authority" | The stop mechanism, with no message wording | Add the pinned finish-and-stop wording (§2.3 Step 2). Part 2, listed here so the whole doc's edits are in one table. |
| `skills/dispatching-bg-agents/bg-dispatch.sh`, the `case "$_bgd_permissions"` block and the comment above it | `approve-all) _bgd_mode="bypassPermissions" ;;` | `approve-all) _bgd_mode="auto" ;;` and update the comment. The `*)` unmapped-value error message stays as it is — it names the three accepted **binding** values, not CLI modes. |
| `skills/dispatching-bg-agents/SKILL.md`, "Wrapper responsibilities" step 5 | `` (`approve-all` → `bypassPermissions`; `approve-reads` or absent → `plan`) `` | `` (`approve-all` → `auto`; `approve-reads` or absent → `plan`) `` |
| `skills/dispatching-bg-agents/preamble.md` | no refusal rule | Add the §1.3 rule. |
| `scripts/bg-launch.sh` header comment | Describes the `dontAsk` refusal | No behavior change. Optionally note that `auto` is the unattended mode a binding now selects and that `bypassPermissions` stays accepted as a raw argument. No test pins this. |

**`skills/orchestrating-session-trees/SKILL.md` performs no mapping of its own.** It defers
every launch to `bg-launch.sh` and defers the mapping to the contract doc. Confirmed by
reading the file: it contains neither `approve-all` nor `bypassPermissions`. It therefore
needs no edit for Part 1. Do not add a second copy of the table to it.

Everything else the search finds is the **acpx** `--approve-all` CLI flag, a different
mechanism on a different transport. Do not touch any of it. Specifically leave alone:
`skills/dispatching-acpx-agents/*`, `scripts/run-claude-command.sh`,
`scripts/run-claude-prompt.sh`, `skills/verifying-until-clean/SKILL.md`,
`commands/verify.md`, `docs/dispatch-contract.md`'s `ACPX_PERMISSIONS` row,
`bindings/presets.yaml`'s comment about the acpx approval mode, and the CHANGELOG history.

### 1.6 Tests for Part 1

**`tests/unit/skill-structure/test_bg_dispatch_env.py` — extend, do not rewrite.**

`test_permission_mode_mapping` currently asserts `implementer → bypassPermissions`.
Change it to assert:

- `implementer` (`permissions: approve-all`) → `RELAY_BG_PERMISSION_MODE=auto`
- `code-reviewer` (`permissions: approve-reads`) → `plan`
- `scout` (no `permissions` key) → `plan`

Add one new test that reads `bindings/presets.yaml` directly and asserts **no role's
`permissions` value maps to `bypassPermissions`** — that is, every role either has no
`permissions` key, or a value in `{approve-all, approve-reads}`, and the dispatcher maps
none of them to `bypassPermissions`. The strongest form: run `bg-dispatch.sh` for every
`delegate_eligible: true` role in the presets file and assert no sidecar holds
`RELAY_BG_PERMISSION_MODE=bypassPermissions`. This is the guard that stops a future preset
value from quietly restoring the blanket grant.

**`tests/unit/skill-structure/test_bg_dispatch_contract.py` — must be edited.**
`test_permission_mode_mapping_rows` asserts
`"approve-all" in text and "bypassPermissions" in text`. That assertion passes for the wrong
reason after the change, because the doc still mentions `bypassPermissions` in the
raw-argument note. Rewrite it to assert the `approve-all` row maps to `` `auto` `` and that
`bypassPermissions` no longer appears in the mapping table itself. Also add a test for the
new failure-behavior row (`classifier refused`).

**New test — the exact `BLOCKED:` wording.** Pin the literal string
`BLOCKED: classifier refused <tool>: <reason>` in `preamble.md`. Put it in
`test_dispatching_bg_skill.py` (the module that already owns preamble assertions) or in the
new `TestVersion4450` class. Assert the literal, not a paraphrase — a test that greps only
for `classifier` proves nothing.

**`tests/unit/skill-structure/test_bg_launch.py` — no change required.** Its
`mode="bypassPermissions"` default exercises the launcher's raw-argument path, which stays
supported on purpose. Leave it.

**`tests/unit/skill-structure/test_envelope_tokens.py` — must NOT be edited.** Part 1 adds
no token.

---

## 2. Part 2 — delete the bg sessions a run created, once the run completes

### 2.1 The problem

A run that launches background sessions leaves them behind: a live or stopped session, a
job directory at `~/.claude/jobs/<short-id>/`, and a transcript file under
`~/.claude/projects/`. Nothing collects them today. The bg-sessions watcher stops a child on
the `done` and `errored` buckets, and the session-tree orchestrator stops its children at
end of run, but neither deletes anything, and a `needs-decision` child is deliberately left
alive. Over many runs this accumulates without bound.

### 2.2 New script: `plugins/relay/scripts/bg-cleanup.sh`

```
bg-cleanup.sh --runid <id> --outcome <clean|failed> [--keep]
```

The file must be executable (`chmod +x`), like every other script in `scripts/`.

**`--runid <id>`** — required. The run's runid. Accept **either** the bare 4-to-8-character
suffix (`7f3c`) **or** the Workflow run id it was derived from (`wf_918a4deb-aba`), and
normalize with the **exact same rule `bg-dispatch.sh` Step 3 uses**: lowercase, strip a
leading `wf_`, remove every character outside `[a-z0-9]`, then keep the last 8 characters.
Reject a normalized value that does not match `^[a-z0-9]{4,8}$` with a usage error. This
matters because the caller in the implement spine holds a `wf_…` id, and the two registries
are keyed by the derived suffix. One rule, one source — the same sentence §Naming already
uses.

**`--outcome <clean|failed>`** — required. Any other value is a usage error.

**`--keep`** — optional. Present means: stop the sessions, delete nothing.

### 2.3 Behaviour

**Step 1 — collect short ids from BOTH registries.**

| Registry | Path | Written by | Read how |
|---|---|---|---|
| Sidecar env files | `${HOME}/.claude/relay/bg/<runid>/*.env` | `bg-dispatch.sh` (`--engine bg-sessions`) | Parse `RELAY_BG_NAME=` and `RELAY_BG_SHORT_ID=` out of each file. Do not `source` them. |
| Run manifest | `${HOME}/.claude/relay/runs/<runid>/manifest.json` | `bg-manifest.sh` (`--engine session-tree`) | `bash scripts/bg-manifest.sh --runid <runid> names`, which prints `RELAY_BG_NAME=` / `RELAY_BG_SHORT_ID=` pairs |

Union the two sets and remove duplicates, **keyed by short id** (the deletion key), not by
name. Reading only one registry is the bug this step exists to prevent: `--engine
bg-sessions` writes only sidecars and `--engine session-tree` writes only the manifest.

Hard requirements a cold implementer will otherwise get wrong:

- **A missing sidecar directory is normal, not an error.** A session-tree run has none.
- **A missing manifest file is normal, not an error.** A bg-sessions run has none.
  `bg-manifest.sh … names` exits `1` with `manifest write failed: …` when the manifest is
  absent, because a missing manifest is fatal *for the orchestrator*. `bg-cleanup.sh` must
  therefore test `[ -f "$manifest" ]` **before** calling `bg-manifest.sh`, and skip that
  registry when the file is not there. Do not let that exit `1` propagate.
- **A sidecar with an empty `RELAY_BG_SHORT_ID=`** is a launch that was denied before the
  short id was resolved. Report it as skipped. It is not fatal, and there is nothing to
  stop or delete.
- **A short id that does not match `^[0-9a-f]{6,10}$`** — the shape `bg-launch.sh` parses —
  is reported and skipped, never used to build a path.

**Step 2 — stop each session, then confirm.**

The single stop mechanism in the contract (§Spawn authority,
`docs/bg-dispatch-contract.md`) is: **send the session a finish-and-stop instruction, by
name, via `SendMessage`, then confirm the `stopped` verdict through `bg-liveness.sh`.** No
session ever stops a sibling; only this script's caller, at the end of the run, stops
anything.

`SendMessage` is an agent tool. **A shell script cannot call it.** The stop is therefore
split between the script and its caller, and the script is written so that it can never
delete a session it did not see confirmed stopped:

1. `bg-cleanup.sh` runs `bg-liveness.sh --short-id <id>` **once per collected id**, and
   reads the verdict from the `RELAY_BG_VERDICT=` line on stdout.

   **Ignore `bg-liveness.sh`'s exit code. It is inverted for this caller.** That script
   exits `0` only when **every** verdict is `alive`, exits `1` when **any** verdict is
   `stopped`, and exits `3` for stale or unknown
   (`plugins/relay/scripts/bg-liveness.sh`, the tail of the file). The outcome cleanup
   **wants** — everything stopped — therefore surfaces as **exit `1`**. A script that
   branches on the exit code reads a successful cleanup as a failure. Parse the
   `RELAY_BG_VERDICT=` line; do not branch on `$?`. One invocation per id is required so
   that the id-to-verdict association needs no parsing of interleaved blocks.

2. For every id whose verdict is **not** `stopped` (that is `alive`, `stale`, or `unknown`
   with a job directory still present), the script prints one line

   ```
   RELAY_BG_STOP_REQUIRED=<name> <short-id>
   ```

   deletes nothing at all for that session, and — after processing every id — **exits `1`**.
3. The caller (the skill prose in §2.5) sends exactly one finish-and-stop `SendMessage` to
   each printed name, then **re-runs the identical `bg-cleanup.sh` command**.
4. On the re-run every session reads `stopped` and the script proceeds to Step 3.

The caller re-runs the script **at most twice**. A session that is still not `stopped` after
the second re-run is **named in the run's final report** and left alone — never silently
left running and never silently reported as stopped. This is the same rule
`skills/orchestrating-session-trees/SKILL.md` already states in its End-of-run section.

**The finish-and-stop message body.** Neither `docs/bg-dispatch-contract.md` §Spawn
authority nor `skills/orchestrating-session-trees/SKILL.md` §End of run pins a wording
today, and this change adds a second caller — so two callers would otherwise invent two
wordings. Pin one, in `docs/bg-dispatch-contract.md` §Spawn authority, so both callers and
any future one send the same thing:

```
Finish your current turn and stop. Do not start new work. Do not message any other session.
```

It is plain prose on purpose. It must **not** use envelope grammar: a message whose first
line matched `ROLE_DONE`, `BLOCKED:`, `NEEDS_DECISION:`, or `KEY=VALUE` would be parsed as
an envelope by a child that is mid-protocol. Free text is inert by contract (§Envelope,
"Free text is inert"), which is exactly what a stop instruction needs.

The script is fully **idempotent**: running it again over an already-cleaned runid finds the
job directories gone, reports them skipped, and exits `0`.

In the normal path most sessions are already `stopped` before cleanup runs, because the
bg-sessions watcher stops a child on `done`/`errored` and the session-tree orchestrator
stops its children at end of run. The stop step here is the backstop for the abnormal paths:
a child left alive on `needs-decision`, and an orphan from a watcher crash.

**Step 3 — delete, on `--outcome clean` and only when `--keep` was NOT passed.**

For each collected short id, in this order:

1. Resolve the job directory as `<jobs-root>/<short-id>`, where `<jobs-root>` is
   `${RELAY_BG_JOBS_DIR:-$HOME/.claude/jobs}` — the same override `bg-launch.sh` and
   `bg-liveness.sh` already honor, so a test never touches a real jobs directory.
2. If the job directory does not exist: print
   `RELAY_BG_CLEANUP_SKIPPED=<name> <short-id> no-job-directory` and move on. **Not fatal.**
3. Read `linkScanPath` out of `<job-dir>/state.json` with `jq -r '.linkScanPath // ""'`.
   Do this **before** removing the job directory, or the path is lost.

   **The field name is `linkScanPath`, and it is verified, not assumed.** No existing relay
   script reads it — `bg-launch.sh` reads `.intent`, `bg-liveness.sh` reads `.state` and
   `.updatedAt` — so a cold implementer has no in-tree precedent to copy. It was read
   directly off two live job directories on this machine while this spec was written:

   ```
   $ jq -r '.linkScanPath' ~/.claude/jobs/8e54c304/state.json
   /home/jazz/.claude/projects/-home-jazz-dev-github-com-…-bg-auto-cleanup-nesting/8e54c304-e1ae-4e8c-9a4f-22ada6887a59.jsonl

   $ jq -r '.linkScanPath' ~/.claude/jobs/c8b75479/state.json   # the spike child
   /home/jazz/.claude/projects/-home-jazz--claude-jobs-8e54c304-tmp-spike-repo/c8b75479-f175-48b5-a0aa-305507b485b5.jsonl
   ```

   Confirm the key still exists on one real job directory before landing the script.
   Because the fallback is `// ""` and an empty value routes silently to the
   `no-transcript` skip, a wrong field name would make transcript deletion a permanent
   silent no-op that every fixture-based test still passes. §2.7 case 1 is the guard: it
   must assert the transcript file is **gone**, not only that the job directory is.
4. Delete the transcript named by `linkScanPath` **only when all of these hold**: the value
   is non-empty, the path is a regular file, it ends in `.jsonl`, and it is inside
   `$HOME/.claude/projects/`. Otherwise print
   `RELAY_BG_CLEANUP_SKIPPED=<name> <short-id> no-transcript` and continue to step 5 — a
   missing or unusable transcript path never blocks the job-directory deletion and is never
   fatal.
5. Remove the job directory with `rm -rf "<jobs-root>/<short-id>"`.

**Step 4 — on `--outcome failed`, or when `--keep` was passed: stop only.**

Delete nothing. For each session print

```
RELAY_BG_KEPT=<name> <short-id> <job-dir> <reason>
```

where `<reason>` is `outcome-failed` or `keep-flag`. The point is that a person can find
the session, resume it, and read its transcript. `--outcome failed` and `--keep` together
print `outcome-failed`.

**What is never deleted.** The two registries themselves — the sidecar `.env` files, the
sidecar directory, and the run manifest — are the record of what the run did. They stay.
Do not "tidy up" either registry. Keeping them is also what makes a re-run idempotent.

### 2.4 Safety rules — part of the contract, not optional hardening

- The script only ever touches short ids **recorded for the runid it was given**. It never
  globs `~/.claude/jobs/` and never deletes a job directory it did not find in a registry
  for that runid.
- A recorded id whose job directory is already gone is **reported and skipped**. It is not a
  fatal error.
- **Confirm stopped before deleting.** Deleting the job directory of a live session is not
  allowed. `unknown` is not `stopped` — a caller must never treat `unknown` as gone
  (`docs/bg-dispatch-contract.md` §Liveness and truth). The one exception, stated because it
  is otherwise ambiguous: when the job directory is **absent**, `bg-liveness.sh` reports
  `unknown` and there is nothing to delete; that id goes to the `no-job-directory` skipped
  path and never to `RELAY_BG_STOP_REQUIRED`.
- The script prints a final line, and it is the last line of stdout:

  ```
  RELAY_BG_CLEANUP=<deleted|kept> <n> sessions
  ```

  `deleted` when Step 3 ran, `kept` when Step 4 ran. `<n>` is the count of sessions the
  script acted on successfully: for `deleted`, the number of job directories actually
  removed; for `kept`, the number of sessions left resumable. Sessions reported through
  `RELAY_BG_CLEANUP_SKIPPED=` are **not** counted in `<n>`.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Cleanup ran to the end. The final line says what happened, including the zero-session case. |
| `1` | At least one session did not read as `stopped`. Every such session was printed as `RELAY_BG_STOP_REQUIRED=`. **Nothing was deleted, for any session, on this run.** |
| `2` | Usage error — missing or unknown argument, a `--runid` that does not normalize to `^[a-z0-9]{4,8}$`, an `--outcome` outside `{clean, failed}`, or `jq` not on `PATH`. |
| `3` | Zero sessions found in either registry for that runid. Not an error; a distinguishable outcome so a caller can say so honestly instead of reporting a silent success. Stderr carries `[relay] note: no bg session recorded for runid <id> in either registry`. |

Exit `1` is all-or-nothing on purpose: a partial delete followed by a re-run is harder to
reason about than one clean retry.

Errors and notes go to **stderr**, prefixed `[relay] error: ` / `[relay] note: `, per repo
convention. Only `KEY=VALUE` lines go to stdout.

### 2.5 Wiring

**A. `/relay:implement` gains `--keep-sessions`.**

- `commands/implement.md` frontmatter `argument-hint` gains `[--keep-sessions]`.
- Parse it in Step 0, in the same `grep -qw` shape `--verify` and `--retro` already use.
  The check must sit **after** `source "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh"`,
  because it needs the resolved `$RELAY_ENGINE`.
- Passing it with an engine that launches no bg session is an **ERROR with a clear message,
  not a silent no-op** — the same shape as the existing `--rounds` without `--verify` error.
  The engines that launch bg sessions are `bg-sessions` and `session-tree`; every other
  value (`in-session`, `acpx`, `smart-routing`) is the error case.

  ```bash
  _keep_sessions=0
  printf '%s' "$_relay_args" | grep -qw -- '--keep-sessions' && _keep_sessions=1
  if [ "$_keep_sessions" -eq 1 ]; then
    case "$RELAY_ENGINE" in
      bg-sessions|session-tree) ;;
      *) echo "implement: --keep-sessions keeps the background sessions a run created, and engine '$RELAY_ENGINE' creates none. Use --engine bg-sessions or --engine session-tree, or drop --keep-sessions."; exit 1 ;;
    esac
  fi
  export RELAY_KEEP_SESSIONS="$_keep_sessions"
  ```

- **Strip `--keep-sessions` from the task text before classification.** Step 1 of
  `commands/implement.md` lists what to remove from `$ARGUMENTS` before running
  `relay:classifying-task-kind`. Add `--keep-sessions` to that list. Leaving the literal
  flag in the text pollutes what the classifier reads — the same reason `--verify` and
  `--retro` are already stripped.

  **That strip list is prose, not code.** Read the file: Step 1's sentence is an
  instruction to the model, and no `_strip_flags` shell variable exists for `--verify` or
  `--retro` either. The change is one added phrase in that sentence. Do not invent shell
  stripping code that the other flags do not have.
- Step 3 of `commands/implement.md` passes the flag through to the spine as an eleventh
  input, `keep_sessions`. Update the "Pass all ten inputs" sentence to eleven and name it.

**B. `relay:running-implement-spine` runs the cleanup for `--engine bg-sessions`.**

- Add `keep_sessions` to the skill's `## Inputs` list. It is **optional and defaults to
  `false`**, so `relay:implementing-spec`, the other caller, needs no edit and keeps passing
  its current inputs.
- Add a step between Step 4 (completeness gate) and `## Output`, numbered **Step 4.5 — Clean
  up the run's background sessions**. It runs **only when `engine` is `bg-sessions`**;
  `session-tree` never reaches this skill (that branch is terminal in
  `commands/implement.md` Step 1), and every other engine launched no bg session.
- `--outcome` is `clean` when the run is about to print `status: ok`, and `failed`
  otherwise. Resolve the status **before** running the cleanup, so a failed run keeps its
  sessions readable.
- `--runid` is the Workflow `run_id` (`wf_…`); the script normalizes it (§2.2).
- Pass `--keep` when `keep_sessions` is true.
- **What the spine does with each exit code.** All four cases must be stated in the skill;
  none of them may be silent, and none of them changes the JSON `status`.

  | Exit | Spine behavior |
  |---|---|
  | `0` | Report the final `RELAY_BG_CLEANUP=` line. Done. |
  | `1` | Send the pinned finish-and-stop `SendMessage` (§2.3 Step 2) to each printed `RELAY_BG_STOP_REQUIRED=` name, then re-run the identical command. At most two re-runs. If a session is still not `stopped` after that, **name it in the run's report** and continue. |
  | `2` | A usage error is a **relay bug**, not a run failure. Report the stderr line verbatim and continue. Never retry — the arguments will not change. |
  | `3` | Zero sessions were recorded for this runid. Say so plainly (`no background session was recorded for this run`) and continue. This is legal for a `bg-sessions` run whose leaves all fell through to in-session dispatch. Do not treat it as a failure and do not treat it as a clean deletion. |

- The cleanup is **advisory for the run's status**: it never turns an `ok` run into a
  failure and never turns a failed run into an `ok` one. Report its final
  `RELAY_BG_CLEANUP=` line, and name any session that would not stop, but do not change the
  JSON `status` because of it. It must, however, never be silent: always print something
  from the table above.

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/bg-cleanup.sh" --runid "<run_id>" --outcome "<clean|failed>" [--keep]
```

**C. `skills/orchestrating-session-trees/SKILL.md` calls the same script.**

Extend its `## End of run` section. The orchestrator already sends each child a
finish-and-stop instruction bottom-up (workers before their operator) and confirms `stopped`
through `bg-liveness.sh`. After that protocol, it runs `bg-cleanup.sh` with the run's runid —
the one the orchestrator allocated in `## Bookkeeping` — so **both bg engines clean up
through one code path**. `--outcome` is `clean` when the run completed and `failed`
otherwise. `--keep` mirrors `--keep-sessions`. Because the orchestrator has already stopped
its children, the script's Step 2 normally confirms `stopped` on the first call.

**On exit `1`, the orchestrator DOES run the §2.3 Step 2 retry loop.** It is the one session
in the tree that can `SendMessage`, so it sends the pinned finish-and-stop message to each
printed `RELAY_BG_STOP_REQUIRED=` name and re-runs, at most twice — the same rule the spine
follows. Only after that does the existing rule apply: any child that still does not confirm
`stopped` is **named in the run's final report**, never silently left running and never
silently reported as stopped. The two rules are sequential, not alternatives: retry first,
then name what survived. Exit `2` and exit `3` follow the same table as the spine (§2.5 B).

### 2.6 Known limitation, deliberately out of scope

`--engine bg-sessions` is wired into four commands — `implement`, `refine`, `execute`, and
`drive` (`tests/unit/skill-structure/test_bg_command_wiring.py` pins all four). This change
wires cleanup into `/relay:implement` and into the session-tree orchestrator only, exactly
as the approved design states. A `/relay:refine --engine bg-sessions` run still leaves its
sessions behind. Recorded here so the gap is known rather than assumed closed, and listed in
§7 Future work. **Do not widen the wiring in this change.**

### 2.7 Tests for Part 2

New file: **`tests/unit/skill-structure/test_bg_cleanup.py`**.

Point `HOME` at a temporary fixture directory for **every** test in the module, so no real
job is ever touched. Build the fixture with: a sidecar directory
`$HOME/.claude/relay/bg/<runid>/` holding `.env` files, a manifest at
`$HOME/.claude/relay/runs/<runid>/manifest.json`, job directories at
`$HOME/.claude/jobs/<short>/state.json` with a `state` and a `linkScanPath`, and transcript
files under `$HOME/.claude/projects/`. Follow the driving shape already used by
`test_bg_dispatch_env.py` and `test_bg_liveness.py`.

Required cases:

1. **A clean run deletes exactly the recorded ids and nothing else.** Put an **unrelated**
   job directory in the fixture — one recorded in no registry for this runid — and assert it
   survives. Assert the recorded job directories and their transcripts are gone.
2. **A failed run deletes nothing.** `--outcome failed`: every job directory and transcript
   survives, the final line reads `RELAY_BG_CLEANUP=kept <n> sessions`, and one
   `RELAY_BG_KEPT=` line names each session with reason `outcome-failed`.
3. **`--keep` deletes nothing**, even with `--outcome clean`. Reason `keep-flag`.
4. **Both registries are read.** Record one session **only** in a sidecar and a different
   session **only** in the manifest, and assert a clean run deletes both. This is the test
   that fails if someone reads one registry.
5. **Duplicates are removed.** The same short id in both registries is stopped once, deleted
   once, and counted once in `<n>`.
6. **A manifest id with no job directory on disk is reported and not fatal.** Exit `0`, a
   `RELAY_BG_CLEANUP_SKIPPED=… no-job-directory` line, and the other recorded session still
   gets deleted.
7. **A session that still reads as live is stopped before any deletion happens.** With one
   job `state.json` holding `"state": "working"` and a fresh `updatedAt`: the script exits
   `1`, prints `RELAY_BG_STOP_REQUIRED=<name> <short-id>`, and **no** job directory is
   deleted — not even the one that already reads `stopped`. Then flip that state file to
   `stopped`, re-run, and assert both are deleted.
8. **A missing manifest is not fatal** for a sidecar-only runid (exit `0`, not `1`), and a
   **missing sidecar directory is not fatal** for a manifest-only runid.
9. **Zero sessions** in either registry exits `3` and prints the note on stderr.
10. **Usage errors exit `2`**: no `--runid`, a `--runid` that does not normalize (for
    example `ab` or `!!!!`), and `--outcome bogus`.
11. **Runid normalization.** `--runid wf_918a4deb-aba` and `--runid <the derived suffix>`
    find the same registries. Derive the expected suffix with the same rule
    `bg-dispatch.sh` uses.
12. **Idempotence.** Running the same clean cleanup twice exits `0` both times; the second
    run reports every id skipped and `<n>` is `0`.
13. **The transcript guard.** A `linkScanPath` pointing outside `$HOME/.claude/projects/`,
    or at a path that is not a file, is skipped with `no-transcript`, the job directory is
    still deleted, and the out-of-root file **still exists** afterwards.

Also extend **`tests/unit/skill-structure/test_bg_command_wiring.py`** (or the new
`TestVersion4450` class) with:

- `commands/implement.md`'s `argument-hint` lists `--keep-sessions`.
- The error branch text is present, and it names both `bg-sessions` and `session-tree`.
- `--keep-sessions` appears in the Step 1 strip sentence.
- `skills/running-implement-spine/SKILL.md` names `bg-cleanup.sh`, declares
  `keep_sessions`, and states all four cleanup exit codes.
- `skills/orchestrating-session-trees/SKILL.md` names `bg-cleanup.sh` in its End-of-run
  section and states that the orchestrator runs the retry loop before naming a surviving
  child.
- `docs/bg-dispatch-contract.md` §Spawn authority carries the pinned finish-and-stop
  wording, and the wording's first line does not match the envelope grammar
  `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$` and starts with none of `BLOCKED:` /
  `NEEDS_DECISION:`.

---

## 3. Part 3 — nested dispatch, with the Workflow as the spine

### 3.1 The shape

The shape already in place for `--engine bg-sessions` is: **a dynamic Workflow is the spine,
and bg sessions are the dispatch mechanism for its leaves.** The new part is **recursion** — a
bg child dispatched from a leaf may itself run a dynamic Workflow. Spike gate 2 proved a bg
child holds the `Workflow` tool and can run one to completion.

The worked example is dispatching the **refine loop** to a bg child, which then runs its own
Workflow with verify and fix leaves alternating as the loop needs.

### 3.2 The nesting primitive is a SKILL LEAF

The child's role body **invokes a relay skill by name** — for example `relay:refining-specs` —
and that skill generates the child's own Workflow.

**A slash-command leaf was considered and rejected.** Relay command files carry
`disable-model-invocation: true`, and a command cannot carry the trailing envelope
instructions the child needs to close with. Do not reintroduce it.

Concretely, for a cold implementer:

- The child's prompt is, as today, `preamble.md` followed by the role body
  (`bg-dispatch.sh` Step 7). The preamble already carries the envelope rules.
- A **nesting role body** is any role body that names a relay skill to invoke and then
  restates the envelope it must close with, as its last instruction. The `Skill` tool call
  is the nesting primitive. Nothing new is needed in `bg-dispatch.sh` to make it work.
- **`[partially verified]` The `Skill` tool is reachable from a bg child.** The spike child
  never called `Skill`, so there is no direct proof of a successful call. What the spike
  transcript does show is that the harness loaded the skill surface into the bg child: its
  context carries the verbatim line *"For all other skills, use the 'Skill' tool"*, injected
  with the `superpowers:using-superpowers` skill body, and the child did call `ToolSearch`
  for deferred tools. The tools it actually used were `Bash`, `Edit`, `Write`, `Read`,
  `EnterWorktree`, `ExitWorktree`, `ToolSearch`, and `Workflow`.

  **Required manual gate before the `## Nested dispatch` prose is trusted.** Launch one bg
  child through `bg-launch.sh` whose prompt invokes a relay skill by name, and confirm from
  its transcript that a `Skill` tool call was made and returned. Record the date and the
  result in the PR commit body — the same convention `docs/bg-dispatch-contract.md` already
  uses for the S1 round trip. If the `Skill` tool turns out not to be reachable, the
  doctrine amendment (§3.5) and the depth cap (§3.4) still stand and still ship; only the
  `## Nested dispatch` section must then say which mechanism replaces the skill leaf.
- **The nested Workflow returns immediately.** Spike gate 2: the `Workflow` tool answered
  `Workflow launched in background. Task ID: …` and the child had to `ToolSearch` for
  `TaskOutput`/`TaskGet` to collect the result. A nesting role body must therefore tell the
  child, in words, to **collect the nested Workflow's result before writing its envelope** —
  the child's turn ends when its final text ends, and a child that writes `ROLE_DONE` on the
  launch acknowledgement reports a result that does not exist yet. State this in the
  `## Nested dispatch` section of `skills/dispatching-bg-agents/SKILL.md`.

**This release adds no new role file and no new entry in `bindings/presets.yaml`.** Part 3
ships the doctrine, the documented primitive, and the depth-1 enforcement. The primitive is
available to any existing `delegate_eligible: true` role whose body invokes a skill.

### 3.3 The envelope does not change

A child running a nested Workflow still closes with `ROLE_DONE`, or `BLOCKED: <reason>`, or
`NEEDS_DECISION: <question>`, with the `TURN=` echo as the first `KEY=VALUE` line.

**Escalation composes with no new machinery.** A leaf inside the child's Workflow escalates;
the child turns that into `NEEDS_DECISION:`; the parent watcher buckets it as
`needs-decision` exactly as it does today. No new token, no new bucket, no new routing.

### 3.4 Depth is capped at 1, and it is enforced

**A bg child must not dispatch a further bg child.** Enforce this, do not merely document
it: the dispatch path refuses, with a clear message, when it is already running inside a bg
child.

`skills/dispatching-bg-agents/bg-dispatch.sh` gains a depth check, **before** it resolves
anything else — before the role file, before the binding, before it creates a directory or
writes a file. It refuses when **either** of two independent signals says "I am inside a bg
child":

**Signal 1 — the exported depth marker (primary).** `bg-dispatch.sh` exports
`RELAY_BG_DEPTH=1` into the environment of the `bg-launch.sh` invocation, so the launched
child process inherits it. On entry, `bg-dispatch.sh` refuses when `RELAY_BG_DEPTH` is set
and non-zero.

`[inferred]` The child inherits its parent's environment through the same fork/exec that
already gives it its cwd, and cwd inheritance through `bg-launch.sh` is **proven** — the
spike's wrapper `cd`-ed into the scratch repo and the child's git work landed there, and
`bg-dispatch.sh` relies on exactly that with `cd "$WORKTREE" && bash "$_bgd_launcher" …`.
Environment inheritance through a bg session's Bash tool was **not** measured directly, and
no unit test can measure it. That is why there is a second signal, and why the second signal
is the one that carries the weight.

**Signal 2 — the job-state backstop (verified).** A session launched by `claude --bg`
records `"template": "bg"` in its own `state.json`. `bg-dispatch.sh` refuses when
`$CLAUDE_JOB_DIR` is set, `$CLAUDE_JOB_DIR/state.json` is readable, and
`jq -r '.template // ""'` on it returns `bg`.

This was verified against two real job directories on this machine:

| Job | How it was started | `state.json` `.template` |
|---|---|---|
| `8e54c304` | a daemon session, not `claude --bg` | `claude` |
| `c8b75479` | the spike child, through `bg-launch.sh` → `claude --bg` | `bg` |

`CLAUDE_JOB_DIR` is exported into every Bash tool call of a session that has a job
directory, so the backstop needs no environment inheritance from the launcher at all. When
`CLAUDE_JOB_DIR` is unset or its `state.json` is unreadable, this signal simply does not
fire — a missing signal never blocks a dispatch, and Signal 1 still applies.

**Refusal shape.** Exit `2` (usage error, the existing bucket for "this dispatch is not
allowed"), with:

```
[relay] error: nested bg dispatch is capped at depth 1 — this session is already a background child, and a bg child must not dispatch a further bg child. Run the work in this session, or run a nested Workflow with in-session leaves.
```

Both signals are overridable for tests through the environment: a test sets
`RELAY_BG_DEPTH` to trip Signal 1, and points `CLAUDE_JOB_DIR` at a fixture job directory to
trip Signal 2. The default (both absent) must dispatch normally, so every existing
`test_bg_dispatch_env.py` case keeps passing unchanged.

**Preamble line.** Add one line to `preamble.md` stating the same rule in the child's own
voice: the child may invoke a relay skill that generates its own Workflow, and it must not
dispatch a further background session. Documentation and enforcement, both.

### 3.5 Doctrine amendment — `docs/orchestration-substrates.md`

The rule today reads as **one Workflow per L3 command**. It becomes:

> **One Workflow per SESSION. Nesting happens across sessions, through dispatch.**

State it in the doc's own voice, in the opening section that carries the rule, and keep the
two existing documented exceptions intact and unchanged:

- **The `/relay:drive` exception** — MAIN may own one long-lived process outside its single
  Workflow.
- **The session-tree exception** — a run may have no Workflow at all.

Add a short third section, in the same shape as the other two, that records nesting: a bg
child dispatched from a leaf of a session's one Workflow may run a Workflow of its own,
because it is a **different session**. Depth is capped at 1. Name where the cap is enforced
(`skills/dispatching-bg-agents/bg-dispatch.sh`) so the doc does not claim behavior with no
code behind it.

### 3.6 `--engine session-tree` is kept exactly as it is

No change to `skills/orchestrating-session-trees/SKILL.md` for Part 3, and no change to the
session-tree substrate.

**Recorded overlap.** `--engine session-tree` and nested bg dispatch now overlap in what an
operator could reach: both let work run as a tree of background sessions across more than one
level. Narrowing `session-tree` is possible future work. **Do not narrow it in this change.**
See §7.

### 3.7 Tests for Part 3

- **`tests/unit/skill-structure/test_bg_dispatch_env.py`** — add depth-cap cases:
  - `RELAY_BG_DEPTH=1` in the environment → exit `2`, stderr names the depth cap, and
    **no sidecar, no handoff directory, and no prompt file were created** (the check runs
    before any of them).
  - `CLAUDE_JOB_DIR` pointing at a fixture job whose `state.json` has `"template": "bg"` →
    exit `2`, same assertions.
  - `CLAUDE_JOB_DIR` pointing at a fixture job whose `state.json` has `"template": "claude"`
    → dispatch proceeds normally.
  - `CLAUDE_JOB_DIR` unset and `RELAY_BG_DEPTH` unset → dispatch proceeds normally (the
    existing happy-path cases already cover this; assert it stays green).
  - The launcher stub records its own environment, and the test asserts `RELAY_BG_DEPTH=1`
    reached it. **Be honest about what this proves.** `bg-launch.sh` is invoked by
    `bg-dispatch.sh` from the same shell, so it inherits the export trivially. The test
    proves only that `bg-dispatch.sh` exports the variable instead of setting it locally.
    It does **not** prove that `claude --bg` carries the variable into the child session's
    Bash tool calls — that is the `[inferred]` step in §3.4, and no unit test can reach it.
    **Signal 2 is the load-bearing check**, because it needs no environment inheritance at
    all. Do not write a comment claiming this test proves the child inherits the marker.
- **`tests/unit/skill-structure/test_session_tree_substrate.py`** (or the doctrine test that
  owns `docs/orchestration-substrates.md`) — assert the amended sentence "one Workflow per
  session" is present, that both existing exception headings survive, and that the nesting
  section names `bg-dispatch.sh` as the enforcement site.
- **`tests/unit/skill-structure/test_dispatching_bg_skill.py`** — assert
  `skills/dispatching-bg-agents/SKILL.md` has a `## Nested dispatch` section that names the
  skill leaf, records that a slash-command leaf was rejected because command files carry
  `disable-model-invocation: true`, and states the async-collection rule for the nested
  Workflow's result.

---

## 4. Release ratchet

Every item is required, in this PR, per `CLAUDE.md` — the version is the plugin-distribution
cache key.

1. **`plugins/relay/.claude-plugin/plugin.json`** — `"version": "4.44.0"` → `"4.45.0"`.
2. **`plugins/relay/CHANGELOG.md`** — add a `## 4.45.0 — 2026-08-25` entry **above** the
   `## 4.44.0` entry, in the existing style: a bold lead sentence per change, then the
   detail. It must name the tokens `TestVersion4450`'s
   `test_the_entry_names_what_shipped` will grep for. Use at least: `bg-cleanup.sh`,
   `--keep-sessions`, `auto`, and `classifier refused`.
3. **`plugins/relay/tests/unit/skill-structure/test_plugin.py`** — the version dance:
   - Convert `TestVersion4440`'s exact pin to the floor form,
     `assert Version(manifest["version"]) >= Version("4.44.0")`, using
     `packaging.version.Version`, and carry the in-tree comment style forward:
     `# Superseded exact pin: 4.45.0 carries this line forward (TestVersion4450 …)`.
   - Add `class TestVersion4450` with the exact pin
     `assert manifest["version"] == "4.45.0"`, a changelog test that splits on
     `## 4.45.0` … `## 4.44.0` and greps the distinguishing tokens, and — per the
     convention every version class that ships a script follows — an assertion that
     `scripts/bg-cleanup.sh` exists and is executable (`os.access(path, os.X_OK)`).
   - Add `keep_sessions` to the `running-implement-spine` "declares every input"
     parametrize list.
4. **`plugins/relay/docs/contributing.md`** — ratchet the worked example
   `assert manifest["version"] == "4.44.0"` to `"4.45.0"`.
   `tests/unit/skill-structure/test_docs_freshness.py::test_version_example_matches_manifest`
   compares that literal against the manifest and fails otherwise.
5. **Run the full suite and make it pass.**

   ```bash
   cd plugins/relay
   pytest tests/ -q
   bash tests/unit/skill-structure/test_parse_engine_agent.sh
   bash tests/unit/skill-structure/test_resolve_tier.sh
   ```

   There is no `pytest.ini` and no CI. The suite is the only gate, so it must be run by hand
   and it must be green.

---

## 5. Testing plan, in one place

| Area | File | New or extended |
|---|---|---|
| `approve-all` → `auto`, no binding reaches `bypassPermissions` | `test_bg_dispatch_env.py` | extended |
| Contract mapping table and the new failure row | `test_bg_dispatch_contract.py` | extended (an existing assertion must be rewritten) |
| The exact `BLOCKED: classifier refused <tool>: <reason>` wording | `test_dispatching_bg_skill.py` | extended |
| `bg-cleanup.sh` behavior, safety, and exit codes | `test_bg_cleanup.py` | **new** |
| `--keep-sessions` flag, error branch, strip list, session-tree wiring | `test_bg_command_wiring.py` | extended |
| Depth-1 enforcement, both signals, and the exported marker | `test_bg_dispatch_env.py` | extended |
| Doctrine amendment and the nesting section | `test_session_tree_substrate.py`, `test_dispatching_bg_skill.py` | extended |
| Version pin, changelog entry, script executability, spine input | `test_plugin.py` | extended + new `TestVersion4450` |
| Version example in contributing.md | `test_docs_freshness.py` | unchanged, must stay green |
| Frozen envelope tokens | `test_envelope_tokens.py` | **must not be edited** |

Two rules the repo's own review lenses enforce, restated because this change touches both:

- **A test must prove something.** Do not assert a value the implementation currently
  produces if it is the wrong value, and do not write a test that passes when the feature is
  absent. The clearest example here is
  `test_bg_dispatch_contract.py::test_permission_mode_mapping_rows`: after this change the
  old assertion still passes, for the wrong reason, because the doc keeps the word
  `bypassPermissions` in a different paragraph. Rewrite it.
- **No step may fail silently.** `bg-cleanup.sh` returns typed exit codes and prints a final
  line on every path, including the zero-session path, so a caller can never report a clean
  cleanup that did nothing.

---

## 6. Files this change touches

**New**

- `plugins/relay/scripts/bg-cleanup.sh` (executable)
- `plugins/relay/tests/unit/skill-structure/test_bg_cleanup.py`
- `plugins/relay/docs/superpowers/specs/2026-08-25-relay-bg-auto-cleanup-nesting-design.md`
  (this file)

**Changed**

- `plugins/relay/docs/bg-dispatch-contract.md` — mapping table, `auto` note, failure row,
  and the pinned finish-and-stop wording in §Spawn authority (§2.3 Step 2)
- `plugins/relay/docs/orchestration-substrates.md` — doctrine amendment, nesting section
- `plugins/relay/docs/contributing.md` — version example
- `plugins/relay/skills/dispatching-bg-agents/bg-dispatch.sh` — mapping, depth cap, marker
- `plugins/relay/skills/dispatching-bg-agents/SKILL.md` — mapping line, `## Nested dispatch`
- `plugins/relay/skills/dispatching-bg-agents/preamble.md` — refusal rule, no-further-dispatch rule
- `plugins/relay/skills/orchestrating-session-trees/SKILL.md` — end-of-run cleanup call
- `plugins/relay/skills/running-implement-spine/SKILL.md` — `keep_sessions` input, Step 4.5
- `plugins/relay/commands/implement.md` — `--keep-sessions` hint, parse, error, strip, pass-through
- `plugins/relay/.claude-plugin/plugin.json` — 4.45.0
- `plugins/relay/CHANGELOG.md` — 4.45.0 entry
- `plugins/relay/tests/unit/skill-structure/test_plugin.py` — version dance, spine input
- `plugins/relay/tests/unit/skill-structure/test_bg_dispatch_env.py`
- `plugins/relay/tests/unit/skill-structure/test_bg_dispatch_contract.py`
- `plugins/relay/tests/unit/skill-structure/test_bg_command_wiring.py`
- `plugins/relay/tests/unit/skill-structure/test_dispatching_bg_skill.py`
- `plugins/relay/tests/unit/skill-structure/test_session_tree_substrate.py`

**Explicitly unchanged**

- `plugins/relay/scripts/bg-launch.sh` (behavior; a header comment is optional)
- `plugins/relay/scripts/bg-liveness.sh`, `plugins/relay/scripts/bg-manifest.sh`
- `plugins/relay/bindings/presets.yaml`
- `plugins/relay/tests/unit/skill-structure/test_envelope_tokens.py`
- `plugins/relay/tests/e2e/bg-s1-roundtrip.sh` (it passes `bypassPermissions` by hand, which
  stays supported)
- every acpx dispatch path and its `--approve-all` CLI flag
- every plugin other than `plugins/relay/`

---

## 7. Future work — recorded, not scheduled

1. **`--engine session-tree` and nested bg dispatch now overlap.** Both let work run as a
   tree of background sessions across more than one level. Narrowing `session-tree`, or
   folding it into nested dispatch, is possible future work. This change does not narrow it.
2. **Cleanup is wired to `/relay:implement` and to the session-tree orchestrator only.**
   `/relay:refine`, `/relay:execute`, and `/relay:drive` also accept `--engine bg-sessions`
   and still leave their sessions behind (§2.6).
3. **The background-session worktree guard.** Every bg child in a git repository must call
   `EnterWorktree` before its first edit, whatever its permission mode. The spike child
   recovered on its own, but a less careful leaf can leave work stranded on an unmerged
   worktree branch, and the merge it performed carried untracked `.pyc` blobs into the
   commit. Teaching the bg preamble the isolate-then-merge-then-remove sequence is a
   separate change.
4. **Free waiting for a Workflow watcher node** is still `[unverified]`
   (`skills/orchestrating-session-trees/SKILL.md` `## Waiting`,
   `skills/dispatching-bg-agents/SKILL.md` `## Multi-turn`). Unchanged here.

---

## 8. See also

- `plugins/relay/docs/bg-dispatch-contract.md` — the contract this change amends
- `plugins/relay/docs/dispatch-contract.md` — the frozen envelope grammar, unchanged
- `plugins/relay/docs/orchestration-substrates.md` — the doctrine this change amends
- `plugins/relay/docs/superpowers/specs/2026-08-19-relay-bg-engines-design.md` — the design
  that introduced both bg engines
- `plugins/relay/docs/superpowers/specs/2026-08-18-bg-session-messaging-spike-findings.md` —
  S1–S4, the spikes the contract is grounded in
