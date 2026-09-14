# Relay bg engines — implementation plan

Date: 2026-08-19
Status: ready to execute.
Spec (the contract): `docs/superpowers/specs/2026-08-19-relay-bg-engines-design.md`.
Spike findings (S1–S4): `docs/superpowers/specs/2026-08-18-bg-session-messaging-spike-findings.md`.
Version target: one bump, `4.29.0` → `4.30.0`, at the end.

All paths in this plan are relative to `plugins/relay/`.

## How to read this plan

Every item is marked with its source:

- **[spec]** — the spec states it. Copy the value or the string exactly. Do not improve it.
- **[repo]** — an existing test, script, or doc in this tree forces it. The plan names the
  file that forces it.
- **[plan]** — the spec is silent and this plan decides it. The implementer may change a
  `[plan]` decision, but must then change every test that pins it.

Read the spec in full before you start. This plan does not repeat the spec's rationale.

## Constraints

### C1 — the work is sequential, never parallel

The three deliverables edit the same files. These are the shared files:

| File | D1 | D2 | D3 |
|---|---|---|---|
| `scripts/parse-engine-agent.sh` | — | adds `bg-sessions` | adds `session-tree` |
| `commands/implement.md` | — | wiring note, hint, Step 0.25 | Step 1 terminal branch, hint, Step 2–5 skip preconditions |
| `commands/refine.md` / `execute.md` / `drive.md` | — | wiring note, hint, Step 0.25 | reject guard |
| `docs/orchestration-substrates.md` | — | — | second exception |
| `docs/architecture.md`, `README.md` | — | new engine value | new engine value |
| `scripts/validate_l3_command.py` | — | `_KNOWN` token | `_KNOWN` token |
| `docs/dispatch-contract.md` | cross-reference | — | — |
| `skills/delegate-and-watch/SKILL.md` | — | bg leg | — |
| `tests/unit/skill-structure/test_parse_engine_agent.sh` | — | new cases | new cases |
| `docs/contributing.md` | — | skill counts | skill counts, version |

Two agents editing `parse-engine-agent.sh` at the same time produce a merge conflict in the
one file that every command sources at Step 0. Build in the fixed order: **D1 → D2 → D3**.
Finish and test each deliverable before you start the next.

### C2 — the frozen tokens do not change

`ROLE_DONE`, `BLOCKED:`, and `NEEDS_DECISION:` keep their exact byte sequences, together
with the capture regex `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$`. [spec §1.1]

`tests/unit/skill-structure/test_envelope_tokens.py` is the pin. **Do not edit that file in
any of the three deliverables.** Its `FROZEN_TOKENS` list and its `DRIVER_FILES` list stay
as they are. The bg scripts are not acpx drivers, so they do not join `DRIVER_FILES`.

The two new tokens, `DECISION: <answer>` and `ESCALATION from <origin>: <question>`, are
**provisional**. [spec §1.1] They live in `docs/bg-dispatch-contract.md` and in their own
test file, `tests/unit/skill-structure/test_provisional_tokens.py`. They never enter
`test_envelope_tokens.py`.

Warning for the test author: the string `"DECISION:"` is a substring of `"NEEDS_DECISION:"`.
A test that asserts `"DECISION:" not in test_envelope_tokens.py` fails on the frozen token.
Assert on list membership after you parse the `FROZEN_TOKENS` literal. See D1 test 4.

### C3 — one version bump, at the end

The spec says each deliverable is its own PR with its own bump. **This plan overrides that
sentence.** The three deliverables land as three sequential commits, and the version bumps
once at the end, to `4.30.0`, with one CHANGELOG entry that covers all three. The release
step is a separate, final step of this plan.

This changes nothing about C1: the work is still strictly sequential.

### C4 — repo gates that a new engine value or a new skill trips

These are not obvious, and each one turns the suite red the moment you touch the parser or
add a skill directory. Handle each in the same step that causes it. [repo]

1. `tests/unit/skill-structure/test_docs_freshness.py::TestArchitectureAxisMatchesParser`
   reads the engine enum straight out of `parse-engine-agent.sh` and asserts every value
   appears as `` `value` `` in `docs/architecture.md`.
2. `test_docs_freshness.py::TestPluginReadmeMatchesTree::test_axis_values_match_the_parser`
   does the same for `README.md`.
3. `test_docs_freshness.py::test_skill_inventory_numbers_are_current` asserts that
   `EXPECTED_SKILLS` (`test_plugin.py`) + `L2_NAMES` + `RESOLUTION_POLICY_SKILLS`
   (`test_l2_skills_present.py`) + 1 equals the number of directories under `skills/`, and
   that `docs/contributing.md` states each constant's size as `` `EXPECTED_SKILLS` (15) ``.
   Today: 15 + 7 + 2 + 1 = 25 directories. Each new skill directory needs an
   `EXPECTED_SKILLS` entry **and** an updated count in `docs/contributing.md` line 140.
4. `scripts/validate_l3_command.py` rejects any `relay:<name>` token in a command body that
   is not in its `_KNOWN` set. A command body that names a new skill fails the L3 gate until
   you add the name to `_KNOWN`.
5. `test_docs_freshness.py::TestLinksResolve::test_backticked_paths_exist` checks every
   backticked repo path in `docs/architecture.md` and `docs/contributing.md`. Name a script
   in those docs only after the file exists.
6. `test_plugin.py::test_command_step_025_ask_when_unpinned` asserts the exact strings
   `in-session (default)` and `acpx (hybrid)` in all five command bodies. A third option is
   an addition, never a replacement.

### C5 — two properties are unverified, and each blocks its deliverable

The spec marks two mechanism claims `[unverified]`. Each is the **first task** of its
deliverable, before any other work in that deliverable.

- **D2, first task.** Can a Workflow watcher node send a message to a named session? [spec
  §Deliverable 2, Multi-turn] If it cannot, v1 restricts `bg-sessions` to roles with
  `one_shot: true`, and multi-turn roles keep the acpx leg.
- **D3, first task.** Does an inbound message re-invoke an idle MAIN session that sits
  mid-slash-command, and does the re-invoked turn still hold the command's run state? [spec
  §Deliverable 3, Waiting] If it does not, the orchestrator holds a bounded poll over the
  manifest instead, in the same shape as the `delegate-and-watch` watcher.

Record the result of each check in the commit body and in the CHANGELOG entry. Do not
assume either property.

## The gate — run this before you call any deliverable done

From `plugins/relay/`. There is no CI. This run is the whole gate. [repo
`docs/contributing.md`]

```bash
pytest tests/ -q
bash tests/unit/skill-structure/test_parse_engine_agent.sh
bash tests/unit/skill-structure/test_resolve_tier.sh
bash tools/fidelity-check.sh --smoke
python3 scripts/doc_reference_scan.py --repo-root . --run-gate
bash scripts/check-deps.sh
```

`doc_reference_scan.py` is advisory and noisy. It exits `0` on findings. Read the findings
and look for a path you actually renamed or removed.

Check for silent skips before you trust a green run:

```bash
pytest tests/ -q -rs | grep SKIPPED
```

`yq` and `jq` must be installed, or more than thirty acpx-dispatch tests skip and the run
proves nothing.

---

# Deliverable 1 — the bg dispatch contract

The contract layer both engines stand on. No engine may deviate from it. This deliverable
ships two scripts and one doc, and nothing that calls them.

## D1 files

Create:

- `docs/bg-dispatch-contract.md`
- `scripts/bg-launch.sh` (executable, `chmod +x`)
- `scripts/bg-liveness.sh` (executable, `chmod +x`)
- `tests/e2e/bg-s1-roundtrip.sh` (executable) — the scripted live check, never run by pytest
- `tests/fixtures/bg-state/*.json` — state-file fixtures (list in D1.6)
- `tests/unit/skill-structure/test_bg_dispatch_contract.py`
- `tests/unit/skill-structure/test_bg_launch.py`
- `tests/unit/skill-structure/test_bg_liveness.py`
- `tests/unit/skill-structure/test_bg_naming_grammar.py`
- `tests/unit/skill-structure/test_provisional_tokens.py`

Modify:

- `docs/dispatch-contract.md` — one cross-reference block. Nothing else.

Do not touch:

- `tests/unit/skill-structure/test_envelope_tokens.py` (C2).
- `bindings/presets.yaml`. It is unchanged in v1. [spec §Deliverable 2, Bindings]
- `scripts/record-run-intent.sh`. The spec's refined text is explicit: the session-tree
  manifest is its own artifact and `record-run-intent.sh` itself is unchanged. [spec
  §Deliverable 3, Bookkeeping]

## D1.1 `docs/bg-dispatch-contract.md`

The doc is the single statement of the shared layer. Write these sections, in this order,
with these headings. Each maps to one spec section.

| Section | Content, from the spec |
|---|---|
| `## Envelope` (§1.1) | The four frozen tokens, verbatim. The statement that the envelope travels in the message body, not on stdout. The rule that sender identity comes from the transport `from-name`, never from the body — and that `ROLE_DONE from <name>` is forbidden. The two provisional tokens, each marked provisional. The rule that a message matching none of these grammars is logged and moves no run state. |
| `## Naming` (§1.2) | The grammar block `<product>-<role>-<goal>-<runid>`. The four field sources per engine. The rule that addresses resolve at send time and a `[ref]` is never cached (S4-3). The reduced validation rule: length ≤ 63, charset `[a-z0-9-]`, runid suffix `-[a-z0-9]{4,8}$`, and one roster role token at a fixed position. |
| `## Launch` (§1.3) | The prompt-last rule and why (launch trap 1). The `intent` check. `LAUNCH_DENIED` as a normal typed outcome (launch trap 2). The permission-mode mapping table. The statement that `dontAsk` is forbidden for any role that runs Bash (S3-1). |
| `## bg-launch.sh interface` | The full interface from D1.2 below, verbatim. |
| `## Identity preamble` (§1.4) | The five lines every child gets. The bg-sessions substitution of the parent line. The three extra fork lines, marked **reserved and unused in v1**. |
| `## Liveness and truth` (§1.5) | The `state` → verdict table, all six rows. The rule that the state file never answers "did it succeed" (S4-2). The `updatedAt` rule: age downgrades only the alive values. `RELAY_BG_STALE_SECONDS`, default 900. The statement that a dead child sends no message (S4-1). |
| `## Spawn authority` (§1.6) | The orchestrator spawns every session; operators never spawn. The single stop mechanism: send a finish-and-stop instruction by name, then confirm the `stopped` verdict through `bg-liveness.sh`. No other means, and no session stops a sibling. |
| `## Failure behavior` | The spec's failure table, both columns. |
| `## Live validation — the S1 round trip` | The scripted procedure. See D1.5. |

