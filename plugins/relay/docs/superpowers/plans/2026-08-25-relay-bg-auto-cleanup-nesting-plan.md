# Relay bg engines: auto mode, session cleanup, nested dispatch — implementation plan

Date: 2026-08-25
Status: ready to execute.
Spec (the contract): `docs/superpowers/specs/2026-08-25-relay-bg-auto-cleanup-nesting-design.md`.
Sibling design: `docs/superpowers/specs/2026-08-19-relay-bg-engines-design.md`.
Version target: one bump, `4.44.0` → `4.45.0`, in the last step.

All paths in this plan are relative to `plugins/relay/` unless the path starts with
`plugins/`. The test tree is `plugins/relay/tests/`, never a repo-root `tests/`.

## How to read this plan

Every decision is marked with its source:

- **[spec]** — the spec states it. Copy the value or the literal string exactly. Do not
  improve it.
- **[repo]** — an existing test, script, or doc in this tree forces it. The plan names the
  file that forces it.
- **[plan]** — the spec is silent and this plan decides it. An implementer may change a
  `[plan]` decision, but must then change every test that pins it.

Read the spec in full before you start. This plan does not repeat the spec's rationale.

## Constraints

### C1 — the steps are sequential, never parallel

Steps 1 and 2 both edit `skills/dispatching-bg-agents/bg-dispatch.sh` and
`skills/dispatching-bg-agents/preamble.md`. Steps 5, 6 and 7 all edit
`tests/unit/skill-structure/test_bg_command_wiring.py` or `test_plugin.py`. Run the steps
in the printed order, one at a time. Two workers editing `bg-dispatch.sh` at the same time
produce a merge conflict in the one file every bg dispatch runs.

### C2 — the frozen tokens do not change

`ROLE_DONE`, `BLOCKED: <reason>`, `NEEDS_DECISION: <question>`, and the capture regex
`^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$` keep their exact byte sequences. [spec §1.2]
`tests/unit/skill-structure/test_envelope_tokens.py` is the pin. **Do not edit that file in
any step.** The five watcher exit buckets — `done`, `not-done`, `blocked`,
`needs-decision`, `errored` — do not change either.

### C3 — one version bump, in the last step

No step before Step 7 touches `.claude-plugin/plugin.json`, `CHANGELOG.md`,
`docs/contributing.md`, or the version classes in `test_plugin.py`. [repo: the exact pin in
`TestVersion4440` fails the whole suite the moment the manifest moves ahead of it]

### C4 — the gate every step runs before it reports done

```bash
cd plugins/relay
pytest tests/ -q
bash tests/unit/skill-structure/test_parse_engine_agent.sh
bash tests/unit/skill-structure/test_resolve_tier.sh
```

There is no `pytest.ini` and no CI. This suite is the only gate. A step is done when the
whole suite is green, not when the step's own new tests pass. [repo]

`yq` and `jq` must be on `PATH`; several bg test modules skip themselves without them, and
a skip here is uncovered code, not a pass. [repo: `test_bg_dispatch_env.py` `pytestmark`]

### C5 — the acpx `--approve-all` flag is a different mechanism

A search for `approve-all` finds the acpx CLI flag as well as the binding value. Leave
every acpx path alone: `skills/dispatching-acpx-agents/*`, `scripts/run-claude-command.sh`,
`scripts/run-claude-prompt.sh`, `skills/verifying-until-clean/SKILL.md`,
`commands/verify.md`, the `ACPX_PERMISSIONS` row in `docs/dispatch-contract.md`, the
presets comment about the acpx approval mode, and the CHANGELOG history. [spec §1.5]

---

## Step 1 — `auto` becomes the unattended permission mode

**Spec:** §1. **Files:** `docs/bg-dispatch-contract.md`,
`skills/dispatching-bg-agents/bg-dispatch.sh`, `skills/dispatching-bg-agents/SKILL.md`,
`skills/dispatching-bg-agents/preamble.md`, `scripts/bg-launch.sh` (comment only),
`tests/unit/skill-structure/test_bg_dispatch_env.py`,
`tests/unit/skill-structure/test_bg_dispatch_contract.py`,
`tests/unit/skill-structure/test_dispatching_bg_skill.py`.

### 1.1 The mapping

`skills/dispatching-bg-agents/bg-dispatch.sh`, the `case "$_bgd_permissions"` block:
`approve-all)` maps to `auto`, not `bypassPermissions`. Update the comment above the block
in the same edit. The `*)` unmapped-value error keeps its wording — it names the three
accepted **binding** values, not CLI modes. [spec §1.5]

`skills/dispatching-bg-agents/SKILL.md`, "Wrapper responsibilities" step 5: the inline
mapping reads ``(`approve-all` → `auto`; `approve-reads` or absent → `plan`)``. [spec §1.5]

`docs/bg-dispatch-contract.md`, §"Permission-mode mapping": the `approve-all` row maps to
`auto`, and the row's cell text is rewritten. Add a short paragraph under the table stating
that `auto` is a classifier and not a blanket grant, that it can refuse a tool call with no
human present, and that `bg-launch.sh` still accepts `bypassPermissions` as a raw
`--permission-mode` argument for hand-run spikes and `tests/e2e/bg-s1-roundtrip.sh`.
[spec §1.5]

### 1.2 What does not change

`scripts/bg-launch.sh` gets **no behaviour change**. It keeps refusing `dontAsk` with the
S3-1 note, and it keeps accepting any other mode, `bypassPermissions` included. Do not add
a mode allowlist. A header-comment line naming `auto` as the mode a binding now selects is
optional and no test pins it. [spec §1.2]

`bindings/presets.yaml` does not change. `skills/orchestrating-session-trees/SKILL.md`
performs no mapping of its own — it holds neither `approve-all` nor `bypassPermissions` —
so it needs no edit here, and no second copy of the table is added to it. [spec §1.5]

### 1.3 The classifier-refusal rule

Add to `skills/dispatching-bg-agents/preamble.md`: on a classifier refusal the child stops
and emits, as the first line of its final text and of the handoff-file envelope, this
literal:

```
BLOCKED: classifier refused <tool>: <reason>
```

The child does not retry the call, does not try to escalate or change its own permissions,
and does not reword the call and try again. `<tool>` is the tool name the harness reported.
`<reason>` is the harness refusal text on one line. The `TURN=` echo rule already in the
preamble still applies: the sentinel is the first non-empty line and `TURN=<n>` is the
first `KEY=VALUE` line under it. [spec §1.3]

### 1.4 The failure-behavior row

Add exactly one row to the failure-behavior table in `docs/bg-dispatch-contract.md`, in the
table's existing three-column shape:

| Failure | bg-sessions (watcher) | session-tree (orchestrator) |
|---|---|---|
| Classifier refused a tool call under `auto` | Child writes `BLOCKED: classifier refused <tool>: <reason>` and stops → `blocked` bucket | Child sends the same `BLOCKED:` line to its operator → recorded in the manifest, routed as any other `BLOCKED:` |

[spec §1.4]

### 1.5 Tests

`test_bg_dispatch_env.py` — change `TestHappyPath::test_permission_mode_mapping` so the
`cases` dict reads `implementer: "auto"`, `code-reviewer: "plan"`, `scout: "plan"`.
[spec §1.6]

