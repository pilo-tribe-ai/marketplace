# Relay integration-test harness — design

**Date:** 2026-09-08
**Status:** Approved design, awaiting implementation plan
**Depends on:** relay 4.51.0 (acpx 0.13.2 floor), Claude Code CLI >= 2.1.263

## 1. Goal

Give relay a pre-merge check that runs the plugin the way a user runs it. The
harness loads the plugin from the local working tree with `claude --plugin-dir`,
starts headless `claude -p` sessions inside a throwaway sandbox repository, and
asserts on what those sessions actually did — files, commits, printed
contract lines — not on what they said.

The unit suite (3249 tests) proves the scripts and the skill text. It cannot
prove that a live model, given the command markdown, follows it. This harness
closes that gap. It is slow and it costs money, so it runs locally, on demand,
before a PR merges. It is not wired into CI in v1.

## 2. Scope

**In scope (v1):**
- A `gates` tier: cheap, deterministic refusal and contract checks.
- An `e2e` tier: full `/relay:implement`, `/relay:verify`, and
  `/relay:implement --verify` runs, parameterized by engine and agent.
- An `acpx` tier: live envelope and driver contract probes (no `claude -p`).
- A pytest substrate under `plugins/relay/tests/integration/`, excluded from
  the default run and from CI.
- A `make itest` entry point.

**Out of scope (v1), recorded as follow-ups in §13:**
- CI wiring.
- Answering `AskUserQuestion` through `--input-format stream-json`.
- codex / hybrid / smart-routing e2e rows in the default matrix (they stay
  parameter-reachable).
- A `claude plugin eval` bolt-on suite.
- Skill-selection judging (LLM-as-judge tiers).

**Relationship to `tests/e2e/`:** that directory holds ad-hoc shell scripts
(`run-eval.sh`, `bg-s1-roundtrip.sh`) and their fixtures. This harness does not
touch, replace, or collect them. New work goes under `tests/integration/`.

## 3. Layout

```
plugins/relay/
  Makefile                          # NEW — itest entry point (no Makefile exists today)
  pytest.ini                        # NEW — marker + default deselect (no pytest config exists today)
  tests/integration/
    conftest.py                     # fixtures: sandbox_repo, relay_session, options
    contracts.py                    # black-box assertion helpers per command
    seeds/                          # sandbox seed templates (toy project, .claude/)
      toy-project/                  #   copied into every sandbox
      commands/verify.md            #   sandbox-level /verify definition
    test_gates.py                   # gates tier
    test_e2e.py                     # e2e tier (parameterized)
    test_acpx_live.py               # acpx tier
    results/                        # git-ignored — one dir per run
      .gitignore
```

### pytest.ini

No pytest config file exists in `plugins/relay` today, and CI runs
`pytest tests/ -q -rs` bare. The new `pytest.ini` registers the marker and
deselects it by default:

```ini
[pytest]
addopts = -m "not integration"
markers =
    integration: live claude -p / acpx tests; cost money; run via make itest
```

`addopts` values are prepended to the command line, so an explicit
`-m integration` on the harness's own invocation comes later and wins (the last
`-m` expression is the one pytest applies). CI's bare `pytest tests/` therefore
deselects the tier with no CI change. Every test in `tests/integration/` carries
`@pytest.mark.integration` (applied once via `pytestmark` in each file).

### Second gate: `RELAY_ITEST=1`

Marker selection alone is not enough — someone running
`pytest tests/ -m integration` casually would start paid sessions. A
`tests/integration/conftest.py` fixture errors out (not skips) unless
`RELAY_ITEST=1` is set in the environment. The Makefile sets it. The error
message names the Makefile target so the path to a legitimate run is printed
where the refusal is.

### Makefile

```
make itest TIER=gates|e2e|acpx|all [CMD=implement|verify|implement-verify]
           [ENGINE=<engine>] [AGENT=<agent>] [ROUNDS=<1..5>] [KEEP=1]
```

- `TIER` is required. `all` runs gates, then acpx, then e2e (cheapest first,
  so a broken contract fails before an expensive row starts).
- `CMD`/`ENGINE`/`AGENT` select one e2e row; unset, the curated default matrix
  (§6.2) runs.
- `ROUNDS` overrides the verify round cap (default 1 — see §6.2).
- `KEEP=1` keeps every sandbox directory for inspection. The default deletes
  sandboxes at teardown, pass or fail; results dirs are always kept.