Cross-reference `docs/dispatch-contract.md` for the frozen grammar. Say plainly that this
doc adds a transport and adds no token to the frozen set.

## D1.2 `scripts/bg-launch.sh`

**Mode: EXECUTED.** The caller reads its stdout and its exit code. It uses `exit`, not
`return`. [repo convention: printed `KEY=VALUE` lines cross the Bash→Claude boundary]

Header block, per repo convention: purpose; the word EXECUTED; one exact invocation example;
version-numbered behavior notes starting `4.30.0: ...`. Cite `spec §1.3` and the spike
findings `S4-3`, `launch trap 1`, `launch trap 2` at the lines they govern. Use `set -u`
only. No `set -e`. Prefix helper functions `_bgl_`.

### Arguments [spec §1.3]

| Flag | Required | Meaning |
|---|---|---|
| `--name <name>` | yes | The name built per §1.2. |
| `--model <model>` | yes | From the binding's `modalities.claude`. |
| `--permission-mode <mode>` | yes | From the §1.3 mapping table. |
| `--prompt-file <path>` | yes | The identity preamble plus the role body, already assembled by the caller. |
| `--fork-from <session-id>` | no | Adds `--resume <id> --fork-session`. **No v1 caller passes it.** |
| `--check-name <name>` | — | **[plan]** Validate-only mode. See D1.2.4. |

Parse with the repo's long-flag idiom, accepting both spellings:

```bash
while [ $# -gt 0 ]; do
  case "$1" in
    --name) _name="$2"; shift 2;;
    --name=*) _name="${1#--name=}"; shift;;
    ...
    *) printf '[relay] error: unknown argument: %s\n' "$1" >&2; exit 2;;
  esac
done
```

`--prompt-file` must name a readable, non-empty file. If it does not, exit `2`.

**[plan]** Reject `--permission-mode dontAsk` with exit `2` and
`[relay] error: --permission-mode dontAsk is forbidden — a dontAsk child cannot run Bash (S3-1)`.
The spec says the script never selects `dontAsk`. Rejecting it as well makes S3-1
impossible for a caller to reintroduce.

### D1.2.1 Command construction [spec §1.3 step 1]

The prompt is the **last** argument. No variadic flag may sit before it.

```bash
claude --bg --name "$_name" --model "$_model" --permission-mode "$_mode" "$_prompt"
```

With `--fork-from`, insert `--resume "$_fork" --fork-session` before the prompt. The prompt
stays last.

`--allowedTools` must not appear anywhere in this script. A test asserts its absence.

### D1.2.2 Short-id resolution [spec §1.3]

`claude --bg` prints the short id to stdout at launch. Capture stdout and parse the short id
from it. **Never scan `~/.claude/jobs/` by the `name` field** — names are not unique (S4-3).
If stdout holds no parseable short id, the launch failed. Do not run the `intent` check.

### D1.2.3 Intent check and wait ceiling [spec §1.3 step 2]

Poll `${HOME}/.claude/jobs/<short-id>/state.json` once a second for a non-empty `intent`.
Ceiling: `RELAY_BG_LAUNCH_TIMEOUT_SECONDS`, default `15`. A missing file is "not ready", not
a failure, until the ceiling.

Read `intent` with `jq -r '.intent // ""'`. `jq` is already a hard dependency of this
plugin.

Use `$HOME`, never a hard-coded path. Tests set `HOME` to a temporary directory, in the same
way `tests/unit/skill-structure/test_record_run_intent.py` does. [repo]

### D1.2.4 Printed contract and exit codes [spec §1.3]

On success, print exactly these three lines to stdout, in this order:

```
RELAY_BG_NAME=<name>
RELAY_BG_SHORT_ID=<short-id>
RELAY_BG_LAUNCH=OK
```

On failure, print exactly one line:

```
RELAY_BG_LAUNCH=LAUNCH_DENIED
```

Write the reason to stderr, prefixed `[relay] error: `. The reason never goes to stdout.

Exit codes, documented in the header block:

- `0` — `RELAY_BG_LAUNCH=OK`.
- `1` — `LAUNCH_DENIED`. All three causes share this one typed outcome: classifier refusal,
  unparseable short id, `intent` still empty at the ceiling.
- `2` — usage error (missing or unknown argument, unreadable prompt file, forbidden
  permission mode, bad `--name`).

**[plan]** `--check-name <name>` runs the §1.2 name validation and nothing else. It starts no
child. It prints `RELAY_BG_NAME_OK=1` and exits `0` on a valid name, or writes
`[relay] error: invalid session name: <reason>` to stderr and exits `2`. It gives the naming
grammar one implementation and one test target. `bg-launch.sh` runs the same validation on
`--name` at every launch.

### D1.2.5 Name validation rules [spec §1.2]

Check only what a validator can decide. Do not try to parse `product` or `goal` out of a
name — both are open kebab slugs.

1. Length ≤ 63 characters.
2. Charset: `^[a-z0-9-]+$`.
3. Ends with a runid suffix matching `-[a-z0-9]{4,8}$`.
4. Split the name on `-`. Strip the runid suffix. At least one of the two fixed positions
   must hold a roster role: position 2 (`product-role`, the orchestrator shape) or the
   token before the goal (`product-role-goal`). Try both splits; require one roster hit.

**[plan]** Roster source: the role slugs are the stems of `roles/*.md` (minus `README`), plus
the registered agent slugs named in `docs/agent-roster.md`. D3 adds the session-tree
topology roles to `docs/agent-roster.md` (see D3.2). Read the roster at run time; never
hard-code a role list in the script.

## D1.3 `scripts/bg-liveness.sh`

**Mode: EXECUTED.** Header block in the same shape as `bg-launch.sh`. Helper prefix `_bgv_`.

The spec fixes the verdicts, the mapping, and the stale variable. The spec does not fix the
flags or the exit codes. Everything marked **[plan]** below is this plan's choice.

### Arguments **[plan]**

| Flag | Repeatable | Meaning |
|---|---|---|
| `--short-id <id>` | yes | A child to check. At least one is required. |
| `--stale-seconds <n>` | no | Overrides `RELAY_BG_STALE_SECONDS`. |

`RELAY_BG_STALE_SECONDS` default is `900`. [spec §1.5]

### Verdict mapping [spec §1.5 — copy this table into the script's comments]

| `state` value | Verdict |
|---|---|
| `working` | alive |
| `blocked` | alive |
| `done` | alive |
| `stopped` | stopped |
| `failed` | stopped |
| absent or unreadable | unknown |

`done` is **alive**, not stopped. A child between turns reads `done`. This is the mapping's
one counter-intuitive row, and the one most likely to be "corrected" by a later reader. Say
so in a comment.

`updatedAt` age decides only among `working`, `blocked`, and `done`. If the age is greater
than the stale ceiling, the verdict downgrades from `alive` to `stale`. `stopped`, `failed`,
and `unknown` are never reclassified by age.

`updatedAt` is ISO-8601 with milliseconds and a `Z` suffix, for example
`2026-08-03T12:07:31.746Z`. `jq`'s `fromdateiso8601` rejects the fractional part, so strip it
first. This form is portable and does not depend on GNU `date`: [repo, measured against a
live jobs directory]

```bash
_epoch="$(jq -r '(.updatedAt // "") | sub("\\.[0-9]+Z$";"Z") | fromdateiso8601' "$_state" 2>/dev/null)"
```

### Printed contract **[plan]**

One four-line block per `--short-id`, in the order the flags were given:

```
RELAY_BG_SHORT_ID=<short-id>
RELAY_BG_STATE=<raw state value, or empty when the file is absent or unreadable>
RELAY_BG_AGE_SECONDS=<whole seconds, or -1 when unknown>
RELAY_BG_VERDICT=alive|stopped|stale|unknown
```

Then exactly one summary line:

```
RELAY_BG_SUMMARY=alive=<n>,stale=<n>,stopped=<n>,unknown=<n>
```

`RELAY_BG_VERDICT` takes one of exactly four values. Never print any other word there.

### Exit codes **[plan]**

- `0` — every verdict is `alive`.
- `1` — at least one verdict is `stopped`.
- `2` — usage error.
- `3` — no `stopped`, but at least one `stale` or `unknown`.

The watcher's liveness escape (D2) fires on rc `1`. A caller must not respawn on `unknown`
alone. [spec §1.5]

### What this script must never do

It never reports task success or failure. Its verdict is about presence only. [spec §1.5,
S4-2] Do not read `output`, `result`, or `detail` from the state file. A test asserts that
the script body never names `ROLE_DONE`.

## D1.4 `docs/dispatch-contract.md` — the only change

Add one short block under the frozen-token section:

> **Background-session transport.** `docs/bg-dispatch-contract.md` carries the same four
> frozen tokens over a different transport: the envelope travels in a message body or a
> handoff file instead of on stdout. The tokens are unchanged. The two tokens that document
> adds, `DECISION:` and `ESCALATION from …:`, are provisional and are not part of this
> frozen set.