`test_bg_dispatch_env.py` — add one test that drives `bg-dispatch.sh` for **every** role
with `delegate_eligible: true` in `bindings/presets.yaml` and asserts no sidecar holds
`RELAY_BG_PERMISSION_MODE=bypassPermissions`. Read the role list from the presets file with
`yq`, not from a hard-coded list, so a future preset row cannot slip past. This is the guard
that stops a future binding value from quietly restoring the blanket grant. [spec §1.6]

Skip a `delegate_eligible: true` role that has no `roles/<slug>.md` and no
`agents/<slug>.md` — `bg-dispatch.sh` exits `2` with `ROLE_FILE_MISSING` for it, which is a
different defect and not a bg-permission regression. Assert the loop ran over at least one
role, so a lookup that matches nothing cannot make the guard vacuous. [plan]

`test_bg_dispatch_contract.py` — rewrite `test_permission_mode_mapping_rows`. The current
assertion `"approve-all" in text and "bypassPermissions" in text` passes for the wrong
reason after this change, because the raw-argument note keeps the word. The new test must
assert the `approve-all` row maps to `` `auto` `` **inside the mapping table** and that
`bypassPermissions` does not appear in that table. Slice the table out of the doc (from the
`### Permission-mode mapping` heading to the next heading) and assert on the slice.
[spec §1.6, §5]

`test_bg_dispatch_contract.py` — add a test for the new failure row: the failure-behavior
table names `classifier refused`. [spec §1.6]

`test_dispatching_bg_skill.py` — add a test that pins the literal string
`BLOCKED: classifier refused <tool>: <reason>` in
`skills/dispatching-bg-agents/preamble.md`. Assert the literal, not a paraphrase. A test
that greps only for `classifier` proves nothing. [spec §1.6]

`test_bg_launch.py` — **no change**. Its `mode="bypassPermissions"` default exercises the
launcher's raw-argument path, which stays supported on purpose. [spec §1.6]

### 1.6 Done criteria

The C4 gate is green, and `grep -rn "bypassPermissions" skills/dispatching-bg-agents/`
returns nothing.

---

## Step 2 — depth is capped at 1, and it is enforced

**Spec:** §3.4. **Files:** `skills/dispatching-bg-agents/bg-dispatch.sh`,
`skills/dispatching-bg-agents/preamble.md`,
`tests/unit/skill-structure/test_bg_dispatch_env.py`.

### 2.1 Where the check goes

`bg-dispatch.sh` gains a depth check **before it resolves anything else** — before the role
file (Step 1 of the script), before the binding, before it creates a directory, and before
it writes a file. It refuses when **either** of two independent signals says "I am inside a
bg child". [spec §3.4]

**Signal 1 — the exported depth marker (primary).** Refuse when `RELAY_BG_DEPTH` is set and
non-zero. `bg-dispatch.sh` **exports** `RELAY_BG_DEPTH=1` into the environment of the
`bg-launch.sh` invocation in Step 8, so the launched child process inherits it. Export it;
do not set it as a shell-local variable. [spec §3.4]

**Signal 2 — the job-state backstop (verified, load-bearing).** Refuse when
`$CLAUDE_JOB_DIR` is set, `$CLAUDE_JOB_DIR/state.json` is readable, and
`jq -r '.template // ""'` on it returns `bg`. A session launched by `claude --bg` records
`"template": "bg"`; a daemon session records `"template": "claude"`. `CLAUDE_JOB_DIR` is
exported into every Bash tool call of a session that has a job directory, so this signal
needs no environment inheritance from the launcher. When `CLAUDE_JOB_DIR` is unset or its
`state.json` is unreadable, the signal does not fire — a missing signal never blocks a
dispatch. [spec §3.4]

### 2.2 The refusal

Exit `2` — the existing usage-error bucket, which already means "this dispatch is not
allowed" — with this stderr line:

```
[relay] error: nested bg dispatch is capped at depth 1 — this session is already a background child, and a bg child must not dispatch a further bg child. Run the work in this session, or run a nested Workflow with in-session leaves.
```

Use the script's existing `_bgd_err` helper so the `[relay] error: ` prefix and the exit
code stay consistent with every other refusal in the file. [plan]

### 2.3 The preamble line

Add one line to `skills/dispatching-bg-agents/preamble.md` stating the same rule in the
child's own voice: the child may invoke a relay skill that generates its own Workflow, and
it must not dispatch a further background session. Documentation and enforcement, both.
[spec §3.4]

### 2.4 Tests — `test_bg_dispatch_env.py`

Add a `TestDepthCap` class. The module's `_run` helper already points `HOME`, `WORKTREE`,
and `BG_LAUNCH_OVERRIDE` at `tmp_path`, so every case is synthetic. [repo]

**First, scrub both signal variables in `_run`.** That helper seeds the child environment
with `env = dict(os.environ)` and only adds per-case overrides. After this step both signals
are read from that inherited environment, so a developer whose shell exports
`RELAY_BG_DEPTH`, or who runs `pytest` from inside a bg session — where `CLAUDE_JOB_DIR` is
exported into every Bash tool call — would see **every existing happy-path case** refuse with
exit `2`. Add `env.pop("RELAY_BG_DEPTH", None)` and `env.pop("CLAUDE_JOB_DIR", None)`
**before** `env.update(env_extra)`, so a case that does not set them proves the
default-dispatch path and a case that does set them still wins. Without this the §2.5 done
criterion is not reproducible. [plan]

1. `RELAY_BG_DEPTH=1` in the environment → exit `2`, stderr names the depth cap, and **no
   sidecar, no handoff directory, and no prompt file were created**. Assert the absence
   directly on disk — the check runs before any of them.
2. `CLAUDE_JOB_DIR` pointing at a fixture job whose `state.json` holds `"template": "bg"` →
   exit `2`, same absence assertions.
3. `CLAUDE_JOB_DIR` pointing at a fixture job whose `state.json` holds
   `"template": "claude"` → dispatch proceeds normally, exit `0`.
4. `CLAUDE_JOB_DIR` unset and `RELAY_BG_DEPTH` unset → dispatch proceeds normally. The
   existing happy-path cases already cover this; assert here that they stay green.
5. The launcher stub records its own environment, and the test asserts `RELAY_BG_DEPTH=1`
   reached it. Add a **new** helper — for example `_make_env_recording_launcher(tmp_path)` —
   that writes `env | grep '^RELAY_BG_DEPTH=' >> <recorder>` on every non-`--check-name`
   call, and use it only in this case. Leave the existing `_make_stub_launcher` factory
   untouched; every other case in the module depends on its current shape. [plan]

**Be honest in the test's docstring about what case 5 proves.** `bg-launch.sh` is invoked by
`bg-dispatch.sh` from the same shell, so it inherits the export trivially. The test proves
only that `bg-dispatch.sh` **exports** the variable instead of setting it locally. It does
**not** prove that `claude --bg` carries the variable into the child session's Bash tool
calls; that is the `[inferred]` step in spec §3.4 and no unit test can reach it. Signal 2 is
the load-bearing check, because it needs no environment inheritance at all. Do not write a
comment claiming this test proves the child inherits the marker. [spec §3.7]

Add the two fixture job files under `tests/fixtures/bg-state/` — for example
`template-bg.json` and `template-claude.json` — or build them inline in `tmp_path`. Either
is acceptable; `test_bg_liveness.py` shows the fixture-copy shape and `test_bg_dispatch_env.py`
shows the inline shape. [plan]

### 2.5 Done criteria