The Makefile translates these to pytest options declared in `conftest.py`
(`--relay-cmd`, `--relay-engine`, `--relay-agent`, `--relay-rounds`,
`--relay-keep`), exports `RELAY_ITEST=1`, and runs
`python3 -m pytest tests/integration -m integration -q -rs` plus the tier's
file selection.

## 4. The child session: `relay_session()`

One fixture owns every child invocation. Nothing else in the harness calls
`claude`. The full command line:

```bash
claude -p "<prompt>" \
  --plugin-dir "<working-tree>/plugins/relay" \
  --output-format stream-json --verbose \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --max-budget-usd <tier cap> \
  --max-turns <tier cap>
```

- **`--plugin-dir`** points at the working tree. This is the seam the whole
  harness exists for: the session under test runs the branch's plugin, not the
  installed copy. §10 proves it per run.
- **`--output-format stream-json --verbose`** captures the full transcript, not
  only the final text. The stream is written to the results dir (§10). The
  `result` event at the end of the stream carries the same fields as
  `--output-format json` (`result`, `total_cost_usd`, `session_id`,
  `num_turns`), so nothing is lost by choosing stream-json.
- **`--permission-mode bypassPermissions`** — approved decision. The child
  works inside a throwaway sandbox git repo; the blast radius is the sandbox.
  This is a containment argument, not a security boundary — same posture as
  relay's own `--approve-all` acpx children.
- **`--strict-mcp-config`** with no `--mcp-config`: the child gets **zero MCP
  servers**. Without this, the child inherits the developer's global config —
  GitHub write tools, Notion, Playwright. A model told to *implement* with
  approvals off and a live `create_pull_request` tool in reach is a hazard, and
  the rest is cost and flake. Non-negotiable on every child.
- **`--setting-sources project,local`** is desirable on top (it drops the
  developer's global CLAUDE.md, which injects unrelated instructions into every
  child), but relay depends on the superpowers plugin via `check-deps.sh`, and
  whether installed plugins still load when the `user` source is dropped is
  unverified. Calibration item C1 (§12) settles it on the first gates run. Until
  then the flag is off and the global CLAUDE.md noise is accepted.

**cwd** = the sandbox repo (§5). **Process control:** macOS has no `timeout`
binary, so the fixture uses Python: `subprocess.Popen(start_new_session=True)`,
`wait(timeout=<tier cap>)`, and on expiry `os.killpg` on the child's process
group — the child spawns its own subprocesses (acpx children, git, pytest) and
a bare `kill` would orphan them.