Change nothing else in the file. In particular, the four numbered frozen-token entries and
the capture regex keep their exact text. (C2)

## D1.5 `tests/e2e/bg-s1-roundtrip.sh` — the live check

This cannot run in CI. It launches real sessions. [spec §Tests] It is run by hand before
each engine's work is called done, and the result is recorded in the commit body.

The script drives the S1 round trip:

1. Build a name per §1.2 with a fresh runid.
2. Write a prompt file: identity preamble, plus an instruction that makes the child ask one
   question with `NEEDS_DECISION:` and then wait.
3. Launch through `bg-launch.sh`. Assert `RELAY_BG_LAUNCH=OK`.
4. Wait for the `NEEDS_DECISION:` line.
5. Reply with `DECISION: <answer>` by name, resolving the address at send time.
6. Assert the child finishes with `ROLE_DONE` and the value the answer chose.
7. Send the finish-and-stop instruction. Confirm `stopped` through `bg-liveness.sh`.
8. Print `BG_S1_ROUNDTRIP=PASS` or `BG_S1_ROUNDTRIP=FAIL <step>`.

Guard it behind `RELAY_RUN_LIVE_BG=1`, in the same way `test_flows.py` guards its live
smoke. Without the variable, print `BG_S1_ROUNDTRIP=SKIPPED` and exit `0`.

Document the procedure and the variable in `docs/bg-dispatch-contract.md`.

## D1.6 Fixtures

`tests/fixtures/bg-state/` holds one small state file per case. Copy the real shape: the
live files carry `state`, `detail`, `tempo`, `intent`, `name`, `createdAt`, `updatedAt` and
much more. The fixtures need only the fields the scripts read, plus one extra field so a
test proves the scripts ignore what they do not need.

| Fixture | Content |
|---|---|
| `working.json` | `state: working`, non-empty `intent` |
| `blocked.json` | `state: blocked`, non-empty `intent` |
| `done.json` | `state: done`, non-empty `intent` |
| `stopped.json` | `state: stopped` |
| `failed.json` | `state: failed` |
| `empty-intent.json` | `state: working`, `intent: ""` — the failed-launch shape from launch trap 1 |
| `malformed.json` | not valid JSON |

`updatedAt` staleness is relative to now, so the fixtures carry a placeholder and each test
rewrites `updatedAt` into a copy under `tmp_path` before it runs the script. Never ship a
fixture with a fixed timestamp that a test compares against the real clock.

## D1.7 Tests

All under `tests/unit/skill-structure/`. Load `conftest.py` with
`importlib.util.spec_from_file_location`, in the same way `test_ensuring_worktree_isolation.py`
does, so collection works from any directory. [repo]

### Test 1 — `test_bg_launch.py`

Drive the real script with `subprocess.run`, `HOME` pointed at `tmp_path`, and a stub
`claude` executable first on `PATH`. The stub writes its own `"$@"` to a file, so the tests
can assert the exact argument vector.

| Test | Asserts |
|---|---|
| `test_script_exists_and_is_executable` | file present, `os.access(..., X_OK)` |
| `test_header_declares_executed_and_gives_an_example` | header block holds `EXECUTED` and a `bash scripts/bg-launch.sh --name` example |
| `test_missing_required_flag_exits_2` | parametrized over the four required flags; rc `2`; stderr starts `[relay] error: ` |
| `test_unknown_flag_exits_2` | rc `2` |
| `test_unreadable_prompt_file_exits_2` | rc `2` |
| `test_dontask_permission_mode_is_refused` | rc `2`; stderr names S3-1 |
| `test_prompt_is_the_last_argument` | the stub's last argv element equals the prompt file's content |
| `test_no_variadic_flag_precedes_the_prompt` | `--allowedTools` never appears in argv, and the script body never names it |
| `test_fork_from_adds_resume_and_fork_session` | argv holds `--resume <id>` and `--fork-session`, and the prompt is still last |
| `test_launch_ok_prints_three_lines_in_order` | stdout is exactly `RELAY_BG_NAME=`, `RELAY_BG_SHORT_ID=`, `RELAY_BG_LAUNCH=OK` |
| `test_every_stdout_line_is_key_value` | every stdout line matches `^[A-Z][A-Z0-9_]*=.*$` |
| `test_unparseable_short_id_is_launch_denied` | stub prints no short id; rc `1`; stdout is exactly `RELAY_BG_LAUNCH=LAUNCH_DENIED`; no `OK` anywhere |
| `test_classifier_refusal_is_launch_denied` | stub prints `Blocked by classifier` and exits non-zero; rc `1` |
| `test_empty_intent_at_ceiling_is_launch_denied` | `empty-intent.json`, `RELAY_BG_LAUNCH_TIMEOUT_SECONDS=1`; rc `1`; returns in under 5 seconds |
| `test_absent_state_file_is_not_an_immediate_failure` | the file appears after about one second; rc `0` |
| `test_never_resolves_the_short_id_by_name` | two job directories share the `name` field; only the launched short id has a non-empty `intent`; the wrong one must not satisfy the check (S4-3) |
| `test_reason_goes_to_stderr_not_stdout` | on failure, stdout holds no `[relay]` text |

### Test 2 — `test_bg_liveness.py`

Same driving style: `HOME` at `tmp_path`, fixtures copied into
`$HOME/.claude/jobs/<short-id>/state.json`.

| Test | Asserts |
|---|---|
| `test_script_exists_and_is_executable` | file present and executable |
| `test_state_maps_to_verdict` | parametrized over all six rows of the §1.5 table |
| `test_done_is_alive_not_stopped` | its own named test — this is the row a reader will "fix" |
| `test_stale_downgrades_only_alive_states` | `updatedAt` older than the ceiling turns `working`/`blocked`/`done` into `stale` |
| `test_stopped_is_never_reclassified_by_age` | an old `stopped` still reads `stopped` |
| `test_unknown_is_never_reclassified_by_age` | an absent file still reads `unknown` |
| `test_default_stale_seconds_is_900` | with no variable set, a child 800 seconds old is `alive` and one 1000 seconds old is `stale` |
| `test_stale_seconds_flag_overrides_the_env_var` | flag wins |
| `test_updated_at_with_milliseconds_parses` | `…T12:00:00.123Z` gives a real age, not `-1` |
| `test_malformed_state_file_is_unknown` | `malformed.json` gives `unknown`, and the script does not crash |
| `test_multiple_children_print_one_block_each_in_order` | three ids, three blocks, input order kept |
| `test_summary_line_counts_every_child` | the four counts add up to the number of ids |
| `test_exit_codes` | parametrized: all alive → `0`; any stopped → `1`; usage error → `2`; stale or unknown with no stopped → `3` |
| `test_verdict_vocabulary_is_closed` | every printed `RELAY_BG_VERDICT=` value is one of the four |
| `test_script_never_reads_task_outcome` | the script body does not hold `ROLE_DONE`, `.output`, or `.result` (S4-2) |

### Test 3 — `test_bg_naming_grammar.py`

Drives `bash scripts/bg-launch.sh --check-name <name>`. It starts no child.

| Test | Asserts |
|---|---|
| `test_accepts_the_spec_example` | `roi-dashboard-implementer-feature-a-7f3c` → rc `0` |
| `test_accepts_the_orchestrator_shape` | `product-role-runid`, with a roster role at position 2 |
| `test_rejects_a_name_with_no_runid_suffix` | rc `2` |
| `test_rejects_a_runid_that_is_too_short_or_too_long` | 3 characters and 9 characters both rc `2` |
| `test_rejects_uppercase_and_underscore` | rc `2` for each |
| `test_accepts_63_characters_and_rejects_64` | the boundary, both directions |
| `test_rejects_a_role_token_that_is_not_on_the_roster` | `roi-dashboard-wizard-feature-a-7f3c` → rc `2` |
| `test_roster_source_is_not_empty` | the roles the validator reads number more than ten — a vacuous roster would accept everything |
| `test_validator_never_parses_product_or_goal` | a product slug that itself holds a role word, for example `implementer-tools-scout-feature-a-7f3c`, is still accepted; the check is a roster hit at a fixed position, not a parse |

### Test 4 — `test_provisional_tokens.py`

This file exists to keep the provisional pair **out** of the frozen set. It never imports
`test_envelope_tokens.py`; it reads it as text and parses the list literal.

| Test | Asserts |
|---|---|
| `test_contract_documents_both_provisional_tokens` | `docs/bg-dispatch-contract.md` holds `DECISION: ` and `ESCALATION from ` |
| `test_contract_marks_them_provisional` | the word `provisional` appears in the same section |
| `test_frozen_list_is_exactly_the_four` | parse `FROZEN_TOKENS` out of `test_envelope_tokens.py`; assert it equals the four current values, as a list |
| `test_provisional_tokens_are_not_in_the_frozen_list` | `"DECISION:"` and `"ESCALATION from"` are not **members** of the parsed list. Membership, not substring — `"DECISION:"` is a substring of `"NEEDS_DECISION:"` |
| `test_envelope_tokens_file_never_names_escalation` | `ESCALATION` does not appear anywhere in `test_envelope_tokens.py` |
| `test_decision_is_the_downward_reply` | the contract says `DECISION:` answers a `NEEDS_DECISION:` |
| `test_escalation_is_distinct_from_blocked` | the contract states why: a relay must not read as the operator being stuck |

### Test 5 — `test_bg_dispatch_contract.py`

Doc guard for `docs/bg-dispatch-contract.md`.