The C4 gate is green. Every pre-existing case in `test_bg_dispatch_env.py` still passes with
no edit, which proves the default (both signals absent) still dispatches.

---

## Step 3 — the doctrine amendment and the nested-dispatch prose

**Spec:** §3.1, §3.2, §3.3, §3.5, §3.6. **Files:** `docs/orchestration-substrates.md`,
`skills/dispatching-bg-agents/SKILL.md`,
`tests/unit/skill-structure/test_session_tree_substrate.py`,
`tests/unit/skill-structure/test_dispatching_bg_skill.py`.

### 3.1 The required manual gate — decide first whether you can run it

Before you trust the `## Nested dispatch` prose, launch one bg child through
`scripts/bg-launch.sh` whose prompt invokes a relay skill by name, and confirm from the
child's transcript that a `Skill` tool call was made and returned. Record the date and the
result in the commit body, the same convention `docs/bg-dispatch-contract.md` already uses
for the S1 round trip. [spec §3.2]

**A cold worker takes outcome 3 by default.** A cold worker is any executor whose
environment cannot reach an interactive Claude Code session it may launch a real background
child from. Decide this first, with one command: `command -v claude`. If `claude` is not on
`PATH`, or you were told not to start real sessions, take outcome 3 and do not spend the
step trying. [plan]

Three outcomes, three actions:

1. **The `Skill` call is made and returns** — write the `## Nested dispatch` section as §3.3
   describes and drop the `[partially verified]` marker for that claim.
2. **The `Skill` tool is not reachable** — the doctrine amendment (§3.2) and the depth cap
   (Step 2) still stand and still ship. The `## Nested dispatch` section must then say which
   mechanism replaces the skill leaf. [spec §3.2]
3. **The gate was not run** (the cold-worker default above) — keep the
   `[partially verified]` marker in the prose exactly as the spec words it, add one sentence
   to the section saying the gate has not run yet and naming it as the thing that would lift
   the marker, and record that fact in the commit body. This is a legal, expected outcome —
   not a failure of the step. What is forbidden is writing the prose as verified on evidence
   that was not collected. [plan]

### 3.2 `docs/orchestration-substrates.md` — the amendment

The rule today reads as **one Workflow per L3 command**. It becomes:

> **One Workflow per SESSION. Nesting happens across sessions, through dispatch.**

State it in the doc's own voice, in the opening section that carries the rule. Keep the two
existing documented exception sections intact and unchanged: "The `/relay:drive` exception"
and "The session-tree exception". Add a short third section, in the same shape as the other
two, recording nesting: a bg child dispatched from a leaf of a session's one Workflow may
run a Workflow of its own, because it is a **different session**. Depth is capped at 1. Name
`skills/dispatching-bg-agents/bg-dispatch.sh` as the enforcement site, so the doc does not
claim behavior with no code behind it. [spec §3.5]

`--engine session-tree` is kept exactly as it is. Record in the doc, or in the spec's §7 if
the doc has no natural home for it, that session-tree and nested bg dispatch now overlap in
what an operator could reach and that narrowing session-tree is possible future work. **Do
not narrow it in this change.** [spec §3.6]

### 3.3 `skills/dispatching-bg-agents/SKILL.md` — `## Nested dispatch`

Add a `## Nested dispatch` section that states:

- **The nesting primitive is a SKILL LEAF.** The child's role body invokes a relay skill by
  name — for example `relay:refining-specs` — and that skill generates the child's own
  Workflow. The `Skill` tool call is the nesting primitive; `bg-dispatch.sh` needs nothing
  new to make it work, because the child's prompt is already `preamble.md` plus the role
  body. [spec §3.2]
- **A slash-command leaf was considered and rejected**, because relay command files carry
  `disable-model-invocation: true` and a command cannot carry the trailing envelope
  instructions the child needs to close with. Do not reintroduce it. [spec §3.2]
- **The nested Workflow returns immediately.** The `Workflow` tool answers
  `Workflow launched in background. Task ID: …`, so the child must `ToolSearch` for
  `TaskOutput`/`TaskGet` and **collect the nested Workflow's result before writing its
  envelope**. A child that writes `ROLE_DONE` on the launch acknowledgement reports a result
  that does not exist yet. [spec §3.2]
- **The envelope does not change.** A child running a nested Workflow still closes with
  `ROLE_DONE`, `BLOCKED: <reason>`, or `NEEDS_DECISION: <question>`, with the `TURN=` echo as
  the first `KEY=VALUE` line. A leaf inside the child's Workflow escalates, the child turns
  that into `NEEDS_DECISION:`, and the parent watcher buckets it as `needs-decision` exactly
  as it does today. No new token, no new bucket, no new routing. [spec §3.3]
- **Depth is capped at 1**, enforced in `bg-dispatch.sh` (Step 2 of this plan).

**This release adds no new role file and no new entry in `bindings/presets.yaml`.** The
primitive is available to any existing `delegate_eligible: true` role whose body invokes a
skill. [spec §3.2]

### 3.4 Tests

`test_session_tree_substrate.py` — assert the amended sentence "one Workflow per session"
is present (case-insensitively, after collapsing whitespace with the module's existing
`_collapsed` helper), that both existing exception headings survive, and that the nesting
section names `bg-dispatch.sh` as the enforcement site. [spec §3.7]

`test_dispatching_bg_skill.py` — slice the `## Nested dispatch` section out of
`skills/dispatching-bg-agents/SKILL.md` (heading to the next `## `) and assert on the slice,
so a mention elsewhere in the file cannot satisfy the test. Three assertions, on these exact
substrings:

1. `skill leaf` — the primitive is named.
2. `disable-model-invocation: true` — the literal reason the slash-command leaf was rejected.
3. `ToolSearch` and `TaskOutput` — the async-collection rule names the tools the child needs.

[spec §3.7, plan]

### 3.5 Done criteria

The C4 gate is green. `test_session_tree_substrate.py::TestSubstrateDoc` still passes with
no edit to its existing assertions — the amendment adds, it does not replace.

---

## Step 4 — `scripts/bg-cleanup.sh` and its test module

**Spec:** §2.1–§2.4, §2.7. **Files:** `scripts/bg-cleanup.sh` (new, executable),
`tests/unit/skill-structure/test_bg_cleanup.py` (new).

This step ships the script and its tests only. No caller is wired to it yet; Steps 5 and 6
do that.

### 4.1 Interface

```
bg-cleanup.sh --runid <id> --outcome <clean|failed> [--keep]
```

`chmod +x` the file, like every other script in `scripts/`. Follow the long-flag idiom and
the `_bgX_usage_exit` helper shape `scripts/bg-liveness.sh` and `scripts/bg-manifest.sh`
already use. [repo]

**`--runid <id>`** — required. Accept **either** the bare 4-to-8-character suffix (`7f3c`)
**or** the Workflow run id it was derived from (`wf_918a4deb-aba`), and normalize with the
**exact same rule** `skills/dispatching-bg-agents/bg-dispatch.sh` Step 3 uses: lowercase,
strip a leading `wf_`, remove every character outside `[a-z0-9]`, then keep the last 8
characters. Reject a normalized value that does not match `^[a-z0-9]{4,8}$` with a usage
error. The caller in the implement spine holds a `wf_…` id and the two registries are keyed
by the derived suffix. One rule, one source. [spec §2.2]