**Child environment**, built from `os.environ`:
- Scrub every `RELAY_*` variable (same reasoning as the unit conftest: the
  caller's shell must not preset the axis).
- Scrub `CLAUDECODE` and every `CLAUDE_CODE_*` variable, so running the harness
  from inside a Claude Code session behaves like running it from a plain shell.
  (`bg-dispatch.sh` has no scrub to reuse; the harness defines its own list.)
- **Keep the real `HOME`.** The child must find the developer's login and the
  installed superpowers plugin. This is a deliberate divergence from the unit
  conftest's hermetic-HOME policy, and it is what makes these integration
  tests: they run on a provisioned machine, not a hermetic one.

**Budgets** (calibration values; the plan may tune them):

| tier  | --max-budget-usd | --max-turns | wall clock (killpg) |
|-------|------------------|-------------|---------------------|
| gates | 1                | 40          | 600 s               |
| e2e   | 10               | 300         | 7200 s              |

Calibration item C2 (§12): on a subscription login `total_cost_usd` may be an
estimate and `--max-budget-usd` may not enforce. The first gates run verifies
whether a deliberately tiny cap stops a session. If it does not, `--max-turns`
is the real ceiling and the budget flag stays as a best-effort second line.

**Teardown**, always, pass or fail:
1. `os.killpg` if the child is still alive.
2. Close acpx sessions the row opened: acpx scopes a session by
   `(agentCommand, cwd, name)`, so list sessions whose cwd is the sandbox and
   close them. Without this, an aborted acpx row leaks orphan children.
3. Delete the sandbox (kept only under `KEEP=1` / `--relay-keep`).

**No retries in v1.** A flaky row fails and prints its transcript path. Retry
policy is a follow-up once flake modes are known, not a v1 guess.

## 5. The sandbox

`sandbox_repo()` builds a throwaway git repo per test row, from
`seeds/toy-project/`:

- A toy Python project: `src/wordcount.py` (a small pure function),
  `tests/test_wordcount.py` (a passing pytest file), `README.md`.
- `git init`, an initial commit on `main`, then `git checkout -b feature/itest`.
  Relay's branch guards refuse the default branch, so seeded rows start where a
  real run starts. Gates rows that test the refusals stay on `main` or detach
  `HEAD` deliberately.
- `.claude/relay.json` seeding the engine/agent pin for the row under test.
  This is the documented pre-answer for `/relay:implement` Step 0.25 (the
  ask-when-unpinned question, unanswerable under `-p`), and it makes the
  command-line flags belt-and-braces rather than the only channel.
- `.claude/commands/verify.md` — **the sandbox defines `/verify`.** Relay's
  verify loop states that `/verify` "resolves to whatever the repository
  defines"; an empty repo defines nothing, so without this seed the check node
  fails on a missing command, not on relay. The seeded command runs the toy
  test suite and reports honestly in the shape the check node's verdict
  contract asks for.
- Calibration item C3 (§12): where `/simplify` and `/code-review` resolve from
  on a provisioned machine. If either does not resolve inside the sandbox, the
  seed grows a repo-level definition the same way `/verify` does.

Variant seeding: `implement` rows seed only the toy project;
`verify` and `implement-verify` rows also seed one small committed change on
the feature branch so the loop has a diff to polish.

## 6. Tiers

### 6.1 gates — deterministic, cheap, first

Each case is one short `claude -p` session asserting an exact, deterministic
relay contract. Day-one cases:

| case | seed | prompt | assertion |
|---|---|---|---|
| verify refuses main | sandbox on `main` | `/relay:verify --engine in-session` | refusal text `refusing to run on the default branch` reaches the result; no commit made |
| verify refuses detached HEAD | detached HEAD | same | the detached-HEAD refusal; no commit |
| unsupported engine | feature branch | `/relay:verify --engine bg-sessions` | the exact `is not supported by /relay:verify (supported: in-session \| acpx)` message. `bg-sessions` is a valid relay engine, so the argument parser accepts it and this verify-only rejection fires. [inferred] A value outside the engine enum, such as `bogus`, fails earlier with the parser's own `invalid engine` message. [inferred] |
| rounds out of range | feature branch | `/relay:verify --rounds 9 --engine in-session` | the `--rounds takes an integer from 1 to 5` message; never clamped |
| floor gate | fake `acpx` shim printing `acpx 0.12.0` first on `PATH` | `/relay:setup` (or the floor script via a command) | the child reports the floor failure and the `npm install -g acpx@latest` remediation |
| preflight provenance | feature branch | `/relay:verify --engine in-session` (any Step-0 command) | §10's provenance assertion on this row's transcript |

Assertions read three places, in order of authority: the sandbox's git state,
the captured transcript (tool-use inputs and outputs), and the final result
text. A refusal case additionally asserts the *absence* of effects (no new
commit, no state root created).

### 6.2 e2e — the black-box variant matrix

One test, parameterized. The row's parameters are
`(cmd, engine, agent, rounds)`. Regardless of the variant chosen, the test
does the same thing: build the sandbox, run the relay command headless, then
assert **completion** and **correctness** from the outside. `implement` and
`verify` are two separate commands, and `implement --verify` is a third shape
covering the combined path — per the approved requirement.

**Prompts:**
- `implement`: `/relay:implement --engine <e> --agent <a> <task>` where
  `<task>` is a fixed `script`-kind task: *"Write scripts/linecount.py: print
  the number of non-empty lines of the file named by argv[1]. Add a pytest
  test for it."* `script` kind hits the shortest spine
  (`delegate-leaf(write) → commit → verify`); `feature` kind triples the node
  count and the cost, so it is parameter-reachable, not default.
- `verify`: `/relay:verify --engine <e> --rounds <r>` on the seeded branch.
- `implement-verify`: the implement prompt plus `--verify --rounds <r>`.

`rounds` defaults to **1** on every default row — the loop's stop logic is
covered by unit tests; the harness pays for one live round, not three.

**Curated default matrix** (approved decision — other engines stay reachable
via `CMD=`/`ENGINE=`/`AGENT=`):

| cmd | engine | agent | expected outcome class |
|---|---|---|---|
| implement | in-session | claude | completed |
| implement | acpx | claude | completed |
| implement | bg-sessions | claude | completed |
| verify | in-session | claude | completed |
| verify | acpx | claude | documented-refusal |
| implement-verify | in-session | claude | completed |

**Correctness contracts** (in `contracts.py`, shared by every row):

`implement` — completion: the child exited before the wall clock, and the
spine's final fenced JSON block `{"status": "ok", ...}` appears in the
transcript (secondary: the block is *not* required to be the last message —
`.result` holds only the final text, so the transcript is searched, and the
sandbox state is the primary evidence). Correctness:
- The sandbox is on a non-default branch with >= 1 commit ahead of `main`.
- The deliverable exists (`scripts/linecount.py`).
- The deliverable is correct: the harness runs it on a fixture file and checks
  the number.
- The toy test suite passes (`python3 -m pytest` in the sandbox exits 0).

`verify` — completion: a `RELAY_VERIFY_RESULT=<verdict>` line appears.
Correctness:
- The loop state root exists under the sandbox's git dir, with round-1 records
  present (`SIMPLIFY=`, `REVIEW=`, `CHECK=` keys — the shapes
  `verify-loop-node.sh` writes).
- The verdict matches the row's expected outcome class (§7).
- The working tree is committed (the loop commits every round; no dirty tree
  left behind).

The first and third bullets apply only to a row whose expected outcome class is
`completed`. [inferred] A `documented-refusal` row generates no node, so it
writes no state root and makes no commit; its correctness assertion is the
refusal contract in §7 — no state root, no round records, no commit, and
`RELAY_VERIFY_RESULT=unverified`. [inferred]

`implement-verify` — both contract sets, in order, on the same sandbox.

### 6.3 acpx — live dispatch contracts, no `claude -p`

Codifies the live-probe methodology from the 4.51.0 work as repeatable tests.
Each case runs the real `acpx` binary the way relay's scripts do and asserts
the frozen envelope/driver contract:

- `acpx --format json --json-strict --approve-all claude exec` with a prompt
  instructing an envelope-only reply → `acpx-envelope.sh` extracts it, and the
  **first line** carries the sentinel (the last-message-wins rule the
  narration fixture pins statically, proven again against the live adapter).
- A session-driver round trip: open, one turn, close; assert the
  `first_line` sentinel path in `claude-session-driver.sh` fires on a
  `BLOCKED:` reply.
- The floor script against the real installed acpx: exits 0, prints
  `RELAY_ACPX_VERSION=` with a plausible number.

These need acpx installed and a Claude login, but no sandbox repo and no
`claude -p`; they are minutes and cents, not tens of minutes and dollars.

## 7. Outcome classes and the calibration-run policy

Every e2e row declares one expected outcome class:

- **`completed`** — the command ran its path to the end and the correctness
  contract holds.
- **`documented-refusal`** — the command refused *in the exact way its own
  documentation says it must under headless constraints*, and reported
  honestly. The canonical row: `verify × acpx` under `-p` cannot answer the
  Step-1 `AskUserQuestion` consent gate, so the documented behavior is to
  generate no node and report `RELAY_VERIFY_RESULT=unverified`. The harness
  asserts that refusal as a correctness class — an assertable contract about
  instruction-following under headless, not a skipped test.

A refusal row that instead completes, hangs, or reports `clean` **fails**. If
the model does not take the documented headless fallback, that is a relay
finding about the fallback text, not a harness bug.

**Calibration-run policy.** Dogfood history is honest here: a clean in-session
verify loop has never been observed, and loop nodes have idled mid-protocol.
So the harness asserts in two stages:
- **Day one, every row:** the completion contracts (command returned before
  the wall clock, state root exists, `RELAY_VERIFY_RESULT=` printed, spine
  block present) and the deterministic correctness checks (files, commits,
  toy tests). On a `documented-refusal` row the state-root and commit checks
  are replaced by the refusal contract above. [inferred]
- **After the first full matrix run:** the observed verdict per row is
  reviewed, and the *specific* expected verdict (`clean` vs `unverified` for
  in-session verify rows) is pinned in the matrix from evidence, not
  prediction. The spec deliberately does not pre-pin what has never been
  observed.

**Preconditions unmet ⇒ loud skip, never pass.** Missing `claude` binary,
missing acpx (for acpx-engine rows), missing login: the row calls
`pytest.skip` with a message naming the missing piece. CI-invisible (the tier
never runs there); locally visible via `-rs`.

## 8. Results and debuggability

Every run writes `tests/integration/results/<UTC timestamp>/`:

```
results/2026-09-08T14-30-00Z/
  row-<cmd>-<engine>-<agent>/
    command.txt        # the exact claude invocation
    stream.jsonl       # the full stream-json transcript
    result.json        # the final result event, extracted
    sandbox-git.txt    # git log + status of the sandbox at teardown
    verdict.txt        # the harness's own pass/fail reasoning
```

A 20-minute failure is debuggable only if the evidence survives; the results
dir is the deliverable of a failed run. `results/` is git-ignored.

## 9. What the harness never does

- Never runs against the installed plugin copy on purpose (§10 catches it
  happening by accident).
- Never mutates the working tree: the child's cwd is the sandbox; the plugin
  dir is read to load the plugin, not written.
- Never talks to GitHub, Notion, or any MCP server (`--strict-mcp-config`).
- Never runs in CI in v1.
- Never retries.

## 10. The provenance gate

Nothing in `--plugin-dir` semantics *proves* the working tree was loaded — an
installed copy of the same plugin name is overridden silently, and on this
machine the installed `-local` copy may even point at a different checkout.
If the override ever silently failed, the harness would green-light a broken
branch. So one gates case asserts provenance every run, mechanically:

Relay's command markdown embeds `${CLAUDE_PLUGIN_ROOT}` in its Step-0 Bash
blocks; the harness substitutes it to an absolute path before the block runs.
The captured stream-json transcript carries every tool-use input, so the gates
provenance case greps its own transcript for the Step-0 invocation and asserts
the path prefix is exactly the `--plugin-dir` value passed — i.e.
`<working-tree>/plugins/relay/scripts/l3-preflight.sh`. A transcript showing
any other prefix (an installed-copy path) fails the run before an e2e dollar
is spent. No relay change is needed; the assertion reads what the plugin
already prints into its tool calls.

## 11. Committed content hygiene

Seeds and fixtures are committed. Rules, same as the 4.51.0 fixture work:
- No personal data: before commit, grep seeds/fixtures for the developer's
  username, email, and machine paths; the toy project is generic.
- No secrets: children authenticate via the real `HOME`, never via committed
  tokens.
- Results dirs and sandboxes are never committed (`.gitignore`).

## 12. Calibration items (settled by the first runs, then pinned)

| id | question | how it settles |
|---|---|---|
| C1 | Does the superpowers plugin still load under `--setting-sources project,local`? | First gates run with the flag on; if `check-deps.sh` blocks, the flag stays off and the decision is recorded here. |
| C2 | Does `--max-budget-usd` enforce on a subscription login? | A throwaway session with a tiny cap; if it does not stop, `--max-turns` is documented as the real ceiling. |
| C3 | Where do `/simplify` and `/code-review` resolve from inside the sandbox? | Inspect the first in-session verify transcript; seed repo-level definitions if unresolved. |
| C4 | Observed verdicts per default e2e row (first full matrix run). | Pin expected verdicts in the matrix from the evidence (§7). |
| C5 | Can the child run a Workflow-generating L3 command to completion under `-p`? | The first implement row's transcript; if `-p` degrades the Workflow path, that is a relay finding to file, and the row's contract stands on sandbox state. |

## 13. Follow-ups (recorded, not v1)

- Answer consent questions through `--input-format stream-json`, unlocking
  `verify × acpx` as a `completed` row.
- An opt-in CI job (manual dispatch) once budgets and flake modes are known.
- codex / hybrid / smart-routing e2e rows in the default matrix.
- A `claude plugin eval` bolt-on suite for skill-selection judging.
- A retry policy, once observed flake modes justify one.

## 14. Decision log

| decision | choice | why |
|---|---|---|
| Coverage | gates + one full e2e flow + acpx live contracts | approved in brainstorming; judging tiers excluded |
| Substrate | pytest | matches the existing suite and its idioms; approved |
| Venue | local, on demand | approved; CI is a follow-up |
| E2E shape | one black-box test parameterized by `(cmd, engine, agent, rounds)`; implement and verify as two commands plus `implement --verify` | approved verbatim requirement |
| Child permission mode | `bypassPermissions` inside the sandbox | approved; containment by sandbox, zero MCP servers |
| Default matrix | implement×{in-session, acpx-claude, bg-sessions} + verify×{in-session, acpx} + implement-verify×{in-session} | approved; other variants parameter-reachable |
| Headless verify×acpx | `documented-refusal` outcome class, asserted | turns the consent constraint into a contract |
| MCP exposure | none (`--strict-mcp-config`) | safety: no write tools reachable from an approvals-off child |
| Transcript capture | stream-json per row, kept in results | `.result` is final text only; state + transcript are the evidence |
| Toy task kind | `script` | shortest spine; `feature` is parameter-reachable |
| Rounds default | 1 | unit tests own the stop logic; the harness pays for one live round |
| Retries | none in v1 | fail loudly with the transcript path |

## Refinement Status

Refinement: CONVERGED round 2