| Test | Asserts |
|---|---|
| `test_doc_exists_and_is_substantial` | present, longer than 2000 characters |
| `test_holds_the_four_frozen_tokens_verbatim` | all four, byte for byte |
| `test_adds_no_token_to_the_frozen_set` | the doc says the frozen set is unchanged |
| `test_naming_grammar_block_present` | `<product>-<role>-<goal>-<runid>` |
| `test_runid_is_mandatory_and_says_why` | S4-3 is cited |
| `test_permission_mode_mapping_rows` | `approve-all` → `bypassPermissions`; `approve-reads` → `plan`; no key → `plan` |
| `test_dontask_is_named_forbidden` | `dontAsk` and S3-1 both appear |
| `test_state_verdict_table_rows` | parametrized over all six rows |
| `test_state_file_is_not_a_success_oracle` | the sentence is present, citing S4-2 |
| `test_stale_default_is_900` | `RELAY_BG_STALE_SECONDS` and `900` |
| `test_identity_preamble_five_lines` | all five lines, and the bg-sessions substitution |
| `test_fork_lines_are_marked_reserved` | the three fork lines are present and marked unused in v1 |
| `test_single_stop_mechanism_stated_once` | send by name, then confirm `stopped` through `bg-liveness.sh` |
| `test_both_scripts_named_and_present` | both paths appear in the doc and exist on disk |
| `test_every_backticked_repo_path_exists` | the same guard shape `test_docs_freshness.py` applies to the narrative docs |
| `test_live_validation_section_present` | names `tests/e2e/bg-s1-roundtrip.sh` and `RELAY_RUN_LIVE_BG` |

## D1.8 Order of work

1. Write `docs/bg-dispatch-contract.md` first. It is the contract, and both scripts are
   written against it.
2. Write the fixtures.
3. Write `test_bg_launch.py` and `test_bg_naming_grammar.py`. Watch them fail.
4. Write `scripts/bg-launch.sh` until they pass.
5. Write `test_bg_liveness.py`. Watch it fail.
6. Write `scripts/bg-liveness.sh` until it passes.
7. Write `test_provisional_tokens.py` and `test_bg_dispatch_contract.py`. Fix the doc, not
   the tests.
8. Add the cross-reference block to `docs/dispatch-contract.md`.
9. Write `tests/e2e/bg-s1-roundtrip.sh`. Run it live once, with `RELAY_RUN_LIVE_BG=1`.
   Record the result.
10. Run the full gate.

## D1.9 Done criteria

- The full gate passes.
- `git diff --stat` shows no change to `test_envelope_tokens.py`, `bindings/presets.yaml`,
  or `scripts/record-run-intent.sh`.
- `bash tests/e2e/bg-s1-roundtrip.sh` printed `BG_S1_ROUNDTRIP=PASS` in a live run, and the
  commit body records the date and the run.

---

# Deliverable 2 — `--engine bg-sessions`

Per-leaf dispatch. The one-Workflow doctrine is untouched. This engine changes only what a
delegated leaf runs. [spec §Deliverable 2]

## D2.0 First task — resolve the unverified property (C5)

Before any other work in D2, answer this: **can a Workflow watcher node send a message to a
named session?** The spikes proved session-to-session messaging from top-level sessions
only. [spec §Deliverable 2, Multi-turn]

How to check: build a throwaway Workflow with one agent node. Launch a background child by
name. From inside the node, send the child a message by name and confirm the child's next
turn starts.

- **Pass** — build multi-turn as specified below.
- **Fail** — v1 restricts `bg-sessions` to roles with `one_shot: true`. Multi-turn roles
  keep the acpx leg. The dispatcher then refuses a non-one-shot role with a typed error, and
  the `## Multi-turn` section of the new skill states the restriction and its reason.

Record the answer in the commit body. The rest of D2 depends on it.

## D2.1 Files

Create:

- `skills/dispatching-bg-agents/SKILL.md`
- `skills/dispatching-bg-agents/preamble.md` — the identity preamble of §1.4, the
  bg-sessions variant. **[plan]** A separate file, in the same way
  `skills/dispatching-acpx-agents/preamble.md` holds the acpx preamble.
- `skills/dispatching-bg-agents/bg-dispatch.sh` — the dispatcher entry point. **[plan]**
- `tests/unit/skill-structure/test_dispatching_bg_skill.py`
- `tests/unit/skill-structure/test_bg_dispatch_env.py`
- `tests/unit/skill-structure/test_bg_command_wiring.py`

Modify:

- `scripts/parse-engine-agent.sh` — the `bg-sessions` enum value and invariant.
- `tests/unit/skill-structure/test_parse_engine_agent.sh` — new cases.
- `skills/delegate-and-watch/SKILL.md` — the bg leg.
- `tests/unit/skill-structure/test_delegate_and_watch.py` — new cases.
- `commands/implement.md`, `commands/refine.md`, `commands/execute.md`, `commands/drive.md`
  — wiring note, `argument-hint`, Step 0.25 option.
- `scripts/validate_l3_command.py` — `_KNOWN` gains `dispatching-bg-agents`.
- `docs/architecture.md`, `README.md` — the new engine value (C4).
- `tests/unit/skill-structure/test_plugin.py` — `EXPECTED_SKILLS` gains
  `dispatching-bg-agents` (C4).
- `docs/contributing.md` — the skill count on line 140 (C4).

Do not touch: `bindings/presets.yaml` [spec], `test_envelope_tokens.py` [C2].

## D2.2 `scripts/parse-engine-agent.sh`

Four edits, and no more.

1. **Step 3, engine enum.** `in-session|acpx|smart-routing` becomes
   `in-session|acpx|smart-routing|bg-sessions`.
2. **Step 3, the enum error string.** It hard-codes the allowed list. It becomes
   `(expected: in-session | acpx | smart-routing | bg-sessions)`.
3. **Step 4, a new invariant**, placed directly after the `in-session` block and shaped the
   same way:

   ```bash
   # bg-sessions requires agent=claude (no codex leg) — spec §Deliverable 2, Axis
   if [ "$_relay_engine" = "bg-sessions" ] && [ "$_relay_agent" != "claude" ]; then
     echo "[relay] error: engine=bg-sessions requires agent=claude (got '$_relay_agent')" >&2
     _re_pin_hints "acpx" "claude"
     return 1
   fi
   ```
4. Nothing in Step 2. `bg-sessions` falls through the default-agent `case` to
   `*) _relay_agent="claude"`, which is the wanted default. Do not add a `case` arm. [spec:
   "the same shape as `in-session ⇒ claude`"]

Everything else in that script stays as it is: the source tracking, the `relay.json` read,
the extras rejection, the exports.

## D2.3 `skills/dispatching-bg-agents/`

Mirror `skills/dispatching-acpx-agents/` one to one in shape. Swap the acpx driver and
session mechanics for `bg-launch.sh` plus handoff-file completion. [spec §Deliverable 2]

### Frontmatter [repo convention]

```yaml
---
name: dispatching-bg-agents
description: <one dense paragraph naming the mechanism, what it resolves from where, and how it differs from its sibling — it must say it is the background-session counterpart of dispatching-acpx-agents>
user-invocable: false
---
```

### Body sections, in this order

1. `## Overview` — names the spec section it implements and its wrapper-contract
   counterpart. Points at `docs/bg-dispatch-contract.md` for the shared layer, in the same
   way the acpx skill points at `docs/dispatch-contract.md`.
2. `## Wrapper contract (per spec §5.1)` — the fenced block, verbatim:

   ```
   dispatch(role_slug, binding, inputs) →
     {
       status: "completed" | "verification_failed" | "timeout" | "engine_error",
       output: <captured envelope>,
       tokens: { <token-name>: <captured-value> },
       sidecars: { <sidecar-name>: <absolute-path> },
       elapsed_seconds: <float>,
       attempt_count: <int>,
     }
   ```
3. `## Wrapper responsibilities (per spec §5.2)` — the same six numbered steps as the acpx
   skill, with bold lead terms. The bg deltas:
   - **Resolve bindings.** Same `bindings/presets.yaml`, same `delegate_eligible` flag. The
     worker model comes from `modalities.claude`. No new binding field. [spec]
   - **Validate capabilities.** Unchanged. Same gate, same `capability-validate.js`.
   - **Materialize the role body.** Same `RELAY_ROLE_PATH` → `roles/<slug>.md` →
     `agents/<slug>.md` order and the same `ROLE_FILE_MISSING` typed error.
   - **Wrap with scaffolding.** Prepend `preamble.md` — the §1.4 identity preamble — then
     the role body. The bg-sessions preamble replaces the "send to your parent" line with
     *write your envelope to `<handoff-file>` — you have no parent to message*. Add the
     `TURN=<n>` echo instruction.
   - **Resolve the modality, then launch.** `modalities.claude` gives the model. The
     binding's `permissions` maps to `--permission-mode` through the §1.3 table. Launch
     through `scripts/bg-launch.sh`, in the run's worktree — children inherit the launcher's
     cwd.
   - **Capture and verify.** Read the envelope from the handoff file, not from stdout. Apply
     the same capture regex to the file's content.
4. `## Naming` — the name is built per §1.2. `product` is the worktree directory name,
   kebab-cased. `role` is the role slug. `goal` is omitted for bg-sessions. `runid` is the
   Workflow's `run_id`, lowercased, with the `wf_` prefix and every character outside
   `[a-z0-9]` removed, then the last 4 to 8 characters. **One rule, one source.** [spec §1.2]
5. `## Sidecar contract` — the counterpart of the acpx `${session}.env`. The dispatcher
   writes `~/.claude/relay/bg/${runid}/${role_slug}.env` **before** launch, holding exactly
   these six lines: [spec §Deliverable 2, Dispatch]

   ```
   RELAY_BG_NAME=<name>
   RELAY_BG_SHORT_ID=<short-id>
   RELAY_BG_HANDOFF=<handoff-file-path>
   RELAY_BG_MODEL=<model>
   RELAY_BG_PERMISSION_MODE=<mode>
   RELAY_BG_MAX_TURNS=<n>
   ```

   `RELAY_BG_SHORT_ID` is filled in after `bg-launch.sh` returns it. State plainly that the
   file is written before launch and completed after, so a reader knows why the value is
   two-phase.