Duplicate the normalization inline in `bg-cleanup.sh`, line by line against
`bg-dispatch.sh` Step 3. Do not factor it into a shared helper in this change — that touches
the one script every bg dispatch runs, for no behaviour gain. Factoring out is future work.
[plan]

**`--outcome <clean|failed>`** — required. Any other value is a usage error. [spec §2.2]

**`--keep`** — optional. Present means: stop the sessions, delete nothing. [spec §2.2]

### 4.2 Step 1 — collect short ids from BOTH registries

| Registry | Path | Written by | Read how |
|---|---|---|---|
| Sidecar env files | `${HOME}/.claude/relay/bg/<runid>/*.env` | `bg-dispatch.sh` (`--engine bg-sessions`) | Parse `RELAY_BG_NAME=` and `RELAY_BG_SHORT_ID=` out of each file. **Do not `source` them.** |
| Run manifest | `${HOME}/.claude/relay/runs/<runid>/manifest.json` | `bg-manifest.sh` (`--engine session-tree`) | `bash scripts/bg-manifest.sh --runid <runid> names`, which prints `RELAY_BG_NAME=` / `RELAY_BG_SHORT_ID=` pairs |

Union the two sets and remove duplicates **keyed by short id** — the deletion key — never by
name. Reading only one registry is the bug this step exists to prevent. [spec §2.3]

Four rules a cold implementer will otherwise get wrong:

- **A missing sidecar directory is normal, not an error.** A session-tree run has none.
- **A missing manifest file is normal, not an error.** A bg-sessions run has none.
  `bg-manifest.sh … names` exits `1` with `manifest write failed: …` when the manifest is
  absent, because a missing manifest is fatal *for the orchestrator*. `bg-cleanup.sh` must
  test `[ -f "$manifest" ]` **before** calling `bg-manifest.sh`, and skip that registry when
  the file is not there. Do not let that exit `1` propagate. [repo:
  `scripts/bg-manifest.sh` `_bgm_read_or_fatal`]
- **A sidecar with an empty `RELAY_BG_SHORT_ID=`** is a launch that was denied before the
  short id was resolved. Report it as skipped. Not fatal; there is nothing to stop or delete.
  [repo: `bg-dispatch.sh` writes the sidecar with an empty short id **before** launch]
- **A short id that does not match `^[0-9a-f]{6,10}$`** — the shape `bg-launch.sh` parses —
  is reported and skipped, never used to build a path. [spec §2.3]

### 4.3 Step 2 — stop each session, then confirm

The contract's single stop mechanism is: send the session a finish-and-stop instruction, by
name, via `SendMessage`, then confirm the `stopped` verdict through `bg-liveness.sh`.
`SendMessage` is an agent tool and **a shell script cannot call it**, so the stop is split
between the script and its caller, and the script can never delete a session it did not see
confirmed stopped. [spec §2.3]

0. **Test the job directory first, before you call `bg-liveness.sh` for that id.** When
   `<jobs-root>/<short-id>` does not exist, the id never enters the verdict flow at all: it
   goes straight to the §4.4 step 2 `no-job-directory` skipped path, and it is never printed
   as `RELAY_BG_STOP_REQUIRED=`. This ordering is what makes §4.7 case 6 exit `0` instead of
   `1`. `bg-liveness.sh` reports `unknown` for an absent job directory, and `unknown` alone
   would otherwise route to the stop-required branch. Get this order right or case 6 fails.
   [spec §2.4, the stated exception]

1. For every id whose job directory **does** exist, run `bg-liveness.sh --short-id <id>`
   **once**, and read the verdict from the `RELAY_BG_VERDICT=` line on stdout.

   **Ignore `bg-liveness.sh`'s exit code. It is inverted for this caller.** That script exits
   `0` only when every verdict is `alive`, exits `1` when **any** verdict is `stopped`, and
   exits `3` for stale or unknown. The outcome cleanup wants — everything stopped — therefore
   surfaces as exit `1`. A script that branches on the exit code reads a successful cleanup as
   a failure. Parse the `RELAY_BG_VERDICT=` line; do not branch on `$?`. One invocation per id
   is required so the id-to-verdict association needs no parsing of interleaved blocks.
   [repo: the tail of `scripts/bg-liveness.sh`]

   **An absent `RELAY_BG_VERDICT=` line is a hard failure, never a silent `unknown`.**
   `bg-liveness.sh` also exits `2` on its own usage errors and prints no verdict block at all
   (`scripts/bg-liveness.sh`, `_bgv_usage_exit`). When no `RELAY_BG_VERDICT=` line comes back
   for an id, print `[relay] error: bg-liveness.sh did not report a verdict for <short-id>` on
   stderr and exit `2`. Do not downgrade it to `unknown`, and do not delete anything.
   [plan — the spec is silent, and the silent-failure lens forbids the downgrade]

2. For every id whose verdict is **not** `stopped` — `alive`, `stale`, or `unknown` with a job
   directory still present — print one line

   ```
   RELAY_BG_STOP_REQUIRED=<name> <short-id>
   ```

   delete nothing at all for that session, and, after processing every id, **exit `1`**.
3. The caller sends exactly one finish-and-stop `SendMessage` to each printed name, then
   **re-runs the identical `bg-cleanup.sh` command**.
4. On the re-run every session reads `stopped` and the script proceeds to Step 3.

The script is fully **idempotent**: run again over an already-cleaned runid it finds the job
directories gone, reports them skipped, and exits `0`. [spec §2.3]

Pass the jobs-directory override through to `bg-liveness.sh`: resolve `<jobs-root>` as
`${RELAY_BG_JOBS_DIR:-$HOME/.claude/jobs}` and export or forward it, so a test never touches
a real jobs directory. [spec §2.3, repo: `bg-liveness.sh` honors `RELAY_BG_JOBS_DIR`]

### 4.4 Step 3 — delete, on `--outcome clean` and only when `--keep` was NOT passed

For each collected short id, in this order:

1. Resolve the job directory as `<jobs-root>/<short-id>`.
2. If the job directory does not exist: print
   `RELAY_BG_CLEANUP_SKIPPED=<name> <short-id> no-job-directory` and move on. **Not fatal.**
3. Read `linkScanPath` out of `<job-dir>/state.json` with `jq -r '.linkScanPath // ""'`.
   Do this **before** removing the job directory, or the path is lost.

   **The field name is `linkScanPath`, and it is verified, not assumed.** No existing relay
   script reads it — `bg-launch.sh` reads `.intent`, `bg-liveness.sh` reads `.state` and
   `.updatedAt` — so there is no in-tree precedent to copy. Confirm the key still exists on
   one real job directory before you land the script:

   ```bash
   ls ~/.claude/jobs | head -1
   jq -r '[.state, .template, .linkScanPath] | @tsv' ~/.claude/jobs/<that-short-id>/state.json
   ```

   The third column must be a path under `~/.claude/projects/` ending in `.jsonl`. **When
   `~/.claude/jobs/` is empty on your machine, say so in the commit body and continue** — the
   check is evidence, not a gate you can fake. Do not substitute a fixture for it and do not
   claim it passed. [plan]

   Because the fallback is `// ""` and an empty value routes silently to the `no-transcript`
   skip, a wrong field name would make transcript deletion a permanent silent no-op that
   every fixture-based test still passes. Test case 1 in §4.7 is the guard: it asserts the
   transcript file is **gone**, not only that the job directory is. [spec §2.3]