6. `## Handoff file contract` — [spec §Deliverable 2, Completion]
   - Path: `$WORKTREE/.relay-bg/<runid>/<role_slug>.envelope`.
   - The dispatcher creates the directory before launch. The child is the only writer of the
     file.
   - Each turn the child **truncates** the file and writes exactly one fresh envelope. Never
     append. Never leave a previous turn's content in place.
   - The launch prompt and every follow-up prompt supplies a `TURN=<n>` line. The child
     echoes it as the first `KEY=VALUE` line of its envelope, directly under the sentinel or
     under `ROLE_DONE`.
   - The watcher discards any envelope whose `TURN=` does not match the turn it just sent,
     and treats the file as not yet updated.
7. `## Raw envelope → bucket` — the five-row table, verbatim from the spec:

   | First non-empty line of the handoff file | Bucket |
   |---|---|
   | `ROLE_DONE` (with matching `TURN=`) | done |
   | `BLOCKED: <reason>` (with matching `TURN=`) | blocked |
   | `NEEDS_DECISION: <question>` (with matching `TURN=`) | needs-decision |
   | File empty, absent, or `TURN=` stale or missing | not-done (poll continues) |
   | Liveness escape fires (`bg-liveness.sh` reports `stopped`) before any of the above | errored |

   State that no bg child ever emits `ROLE_RESULT=`, and that the driver's grep target
   `^(ROLE_RESULT=|ROLE_DONE$)` reads the handoff file's content, not stdout.
8. `## Lifecycle` — [spec §Deliverable 2, Exit buckets]
   - On `done` or `errored`: the watcher sends the child a finish-and-stop instruction by
     name, then confirms `stopped` through `bg-liveness.sh` before the node ends.
   - On `needs-decision`: the child is left alive. Its name is recorded in the run's
     bookkeeping so a later invocation, or a person, can resume it by message.
   - On watcher crash: no stop instruction is sent. The orphan is caught by a sweep. **[plan]**
     The sweep for bg-sessions reads the sidecar directories under `~/.claude/relay/bg/*/`,
     runs `bg-liveness.sh` over every recorded short id, and stops or records every child
     still alive, before the run uses a fresh runid.
   - The stop mechanism is §1.6's, not a second one. Point at the contract; do not restate
     the mechanism.
9. `## Multi-turn` — the watcher sends the next prompt to the child by name. The address
   resolves at send time. The child never messages the watcher. If D2.0 failed, this section
   states the `one_shot: true` restriction instead, and says why.
10. `## Files` — one clause per file in the skill directory.
11. `## See also` — spec sections, `docs/bg-dispatch-contract.md`,
    `skills/dispatching-acpx-agents/`, `skills/delegate-and-watch/`.

**No `relay-vocab` block.** `dispatching-acpx-agents` has none, and only L2 pattern skills
carry one. A vocab block would force membership of `L2_NAMES` and break
`test_l2_skills_present.py`. [repo]

### `bg-dispatch.sh` **[plan]**

The entry point, in the shape of `acpx-dispatch.sh` but far smaller. EXECUTED. It:

1. reads the binding for `role_slug` from `bindings/presets.yaml` with `yq`;
2. maps `permissions` to `--permission-mode` through the §1.3 table;
3. builds the name per §1.2 and validates it with `bg-launch.sh --check-name`;
4. creates `$WORKTREE/.relay-bg/<runid>/` and `~/.claude/relay/bg/<runid>/`;
5. materializes the prompt: preamble, role body, `{{SLOT}}` substitution, `TURN=1`;
6. writes the sidecar;
7. launches through `bg-launch.sh`, appends `RELAY_BG_SHORT_ID` to the sidecar;
8. prints the sidecar path and the launch outcome as `KEY=VALUE` lines;
9. exits `0` on a launched child, `1` on `LAUNCH_DENIED` after one retry [spec §Failure
   behavior], `2` on a usage error.

The one retry on `LAUNCH_DENIED` is the spec's, not an invention: "LAUNCH_DENIED, one retry,
then errored". [spec §Failure behavior]

**Note (advisory, not blocking).** This section names `bg-dispatch.sh`'s inputs in prose
(`role_slug`, `binding`, `inputs`, `WORKTREE`, `runid`) but does not pin the exact calling
interface — no flags/env-var table, unlike D1.2, D1.3, and D3.4. Before writing
`test_bg_dispatch_env.py` (D2.7), the implementer should fix the concrete interface, using
`acpx-dispatch.sh`'s env-var pattern (`ACPX_ROLE_SLUG`, `ACPX_BINDING_PRESET`,
`ACPX_INPUTS_JSON`, `ACPX_RUN_ID`, `WORKTREE`, `DRIVER_OVERRIDE`) as the analogy, and name
the chosen variables directly in that test rather than inventing hooks ad hoc.

## D2.4 `skills/delegate-and-watch/SKILL.md`

The watcher keeps its bounded foreground poll and its five buckets. Two substitutions, and a
new first step. [spec §Deliverable 2, Completion]

Add a section, `## The bg-sessions leg`:

- **Step 1 substitution.** When `$RELAY_ENGINE` is `bg-sessions`, source
  `~/.claude/relay/bg/${runid}/${role_slug}.env` instead of the acpx
  `~/.acpx/sessions/${session}.env`. Branch the poll target on which sidecar was found.
- **Poll target substitution.** Grep `$RELAY_BG_HANDOFF` instead of the acpx turn log.
- **Liveness escape substitution.** The escape is `bg-liveness.sh --short-id
  "$RELAY_BG_SHORT_ID"` reporting `stopped` (exit `1`), instead of the bracketed `pgrep`.
  Show the bg wait primitive in full, in the same shape as the acpx one:

  ```bash
  timeout "${WATCH_BUDGET:-580}" bash -c '
    until grep -qE "^(ROLE_RESULT=|ROLE_DONE$)" "'"$RELAY_BG_HANDOFF"'" 2>/dev/null \
       || bash "'"$CLAUDE_PLUGIN_ROOT"'/scripts/bg-liveness.sh" --short-id "'"$RELAY_BG_SHORT_ID"'" >/dev/null 2>&1; [ $? -eq 1 ]; do
      sleep 10
    done'
  ```

  Write it so the escape fires on rc `1` only. rc `3` (`stale` or `unknown`) must not fire
  the escape — a caller must not treat `unknown` as gone. [spec §1.5]
- **TURN discipline.** The watcher discards an envelope whose `TURN=` does not match the
  turn it just sent, and keeps polling.
- **Stop on a terminal bucket.** `done` and `errored` end with the stop instruction and a
  `stopped` confirmation. `needs-decision` leaves the child alive and records its name.

**What must not change in this file:**

- The `## TURN-LIFETIME RULE` section, word for word. `test_delegate_and_watch.py` pins
  "Turn end IS termination", "park is not available to an agent node", and "monitor is not a
  wait mechanism".
- The bracketed `[a]cpx-dispatch.sh` pattern and the paragraph that explains it.
  `test_liveness_probe_cannot_match_itself` asserts that the plain form
  `pgrep -f acpx-dispatch.sh` never appears. Do not "tidy" it.
- `PARKED=0` / `PARKED=1`, the conditional trap, and the `detach`-not-`close` rule.
- The five-bucket table and the `relay-vocab` block, including `acpx-leg-required: true`.

## D2.5 Command wiring — all four commands

Without this edit `--engine bg-sessions` parses and then falls through to the in-session
path. That is a silent, unreported no-op. [spec §Deliverable 2, Dispatch]

For each of `implement.md`, `refine.md`, `execute.md`, `drive.md`:

1. **`argument-hint`** — `[--engine in-session|acpx|smart-routing]` becomes
   `[--engine in-session|acpx|smart-routing|bg-sessions]`.
2. **Delegation wiring note** — the arm that today reads "When `$RELAY_ENGINE` resolves to
   `acpx` or `smart-routing` …" gains a third arm for `bg-sessions`: it substitutes
   `relay:delegate-and-watch` in the same way, and the watcher's leg is
   `relay:dispatching-bg-agents` rather than the acpx driver.
3. **Step 0.25** — add a third option. Keep the first two exactly as they are (C4.6):
   - **Option 3:** label `bg-sessions (claude)` — description: delegation-eligible leaves
     run as background Claude sessions. No acpx and no codex CLI needed. The session's
     context is preserved. Every worker bills to the Claude plan. Tip: pin
     `{"engine": "bg-sessions"}` in `.claude/relay.json` to skip this question permanently.
   - Add a matching re-resolution block:
     `source "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh" "bg-sessions" "claude" || exit 1`
     followed by the same `(source: prompt)` echo line.
4. **Step 0 prose** — the paragraph that lists the defaults and invariants gains
   `bg-sessions⇒claude`.

Then add `dispatching-bg-agents` to `_KNOWN` in `scripts/validate_l3_command.py`, with a
comment in the style of the existing entries. Without it, every L3 command body that names
the skill fails the vocabulary gate. (C4.4)

## D2.6 Docs that the parser change forces (C4)

- `docs/architecture.md` — the engine bullet becomes
  `` **`engine`** ∈ `in-session` · `acpx` · `smart-routing` · `bg-sessions` ``, and the
  invariants sentence gains `bg-sessions` requires `agent=claude`.
- `README.md` — the argument table row for `--engine` gains `` `bg-sessions` ``, and the
  invariants paragraph gains the new one.
- `docs/contributing.md` line 140 — `` `EXPECTED_SKILLS` (15) `` becomes `(16)`.
- `tests/unit/skill-structure/test_plugin.py` — add `"dispatching-bg-agents"` to
  `EXPECTED_SKILLS`, with a trailing comment in the existing style.

## D2.7 Tests

### `test_parse_engine_agent.sh` — extend the bash suite