4. Delete the transcript named by `linkScanPath` **only when all of these hold**: the value is
   non-empty, the path is a regular file, it ends in `.jsonl`, and it is inside
   `$HOME/.claude/projects/`. Otherwise print
   `RELAY_BG_CLEANUP_SKIPPED=<name> <short-id> no-transcript` and continue to step 5. A missing
   or unusable transcript path never blocks the job-directory deletion and is never fatal.
5. Remove the job directory with `rm -rf "<jobs-root>/<short-id>"`.

[spec §2.3]

### 4.5 Step 4 — on `--outcome failed`, or when `--keep` was passed: stop only

Delete nothing. For each session print

```
RELAY_BG_KEPT=<name> <short-id> <job-dir> <reason>
```

where `<reason>` is `outcome-failed` or `keep-flag`. `--outcome failed` and `--keep` together
print `outcome-failed`. The point is that a person can find the session, resume it, and read
its transcript. [spec §2.3]

**What is never deleted.** The two registries themselves — the sidecar `.env` files, the
sidecar directory, and the run manifest — are the record of what the run did. They stay. Do
not tidy up either registry. Keeping them is also what makes a re-run idempotent. [spec §2.3]

### 4.6 Safety rules, the final line, and the exit codes

- The script only ever touches short ids **recorded for the runid it was given**. It never
  globs the jobs root and never deletes a job directory it did not find in a registry for that
  runid.
- A recorded id whose job directory is already gone is reported and skipped, not fatal.
- **Confirm stopped before deleting.** `unknown` is not `stopped`. The one stated exception:
  when the job directory is **absent**, `bg-liveness.sh` reports `unknown` and there is
  nothing to delete; that id goes to the `no-job-directory` skipped path and never to
  `RELAY_BG_STOP_REQUIRED`. [spec §2.4]
- The last line of stdout is always:

  ```
  RELAY_BG_CLEANUP=<deleted|kept> <n> sessions
  ```

  `deleted` when Step 3 ran, `kept` when Step 4 ran. `<n>` counts the sessions the script
  acted on successfully: for `deleted`, the job directories actually removed; for `kept`, the
  sessions left resumable. Sessions reported through `RELAY_BG_CLEANUP_SKIPPED=` are **not**
  counted in `<n>`. [spec §2.4]

| Code | Meaning |
|---|---|
| `0` | Cleanup ran to the end. The final line says what happened, including the zero-session case. |
| `1` | At least one session did not read as `stopped`. Every such session was printed as `RELAY_BG_STOP_REQUIRED=`. **Nothing was deleted, for any session, on this run.** |
| `2` | Usage error — missing or unknown argument, a `--runid` that does not normalize to `^[a-z0-9]{4,8}$`, an `--outcome` outside `{clean, failed}`, or `jq` not on `PATH`. |
| `3` | Zero sessions found in either registry for that runid. Not an error; a distinguishable outcome so a caller can say so honestly instead of reporting a silent success. Stderr carries `[relay] note: no bg session recorded for runid <id> in either registry`. |

Exit `1` is all-or-nothing on purpose: a partial delete followed by a re-run is harder to
reason about than one clean retry. Errors and notes go to **stderr**, prefixed
`[relay] error: ` / `[relay] note: `. Only `KEY=VALUE` lines go to stdout. [spec §2.4]

**One ambiguity in the spec's exit table, resolved here.** Row `0` says the final line is
printed "including the zero-session case", and row `3` says the zero-session case exits `3`.
Read together: **exit `3` also prints the final line**, as
`RELAY_BG_CLEANUP=deleted 0 sessions` on `--outcome clean` and
`RELAY_BG_CLEANUP=kept 0 sessions` on `--outcome failed` or `--keep`. The exit code carries
the "no session was recorded" signal; the final line is never dropped, on any path. A path
that exits without printing it is the silent success this script exists to prevent.
Exit `2` is the one exception: a usage error never reached the work, so it prints no final
line. [plan — the spec is ambiguous, and the silent-failure lens decides it]

### 4.7 Tests — new `tests/unit/skill-structure/test_bg_cleanup.py`

Point `HOME` at a temporary fixture directory for **every** test in the module, so no real
job is ever touched. Build the fixture with a sidecar directory
`$HOME/.claude/relay/bg/<runid>/` holding `.env` files, a manifest at
`$HOME/.claude/relay/runs/<runid>/manifest.json`, job directories at
`$HOME/.claude/jobs/<short>/state.json` carrying a `state` and a `linkScanPath`, and
transcript files under `$HOME/.claude/projects/`. Follow the driving shape already used by
`test_bg_dispatch_env.py` and `test_bg_liveness.py`. A `state.json` needs a fresh `updatedAt`
whenever the case wants an `alive` verdict — copy `_iso()` from `test_bg_liveness.py`.
[spec §2.7, repo]

**Every recorded id a case expects to be deleted needs a full fixture triple**: a job
directory `$HOME/.claude/jobs/<short>/state.json` holding `"state": "stopped"` — so the id
passes the §4.3 stop check on the first run — plus a `linkScanPath` pointing at a transcript
file that **exists** under `$HOME/.claude/projects/`. Build the triple with one helper and
call it from every case. A case that records an id in a registry but builds no job directory
passes vacuously through the `no-job-directory` skip and proves nothing. [plan]

Required cases — 13 numbered behavioral cases, of which case 13 has two required sub-cases,
plus one shape test at 14. **15 test functions in all.**

1. **A clean run deletes exactly the recorded ids and nothing else.** Put an **unrelated** job
   directory in the fixture — recorded in no registry for this runid — and assert it survives.
   Assert the recorded job directories **and their transcript files** are gone.
2. **A failed run deletes nothing.** `--outcome failed`: every job directory and transcript
   survives, the final line reads `RELAY_BG_CLEANUP=kept <n> sessions`, and one
   `RELAY_BG_KEPT=` line names each session with reason `outcome-failed`.
3. **`--keep` deletes nothing**, even with `--outcome clean`. Reason `keep-flag`.
4. **Both registries are read.** Record one session **only** in a sidecar and a different
   session **only** in the manifest. Build the full fixture triple for **both** ids. Assert a
   clean run deletes both job directories **and** both transcripts. This is the test that
   fails if someone reads one registry — and it only fails for that reason when both ids have
   job directories to delete.
5. **Duplicates are removed.** The same short id in both registries is stopped once, deleted
   once, and counted once in `<n>`.
6. **A manifest id with no job directory on disk is reported and not fatal.** Record **two**
   sessions for the runid: session A with **no** job directory, and session B with the full
   fixture triple. Assert exit `0`, one
   `RELAY_BG_CLEANUP_SKIPPED=<name> <short-id> no-job-directory` line for A, B's job
   directory and transcript gone, and a final line of `RELAY_BG_CLEANUP=deleted 1 sessions` —
   A is skipped, so it is not counted in `<n>`.
7. **A live session is stopped before any deletion happens.** The fixture records **two**
   sessions under one runid: session A with `"state": "working"` and a fresh `updatedAt`, and
   session B with `"state": "stopped"`. Both have the full fixture triple. On the first run
   the script exits `1`, prints `RELAY_BG_STOP_REQUIRED=<name> <short-id>` for A, and deletes
   **neither** A nor B — the all-or-nothing rule, proven by B surviving. Then flip A's state
   file to `stopped`, re-run the identical command, and assert both are deleted.