Add cases in the existing `_check` / `_check_err` style. Do not restructure the file.

| Case | Expects |
|---|---|
| `bg-sessions` with no agent | rc `0`, `bg-sessions/claude`, source `flags` |
| `bg-sessions claude` | rc `0`, `bg-sessions/claude` |
| `bg-sessions codex` | rc `1`, stderr holds `engine=bg-sessions requires agent=claude` |
| `bg-sessions hybrid` | rc `1` |
| `BG-SESSIONS` | rc `0` — the value is lowercased first |
| relay.json pin `{"engine":"bg-sessions"}` | rc `0`, `bg-sessions/claude`, source `relay.json` |
| pin `{"engine":"bg-sessions","agent":"codex"}` | rc `1`, and both pin hint lines print |
| an invalid engine value | stderr names `bg-sessions` in the expected list |
| `bg-sessions claude extra` | rc `1`, `too many arguments` — the extras check still bites |

### `test_dispatching_bg_skill.py`

Mirror of `test_dispatching_acpx_skill.py`.

| Test | Asserts |
|---|---|
| `test_skill_file_exists` | `skills/dispatching-bg-agents/SKILL.md` present |
| `test_frontmatter_name_matches_dir` | `name == "dispatching-bg-agents"` |
| `test_user_invocable_false` | internal skill |
| `test_description_names_its_sibling` | the description names `dispatching-acpx-agents` |
| `test_wrapper_contract_block_present` | `dispatch(role_slug, binding, inputs) →` |
| `test_six_responsibilities_numbered` | all six lead terms appear |
| `test_launcher_is_bg_launch_sh` | `bg-launch.sh` is named as the only launcher |
| `test_sidecar_path_and_all_six_keys` | the path, and each of the six `RELAY_BG_*` keys |
| `test_handoff_path_documented` | `$WORKTREE/.relay-bg/` and `.envelope` |
| `test_truncate_not_append_rule` | the words `truncate` and `never append` |
| `test_turn_marker_rule` | `TURN=` and the discard rule |
| `test_bucket_table_five_rows` | parametrized over the five rows |
| `test_no_role_result_from_a_bg_child` | the skill states it |
| `test_stop_lifecycle_documented` | stop on done and errored; alive on needs-decision |
| `test_stop_mechanism_defers_to_the_contract` | §1.6 or `bg-dispatch-contract.md` is cited, and the skill does not restate a second mechanism |
| `test_preamble_replaces_the_parent_line` | the "write your envelope to" line |
| `test_names_no_acpx_env_var` | no `ACPX_` string leaks into the bg skill |
| `test_files_section_matches_the_directory` | the set of files listed equals the set on disk |
| `test_no_relay_vocab_block` | the skill carries none |
| `test_bindings_are_unchanged_in_v1` | the skill states that `presets.yaml` gains no field |

### `test_bg_dispatch_env.py`

Behavioral tests for `bg-dispatch.sh`, in the style of `test_acpx_dispatch_env.py`, with
`HOME` and `WORKTREE` pointed at `tmp_path` and a stub `bg-launch.sh` on `PATH`.

| Test | Asserts |
|---|---|
| `test_sidecar_written_before_launch` | the sidecar exists when the stub launcher runs |
| `test_sidecar_holds_exactly_six_keys` | no extra key, no missing key |
| `test_short_id_appended_after_launch` | `RELAY_BG_SHORT_ID` holds the launcher's value |
| `test_handoff_directory_created_before_launch` | the directory exists when the stub runs |
| `test_permission_mode_mapping` | parametrized: `approve-all` → `bypassPermissions`; `approve-reads` → `plan`; no key → `plan` |
| `test_runid_is_derived_from_the_workflow_run_id` | `wf_918a4deb-aba` gives a 4-to-8-character `[a-z0-9]` suffix, and the same input always gives the same suffix |
| `test_name_is_validated_before_launch` | a bad role slug stops the dispatch before any launch |
| `test_launch_denied_retries_once_then_fails` | the stub denies twice; the launcher is called exactly twice; rc `1` |
| `test_launch_denied_once_then_succeeds` | the stub denies once; rc `0` |
| `test_prompt_holds_the_preamble_then_the_role_body` | order, and `TURN=1` present |

Skip the whole module with a clear reason when `yq` is missing, in the same way the acpx
tests do — but never skip silently. [repo]

### `test_delegate_and_watch.py` — extend

| Test | Asserts |
|---|---|
| `test_bg_leg_section_present` | a `bg-sessions` section exists |
| `test_bg_leg_sources_the_bg_sidecar` | `~/.claude/relay/bg/` is named |
| `test_bg_leg_polls_the_handoff_file` | `RELAY_BG_HANDOFF` is the poll target |
| `test_bg_liveness_is_the_escape` | `bg-liveness.sh` is named, and `stopped` is the trigger |
| `test_bg_escape_fires_on_rc_1_only` | the prose says rc `3` does not fire it |
| `test_acpx_bracketed_pgrep_unchanged` | the existing guard still holds — regression check |
| `test_turn_lifetime_rule_unchanged` | the four pinned sentences are still present |

### `test_bg_command_wiring.py`

Parametrized over the four commands.

| Test | Asserts |
|---|---|
| `test_argument_hint_lists_bg_sessions` | `bg-sessions` in `argument-hint` |
| `test_wiring_note_has_a_bg_arm` | the note names `bg-sessions` |
| `test_step_025_offers_bg_sessions` | the third option label is present |
| `test_step_025_keeps_the_first_two_options` | `in-session (default)` and `acpx (hybrid)` are still there |
| `test_bg_re_resolution_block_present` | the `parse-engine-agent.sh "bg-sessions" "claude"` line |
| `test_validate_l3_knows_the_new_skill` | `dispatching-bg-agents` is in `_KNOWN` |

## D2.8 Order of work

1. Run the D2.0 check. Write the answer down.
2. Edit `parse-engine-agent.sh`; extend `test_parse_engine_agent.sh`; run that bash suite.
3. Edit `docs/architecture.md`, `README.md` at once — the parser change turns
   `test_docs_freshness.py` red until you do. (C4)
4. Write `skills/dispatching-bg-agents/` and its tests.
5. Add the skill to `EXPECTED_SKILLS` and update the count in `docs/contributing.md`. (C4)
6. Write `bg-dispatch.sh` and `test_bg_dispatch_env.py`.
7. Edit `skills/delegate-and-watch/SKILL.md` and extend its test.
8. Edit the four command bodies and `validate_l3_command.py`; write
   `test_bg_command_wiring.py`.
9. Run the full gate.
10. Re-run `tests/e2e/bg-s1-roundtrip.sh` live. Record the run.

## D2.9 Done criteria

- The full gate passes.
- `git diff` shows no change to `bindings/presets.yaml` or `test_envelope_tokens.py`.
- `/relay:implement --engine bg-sessions <task>` resolves the axis, and the printed axis
  line reads `engine=bg-sessions agent=claude`.
- The D2.0 answer is recorded, and the skill's `## Multi-turn` section matches it.

---

# Deliverable 3 — `--engine session-tree`

A new substrate. The command generates no Workflow. MAIN is the orchestrator. [spec
§Deliverable 3]

## D3.0 First task — resolve the unverified property (C5)

Before any other work in D3, answer this: **does an inbound message re-invoke an idle MAIN
session that sits mid-slash-command, and does the re-invoked turn still hold the command's
run state?** S1 proved free waiting for a background child, never for MAIN. [spec
§Deliverable 3, Waiting]

How to check: start a slash command in a foreground session that ends its turn while it
waits. Send it an envelope from another session. Confirm two things, not one:

1. the turn restarts;
2. the restarted turn still holds the manifest path, the runid, and the spawned children's
   names.

- **Pass** — build free waiting as specified. The orchestrator also arms a long fallback
  heartbeat that runs `bg-liveness.sh` across the manifest. The heartbeat catches silence.
  It never polls for results.
- **Fail** — the orchestrator holds a bounded poll over the manifest instead, in the same
  shape as the `delegate-and-watch` watcher. Free waiting is deferred. The skill states the
  fallback and its reason.

This property is load-bearing for the whole substrate. Record the answer in the commit body
and in the CHANGELOG.

## D3.1 Files

Create:

- `skills/orchestrating-session-trees/SKILL.md`
- `scripts/bg-manifest.sh` **[plan]** — see D3.4
- `tests/unit/skill-structure/test_orchestrating_session_trees.py`
- `tests/unit/skill-structure/test_bg_manifest.py`
- `tests/unit/skill-structure/test_session_tree_substrate.py`

Modify:

- `scripts/parse-engine-agent.sh` — the `session-tree` enum value and invariant.
- `tests/unit/skill-structure/test_parse_engine_agent.sh` — new cases.
- `docs/orchestration-substrates.md` — the second documented exception.
- `commands/implement.md` — the Step 1 branch (terminal for `session-tree`) and
  `argument-hint`. See D3.7 — the branch must also stop the command from reaching Steps
  2 through 5, which assume a `Workflow` ran.
- `commands/refine.md`, `commands/execute.md`, `commands/drive.md` — the reject guard.
- `scripts/validate_l3_command.py` — `_KNOWN` gains `orchestrating-session-trees`.
- `docs/architecture.md`, `README.md` — the new engine value (C4).
- `docs/agent-roster.md` — the topology roles (D3.2).
- `tests/unit/skill-structure/test_plugin.py` — `EXPECTED_SKILLS` gains
  `orchestrating-session-trees`.
- `docs/contributing.md` — the skill count.

Do not touch: `scripts/record-run-intent.sh`. The spec is explicit — session-tree runs no
Workflow, allocates no `wf_` id, and never calls it. The manifest is a separate artifact.
[spec §Deliverable 3, Bookkeeping]

## D3.2 `docs/agent-roster.md` — the topology roles

The naming validator (D1.2.5) reads its roster from this file plus `roles/*.md`. The
session-tree topology uses `orchestrator` and `operator`, and neither is a role file. Add a
section:

```markdown
## Session-tree topology roles

These name a session's place in a session tree. They are not dispatchable roles and they
have no file under `roles/`. They are part of the closed roster the §1.2 naming grammar
validates against.

| role | meaning |
|---|---|
| `orchestrator` | MAIN. Spawns every session. Owns the user channel. |
| `operator` | Coordinates one goal's subtree. Never spawns. |
| `worker` | A leaf under an operator. |
```

**Do not change the sentence `7 agents total`.** `test_docs_freshness.py` compares that
number against `agents/*.md`, and this section adds no agent file. (C4)

## D3.3 `scripts/parse-engine-agent.sh`

The same four-edit shape as D2.2:

1. Engine enum becomes `in-session|acpx|smart-routing|bg-sessions|session-tree`.
2. The enum error string becomes
   `(expected: in-session | acpx | smart-routing | bg-sessions | session-tree)`.
3. A new invariant, after the `bg-sessions` block and shaped the same way:
   `session-tree` requires `agent=claude`; the error reads
   `[relay] error: engine=session-tree requires agent=claude (got '<agent>')`; hints call
   `_re_pin_hints "acpx" "claude"`.
4. No new `case` arm in Step 2. `session-tree` falls through to `*) _relay_agent="claude"`.

`session-tree` is an **engine-axis value**, not a substrate flag. The spec's Refinement
Status resolves an earlier disagreement in favour of this. [spec §Deliverable 3, Doctrine]

## D3.4 `scripts/bg-manifest.sh` **[plan]**

The spec states the manifest's path, its content, its atomic rewrite, and that a write
failure is FATAL. Prose alone cannot be tested for atomicity, so this plan gives the
manifest a script. If the implementer chooses prose only, the manifest tests become doc
guards and the atomicity claim goes untested. Prefer the script.

**Mode: EXECUTED.** Header block in the same shape as the other two. Helper prefix `_bgm_`.

Path: `${HOME}/.claude/relay/runs/<runid>/manifest.json`. One file per run. [spec]

Subcommands:

| Invocation | Effect |
|---|---|
| `--runid <id> init --command <name>` | Creates the file. Holds `runid`, `command`, `started_at`, and an empty `sessions` array. |
| `--runid <id> add-session --name <n> --launch-id <short-id> --role <slug> --parent <name\|MAIN> --phase <status>` | Appends one session record. |
| `--runid <id> set-phase --name <n> --phase <status>` | Updates one record's phase. |
| `--runid <id> read` | Prints the JSON to stdout. |
| `--runid <id> names` | Prints `RELAY_BG_NAME=<n>` and `RELAY_BG_SHORT_ID=<id>` line pairs, for the sweep and the heartbeat. |

Rules:

- `<runid>` must match `^[a-z0-9]{4,8}$`, or exit `2`.
- Every write goes to a temporary path in the same directory, then `mv` into place. The
  reader never sees a half-written file. [spec: "rewrites the whole file atomically"]
- The file always holds current state. It is never a log of past events. [spec]
- **A write failure is FATAL.** Print `[relay] error: manifest write failed: <path>` and
  exit `1`. Do not degrade and do not continue. This is the opposite of
  `record-run-intent.sh`'s advisory line, and the difference is deliberate: the manifest is
  the only resume path. [spec]

Exit codes: `0` on success; `1` on a read or write failure (FATAL); `2` on a usage error.

## D3.5 `skills/orchestrating-session-trees/SKILL.md`

Holds the orchestrator prose that has no other home. [spec §Deliverable 3, Doctrine]

Frontmatter: `name: orchestrating-session-trees`, a dense description, `user-invocable:
false`. No `relay-vocab` block, for the same reason as D2.3.

Body sections:

1. `## Overview` — this skill runs in MAIN. Under `session-tree` the command generates no
   Workflow. The §4.2.1 spine still governs what happens; only the substrate changes.
2. `## Scope` — `/relay:implement` only in v1. Refine and verify loops keep their current
   substrates. [spec §Scope v1]
3. `## Topology` — the orchestrator spawns every session, flat. Parent and child are
   logical, set by the identity preamble, not by who spawned whom (S3-1). **v1 cap: one
   operator per goal, and at most three workers under it.** Fan-out and cost are untested,
   so the cap is deliberate, and the run's report states the cap when it binds.
4. `## Bookkeeping` — the orchestrator allocates the runid at the start of the run: a fresh
   `[a-z0-9]{4,8}` string, the same shape §1.2 needs, and the same value that every session
   name's runid suffix carries. It is not read from `record-run-intent.sh`, which never
   runs here. Every spawn and every envelope rewrites the manifest through
   `scripts/bg-manifest.sh`. A manifest write failure stops the turn with an error.
5. `## Spawning` — names are built per §1.2, with the phase or feature slug as `goal`, and
   with `goal` omitted for the orchestrator itself. Every launch goes through
   `bg-launch.sh`. Operators never spawn (S3-1).
6. `## Waiting` — matches the D3.0 answer. On pass: the orchestrator ends its turn, an
   envelope re-invokes it, and a long fallback heartbeat runs `bg-liveness.sh` across the
   manifest. The heartbeat catches silence; it never polls for results. On fail: a bounded
   poll over the manifest, and a plain statement that free waiting is deferred.
7. `## Questions` — `NEEDS_DECISION` flows worker → operator → orchestrator. The operator
   answers when the run rubric covers it. If it does not, the operator relays it as
   `ESCALATION from …:`. The orchestrator answers from run context when it can. When the
   question is truly the person's: an interactive run uses `AskUserQuestion` — the
   orchestrator is the one session that owns the user channel — and a headless run escalates
   one hop further, by message to the orchestrator's own parent session.
8. `## End of run` — the orchestrator sends each child a finish-and-stop instruction,
   confirms `stopped` through liveness, and **names any child it could not stop**. Stopped
   sessions keep their names; the next run's fresh runid prevents a collision.
9. `## Resume` — after an orchestrator crash: read the manifest, poll liveness on each name,
   then re-attach or respawn. This replaces Workflow-native resume.
10. `## Failure behavior` — the orchestrator column of the spec's failure table, all five
    rows.
11. `## See also` — `docs/bg-dispatch-contract.md`, `docs/orchestration-substrates.md`,
    `skills/dispatching-bg-agents/`.

## D3.6 `docs/orchestration-substrates.md`

Add a section directly after the `/relay:drive` exception, so the two exceptions sit
together:

`## The session-tree exception: a run may have no Workflow at all`

It states:

- Under `--engine session-tree` the command generates no Workflow. This is the **second**
  documented exception to "every L3 command generates one Workflow", next to `/relay:drive`.
- The two exceptions are different in kind. `/relay:drive` still generates exactly one
  Workflow and only holds one long-lived process outside it. `session-tree` generates none.
- MAIN is the orchestrator. The §4.2.1 spine still governs what happens; only the substrate
  changes — spine roles run as sessions, not `agent()` nodes.
- The contract is `docs/bg-dispatch-contract.md`. The orchestrator prose is
  `skills/orchestrating-session-trees/SKILL.md`.
- v1 scope: `/relay:implement` only.

Also update the first paragraph, which today says relay uses "a **single** orchestration
substrate". It must now say there are two, and name the second. Leaving that sentence is a
documentation lie the moment this ships.

## D3.7 Command wiring

**`commands/implement.md`:**

1. `argument-hint` gains `session-tree`.
2. **Step 1** gains a branch at the top: when `$RELAY_ENGINE` resolves to `session-tree`,
   invoke `relay:orchestrating-session-trees` in the current (MAIN) session, report its
   result, and **end the command turn there**. `Skill` is already in `allowed-tools`, so no
   frontmatter change is needed. This branch is **terminal** — the command does not fall
   through to Step 2. Every other engine value keeps the current Step 1 behavior and reaches
   Step 2 as today.
3. **Steps 2 through 5 gain a one-line precondition each**, stated at the top of each step:
   "Skip this step when Step 1 took the `session-tree` branch." Steps 2–5 all read state a
   `Workflow` run produces (`runId`, an in-progress branch to append to, or a completed run
   to verify/retro), and none of that state exists on a `session-tree` run — the orchestrator
   allocates its own runid through `bg-manifest.sh` instead [spec §Deliverable 3,
   Bookkeeping]. Concretely: Step 3 generates no Workflow, Step 3.5 records no run intent,
   Step 4's "exactly one `Workflow` run was launched" check does not run and must not fire
   its "stop and re-issue the work as a single Workflow" branch, and Step 5 retros nothing.
   The terminal return in Step 1 already makes these steps unreachable in practice; the
   precondition line is there so the written command does not contradict its own behavior —
   an implementer reading Step 4 in isolation must not find an instruction that fights the
   substrate this deliverable adds.
4. Step 0 prose gains `session-tree⇒claude`.
5. Step 0.25 is **not** changed for `session-tree`. Like `smart-routing`, it stays flag- and
   pin-reachable only. Say so in the same sentence that already says it about
   `smart-routing`.

**`commands/refine.md`, `execute.md`, `drive.md`:**

Add a guard immediately after the Step 0 axis echo. Their `argument-hint` does **not** gain
`session-tree` — they do not support it.

```bash
if [ "$RELAY_ENGINE" = "session-tree" ]; then
  echo "[relay] error: engine=session-tree is not supported by /relay:<command> (v1 scope: /relay:implement only)" >&2
  exit 1
fi
```

**[plan]** The exact error string. The spec calls it "the standard engine-not-supported
error", and no such error exists in the tree yet. This defines it. Use the same string in
all three commands, with only the command name changed.

Add `orchestrating-session-trees` to `_KNOWN` in `scripts/validate_l3_command.py`. (C4.4)