8. **A missing manifest is not fatal** for a sidecar-only runid, and a **missing sidecar
   directory is not fatal** for a manifest-only runid. Give **both** fixtures a full fixture
   triple, so exit `0` comes from a real deletion and the final line reads
   `RELAY_BG_CLEANUP=deleted 1 sessions` — not from a vacuous `no-job-directory` skip, which
   would make this case indistinguishable from case 6.
9. **Zero sessions** in either registry exits `3` and prints the note on stderr. Supply a
   valid `--runid` whose sidecar directory does **not** exist and whose manifest file does
   **not** exist — do not create empty ones. Assert exit `3`, the stderr note, and the final
   stdout line `RELAY_BG_CLEANUP=deleted 0 sessions` (see the resolution note under the exit
   table in §4.6).
10. **Usage errors exit `2`**: no `--runid`, a `--runid` that does not normalize (for example
    `ab` or `!!!!`), and `--outcome bogus`.
11. **Runid normalization.** `--runid wf_918a4deb-aba` and `--runid <the derived suffix>` find
    the same registries. Derive the expected suffix with the same rule `bg-dispatch.sh` uses.
12. **Idempotence.** Running the same clean cleanup twice exits `0` both times; the second run
    reports every id skipped and `<n>` is `0`.
13. **The transcript guard — two sub-cases, both required.**
    - **13a, out of root.** `linkScanPath` points at a real file **outside**
      `$HOME/.claude/projects/`. Assert `RELAY_BG_CLEANUP_SKIPPED=… no-transcript`, the job
      directory is deleted, and the out-of-root file **still exists** afterwards.
    - **13b, not a regular file.** `linkScanPath` points at a **directory** under
      `$HOME/.claude/projects/`. Assert the same `no-transcript` skip, the job directory is
      deleted, and the directory still exists.

    Write them as two tests. One combined test asserts 13a's properties and never exercises
    the regular-file check.

14. **Shape.** `scripts/bg-cleanup.sh` exists and `os.access(path, os.X_OK)` is true.
    [repo convention]

### 4.8 Done criteria

The C4 gate is green, and all fifteen test functions in §4.7 pass. The manual `jq` check in §4.4
step 3 has been run and its result — the confirmed `linkScanPath` value, or the note that
`~/.claude/jobs/` was empty — is recorded in the commit body.

---

## Step 5 — pin the stop wording, and wire `--keep-sessions` through `/relay:implement`

**Spec:** §2.3 (message body), §2.5 A and B. **Files:** `docs/bg-dispatch-contract.md`,
`commands/implement.md`, `skills/running-implement-spine/SKILL.md`,
`tests/unit/skill-structure/test_bg_command_wiring.py`,
`tests/unit/skill-structure/test_relay_implement_polish.py`,
`tests/unit/skill-structure/test_plugin.py` (the spine input parametrize only — no version
class yet, per C3).

### 5.0 Declare `SendMessage` in `implement.md`'s `allowed-tools`

`commands/implement.md` frontmatter today reads:

```
allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill
```

`SendMessage` is not there. No relay command lists it, in any of the eight command files.
The spine's exit-`1` branch (§5.3) and the session-tree orchestrator's end-of-run stop
protocol (Step 6) both call it, and both run inside a `/relay:implement` turn. Add it:

```
allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill, SendMessage
```

**One existing test pins that line exactly and must be updated in the same edit:**
`tests/unit/skill-structure/test_relay_implement_polish.py` asserts

```python
assert "allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill" in frontmatter
```

Change the literal to the new line. Do not delete the assertion — an exact pin on this line
is the only thing that stops a tool from being dropped from the command by accident. [repo,
verified by reading both files]

**Be accurate about why.** `SendMessage` is a **deferred** tool: a session can load its
schema through `ToolSearch` at run time, so the retry loop is not provably unexecutable
without this edit. Two facts are established by reading the tree, and one is not:

- Established: no relay command declares `SendMessage` today.
- Established: `skills/orchestrating-session-trees/SKILL.md` `## End of run` already tells
  the orchestrator to send a finish-and-stop message in every
  `/relay:implement --engine session-tree` run, so the tool is already needed on that path
  and the omission is pre-existing.
- **Not established:** whether a `/relay:implement` turn can reach `SendMessage` without the
  declaration. No unit test can settle it; it needs a live session.

So this edit is a **declaration of intent**, the same reason `Skill` is pinned in the
frontmatter, and it makes the dependency assertable by `test_bg_command_wiring.py`. Write it
that way in the commit body. If a live check later shows `SendMessage` is unreachable from a
`/relay:implement` turn without the declaration, then this edit was load-bearing and the
current session-tree stop protocol was a pre-existing bug — record that when it is known, do
not claim it now. [plan]

### 5.1 Pin the finish-and-stop message body

Neither `docs/bg-dispatch-contract.md` §Spawn authority nor
`skills/orchestrating-session-trees/SKILL.md` §End of run pins a wording today, and this
change adds a second caller. Pin one, in `docs/bg-dispatch-contract.md` §Spawn authority, so
both callers and any future one send the same thing:

```
Finish your current turn and stop. Do not start new work. Do not message any other session.
```

It is plain prose on purpose. It must **not** use envelope grammar: a message whose first
line matched `ROLE_DONE`, `BLOCKED:`, `NEEDS_DECISION:`, or `KEY=VALUE` would be parsed as an
envelope by a child that is mid-protocol. Free text is inert by contract, which is exactly
what a stop instruction needs. [spec §2.3]

**Watch the existing guard.** `test_bg_dispatch_contract.py::test_single_stop_mechanism_stated_once`
asserts `text.count("finish-and-stop instruction") == 1`. Word the new paragraph so that
phrase is still used exactly once in the whole doc. [repo]

### 5.2 `commands/implement.md` — the flag

- Frontmatter `argument-hint` gains `[--keep-sessions]`.
- Parse it in Step 0, in the same `grep -qw` shape `--verify` and `--retro` already use. The
  check must sit **after** `source "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh"`,
  because it needs the resolved `$RELAY_ENGINE`.
- Passing it with an engine that launches no bg session is an **ERROR with a clear message,
  not a silent no-op**, in the same shape as the existing `--rounds` without `--verify` error.
  The engines that launch bg sessions are `bg-sessions` and `session-tree`; every other value
  (`in-session`, `acpx`, `smart-routing`) is the error case.

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

- **Strip `--keep-sessions` from the task text before classification.** Step 1's sentence
  lists what to remove from `$ARGUMENTS` before `relay:classifying-task-kind` runs. **That
  strip list is prose, not code** — read the file: the sentence is an instruction to the
  model, and no `_strip_flags` shell variable exists for `--verify` or `--retro` either. The
  change is one added phrase. Do not invent shell stripping code the other flags do not have.
  [spec §2.5 A]

  The sentence today reads:

  > `$ARGUMENTS` minus the parsed `--engine`/`--agent` flags, minus `--verify`, minus
  > `--rounds` with its value, **and minus `--retro` with its optional target**

  It becomes:

  > `$ARGUMENTS` minus the parsed `--engine`/`--agent` flags, minus `--verify`, minus
  > `--rounds` with its value, minus `--keep-sessions`, **and minus `--retro` with its
  > optional target**

  The `and` stays in front of `--retro`. [plan]
- Step 3 passes the flag through to the spine as an eleventh input, `keep_sessions`. Update
  the "Pass all ten inputs" sentence to eleven and name it. [spec §2.5 A]