## D3.8 Tests

### `test_parse_engine_agent.sh` — extend again

Mirror the D2.7 cases for `session-tree`: bare value defaults to `claude`; `session-tree
codex` fails with the invariant message; the enum error string names `session-tree`; the pin
path works; the extras check still bites.

### `test_bg_manifest.py`

`HOME` at `tmp_path`, in the style of `test_record_run_intent.py`.

| Test | Asserts |
|---|---|
| `test_script_exists_and_is_executable` | present and executable |
| `test_init_creates_the_documented_path` | `~/.claude/relay/runs/<runid>/manifest.json` |
| `test_runid_charset_is_enforced` | `WF_123`, `abc`, and a 9-character value each exit `2` |
| `test_add_session_records_every_field` | name, launch id, role, logical parent, phase |
| `test_set_phase_updates_in_place` | the record count does not grow |
| `test_manifest_is_state_not_a_log` | two `set-phase` calls leave one record, holding the last value |
| `test_write_is_atomic` | after any write, no temporary file is left in the directory, and the file parses as JSON |
| `test_write_failure_is_fatal` | make the directory read-only; rc `1`; stderr holds `manifest write failed` |
| `test_read_prints_valid_json` | `jq empty` accepts the output |
| `test_names_prints_key_value_pairs` | one `RELAY_BG_NAME=` and one `RELAY_BG_SHORT_ID=` per session |
| `test_usage_error_exits_2` | unknown subcommand, missing `--runid` |

### `test_orchestrating_session_trees.py`

| Test | Asserts |
|---|---|
| `test_skill_exists_and_frontmatter` | name matches the directory; `user-invocable: false`; description non-empty |
| `test_no_relay_vocab_block` | none present |
| `test_scope_is_implement_only` | the skill says v1 covers `/relay:implement` only |
| `test_spawns_flat` | the topology section says the orchestrator spawns every session flat |
| `test_operators_never_spawn` | S3-1 is cited |
| `test_v1_cap_stated` | one operator per goal, at most three workers |
| `test_cap_is_reported_when_it_binds` | the skill says the report states the cap |
| `test_manifest_path_and_script` | the path and `bg-manifest.sh` are both named |
| `test_manifest_write_failure_is_fatal` | the word FATAL, or an equally plain sentence |
| `test_runid_is_orchestrator_allocated` | the skill says `record-run-intent.sh` never runs here |
| `test_question_routing_three_hops` | worker → operator → orchestrator |
| `test_escalation_token_used_for_a_relay` | `ESCALATION from` appears |
| `test_askuserquestion_only_in_an_interactive_run` | and only in the orchestrator |
| `test_headless_escalates_to_the_parent_session` | stated |
| `test_end_of_run_names_unstoppable_children` | stated |
| `test_resume_reads_the_manifest_then_polls_liveness` | stated |
| `test_waiting_section_matches_the_verified_answer` | either the free-waiting shape or the bounded-poll fallback is present, and never both |
| `test_stop_mechanism_defers_to_the_contract` | §1.6 is cited, and no second mechanism is described |

### `test_session_tree_substrate.py`

| Test | Asserts |
|---|---|
| `test_substrate_doc_names_the_second_exception` | `session-tree` appears next to `/relay:drive` |
| `test_doc_no_longer_claims_a_single_substrate` | the old "single orchestration substrate" sentence is gone or corrected |
| `test_doc_says_no_workflow_is_generated` | stated plainly |
| `test_doc_says_the_spine_still_governs` | §4.2.1 is cited |
| `test_implement_step_1_branches_on_session_tree` | `implement.md` names the branch and the skill, the branch is stated as terminal (ends the command turn), and Steps 2 through 5 each carry the "skip this step when Step 1 took the `session-tree` branch" precondition |
| `test_implement_argument_hint_lists_session_tree` | present |
| `test_other_three_commands_reject_session_tree` | parametrized over refine/execute/drive: the exact error string is present |
| `test_other_three_hints_do_not_list_session_tree` | absent from their `argument-hint` |
| `test_step_025_does_not_offer_session_tree` | flag- and pin-reachable only |
| `test_validate_l3_knows_the_orchestrator_skill` | `orchestrating-session-trees` is in `_KNOWN` |
| `test_roster_doc_holds_the_topology_roles` | `orchestrator`, `operator`, `worker` |
| `test_roster_agent_count_sentence_unchanged` | `7 agents total` is still exact |

## D3.9 Order of work

1. Run the D3.0 check. Write the answer down. It decides section 6 of the skill.
2. Edit `parse-engine-agent.sh`; extend `test_parse_engine_agent.sh`; run that bash suite.
3. Edit `docs/architecture.md` and `README.md` at once. (C4)
4. Edit `docs/agent-roster.md` and re-run `test_bg_naming_grammar.py` — the roster is the
   validator's source, so the new roles must be accepted after this edit.
5. Write `scripts/bg-manifest.sh` and `test_bg_manifest.py`.
6. Write `skills/orchestrating-session-trees/` and its test. Add it to `EXPECTED_SKILLS`
   and update the count in `docs/contributing.md`.
7. Edit `docs/orchestration-substrates.md`.
8. Edit the four command bodies and `validate_l3_command.py`; write
   `test_session_tree_substrate.py`.
9. Run the full gate.

## D3.10 Done criteria

- The full gate passes.
- `git diff` shows no change to `scripts/record-run-intent.sh`, `bindings/presets.yaml`, or
  `test_envelope_tokens.py`.
- `/relay:refine --engine session-tree` exits `1` with the engine-not-supported error.
- The D3.0 answer is recorded, and the skill's `## Waiting` section matches it.

---

# Release step — the single version bump (C3)

Run this last, after all three deliverables pass the gate.

1. **`.claude-plugin/plugin.json`** — `"version": "4.29.0"` becomes `"version": "4.30.0"`.
2. **`CHANGELOG.md`** — a new `## 4.30.0 — <date>` entry at the top, newest first, no
   `[Unreleased]` section. Follow the house style: a one-line bold thesis, then bolded
   lead-in bullets with real rationale. Entries here are long. Write down what did not work.
   The entry must cover all three deliverables and must record:
   - the contract layer, both scripts, and why the state file is not a success oracle (S4-2);
   - the prompt-last rule and the idle children that taught it (launch trap 1);
   - `LAUNCH_DENIED` as a normal outcome (launch trap 2);
   - why `done` maps to alive and not to stopped;
   - the two provisional tokens, and the plain statement that the frozen set is unchanged;
   - `bg-sessions`, and the answer to the D2.0 check;
   - `session-tree`, the second substrate exception, and the answer to the D3.0 check;
   - the v1 caps and what is deliberately not done.
3. **`tests/unit/skill-structure/test_plugin.py`** — do the ratchet, in the tree's exact
   idiom: [repo `docs/contributing.md`]
   - In `TestVersion4290`, relax the exact pin to a `>=` comparison and add the comment
     `# Superseded exact pin: 4.30.0 carries this line forward (TestVersion4300 owns the
     current exact pin).`, keeping the `packaging.version.Version` import shape the other
     superseded classes use.
   - Add `class TestVersion4300` with a docstring, an exact pin
     `assert manifest["version"] == "4.30.0"`, a parametrized `test_changelog_has_4300_entry`
     over distinguishing tokens (for example `bg-sessions`, `session-tree`,
     `LAUNCH_DENIED`, `RELAY_BG_STALE_SECONDS`, `provisional`), and an executability check
     over the three new scripts: `bg-launch.sh`, `bg-liveness.sh`, `bg-manifest.sh`.
4. **`docs/contributing.md`** — the worked example must read
   `assert manifest["version"] == "4.30.0"`, or
   `test_docs_freshness.py::test_version_example_matches_manifest` fails. Confirm the skill
   counts on line 140 are `(17)` for `EXPECTED_SKILLS` after both new skills.
5. Run the full gate one more time.
6. Commit on a feature branch, never on `main`. Conventional commit, for example:
   `feat(relay)!: v4.30.0 — background-session dispatch contract, --engine bg-sessions, --engine session-tree`.
   Use `feat`, not `feat!`, unless something frozen actually changed — nothing here does.
   Open a PR. The PR description records both live checks: the S1 round-trip run, and the
   two `[unverified]` property answers.

`.claude-plugin/marketplace.json` needs no edit. Its relay entry carries no version, and
`test_marketplace.py` asserts that it must not.

---

# Deliberate non-goals

Copied from the spec so an implementer does not add them by reflex. Each has a named
add-later path.

- **No codex or opencode workers in the bg engines.** The acpx leg keeps them.
- **No fan-out past the v1 cap.** A load spike unlocks a bigger cap later.
- **session-tree v1 covers the implement spine only.**
- **smart-routing does not learn the bg legs in v1.**
- **No token cost accounting in v1.** The manifest notes that cost is unknown.
- **`bindings/presets.yaml` gains no field.** The existing `delegate_eligible` flag and
  `modalities.claude` tier are enough.
- **The auto-spec skill stays punted.** Its settled decisions are in the spec's Appendix B.

# Open decision points

The implementer must settle each one, in the deliverable named.

| # | Question | Where | Fallback if the answer is no |
|---|---|---|---|
| 1 | Can a Workflow node message a named session? | D2.0 | Restrict `bg-sessions` to `one_shot: true` roles |
| 2 | Does an inbound message re-invoke a mid-command MAIN session, with its state? | D3.0 | The orchestrator holds a bounded poll over the manifest |
| 3 | Ship `scripts/bg-manifest.sh`, or leave the manifest as prose? | D3.4 | Prose only. The atomicity and the FATAL rule then go untested. Not recommended |
| 4 | Does `bg-launch.sh --check-name` stay the one naming validator? | D1.2.4 | A separate `scripts/bg-name-check.sh`. Then both callers must use it, and the naming test moves with it |