### 5.3 `skills/running-implement-spine/SKILL.md` — Step 4.5

- Add `keep_sessions` to the `## Inputs` list. It is **optional and defaults to `false`**, so
  `relay:implementing-spec`, the other caller, needs no edit and keeps passing its current
  inputs. [spec §2.5 B]
- Add a step between Step 4 (completeness gate) and `## Output`, numbered **Step 4.5 — Clean
  up the run's background sessions**. It runs **only when `engine` is `bg-sessions`**;
  `session-tree` never reaches this skill (that branch is terminal in `commands/implement.md`
  Step 1), and every other engine launched no bg session.
- `--outcome` is `clean` when the run is about to print `status: ok`, and `failed` otherwise.
  Resolve the status **before** running the cleanup, so a failed run keeps its sessions
  readable.
- `--runid` is the Workflow `run_id` (`wf_…`); the script normalizes it.
- Pass `--keep` when `keep_sessions` is true.

  ```bash
  "${CLAUDE_PLUGIN_ROOT}/scripts/bg-cleanup.sh" --runid "<run_id>" --outcome "<clean|failed>" [--keep]
  ```

- **State all four exit codes.** None of them may be silent, and none of them changes the JSON
  `status`.

  | Exit | Spine behavior |
  |---|---|
  | `0` | Report the final `RELAY_BG_CLEANUP=` line. Done. |
  | `1` | Send the pinned finish-and-stop `SendMessage` (§5.1) to each printed `RELAY_BG_STOP_REQUIRED=` name, then re-run the identical command. At most two re-runs. If a session is still not `stopped` after that, **name it in the run's report** and continue. §5.0 declares `SendMessage` in the command's `allowed-tools`. If the tool is genuinely unavailable in this session, say so in the report and name the sessions — never report them as stopped. |
  | `2` | A usage error is a **relay bug**, not a run failure. Report the stderr line verbatim and continue. Never retry — the arguments will not change. |
  | `3` | Zero sessions were recorded for this runid. Say so plainly (`no background session was recorded for this run`) and continue. This is legal for a `bg-sessions` run whose leaves all fell through to in-session dispatch. Do not treat it as a failure and do not treat it as a clean deletion. |

- The cleanup is **advisory for the run's status**: it never turns an `ok` run into a failure
  and never turns a failed run into an `ok` one. Report its final `RELAY_BG_CLEANUP=` line and
  name any session that would not stop, but do not change the JSON `status` because of it. It
  must, however, never be silent: always print something from the table. [spec §2.5 B]

### 5.4 Tests

Extend `tests/unit/skill-structure/test_bg_command_wiring.py` with a new class — for example
`TestKeepSessionsWiring` — asserting:

- `commands/implement.md`'s `argument-hint` line lists `--keep-sessions`.
- The error branch text is present and it names both `bg-sessions` and `session-tree`.
- `--keep-sessions` appears in the Step 1 strip sentence.
- `skills/running-implement-spine/SKILL.md` names `bg-cleanup.sh`, declares `keep_sessions`,
  and states all four cleanup exit codes.
- `commands/implement.md`'s `allowed-tools` line lists `SendMessage` (§5.0).
- `docs/bg-dispatch-contract.md` §Spawn authority carries the pinned finish-and-stop wording,
  and it is not envelope grammar. Write this assertion as: define the wording as a module
  constant, assert it appears in the doc by exact substring, then assert on the constant
  itself, not on a line the test grepped out of the doc —

  ```python
  WORDING = ("Finish your current turn and stop. Do not start new work. "
             "Do not message any other session.")
  first = WORDING.splitlines()[0]
  assert WORDING in CONTRACT.read_text()
  assert re.match(r"^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$", first) is None
  assert not first.startswith(("BLOCKED:", "NEEDS_DECISION:"))
  ```

  Slicing the line out of the rendered doc would make the test depend on the fence and the
  wrapping, which a later doc edit may change without changing the wording. [spec §2.7, plan]

Use the module's existing `_body(name)` helper for command files. Collapse whitespace before
a multi-word substring assertion — prose wraps at ~88 characters in this repo. [repo:
`test_session_tree_substrate.py::_collapsed`]

`tests/unit/skill-structure/test_plugin.py` — add `keep_sessions` to the
`TestRunningImplementSpineSkill::test_it_declares_every_input` parametrize list. That is the
only edit to this file in this step. [spec §4.3]

### 5.5 Known limitation, deliberately out of scope

`--engine bg-sessions` is wired into four commands — `implement`, `refine`, `execute`, and
`drive` (`tests/unit/skill-structure/test_bg_command_wiring.py` pins all four). This change
wires cleanup into `/relay:implement` and, in Step 6, into the session-tree orchestrator only.
A `/relay:refine --engine bg-sessions` run still leaves its sessions behind. **Do not widen the
wiring in this change.** Record it in the CHANGELOG entry in Step 7 as a known limitation.
[spec §2.6]

### 5.6 Done criteria

The C4 gate is green, and `test_bg_dispatch_contract.py::test_single_stop_mechanism_stated_once`
still passes.

---

## Step 6 — wire the cleanup into the session-tree end-of-run protocol

**Spec:** §2.5 C. **Files:** `skills/orchestrating-session-trees/SKILL.md`,
`tests/unit/skill-structure/test_bg_command_wiring.py`.

### 6.1 The edit

Extend the skill's `## End of run` section. The orchestrator already sends each child a
finish-and-stop instruction bottom-up — workers before their operator — and confirms
`stopped` through `bg-liveness.sh`. After that protocol it runs
`scripts/bg-cleanup.sh` with the run's runid — the one the orchestrator allocated in
`## Bookkeeping` — so **both bg engines clean up through one code path**. `--outcome` is
`clean` when the run completed and `failed` otherwise. `--keep` mirrors `--keep-sessions`.
Because the orchestrator has already stopped its children, the script's stop step normally
confirms `stopped` on the first call. [spec §2.5 C]

**The runid needs a named handle, and the skill has none today.** Read `## Bookkeeping`: it
says the orchestrator allocates a fresh `[a-z0-9]{4,8}` string at the start of the run and
passes it as `--runid <id>` to every `bg-manifest.sh` call, but it never binds that value to a
name. Give it one in this step, in `## Bookkeeping`: state that the orchestrator holds the
allocated runid as `$RELAY_RUN_ID` for the whole run and uses that variable wherever the
skill needs the value. Then the end-of-run call has something unambiguous to point at:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-cleanup.sh" \
  --runid "$RELAY_RUN_ID" --outcome "<clean|failed>" [--keep]
```

This is a two-line addition to `## Bookkeeping` plus the call above. Do not change how the
runid is allocated, and do not introduce a second runid space. [plan]

**On exit `1`, the orchestrator DOES run the retry loop.** It is the one session in the tree
that can `SendMessage`, so it sends the pinned finish-and-stop message (Step 5 §5.1) to each
printed `RELAY_BG_STOP_REQUIRED=` name and re-runs, at most twice — the same rule the spine
follows. Only after that does the existing rule apply: any child that still does not confirm
`stopped` is **named in the run's final report**, never silently left running and never
silently reported as stopped. **The two rules are sequential, not alternatives: retry first,
then name what survived.** Exit `2` and exit `3` follow the same four-row table the spine
uses (Step 5 §5.3). [spec §2.5 C]

Part 3 changes nothing in this file. `--engine session-tree` is kept exactly as it is.
[spec §3.6]

### 6.2 Tests

Extend `tests/unit/skill-structure/test_bg_command_wiring.py`:

- `skills/orchestrating-session-trees/SKILL.md` names `bg-cleanup.sh` in its `## End of run`
  section — slice the section out of the file and assert on the slice, so a mention elsewhere
  cannot satisfy the test.
- The End-of-run section states that the orchestrator runs the retry loop **before** naming a
  surviving child. Assert both phrases are present and that the retry phrase appears before
  the naming phrase in the section text. [spec §2.7]

### 6.3 Done criteria

The C4 gate is green, and `tests/unit/skill-structure/test_orchestrating_session_trees.py`
still passes with no edit.

---

## Step 7 — the release ratchet

**Spec:** §4. **Files:** `.claude-plugin/plugin.json`, `CHANGELOG.md`, `docs/contributing.md`,
`tests/unit/skill-structure/test_plugin.py`.

Every item is required, in this PR, per `CLAUDE.md` — the version is the plugin-distribution
cache key.

1. **`.claude-plugin/plugin.json`** — `"version": "4.44.0"` → `"4.45.0"`.
2. **`CHANGELOG.md`** — add a `## 4.45.0 — 2026-08-25` entry **above** the `## 4.44.0` entry,
   in the existing style: a bold lead sentence per change, then the detail. It must name the
   tokens the new version class greps for. Use at least: `bg-cleanup.sh`, `--keep-sessions`,
   `auto`, and `classifier refused`. Record the §5.5 known limitation — cleanup is wired to
   `/relay:implement` and the session-tree orchestrator only — in the entry.
3. **`tests/unit/skill-structure/test_plugin.py`** — the version dance:
   - Convert `TestVersion4440`'s exact pin to the floor form,
     `assert Version(manifest["version"]) >= Version("4.44.0")`, using
     `packaging.version.Version`, and carry the in-tree comment style forward:
     `# Superseded exact pin: 4.45.0 carries this line forward (TestVersion4450 …)`.
   - Add `class TestVersion4450` with the exact pin `assert manifest["version"] == "4.45.0"`,
     a `_entry()` helper that splits on `## 4.45.0` … `## 4.44.0`, a
     `test_the_entry_names_what_shipped` parametrized over the distinguishing tokens, and —
     per the convention every version class that ships a script follows — an assertion that
     `scripts/bg-cleanup.sh` exists and `os.access(path, os.X_OK)` is true.
4. **`docs/contributing.md`** — ratchet the worked example `assert manifest["version"] ==
   "4.44.0"` to `"4.45.0"`.
   `tests/unit/skill-structure/test_docs_freshness.py::test_version_example_matches_manifest`
   compares that literal against the manifest and fails otherwise. Do not edit that test.
5. **Run the full suite and make it pass** — the C4 gate. The suite is the only gate, so it
   must be run by hand and it must be green.

### 7.1 Done criteria

`pytest tests/ -q` is green with zero failures, the two shell test scripts exit `0`, and
`git status --short` shows only the files this plan names.

---

## Files this change touches

**New**

- `plugins/relay/scripts/bg-cleanup.sh` (executable) — Step 4
- `plugins/relay/tests/unit/skill-structure/test_bg_cleanup.py` — Step 4
- `plugins/relay/docs/superpowers/plans/2026-08-25-relay-bg-auto-cleanup-nesting-plan.md`
  (this file)
- `plugins/relay/tests/fixtures/bg-state/template-bg.json` and `template-claude.json` —
  Step 2, and only when Step 2.4 chose the fixture-file shape over the inline shape

**Changed**

| File | Steps |
|---|---|
| `docs/bg-dispatch-contract.md` | 1, 5 |
| `docs/orchestration-substrates.md` | 3 |
| `docs/contributing.md` | 7 |
| `skills/dispatching-bg-agents/bg-dispatch.sh` | 1, 2 |
| `skills/dispatching-bg-agents/SKILL.md` | 1, 3 |
| `skills/dispatching-bg-agents/preamble.md` | 1, 2 |
| `skills/orchestrating-session-trees/SKILL.md` | 6 |
| `skills/running-implement-spine/SKILL.md` | 5 |
| `commands/implement.md` | 5 |
| `.claude-plugin/plugin.json`, `CHANGELOG.md` | 7 |
| `tests/unit/skill-structure/test_bg_dispatch_env.py` | 1, 2 |
| `tests/unit/skill-structure/test_bg_dispatch_contract.py` | 1 |
| `tests/unit/skill-structure/test_dispatching_bg_skill.py` | 1, 3 |
| `tests/unit/skill-structure/test_session_tree_substrate.py` | 3 |
| `tests/unit/skill-structure/test_bg_command_wiring.py` | 5, 6 |
| `tests/unit/skill-structure/test_relay_implement_polish.py` | 5 (the exact `allowed-tools` pin only) |
| `tests/unit/skill-structure/test_plugin.py` | 5, 7 |

**Explicitly unchanged**

- `scripts/bg-launch.sh` (behavior; a header comment is optional), `scripts/bg-liveness.sh`,
  `scripts/bg-manifest.sh`
- `bindings/presets.yaml`
- `tests/unit/skill-structure/test_envelope_tokens.py` — must not be edited
- `tests/unit/skill-structure/test_bg_launch.py`
- `tests/e2e/bg-s1-roundtrip.sh` — it passes `bypassPermissions` by hand, which stays supported
- every acpx dispatch path and its `--approve-all` CLI flag
- every plugin other than `plugins/relay/`

---

## Refinement Status

**Refinement: CONVERGED round 3.**

Adapter `plan`, critic `roles/plan-simulator.md` dispatched read-only through
`acpx claude exec` (engine=acpx, agent=claude), three rounds.

| Round | critical | important | minor | Action |
|---|---|---|---|---|
| 1 | 3 | 7 | 5 | All 15 fixed. |
| 2 | 0 | 2 | 5 | All 7 fixed. |
| 3 | 0 | 0 | 0 | CONVERGED — every prior fix verified against the source files it names. |

The findings that changed this plan the most:

1. **critical** — §4.3 ordered the liveness check before the job-directory check, which would
   make an absent job directory print `RELAY_BG_STOP_REQUIRED=` and exit `1`, contradicting
   §4.6 and failing case 6. The job-directory test is now step 0, before the verdict flow.
2. **critical** — the Step 3 live gate and the Step 4 `jq` check were done criteria a cold
   worker may be unable to meet. Both now have a stated, honest fallback that records what
   was not measured, instead of a step that stalls or fakes evidence.
3. **important** — `commands/implement.md` does not declare `SendMessage` in `allowed-tools`,
   and one existing test pins that line exactly. §5.0 now names both, and states honestly
   that the tool is deferred and loadable through `ToolSearch`, so the edit is a declaration
   of intent rather than a proven unblock.
4. **important** — `test_bg_dispatch_env.py`'s `_run` helper inherits the real environment,
   so a developer running `pytest` inside a bg session would see every existing case refuse
   once the depth cap lands. §2.4 now scrubs both signal variables first.
5. **plan** — the spec's exit table is ambiguous about whether exit `3` prints the final
   `RELAY_BG_CLEANUP=` line. §4.6 resolves it: the line is printed on every path except the
   usage error, because a path that exits silently is the failure the script exists to
   prevent.
