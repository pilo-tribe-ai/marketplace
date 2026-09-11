# Changelog

All notable changes to relay are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## 4.52.0 — 2026-09-09

### Added

- Add the integration-test harness under `tests/integration/` (`make itest`):
  gates, e2e, and acpx live-contract tiers. Double-gated (the `integration`
  marker is deselected by default; `RELAY_ITEST=1` is required) so CI's bare
  `pytest tests/` never runs it. Local and on demand; not wired into CI.

## 4.51.0 — 2026-09-05

Relay moves to acpx 0.13.2, four releases up from the 0.12.0 it claimed. Design:
`docs/superpowers/specs/2026-09-05-relay-acpx-0.13.2-upgrade-design.md`.

### Added

- **`scripts/acpx-floor.sh` — one floor, checked in code.** The acpx floor was
  prose that disagreed with itself: two skills said 0.12.0, one said 0.7.0, and
  `flows/package.json` said 0.7.0 while its lock resolved 0.10.0. Nothing ever
  checked it, so a stale acpx failed later, inside a dispatch, with an error that
  named neither acpx nor a version. The script holds the number and the reason,
  prints `RELAY_ACPX_VERSION=<v>`, and on failure prints one line naming the
  version found, the floor, and `npm install -g acpx@latest`. It reads the number
  out of the `--version` line, because acpx may print a name first: stripping
  whitespace alone leaves `acpx0.12.0`, which `sort -V` orders above `0.13.2`. `l3-preflight.sh`
  runs it after the axis resolves, for the `acpx` engine only — `in-session`,
  `bg-sessions` and `session-tree` never call the acpx CLI and do not pay the
  check. The four prose sites and the flows package now point at the script.
- **`bindings/acpx-policy.json` — the wide permission grant.** Every acpx turn
  now passes `--approve-all --permission-policy <policy>`, the widest grant acpx
  exposes. Codex keeps a sandbox behind acpx's layer, so codex paths widen that
  too: the session driver sets `mode agent-full-access`, and the one-shot `exec`
  path (no `set` subcommand) carries `approval_policy: never` and
  `sandbox_mode: danger-full-access` in `CODEX_CONFIG`.
- **`skills/dispatching-acpx-agents/acpx-envelope.sh` — structured capture.**
  Every acpx call runs under `--format json --json-strict`, and this script
  rebuilds the turn's final assistant text from the ACP message chunks. It groups
  chunks by `messageId`, keeps only codex `final_answer` chunks, and drops
  non-JSON lines. The frozen envelope contract — the capture regex and the
  `BLOCKED:` / `NEEDS_DECISION:` sentinels — is untouched; only the source of the
  text changed. The raw stream is kept beside the extracted text for forensics.
- **`errored` now covers session-config replay failure.** acpx >= 0.13.1
  re-applies a reconnected session's saved model and config options and reports a
  failure instead of continuing on adapter defaults. The envelope script turns
  that report into `ERRORED_REASON=config_replay_failed`, each driver classifies
  it as `ROLE_RESULT=ERRORED` before any other outcome, and `delegate-and-watch`
  routes it to `errored`. It must never reach `not-done`: re-dispatching would
  run the worker on a model it did not ask for.

### Fixed

- **Three roles ran with every write silently denied.** `code-reviewer`,
  `doc-reference-reviewer` and `ui-code-evaluator` are bound to
  `permissions: approve-reads`, and the dispatch gated `--approve-all` on
  `permissions: approve-all` exactly. acpx's default mode is `--approve-reads`
  and its non-TTY fallback is `deny`, so those workers had every write request
  refused and nothing reported it. Both permission flags are now unconditional.
  `permissions` in `bindings/presets.yaml` records the role's intent only —
  a read-only role is kept read-only by its role body and its agent `tools:`
  frontmatter, not by the acpx substrate.
- **Codex reasoning effort no longer rides an env hack on the session path.**
  `codex-session-driver.sh` gains the settle block the other two drivers have:
  `set model`, then `set reasoning_effort`, then `set mode agent-full-access`,
  each soft-degrading on rc≠0. The turn no longer re-passes `--model`. The
  one-shot `exec` path keeps `CODEX_CONFIG`, because `exec` has no `set`
  subcommand and acpx still rejects the bracket encoding.

### Removed

- **`ACPX_CODEX_AGENT_OVERRIDE` (added in 4.6.1).** It replaced the `codex`
  positional with `--agent "npx -y @agentclientprotocol/codex-acp@latest"`
  because acpx pinned a broken `@agentclientprotocol/codex-acp@^0.0.44`. acpx
  0.12.1 moved that pin to `^1.1.5`, which resolves to the same adapter. Removing
  it also unblocked the codex session driver, which could never use `--agent`:
  the flag cannot be combined with a positional engine, and the session
  subcommands need that positional to scope the session by agent identity.
  `CODEX_CONFIG` is still written to the codex sidecar for one release so a
  watcher on the 4.50.0 contract sources it cleanly; remove it in 4.52.0.

## 4.50.0 — 2026-09-04

### Added

- **`--worktree current|<path>|<branch>` pre-answers the Step 0.5 isolation gate
  (issue #112).** `/relay:implement`, `/relay:refine`, `/relay:execute` and
  `/relay:drive` accept the flag and pass the value to the gate, so an operator
  who already knows the workspace does not have to answer the gate's question.
  `current` keeps the checkout the command started in; a path that is a linked
  worktree of this repository is entered; anything else is tried as a branch
  name, and the worktree checked out on that branch is entered. A value that
  matches none of the three resolves as `missing`: an interactive run is offered
  the create-it branch, and a headless run stops with
  `[relay] error: worktree-missing: <value>`. A retro-only run announces that it
  ignores the flag, because a retro is read-only and must not enter anything.
- **`scripts/worktree-preflight.sh` gains three modes.** `--resolve <value>`
  resolves a `--worktree` value against `git worktree list --porcelain` and
  prints `RELAY_WT_RESOLVED` / `RELAY_WT_TARGET` / `RELAY_WT_TARGET_BRANCH`.
  `--create --at <path>` creates the worktree at a caller-named path instead of
  the generated one. `--active` prints `RELAY_WT_ACTIVE=<repository top level>`,
  which the commands record after the gate has resolved the workspace. `--active`
  is a script mode rather than an inline `git rev-parse` for the same reason
  4.49.0 moved Step 0 into a script: a worktree-isolated session refuses an
  inline command substitution (issue #110).
- **`--classify` now recognises any linked worktree,** not only one created under
  `.claude/worktrees`. A worktree an operator made by hand used to classify as
  `stray`, and the gate then offered to create a second worktree inside it.
- **The resolved workspace reaches the leaves.** Each command prints
  `RELAY_WT_ACTIVE` after the gate and injects that literal path as a `WORKTREE`
  value into the dispatches it generates, so a delegated worker acts in the same
  workspace the gate chose instead of re-deriving one.
- **`relay:implementing-spec` gains a `worktree` input and a mismatch guard.** The
  adapter entry point now takes the workspace explicitly, and stops when the
  workspace it was given is not the one it is running in.

### Changed

- **`--worktree` parsing lives in `scripts/l3-preflight.sh`,** beside the other
  Step 0 flags, and prints `RELAY_WT_ARG=<value>` only when the flag carried a
  value. `/relay:drive` strips the flag and its value from the oracle text, so
  `--worktree` is never read as the oracle path.

## 4.49.0 — 2026-09-04

### Fixed

- **L3 Step 0 moved out of inline command bash into `scripts/l3-preflight.sh` (issue
  #110).** The six L3 commands (`implement`, `refine`, `execute`, `drive`, `verify`,
  `diagnose`) each ran their dependency gate, `--verify`/`--rounds` validation,
  `--retro` extraction, and engine/agent axis resolution as an inline fenced bash
  block that sourced `check-deps.sh` and `parse-engine-agent.sh`, used `$(...)`,
  `case`, and `if`. A session isolated in a git worktree refuses an inline Bash
  command that carries any of those shapes, and sourcing `check-deps.sh` under a
  non-bash shell (e.g. zsh) ends the call silently. `scripts/l3-preflight.sh` now
  reproduces all of that behind one call — `bash
  "${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" <command> "$ARGUMENTS"` — printing
  the same `[relay] ...` lines and a `KEY=value` block to stdout, with the same exit
  codes and error text. The Step 0.25 re-resolution blocks collapse into one line
  each via a new `--axis-only <engine> <agent> --source <label>` mode. The script
  also carries the `--fixes-model`/`--verification-model` flag parsing and the
  `RELAY_DEFAULT_ENGINE`/`RELAY_DEFAULT_AGENT` default-layer exports that 4.46.0 and
  4.47.0 added inline, and the `--keep-sessions` flag and its engine check that 4.48.0
  added inline, so moving Step 0 into a script regresses no feature.
- **`scripts/worktree-preflight.sh` gains a `--branch-guard [implement|verify]`
  mode.** It runs the existing `--classify` logic and refuses the default branch and
  a detached `HEAD` with the exact wording `implement.md` Step 0.6 and `verify.md`
  Step 0.5 printed inline before. `implement.md` and `verify.md` now each call it
  with one line instead of an inline `$(...)`/`case`/`if` block. **Behaviour
  change:** a not-git run previously aborted silently with only
  `RELAY_WT_STATE=not-git` on stderr, because `_wt_block="$(... --classify)" ||
  exit 1` exited before the `case` that would have printed a message ever ran.
  `--branch-guard` now reaches that arm and prints `could not read the git state.
  Run this command inside a git checkout.` on a not-git run.
- **New static gate:** `scripts/validate_l3_command.py` now also rejects any fenced
  bash block in `commands/*.md` (except the pre-existing `setup.md` exemption) that
  still carries `$(`, `source `/`. `, `case`, or a line starting `if` — the shapes a
  worktree-isolated session refuses inline.

## 4.48.0 — 2026-08-31

### Changed

- **`approve-all` now maps to `auto`, not `bypassPermissions`.** The bg-dispatch
  contract used to lower `--approve-all` to `bypassPermissions`, which turned every
  child into an unrestricted actor and hid classifier judgement behind a blanket
  allow. The mapping is now `auto`, so a child still auto-accepts every prompt the
  classifier lets through but stops on anything the classifier refuses. A child that
  meets a classifier refusal writes `BLOCKED: classifier refused <tool>: <reason>`
  as the first line of its final turn and exits; the parent sees the refusal as a
  typed status instead of a silent skip. `bypassPermissions` is still available to
  callers that pass it by hand, so the e2e roundtrip that pins the raw envelope
  stays green.
- **New `scripts/bg-cleanup.sh` deletes the background sessions a run created.**
  `/relay:implement` and the session-tree orchestrator now call `bg-cleanup.sh` at
  the end of a run to remove every bg session the run spawned, so an
  `--engine bg-sessions` run no longer leaves an accumulating trail of live
  sessions behind. `/relay:implement` gains `--keep-sessions`, which suppresses the
  cleanup call for a run the operator wants to keep for inspection. Both bg engines
  clean up through the same `bg-cleanup.sh`, so there is one path to audit; the
  script prints a typed final line on every path, including the zero-session path,
  so a caller can never report a clean cleanup that did nothing.
- **One Workflow per session, capped at depth 1.** A bg child may now run its own
  dynamic Workflow, but nested bg dispatch is capped at one level below the root.
  `skills/dispatching-bg-agents/bg-dispatch.sh` enforces the cap by reading the
  depth marker its parent exported and refusing to dispatch further; the refusal
  writes a typed line so the parent sees the cap as a decision, not a crash. This
  keeps the doctrine — one Workflow per session — while giving a child room to run
  its own single-level Workflow when a task fans out.

### Known limitation

- Cleanup is wired to `/relay:implement` and the session-tree orchestrator only.
  `/relay:refine`, `/relay:execute`, and `/relay:drive` also accept
  `--engine bg-sessions` and still leave their sessions behind. Wiring the same
  `bg-cleanup.sh` call into those commands is separate follow-up work.

## 4.47.0 — 2026-08-31

### Changed

- **`/relay:implement` and `/relay:verify` default to `--engine acpx --agent claude`.**
  Both commands send their leaf work out of the calling session by default, as watched
  external Claude workers, so the session keeps its context. `/relay:refine`,
  `/relay:execute` and `/relay:drive` are unchanged: they still default to
  `--engine in-session --agent claude`.
- **The default layer is per command.** `scripts/parse-engine-agent.sh` reads two new
  environment variables, `RELAY_DEFAULT_ENGINE` and `RELAY_DEFAULT_AGENT`, that a
  command body exports before it sources the script. They move only the bottom layer:
  a `--engine`/`--agent` flag still beats them, an `engine`/`agent` pin in
  `.claude/relay.json` still beats them, and the axis line still prints
  `source: default`. Both variables are cleared inside the script, so one command's
  default cannot reach the next command in the same shell.
- **A command default agent applies only when the engine also came from the default.**
  Without that gate, `/relay:implement --engine smart-routing` would inherit
  `agent=claude` and fail the smart-routing invariant on a flag the user typed
  correctly. An explicit engine still derives its own agent from the same table as
  before.
- **`/relay:implement`'s Step 0.25 question now leads with acpx.** The four options are
  `acpx (default)`, `acpx (hybrid)`, `in-session (claude)` and `bg-sessions (claude)`.
  The question still runs only when neither axis carried a flag or a pin, and it is
  still skipped in a headless session. `acpx (hybrid)` keeps the per-role claude/codex
  split reachable from the menu.

### Notes

- **The default `/relay:verify` run now asks for agreement once.** The approvals-off
  consent question in `relay:verifying-until-clean` runs whenever the engine is `acpx`,
  which is now the common path. The question is a consent gate for running a child
  session with the approval gate off; it was not removed, and it must not be answered
  for the user.
- **`--engine in-session` is the escape hatch on a machine with no acpx.** It needs no
  acpx install and starts no child process, so it turns no approval gate off.
- An invalid `RELAY_DEFAULT_*` is a plugin bug, not a user typo, and the error says so:
  `(from this command's built-in default)`.

## 4.46.0 — 2026-08-31

### Added

- **`--fixes-model` and `--verification-model` choose the model for a whole group of
  roles.** `/relay:implement`, `/relay:refine`, `/relay:execute` and `/relay:drive`
  accept both flags. Each takes one of `sonnet`, `opus`, `fable`, and replaces the
  model of every role of its category. It changes no other role, and it changes no
  `effort`. `.claude/relay.json` accepts the same two values as the keys
  `fixes_model` and `verification_model`. Resolution is the layering every other axis
  uses — flag, then pin, then the per-role default beside the role in
  `bindings/presets.yaml`.
- **A role may carry a `category`.** Two groups exist. `fixes` holds the four roles
  that repair an artifact after a critic found a problem: `spec-fixer`, `plan-fixer`,
  `fix-planner`, `fix-coder`. `verification` holds the seven critics that decide
  whether the work is done: `spec-reviewer`, `code-reviewer`,
  `doc-reference-reviewer`, and the four `ui-*-evaluator` roles. Every other role
  carries no category, and neither flag reaches it.

### Changed

- **Every fixes role is `sonnet`, and every verification role is `opus`.** This is the
  ladder's own rule, applied to the two groups without exception: a fix is re-read by
  a critic, so it runs one rung below; a critic is re-read by nobody, so it runs at
  the top. Three roles moved to reach it. `fix-planner` drops from `opus` to `sonnet`.
  `doc-reference-reviewer` rises from `haiku` to `opus`. The four `ui-*-evaluator`
  roles rise from `sonnet` to `opus`. The rung census moves from 3 opus / 3 haiku /
  15 sonnet / 3 inherit to 7 / 2 / 12 / 3.
- **`resolve-tier.sh` states both axes in its `--all` header**, override or not, and
  names where each value came from. With in-session tiers off it says in one line
  that both overrides reached no row, so a flag can never be silently ignored.
- **`resolve-tier.sh` resolves the `.claude/relay.json` path once**, for every axis.
  It used to derive that path inside the tiers-gate branch, which left it unset
  whenever `RELAY_IN_SESSION_TIERS` was exported — a second axis reading it there
  would have found no file and resolved to no override without saying so.

### Notes

- The flag enum is narrower than the per-role ladder on purpose. `haiku` is absent
  because neither category holds a mechanical role. `inherit` is absent because it is
  a per-role property — "this role must track the session model" — that a flag would
  erase rather than replace. `fable` is present although no role pins it: the
  staleness argument that keeps a frontier name out of the static pins does not reach
  a per-run choice a person makes and can undo.
- The two overrides apply to every Claude leg: in-session leaves through
  `resolve-tier.sh`, `acpx-claude` through `acpx-dispatch.sh`, and bg-sessions through
  `bg-dispatch.sh`. They do not apply to the codex or opencode legs, because `sonnet`,
  `opus` and `fable` are Claude ids and forwarding one there would fail engine-side.
  Those legs keep their `modalities` pin, and `acpx-dispatch.sh` says so on stderr
  rather than dropping the override in silence.
- `/relay:verify` and `/relay:diagnose` take neither flag. `/relay:verify` dispatches
  no role — its nodes are pinned wrappers around `/simplify`, `/code-review` and
  `/verify`, and relay does not own the model of a command it did not write.
  `/relay:diagnose` has no Step 0, so it reads the `.claude/relay.json` pins only.

## 4.45.0 — 2026-08-27

### Changed

- **The codex ladder drops from three tiers to two.** `gpt-5.6-luna` was the cheap
  slot for code-writing roles executing against an already-vetted plan. Writing code
  to a vetted plan is not a cheap-model task: those six roles — `implementer`,
  `fix-coder`, `test-writer`, `ui-generator`, `server-runner` and `plan-simulator` —
  now take `gpt-5.6-terra`, the everyday judgment tier. The remaining ladder is
  `gpt-5.6-sol` for demanding planning and architecture, `gpt-5.6-terra` for
  everything else.
- **The slot retires on both engines at once.** `modalities.opencode` mirrors the
  codex ladder slot for slot, so `opencode-go/minimax-m3` retires with the luna slot
  it mirrored. `CODEX_TIER_TO_OPENCODE` is a bijection and the test asserts it, so a
  tier cannot retire on one engine and survive on the other.
- **The reader's map now moves with the pins.** The tier change was made on
  2026-08-01 and left uncommitted; the pins in `bindings/presets.yaml` moved while
  four other files kept describing three tiers. `selecting-the-right-model/SKILL.md`
  and `refining-ui/SKILL.md` are corrected, and a new test ties the set of tiers the
  ladder doc names to the set `presets.yaml` actually pins, so the two cannot drift
  apart again. The header comment in `presets.yaml` had been left mid-edit, naming
  three tiers while listing `gpt-5.6-terra` twice.
- **Not changed: `tests/fixtures/model-inventory-stub.yaml`.** The stub records the
  ids each engine is expected to *serve*, which is not the same as the ids relay
  *pins*. Relay dropping a slot is no evidence that the provider retired the model,
  so the stub keeps both entries.

## 4.44.0 — 2026-08-24

### Changed

- **`verifying-until-clean` states each rule once.** PR 5a of the prompt-optimization
  plan, the last one. The skill loads once per verify run and carried the terminal
  states twice, the parser trap beside the verdict contract it belongs to, an
  evidence-rules list that restated rules already at their point of use, and a
  55-line commit-scope shell block inline. The terminal states now live in the
  report-node section only; the parser trap is part of the verdict contract; the
  evidence rules keep the heading and the one rule that is stated nowhere else
  (returned text is narration, never evidence). The commit-scope block moved to
  `scripts/verify-commit-scope.sh` with its own unit test; the skill keeps the
  commit-token rules and calls the script. The timeout and approval-gate sections
  are about half their length and keep every incident run id, every number, and
  every pinned sentence. Skill word count 6,617 → 5,688.

## 4.43.0 — 2026-08-24

### Changed

- **Shared contracts live in one place each.** PR 4 of the prompt-optimization plan.
  - The writer-role landing contract, the dispatch wrapper block, and the
    per-mechanism driver env-var table each had three to five near-verbatim copies
    across the dispatch skills. `docs/dispatch-contract.md` is now the only full
    copy. Each skill keeps its own deltas and every pinned token: the
    `dispatch(role_slug, binding, inputs) →` line, the `landing_verify_failed`
    markers, the `CODEX_CONFIG` re-export note, the compact `ACPX_*` name list.
  - `docs/dispatch-contract.md` was stale: it omitted `CODEX_CONFIG` and implied
    codex had eight driver vars. It now agrees with the skills — nine for codex, ten
    for claude and opencode, `RELAY_MAX_TURNS` a sidecar value no driver reads.
  - The one-shot execution paragraph moved into both preambles (acpx and
    bg-sessions), so every child reads it once. The seven writer roles keep one
    sentence naming the mode plus their own two or three checklist items, in the
    same words in every file. The fixers' pre-flight base pin keeps its command, its
    byte-for-byte compare, and `BLOCKED: base-mismatch`, with two sentences of
    explanation instead of a page.
  - The five UI roles each carry one browser skeleton; later checks are
    `page.evaluate` one-liners, and the four evaluators share the same three
    Constraints lines. The two simulators share an identical Grounding block; the
    panel trio states the sidecar-only and no-web rules in one sentence each.
  - Word counts: dispatch skills and doc 9245→8529 (the doc grew by the tables it
    absorbed), preambles and writer roles 5518→5190, UI roles 4521→3628, simulators
    and panel 2547→2442.

## 4.42.0 — 2026-08-24

### Changed

- **The five L3 commands lose their shared-block essays.** PR 3 of the
  prompt-optimization plan. `drive`, `execute`, `implement`, `refine`, and `diagnose`
  were built from about nine near-verbatim shared blocks — the retro-target comments,
  the positional-parse warning, Step 0.2 retro-only mode, Step 0.25 ask-when-unpinned,
  the tier note, the verify-node guard, the Step 3.5 gates lecture, the Step 4
  completeness gate, and the Step 5 retro war story — and each block carried its
  design history in full, in every file. Each history is now one clause. Every
  mechanic, every pinned sentence, every sed regex, and every echo line is unchanged,
  and no command points at a skill or doc in place of its own content.
  - `implement.md` states the `--verify` equals implement-then-verify invariant once,
    at Step 2, and keeps the full `--gates` semantics as the only copy; the
    session-tree skip paragraphs are bare skip lines.
  - `refine.md` states the env-vars-do-not-survive-Bash fact once, where the
    injection happens, and says what Step 1 feeds.
  - `drive.md` replaces the classify-the-oracle derivation with one sentence and
    refers Step 3 back to Step 2's spine.
  - `verify.md` keeps its executed bash fence byte for byte and drops the intro copy
    of the axis-inert fact.
  - Word counts: diagnose 1475→796, execute 2118→1358, refine 2545→1758, drive
    3014→2033, implement 2317→1967, verify 1169→760. Each file stops at its pinned
    floor — executed fences, option copies, and pinned sentences — so the inventory's
    per-file targets were not reached and no mechanic was cut to reach them.

## 4.41.0 — 2026-08-24

### Changed

- **Unpinned prose cuts across 35 prompt files (about 3,770 words out).** PR 2 of
  the prompt-optimization plan. No mechanic changed, no envelope token changed, and
  no test was edited except the version ratchet, so every remaining rule is one the
  suite already pins or one a role still needs. What went:
  - `agents/strategist.md` and `agents/analyst.md` lost the reasoning frameworks
    that restated their JSON schema field by field. The strategist keeps one scope
    sentence; the analyst keeps two sentences on weighing evidence. `gatherer`,
    `leaf-reader`, and `leaf-worker` state each prohibition once.
  - Fifteen role files lost their intra-file repeats: the same rule stated three or
    four times in one body, a rubric copied word for word, a Role paragraph that
    pre-narrated every step. The cross-engine fences stay, once each.
  - `using-relay` points each command at its backing skill instead of restating the
    command table. `ensuring-worktree-isolation` merges the `main` and `stray`
    sections into one section keyed by base ref, and drops the summary table.
    `driving-to-done` states each invariant once.
  - The `refining` family: one shared landing-verify block instead of two copies,
    one statement of the never-read-the-axis-from-env rule, no leftover `[inferred]`
    tags. `refining-plans` and `refining-specs` are now frontmatter, announce line,
    config, and one sentence. `refining-ui`, `refining-prs`, `running-web-apps`, and
    five smaller skills each lost one restated block.
  - Emphasis policy: caps and bold are gone wherever they were not test-pinned and
    not fencing a documented failure.

## 4.40.0 — 2026-08-24

### Fixed

- **The acpx preamble told a blocked child to emit a token the watcher does not route
  on.** The last paragraph asked a fire-and-forget child that hit a forbidden prompt to
  return a key-value failure token. The watcher classifies on `^BLOCKED:` as the first
  non-empty line, so those tokens matched the generic envelope regex and were captured as
  stray values instead of reaching the blocked bucket. The paragraph now names `BLOCKED:`
  and its first-line placement. It also promised that the orchestrator routes a
  context request through a panel and re-dispatches the child; no such path exists, so
  that sentence is deleted rather than reworded.

- **`routing-work-to-agents` had no row for two kinds the classifier emits.** `feature`
  and `bugfix` now route as `coding`. A new **When not to dispatch** section names the
  three cases where the orchestrator does the work itself and returns `provider: "none"`,
  because dispatch overhead must be smaller than the work it moves.

- **The two simulators and the code reviewer told their agents to report less than they
  find.** "Flag only genuine gaps" and "blockers and importants only" made the critic the
  filter. The caller filters by severity, so each critic now reports every finding with a
  severity label and pre-filters nothing. The `UNVERIFIED:` prefix rule stays; the clause
  claiming a wrong finding costs more than a missed one is gone, because it argued for the
  under-reporting the prefix already handles.

- **`ui-generator` and the acpx preamble gave one child two opposite commit rules.** The
  role is delegate-eligible, so both texts can reach the same child. The role now states
  the precedence: under acpx dispatch, the preamble's no-commit rule wins.

- **`RELAY_MAX_TURNS` was counted as a driver env var in one skill and not the other.**
  `delegate-and-watch` folded it into its 10-var and 11-var driver groups; the driver
  contract does not pass it to any driver. Both skills now state it identically as a
  sidecar value read by the watcher, and the counts read 9 for codex and 10 for
  claude/opencode on both sides.

- **Drift fixes.** `strategist` no longer claims a phase in a pipeline the plugin absorbed
  years of releases ago. `scout` states the one artifact it may write instead of claiming
  it writes nothing, and drops the CI-discovery step whose result had nowhere to go in the
  summary schema. `implementer` documents `REPO_ROOT`, its landing-verify target.
  `ui-visual-evaluator` no longer claims every leaf renders images: it names the claude
  path that does, and tells the codex and opencode paths to score from DOM evidence and
  report the degrade. `gatherer` documents the free-form prompt its only caller sends,
  replacing a structured command contract that no caller ever passed.

- **Length calibration.** `plan-writer` and `fix-planner` each state that plan length
  tracks the size of their input, so a small spec or a short findings list does not get
  padded into many steps.

## 4.39.3 — 2026-08-24

**Patch — the spine records the caller that actually ran.**

- **`relay:running-implement-spine` now takes a `command` input, and Step 3.5 passes it
  to `scripts/record-run-intent.sh`.** The call hardcoded `--command implement`. That
  was correct in 4.37.0, when the text still lived in `commands/implement.md` and only
  that command could reach it. 4.38.0 moved the text into the skill and carried the
  literal across unchanged, and 4.39.0 gave the skill a second caller. From that point
  every `apk`-driven run through `relay:implementing-spec` was written to
  `~/.claude/relay/runs.jsonl` with `relay_command: "implement"`, and a later
  `scripts/retro-run.sh` printed `RELAY_RETRO_COMMAND=implement` for a run that
  `/relay:implement` never started. Nothing failed and nothing was blocked — the record
  simply named the wrong caller, which is the one question a run record exists to answer.
- **Both callers now pass their own name.** `/relay:implement` passes the literal
  `implement`, and `relay:implementing-spec` passes `implementing-spec`. The command's
  own prose moved from "Pass all nine inputs" to "Pass all ten inputs", and a new test
  parses that count word out of the prose and compares it against the bullets the skill
  declares, so the next input added to one file and not the other fails the suite
  instead of drifting.
- **Same class of defect as 4.39.1 and 4.39.2, found the same way.** Those two releases
  closed the identical gap for `engine`, `axis_source` and `--gates`: a value that was
  true while the spine had one caller, and became a lie when the second one arrived.
  This was the fourth such value and the last one in the Step 3.5 call. A
  `/code-review` child inside a `/relay:verify` round surfaced it and applied no fix,
  so it is fixed here by hand with the regression tests it lacked.
- **Rejected: deriving the command from the environment.** The skill could have read
  `$RELAY_ENGINE` or some other variable that only `/relay:implement`'s Step 0 exports,
  and treated its absence as the adapter path. That inverts the rule the adapter already
  states in its own body — the adapter exports none of that command's environment, and
  the spine must read every value from its declared inputs. An input that is passed is
  checkable; an absence that is inferred is a guess that reads as a fact.
- **Also fixed: a flaky assertion in `test_the_check_node_does_not_retry_after_a_timeout`.**
  The test ran the check node under a one-second budget and asserted that exactly one
  child had started. Zero is also correct there, and `scripts/verify-loop-node.sh` says
  so in its own comment: the node does git calls and state reads before it starts a
  child, so at a tight budget that work can spend the whole budget and the first child
  is refused with `node-budget-spent-before-child-started`. On that path the counter file
  is never created and the test died with `FileNotFoundError` instead of failing on its
  own subject. Measured at 2 failures in 40 local runs, and it turned the `relay suite`
  check red on a branch whose product code it does not touch. The identical race had
  already forced the neighbouring `test_a_slow_child_is_recorded_as_a_timeout` to pin a
  pair of causes rather than one; this test was missed at that time. It now asserts
  `<= 1` child, which is the retry it exists to catch, plus `NODE_STATUS=failed:timeout`,
  so a zero-child run cannot pass without recording the timeout. 60 consecutive runs pass.
  No product code changed.

- **Rejected: a closed set of allowed `--command` values.** `record-run-intent.sh`
  accepts any non-empty value by design, and `retro-run.sh` only prints it back. Adding
  an enum would put a third file in the path of every new caller for no reader that
  needs it.

## 4.39.2 — 2026-08-22

### Fixed

- **`relay:implementing-spec` reads its inputs the way `apk` really sends them.** The
  skill said `apk` calls it as a `skill()` Workflow node and passes one object with
  three keys. That is wrong in both halves. `skill()` is not a Workflow primitive, and
  `apk/tests/unit/test_workflow_primitive_contract.py` forbids that call form outright.
  `apk/phases/build.md` dispatches `agent(prompt, {agentType: 'general-purpose', schema})`
  and puts `spec_path`, `branch_hint`, and `closes_issue` in the prompt as plain
  `key: value` lines. A reader told to look for an object could find no input at all.
  The skill now shows the exact line format and states that no caller sends a
  structured argument. The design spec §2 carried the same error and is corrected.
- **The `--gates` rule keys on the `verify` input, not on the `--verify` flag.**
  `relay:implementing-spec` passes no flags and always sets `verify=true`. A literal
  reader on that path recorded `verify-loop=false` for a run whose loop did dispatch,
  which corrupts the retro record.
- **`relay:implementing-spec` names its round cap.** Step 6 asked for "a round cap"
  while `relay:running-implement-spine` declares `rounds` as required. It now passes
  `$RELAY_VERIFY_ROUNDS`, or `3` when the environment supplies none.
- Removed the command-era wording left in `relay:running-implement-spine` by the
  4.38.0 extraction ("this command generates no second Workflow", "the one skippable
  role on this command"). The file is a skill.

## 4.39.1 — 2026-08-22

### Fixed

- **`relay:running-implement-spine` now runs on the `relay:implementing-spec` path.**
  4.38.0 moved the verify-until-clean tail and its Step 3.5 bookkeeping out of
  `commands/implement.md` verbatim, but left them gated on facts only
  `/relay:implement`'s own Step 0 and Step 1 produce: `enabled=1`, `$RELAY_ENGINE`,
  and "the last Step 0 axis line". `relay:implementing-spec` runs no Step 0 and no
  Step 1 — it passes `verify=true` and a resolved `engine` as plain object keys — so
  on that path the tail's gate was unsatisfiable and the loop-engine `case` fell
  through to its `*` arm, printing `engine= has no verify-loop substrate` on every
  run. A healthy `apk` build therefore reported `error` instead of `ok`.

  The tail now gates on the skill's own `verify` input and reads the loop engine from
  its own `engine` input. The skill declares a new `axis_source` input for Step
  3.5's `--axis-source` flag: `/relay:implement` forwards the source printed on its
  Step 0 axis line, and `relay:implementing-spec` passes `relay.json` or `default`
  from its own pin resolution. The `session-tree` skip conditions in Steps 3, 3.5,
  and 4 now state plainly that they are always false on the adapter path, since
  `relay:implementing-spec` never runs `commands/implement.md`'s Step 1.

## 4.39.0 — 2026-08-22

### Added

- **The `relay:implementing-spec` adapter (#75).** `apk/bin/check-deps.sh` probes on
  disk for `skills/implementing-spec/SKILL.md` and blocks the whole `apk` run when it
  is absent; `apk/tests/unit/test_cross_plugin_skill_names.py` pins the name. This
  skill is the file that probe finds. It is an adapter, not a second pipeline: it
  reads `spec_path`, `branch_hint`, and `closes_issue` from the object `apk`'s build
  phase passes, gates the spec on `lifecycle_state: specified`, asks nothing, makes no
  worktree, keeps the branch it finds, sets `kind=feature` and `verify=true`, and
  delegates the whole run to `relay:running-implement-spine` — the same skill
  `/relay:implement` calls.

  It returns `{status, pr_url?}`. `status` is `ok`, `blocked`, or `error`; `apk` only
  tests `result.status !== 'ok'`, so relay owns the three-value vocabulary. `blocked`
  covers a missing spec file or the wrong `lifecycle_state`. `error` covers a spine
  failure or a verify loop that reported `findings` or `unverified`. `ok` requires
  both a finished spine **and** a made commit — a run with no commit never reports
  `ok`.

  `pr_url` stays in the object for compatibility and is **always absent**. This
  design does not add pull request creation to relay: the run stops on a branch that
  holds a commit, and a person must open the pull request. `closes_issue`, when the
  caller supplied it, goes into the commit body as `Closes #<n>`, so that later pull
  request keeps the link. `docs/contributing.md`'s `EXPECTED_SKILLS` count moves from
  18 to 19.

## 4.38.0 — 2026-08-22

### Changed

- **`/relay:implement`'s Workflow-generation steps now live in a new skill,
  `relay:running-implement-spine`.** The command generated the Workflow, resolved the
  per-leaf tiers, recorded the run intent, and ran the completeness gate all inline —
  Step 3, Step 3.5, and Step 4. That prose is what `relay:implementing-spec` (a later
  change) must also run, and a command cannot be called from a skill. Step 3, Step 3.5,
  and Step 4 move verbatim into `skills/running-implement-spine/SKILL.md`,
  `user-invocable: false`, the same pattern `skills/driving-to-done/SKILL.md` set for
  `/relay:drive`.

  `commands/implement.md` keeps Steps 0 through 2, the §4.2.1 branch table, and Step 5's
  retro. In their place, a new `## Step 3 — Run the spine` section invokes
  `relay:running-implement-spine` with the eight inputs the skill declares — `kind`,
  `task`, `spec_path`, `engine`, `agent`, `verify`, `rounds`, `closes_issue` — and reads
  the skill's one fenced JSON output block:
  `{"status": "ok", "run_id": "wf_...", "branch": "...", "commit": "abc1234"}`.
  `status` is `ok`, `blocked`, or `error`; a non-`ok` status carries a `reason` in plain
  words, and Step 5 now reads `run_id` from this block instead of from the `Workflow`
  tool result. The command shrinks from 408 lines to 248.

  `scripts/validate_l3_command.py`'s `_KNOWN` vocabulary gains `running-implement-spine`,
  and `docs/contributing.md`'s `EXPECTED_SKILLS` count moves from 17 to 18.

## 4.37.0 — 2026-08-22

### Fixed

- **`using-relay` now points at the one spine authority instead of stating a second, disagreeing
  spine** (#77). The skill's `Implement` bullet listed a full pipeline — scout → brainstorm →
  refine spec → write plan → refine plan → execute every task → verify spec → write e2e tests —
  that named four nodes absent from the §4.2.1 branch table in `commands/implement.md` and left
  out `write-plan` and `commit`. Because `commands/implement.md` is a command and not
  model-invocable, a model read `using-relay` and built the wrong Workflow.

  The bullet also closed with a stale promise: "closes out the worktree via
  `superpowers:finishing-a-development-branch`." Relay opens no pull request. No node in the
  §4.2.1 branch table ever called that skill. A person must open the pull request.

  Both the node list and the closeout sentence are deleted, with no replacement copy in any
  form — not even one that matches the table as it reads today. In their place, the bullet
  states one sentence: the spine's one written authority is the §4.2.1 branch table in
  `commands/implement.md`. The `Commands` table row for `/relay:implement` pointed at "the
  language-reference doc" for phase details; it now points at the same §4.2.1 branch table, so
  both pointers name one authority.

  A new test class, `TestUsingRelayNamesNoSpine`, parses the branch table's node labels out of
  `commands/implement.md` itself — not a hard-coded list — and asserts every label it finds
  still lives in the file `using-relay` points to, and that `using-relay`'s `Implement` bullet
  carries no arrow-chain spine list of its own.

## 4.36.0 — 2026-08-22

### Fixed

- **The `feature` spine now writes the plan it refines, and every kind now commits the work
  its leaf made** (#86, #78). The §4.2.1 `feature` row was `refine-spec → refine-plan →
  implement → verify`. It refined a plan that no node ever wrote, and no row in the branch
  table ever committed the leaf's work.

  The `feature` row gains a conditional `write-plan` node between `refine-spec` and
  `refine-plan`. It dispatches `plugins/relay/roles/plan-writer.md` through
  `relay:delegate-leaf`, and runs only when no file under `docs/plans/` matches the spec slug;
  a present plan skips the node. A run with no spec file at all skips both `write-plan` and
  `refine-plan` and goes straight to `implement`.

  The role prints `PLAN_PATH=<path>`, but the plan adapter at `skills/refining/adapters/plan.md`
  reads a lower-case `plan_path` — a case mismatch, and nothing bound the two. The `write-plan`
  node now binds them with the literal line `plan_path = PLAN_PATH` before `refine-plan` runs.

  Every kind's row now ends `commit → verify`. The `commit` node runs in the coordinator, never
  in a leaf — `roles/implementer.md` stays read-only on git. Its message is
  `<type>(<scope>): <summary>`: `feature` gives `feat`, `bugfix` gives `fix`, `docs` gives
  `docs`, and `script` and `config-artifact` give `chore`. The scope comes from the spec slug,
  or from the top directory the diff touches when there is no spec. The body adds
  `Closes #<n>` when the caller supplied `closes_issue`. An empty `git status --short` fails the
  node and the run reports `error` — a run that changed no file is not a clean run.

  The Step 3.5 `--spine` example for `feature` is now
  `refine-spec,write-plan,refine-plan,implement,commit,verify,verify-loop`, and the `--gates`
  placeholder now carries `write-plan=false` alongside `verify-loop=false` for the node the
  condition skipped.

  `skills/refining/SKILL.md` defines a new failure token, `SUBJECT_MISSING`: when `load()`
  finds no subject at the given path, it returns `SUBJECT_MISSING` and the refinement loop
  halts instead of reading an absent plan as an acceptable one.
## 4.35.0 — 2026-08-20

### Fixed

- **A step that is entered twice can no longer overwrite its own record.** Run
  `wf_59fede2c-9e2` forked into two live chains inside one session. Both chains ran the
  `review` step. The second chain deleted the first chain's reply, recorded
  `REVIEW=failed:no-reply` over the first chain's `REVIEW=ran`, then recorded
  `REVIEW=skipped` on top of that, and the report's `tail -1` read kept only the last,
  corrupted line.

  That run ended `unverified`, but not because the report saw the damage. The report
  printed `RELAY_VERIFY_MISSING=0` and `RELAY_VERIFY_FAILED=0`, because `skipped` is an
  approved value. What stopped it was the 4.34.0 `write_state` call, which had already
  put `EXIT=unverified` in the state file. Driving the 4.33.0 report and the 4.34.0
  report against that same record, under a state line that says `EXIT=clean`, makes both
  print `RELAY_VERIFY_RESULT=clean`. The same hole reaches a false clean directly as
  well: a re-entered `check` whose second reply carries `PASS` overwrote a recorded
  `LABEL=findings`, and the fix step then never ran.

  Guard 5, the fifth of the guards this script keeps, closes the hole. Every step now
  claims its record key with an atomic
  `mkdir` before it writes a terminal record line. `mkdir` either makes the claim
  directory or fails; it cannot half-succeed, so exactly one caller ever wins the claim,
  even when two chains run the same step at the same time. A caller that finds the claim
  already held answers `NODE_STATUS=already-done` and changes nothing: it does not touch
  the reply file, does not overwrite the step's `.out` file, and does not move the loop
  state. The `check` step takes its claim only after the retry decision, so the
  documented `NODE_RETRY=1` cycle still records a verdict.

  The report node's gate is now hard, not advisory: it counts how many terminal lines
  each record key holds, not only the last value. A record holding two `REVIEW=` lines
  prints `REVIEW=conflict:ran/skipped` and counts as a failed step, so the run can never
  again print `clean` over a record the write-once claim (guard 5) did not protect.

## 4.34.0 — 2026-08-20

### Fixed

- **A run that records a step failure can no longer print `clean`.** The report node's gate
  checked only for a missing key. A step that ran and recorded its own failure, such as
  `SIMPLIFY=failed:no-reply` or `REVIEW=failed:2`, still counted as present, so the run could
  still print `RELAY_VERIFY_RESULT=clean` over a step that had already failed. The gate is now
  a positive allow-list over the recorded value, not a list of known failure values: the only
  values that pass are `ran`, `skipped`, and, for the `FIX` key only, `fix-noop`. A value the
  script has not yet invented is blocked too, the same as a known failure value, because a
  deny-list fails open on exactly that case. The report also prints the new failed-step count as
  `RELAY_VERIFY_FAILED=<n>`, and a blocked clean names the cause with
  `RELAY_VERIFY_REASON=failed-step steps=<n>`, joined with `incomplete-round steps=<n>` on one
  line when both causes fire in the same run.

- **`simplify` and `review` now end the run at the source.** When either step's child returns
  no reply (`rc 65`) or any other non-zero code that is not one of the already-handled cases,
  the node now marks the run `unverified` right there, the same way it already did for `rc 69`
  and `rc 124`. Before this fix, a run left the state file reading `EXIT=continue`, so the loop
  could burn up to two more rounds and several more child turns chasing a result the report was
  always going to block.

## 4.33.0 — 2026-08-20

### Fixed

- **A run that holds a missing step can no longer print `clean`.** The report node counted the
  step records it did not find, printed the count as `RELAY_VERIFY_MISSING=<n>`, and then
  decided the result from `EXIT` and `LABEL` alone. Those two fields come from the check node's
  `/verify` verdict, which no other step can influence, so a mandatory step that never ran was
  invisible to the result. `clean` now also requires `missing` to be `0`.

  Run `wf_6f6f4d1a-4d3` is the case that found it. Its review node ended its model turn between
  `pre` and `post`, while its own `/code-review medium --fix` subagent was still running, so no
  `REVIEW=` line was ever written. The loop printed `RELAY_VERIFY_RESULT=clean` next to
  `RELAY_VERIFY_MISSING=1`, and `/relay:implement --verify` would have reported that whole run
  clean on the strength of it. The report was not short of evidence. It printed the count on the
  line above and did not read it.

- **A blocked clean names its cause.** When the gate stops a clean result, the report prints
  `RELAY_VERIFY_REASON=incomplete-round steps=<n>` before the result line. A bare `unverified`
  under a passing verdict reads as a loop that broke, rather than as a loop that did not account
  for one of its steps. The line prints only on the path the gate blocks, so it never sits beside
  a result it does not explain.

- **The spec stated a rule too weak to hold.** `skills/verifying-until-clean/SKILL.md` promised
  that `missing` is "never read as a pass" and that it "never turns a `findings` result into
  `clean`". Both clauses were true, and the first was true only because `missing` was never read
  for anything — prose satisfied by omission. The skill now states the rule as a gate: a run that
  holds any missing key cannot print `clean`.

- **The test suite pinned the defect.** `test_clean_is_printed_only_when_the_last_label_is_clean`
  handed `report` an init-only tree, in which all four keys are missing, and asserted `clean`. It
  now builds a fully recorded round. Three tests are new:
  `test_a_round_with_a_missing_step_is_never_clean` reproduces the live run's record shape,
  `test_a_blocked_clean_names_its_cause` pins the reason line, and
  `test_a_complete_clean_run_names_no_cause` pins that the reason line stays off the honest path.

### Known, and not fixed here

- The in-session node prompt never binds a node to finish its `post` call in the same turn, and
  it never says that the command a node starts may dispatch a subagent of its own — which
  `/code-review medium --fix` always does. That gap is what left the record missing. This release
  stops the loop reporting such a run as clean. It does not make the review step run. Both changes
  are needed before the loop does its whole job, and they are separate changes.

## 4.32.0 — 2026-08-20

**`/relay:verify` takes `--engine` and defaults to `in-session`. The default path asks no
question at all: it starts no child process, so the approvals-off consent step now runs
only under `--engine acpx`.**

**Why:** the question added in 4.25.0 was a patch on a substrate choice, not a goal. Every
step of the loop ran as an `acpx --approve-all` child session, which is exactly what the
auto-mode rule `Create Unsafe Agents` refuses, so a question was the only way to clear it.
The substrate choice rested on one sentence in
`skills/verifying-until-clean/SKILL.md`: *"Claude cannot invoke a slash command from inside
its own model turn."* Relay 4.30.0 already contradicted that — it dropped
`disable-model-invocation` from this very command precisely because the model can start a
command through the `SlashCommand` tool. Remove the child process and the rule has nothing
to match, so the question has nothing to ask about.

- **`commands/verify.md` resolves the axis with `scripts/parse-engine-agent.sh`,
  unchanged.** That script already defaults the engine to `in-session` and already
  enforces `in-session` ⇒ `agent=claude`, so an `.claude/relay.json` engine pin behaves
  here exactly as it behaves for `/relay:implement`. The loop carries a substrate for
  `in-session` and `acpx` only; `smart-routing`, `bg-sessions` and `session-tree` are
  rejected at Step 0 with the message shape `commands/execute.md` already uses. None of
  the three carries this loop's deadline, its state directory under the git directory, or
  its commit per round, so claiming them would be prose with no implementation behind it.

- **`scripts/verify-loop-node.sh` gains `--phase pre` and `--phase post`.** Bash cannot
  make a tool call, so an in-session node cannot reach its command from inside the script.
  `pre` reads the state, decides skip or run, and prints the command plus the path to write
  the reply to. `post` reads that reply, parses the verdict, commits, writes the record and
  prints `NODE_STATUS`. Every decision stays in the script — including the retry — so the
  node reads one line and makes no judgement. `init` and `report` start no child in either
  engine and reject `--phase` rather than ignoring it.

- **The node carries out the block; it does not pass it to a tool as a name.** A live
  in-session run found the first node prompt unexecutable. It said to invoke the text between
  the markers through the `Skill` tool, but that tool takes a skill name, and only `simplify`
  holds a bare command: `review` carries arguments, `check` adds a verdict contract under the
  command, and `fix` holds no command at all. A started command also returns its instructions
  rather than its result, so a node that wrote back what the tool returned wrote instruction
  text — and for `check` that is no verdict line, which is `no-answer` every round and
  `unverified` on every run of the new default engine. The node now starts the command with
  `SlashCommand`, does the work, and writes its own closing answer, which is the same artifact
  an acpx child leaves as its final text. `TestTheInSessionNodePromptIsExecutable` pins the
  rule and the reason together.

- **The acpx path is byte-identical.** Without `--phase` the script starts the child itself,
  `run_child` is untouched, and `run-claude-command.sh` and `run-claude-prompt.sh` are not
  changed at all. The locked contract covered by `test_relay_implement_polish.py` still
  holds.

- **A claimed run is weaker evidence than a started run, and the skill says so.** With acpx
  the script starts the child, so a record proves a step ran; in-session the node hands the
  reply back, so a record is a claim. Four mechanical guards stop a fabricated pass from
  being recorded: `pre` deletes the reply file, so a file present at `post` time was written
  after `pre` ran; `pre` writes a marker only where a command must be invoked, and `post`
  reports `failed:no-pre` without it, so a stray `post` cannot overwrite a skip with a
  failure; an absent or empty reply is `failed:no-reply`, never a pass, and `check` does not
  retry it, because no reply is the absence of an attempt and not a verdict of a bad shape;
  and `post` builds the `POLISH_CMD_OUTPUT_*` fence itself around text it treats as opaque,
  so the node cannot forge one. The skill states the limit plainly: the guards do not make a
  claimed run equal to a started run, and only `--engine acpx` removes that possibility.

- **`RELAY_VERIFY_NODE_TIMEOUT` applies to acpx only, and this is a removal rather than a
  gap.** The deadline guards one thing: a child that outlives the node's single Bash call
  and is killed before the record is written. In-session the long step is a model turn and
  the two Bash calls take milliseconds, so that failure cannot happen. The deadline is not
  carried across the two calls either — each is a separate process, and by the time `post`
  runs the work is already done, so refusing an expired deadline there would discard work
  that really happened. `failed:timeout` never appears on an in-session round.

- **`/relay:implement --verify` forwards the engine this run resolved,** so the two paths
  stay equal. Implement accepts three engines the loop cannot run; the tail prints
  `engine=<name> has no verify-loop substrate — the loop runs in-session` and runs the loop
  in-session. The substitution is printed, never silent. A hard rejection at the tail would
  throw away a finished build over its last step.

- **Not changed:** the three terminal states, the verdict-to-label map, the round-1 reset,
  the acpx session names, the one loop identity, and every fail-closed rule. The engine
  picks a substrate. It renames no node, no session and no directory.

- **Tests:** a new `tests/unit/skill-structure/test_verify_loop_in_session.py` drives the
  real script through the two-call protocol — the guards, the retry, the rejections, and
  the acpx single call. `test_verify_loop.py` replaces the two assertions that pinned "no
  engine axis here" and adds the conditionality of the question; the consent assertions
  themselves all stay, because the acpx path still needs every one of them.

- **Design:** `docs/superpowers/specs/2026-08-20-relay-verify-engine-flag-design.md`.

## 4.31.0 — 2026-08-20

**Two new dispatch engines built on Claude Code background sessions and cross-session
messages: `--engine bg-sessions` for per-leaf dispatch, and `--engine session-tree`,
the second documented exception to relay's one-Workflow doctrine.**

**Why:** a Workflow agent node has exactly one turn — it cannot receive a message, so
it must hold its turn open and poll (`delegate-and-watch`, TURN-LIFETIME RULE). A
background session is different: it ends its turn to wait, and an incoming message
starts a new turn. That property is what lets a headless run ask a person a question
instead of guessing. Live spikes proved four things before any of this shipped: two-way
messaging between sessions, fork-identity hazards, a three-level tree, and four typed
failure signals. This release is grounded in those findings (S1–S4,
`docs/superpowers/specs/2026-08-18-bg-session-messaging-spike-findings.md`) and built in
the fixed order the design spec requires: contract → bg-sessions → session-tree.

- **The contract layer, `docs/bg-dispatch-contract.md`, plus `scripts/bg-launch.sh` and
  `scripts/bg-liveness.sh`.** Both engines stand on it; neither may deviate. The most
  load-bearing rule in it: the child's `state.json` **never answers "did it succeed."**
  `state` reports turn posture, not task outcome (S4-2) — `bg-liveness.sh`'s verdict is
  about presence, never about success. The envelope, read from a message body or a
  handoff file, is the only truth about completion.
- **The prompt-last rule, and the idle children that taught it (launch trap 1).** The
  spikes hit background sessions that sat idle forever with an empty `intent` because a
  variadic flag (`--allowedTools`, …) placed before the prompt silently swallowed it.
  `bg-launch.sh` builds `claude --bg --name … --model … --permission-mode … "<prompt>"`
  with the prompt as the strict last argument, names no variadic flag anywhere in its
  body, and a test asserts that absence directly.
- **`LAUNCH_DENIED` is a normal, honestly-reported outcome (launch trap 2), not an
  assumption that the child exists.** A classifier refusal, an unparseable short id, and
  an `intent` still empty at the wait ceiling (`RELAY_BG_LAUNCH_TIMEOUT_SECONDS`, default
  15) all report this one typed outcome. `dontAsk` is refused outright as a permission
  mode: a child under it cannot run Bash (S3-1), and `bg-launch.sh` never selects it and
  never lets a caller reintroduce it.
- **`state=done` maps to `alive`, not `stopped`.** Some Claude Code versions write `done`
  instead of `blocked` at end of turn — a child mid-multi-turn that reads `state=done` is
  idle between turns, not gone. This is the one row of the `state` → verdict table a later
  reader is most likely to "fix," so `bg-liveness.sh` says so directly in its own
  comments and carries a named test, `test_done_is_alive_not_stopped`. `updatedAt` age
  downgrades an alive verdict to `stale` past `RELAY_BG_STALE_SECONDS` (default 900); it
  never reclassifies `stopped`, `failed`, or `unknown`.
- **Two provisional tokens, `DECISION: <answer>` and `ESCALATION from <origin>:
  <question>`, and the frozen set is unchanged.** They carry the downward reply to a
  `NEEDS_DECISION:` and an operator's relay of a child's question upward — kept distinct
  from `BLOCKED:` so a relay is never read as the operator itself being stuck. Both live
  in `docs/bg-dispatch-contract.md` and in their own test file,
  `tests/unit/skill-structure/test_provisional_tokens.py`, which never touches
  `test_envelope_tokens.py`. A message matching none of the grammars is logged and moves
  no run state — the countermeasure to S2-3, where a confused fork sent stand-down orders
  as prose.
- **`--engine bg-sessions`**, the per-leaf engine. `scripts/parse-engine-agent.sh` gains
  the enum value with the invariant `bg-sessions ⇒ claude` (no codex leg, the same shape
  as `in-session`). The new skill `relay:dispatching-bg-agents` mirrors
  `relay:dispatching-acpx-agents` but launches through `bg-launch.sh` and reads the
  child's envelope from a per-run handoff file
  (`$WORKTREE/.relay-bg/<runid>/<role_slug>.envelope`, truncate-then-write, `TURN=<n>`
  discipline) instead of stdout, because a background child has no parent session to
  message. `bindings/presets.yaml` gains no field — the existing `delegate_eligible` flag
  and `modalities.claude` tier are enough. **D2.0 check:** can a Workflow watcher node
  send a message to a named session? No live session harness was available to run this
  check in either engine's implementation task, so both bg-sessions and session-tree ship
  under the spec's own stated fallback rather than an unverified assumption: bg-sessions
  restricts multi-turn dispatch to `delegate_eligible` roles (`bg-dispatch.sh` refuses a
  non-eligible role with a typed error), and every role in `bindings/presets.yaml` today
  carries `one_shot: true`, so the restriction costs nothing in practice yet guards a
  future non-one-shot role from silently taking the unverified path.
- **`--engine session-tree`**, a new substrate — the second documented exception to
  "every L3 command generates one Workflow," alongside `/relay:drive`.
  `docs/orchestration-substrates.md` now states there are two substrates, not one, and
  names the exception. Under `session-tree`, `/relay:implement` generates no Workflow at
  all: MAIN becomes the orchestrator, spawning every session flat through `bg-launch.sh`
  (a child under `dontAsk` cannot spawn — S3-1) and tracking the tree in a run manifest
  (`~/.claude/relay/runs/<runid>/manifest.json`, kept by the new `scripts/bg-manifest.sh`,
  rewritten atomically on every spawn and envelope). A manifest write failure is
  **FATAL** — the opposite of `record-run-intent.sh`'s advisory doctrine, because the
  manifest is the only resume path a session-tree run has; `record-run-intent.sh` itself
  is unchanged and never runs here, since session-tree allocates no `wf_…` id. The new
  skill `relay:orchestrating-session-trees` holds the orchestrator prose: spawning,
  question routing (`NEEDS_DECISION` worker → operator → orchestrator, `ESCALATION from
  …:` when the operator cannot answer, `AskUserQuestion` only in an interactive run and
  by message to the parent session when headless), and the end-of-run stop protocol
  (finish-and-stop by name, confirm `stopped` via `bg-liveness.sh`, name any child that
  would not stop). **D3.0 check:** does an inbound message re-invoke an idle MAIN session
  mid-slash-command, with its run state intact? Also unverifiable live in this task, for
  the same reason as D2.0. Per the spec's own fallback, v1 uses a bounded foreground poll
  over the manifest instead of free waiting — the same shape `delegate-and-watch`'s
  watcher uses — and the skill's `## Waiting` section states the fallback plainly rather
  than claiming an unproven property. Both `[unverified]` checks must be re-run live
  before their engine's next material change, per the contract's own Live validation
  procedure.
- **v1 caps, named where they bind.** session-tree allows at most one operator per goal
  and three workers under it; the run's report states the cap when it binds. Deliberately
  not done in this release: no codex/opencode workers in either bg engine (the acpx leg
  keeps them), no fan-out past the v1 cap, session-tree covers the `/relay:implement`
  spine only (`refine`/`execute`/`drive` reject it with a standard
  engine-not-supported error), smart-routing does not learn either bg leg, and no token
  cost accounting beyond noting it is unknown in the manifest.

## 4.30.0 — 2026-08-19

**The model can invoke `/relay:implement` and `/relay:verify`.**

**Why:** all eight relay commands set `disable-model-invocation: true`, so only a human
could start them. That fit the setup and diagnostic commands, but it blocked useful
automation: an agent that plans a change could not hand the build to the implement
pipeline, and an agent that lands a branch could not start the verify loop.

- **`commands/implement.md` and `commands/verify.md` drop `disable-model-invocation`.**
  The model can now start both commands through the SlashCommand tool. The other six
  commands keep the flag: setup, engines, and diagnose are interactive by design, and
  drive, execute, and refine stay human-started.
- **No body change.** Both commands parse, gate, and run exactly as before. The only
  change is who may start them.

## 4.29.0 — 2026-08-16

**The verify loop states the verdict line it needs, stops retrying a format it cannot
change, and holds one deadline for the whole node.**

**Why:** run `wf_918a4deb-aba` spent three full rounds and verified nothing. All six
simplify and review nodes ran. All three check nodes reported `CHECK=missing`. Two defects,
and the first one started the second.

- **The check node sends the verdict contract with the command.** `/verify` is not relay's
  command: it resolves to whatever the repository defines, and a repository that holds its
  own `verify` skill can prescribe no report format at all. The child answered
  `## Verify result: productivity v0.7.0 — PASS`, which holds no verdict token, so the
  parser read `no-answer`. The loop could not report `clean` in that repository at all. The
  node now names the exact line to print. The text starts with `/`, so the slash-only guard
  in `scripts/run-claude-command.sh` is **untouched**.
- **The contract uses the enum template, not a one-token example.** A child that copies the
  contract back writes four verdict tokens on one line, and the one-token rule rejects it. A
  copied `**Verdict:** PASS` would have been read as a real pass.
- **A reply that holds no verdict line is no longer retried.** `parse-verify-verdict.sh` now
  names the cause on stderr — `VERIFY_REASON=no-output-fence` or
  `VERIFY_REASON=no-verdict-line` — while its two stdout lines and its exit codes stay the
  same. A missing fence is temporary and is still retried once. A missing verdict line is
  deterministic, so the retry only spent a child. The record and the report now carry
  `REASON=`.
- **The node budget is a deadline, not a per-child limit.** `RELAY_VERIFY_NODE_TIMEOUT`
  still defaults to 540 seconds, but the clock is read once and each child gets only the
  time that is left. The old per-child limit let the check node's retry run two children of
  540 seconds against the caller's 600-second ceiling; the caller then won the race, the
  script never reached the line that writes the record, and the round left no trace. A value
  that is not a whole number of seconds now falls back to 540 instead of ending the node
  without a status line.
- **A retry keeps the first reply as `check-1.out`**, so a silent second child cannot erase
  the evidence of the first.
- **The budget is normalized to base 10.** A digit-only guard is not enough, because bash
  reads a leading zero as octal. `0600` meant 384 seconds. `0900` is not a legal octal
  number at all: the deadline arithmetic failed, `set -u` ended `run_child` on its first
  read of the unset deadline, and the node reported `failed:1` without ever starting a
  child — a valid 900-second budget became an immediate hard failure. `00` slipped past the
  off-switch and refused every child before it started.
- **A `failed:timeout` names its real cause.** A child the deadline refused reports
  `node-budget-spent-before-child-started`, not `child-exceeded-<N>s` for a child that
  never ran. This is usually the check node's retry, but at a tight budget it can be the
  first child too: the node does its own work before starting one, and that work can spend
  the budget.
- **`parse-verify-verdict.sh` names a wrong call too**, with `VERIFY_REASON=bad-arguments`,
  so an argument mistake is not read as a missing fence and retried.
- New tests in `test_verify_loop_node.py` and `test_verify_loop.py` execute the real
  contract, the real reason codes, and the real deadline against stub child helpers.

## 4.28.0 — 2026-08-10

**A loop node now relays its status line instead of describing it. Every exit path prints
`NODE_STATUS=` last, and exactly once.**

**Why:** the node that runs a loop command is a model, and it reports what it reads. The
status line used to sit above 25 to 40 lines of child output, so nodes summarised the
whole block. In run `wf_8ad76eec-5ac` several returned invented `detail` values — one the
literal word `placeholder` — and two reported `ran` for a step that had run nothing. That
is the loop's own failure mode, a step that did not run being recorded as one that did,
living one layer above the records built to prevent it. The records on disk were correct
throughout and the report node reads only those, so the verdict stayed honest; but anyone
reading the run's node list was told the opposite of what happened.

- **`NODE_STATUS=` is the last line of every exit path**, in `init`, `simplify`, `review`,
  `check` and `fix` alike. "Read the last line" is then a mechanical rule that needs no
  judgement — the same rule the report node already followed for its result line.
- **A node returns that line verbatim.** It does not summarise it, shorten it, or replace
  a field with a value of its own.
- **A node that saw no status line returns `NODE_STATUS=absent`.** A backgrounded command,
  a command still running, and a command that was killed all end there. None of them is
  `ran`.
- **A round node's returned text is narration, never evidence.** The verdict is read only
  from `verify-loop-report`, whose every value comes from the `record` and `state` files.
  Where a node's account and the records disagree, the records are right.
- 19 new tests: `test_verify_loop_node.py` asserts the ordering on every exit path of
  every kind, including the argument-failure paths, and `test_verify_loop.py` pins the
  return contract and scans the script so a new `echo "NODE_STATUS=` followed by more
  output fails the suite.

This is a reduction, not a removal. A node can still mis-state a line it can plainly read.
What changed is that reading it correctly no longer takes judgement, and that nothing
downstream depends on the node getting it right.

## 4.27.0 — 2026-08-10

**Every verify-loop node now runs under a wall-clock budget, and every node prompt must
ask for the Bash tool's maximum timeout.**

**Why:** a node runs as a single Bash call, and that call stops after 120000 milliseconds
by default. One round starts a child Claude session that runs `/simplify`, then
`/code-review medium --fix`, then `/verify`, over a whole branch. None of that finishes in
two minutes. The call gave up, the node reported that it had moved the command to the
background, and the child was killed when the run ended — after the command started, and
before the script wrote its record. Run `wf_8ad76eec-5ac` lost 9 of its 12 steps this way.
Each of the three round directories held one 12-byte record, `FIX=skipped`. The loop still
reported `RELAY_VERIFY_RESULT=unverified` with `RELAY_VERIFY_MISSING=9`, so nothing was
claimed that was not earned, but the report named no cause and the run bought nothing.

- **Node prompts must set the Bash timeout to `600000`.** `skills/verifying-until-clean/SKILL.md`
  states this and says why. Leaving it at the default is what produced the run above.
- **`RELAY_VERIFY_NODE_TIMEOUT` bounds every child session**, default 540 seconds. It sits
  below the caller's ceiling on purpose, so the script's own timeout fires first and the
  node ends by writing a record instead of being killed without a word. `0` turns it off.
- **A step that runs out of time records `<KEY>=failed:timeout`** and sets the run
  `unverified`. It is not a skip and it is never a pass — the same rule that already
  separates `failed:no-state` from `skipped`.
- **The `check` node does not retry after a timeout.** The retry-once rule covers a
  BLOCKED or unparseable verdict; a second child would start with the budget already
  spent, so it could only end the same way one round later.
- **A `fix` node that runs out of time commits what landed** before it reports, so the
  next round reads the tree that really exists rather than one that looks clean.
- 9 new tests in `tests/unit/skill-structure/test_verify_loop_node.py` execute the real
  timeout path against stub child helpers, and 4 in `test_verify_loop.py` pin the skill
  instruction and check that the script's budget stays below the caller's ceiling.

The helper contracts in `scripts/run-claude-command.sh` and `scripts/run-claude-prompt.sh`
are **untouched** — the budget wraps the call, and exit `69` still reaches the loop
unchanged.

## 4.26.0 — 2026-08-10

**The verify loop's node bodies move out of the generated Workflow script and into
`scripts/verify-loop-node.sh`. Each node now runs one short command instead of about 70
lines of inline bash.**

**Why:** a Claude Code session that is isolated in a git worktree refuses a Bash command it
cannot verify as safe, and every inline node body was refused. A live run
(`wf_ddc51fb5-461`) lost 13 of its 14 nodes this way and reported
`RELAY_VERIFY_RESULT=unverified` after running nothing. The refusal does not need `git` to
be present: a command that only sets a variable from a command substitution is refused, so
there was no inline shape to rewrite toward. `/relay:implement` reaches this state through
its own Step 0.5, which calls `EnterWorktree`.

- **`scripts/verify-loop-node.sh` holds every node body**, dispatched by kind: `init`,
  `simplify`, `review`, `check`, `fix`, `report`. The skill states what each kind does and
  stays the specification; the script is the implementation.

- **The bodies are now testable.** `tests/unit/skill-structure/test_verify_loop_node.py`
  executes the real script: 27 tests covering the reset, the missing-state rule, the skip
  rule, and every terminal result. Inline bash could not be tested at all, so the shape the
  skill documented and the shape a run executed could drift with nothing to catch it.

- **Each node prompt shrinks to one line.** The inline bodies cost about 35000 tokens per
  node to run a single command — about 474000 tokens across one run, on wrappers that did
  no work.

- **The worktree path is passed as an argument, never derived inside the node.** A node's
  working directory is not guaranteed to be the worktree. Callers read it from the
  `RELAY_WT_WORKTREE_ROOT` line that `worktree-preflight.sh --classify` prints.

- **Stated plainly in the skill:** the static check reads the command a node runs and does
  not read this script, so moving the bodies here puts the `git` calls where that check
  does not see them. The calls are unchanged and every one is scoped with `-C` to the
  worktree the session already owns. The skill says so, and a test pins the sentence.

- **Not changed:** the three terminal states, every fail-closed rule, the verdict-to-label
  map, the round-1 reset semantics, and the acpx session names.
  `scripts/run-claude-command.sh` and `scripts/run-claude-prompt.sh` are untouched, so
  their locked contract test is untouched.

## 4.25.0 — 2026-08-08

**BREAKING — the verify loop asks the user one question before it generates any node.
`/relay:verify` and `/relay:implement --verify` now stop and ask the user to agree to the
approvals-off child sessions. A run with nobody present to answer does not start the loop, and
reports `unverified` instead.**

**Why:** Claude Code's auto-mode safety rule `Create Unsafe Agents` refuses any node that starts
a coding-agent loop with the approvals off and with no sandbox. Every leaf of this loop does
exactly that, because each one runs `acpx --approve-all`. The rule is a soft block, and it
clears at one bar: the user must name the agent that runs with approvals off. The rule also
states that naming the enclosing task does not name the dangerous step, so a bare
`/relay:implement --verify` never met the bar. In one live run (`wf_55ed608d-904`) the rule
refused 2 of the 13 loop nodes, and the run reported `RELAY_VERIFY_RESULT=unverified` after
doing no verification at all.

- **Step 0 of `skills/verifying-until-clean/SKILL.md` asks for agreement.** The question names
  the three things that make the loop dangerous: the approval gate is off (`--approve-all`), no
  person approves each step, and the agreement covers every round of this run. Both callers ask
  it, with the same words, so the two paths stay equivalent. **This is consent that did not
  exist before, not wording aimed at the classifier.** The skill says so in one line, and a test
  pins that line: *Do not write it to get past the check.* When the user says no, the loop
  generates no node and reports `unverified`.

- **The reset moved into a new `verify-init` node, which starts no child agent.** This removes a
  single point of failure. The round-1 simplify leaf used to hold both the reset and an
  approvals-off child session, so the rule could refuse the one node that seeds
  `$STATE_ROOT/state`. A refused node writes nothing, so all 12 nodes after it read a missing
  file and recorded themselves `skipped`. `verify-init` runs no `acpx` command, so the rule has
  nothing in it to match, and a refused simplify leaf now costs one step instead of the run.

- **The reset clears `round-*` instead of the whole state root.** `rm -rf "$STATE_ROOT"` also
  removed files this loop does not own. The literal pattern names what goes.

- **A missing state file is no longer recorded as a skip.** `skipped` says the loop decided to
  stop; `failed:no-state` says the loop never started. Recording both the same way hid a refused
  `verify-init` behind an orderly-looking record.

- **The report node names an absent record instead of dropping it.** A refused node writes no
  line at all, so a report that printed only the keys it found showed a short round as a
  complete one. Absent keys now print as `missing`, and the count prints as
  `RELAY_VERIFY_MISSING=<n>` before the result line. `missing` is never read as a pass.

- **Not changed:** the three terminal states, the fail-closed rules, the verdict-to-label map,
  `scripts/run-claude-command.sh`, and `scripts/run-claude-prompt.sh`. Both helper contracts are
  untouched, so `tests/unit/skill-structure/test_relay_implement_polish.py` is untouched.

## 4.24.0 — 2026-08-05

**BREAKING — `/relay:implement` drops its two one-shot polish leaves. It gains `--verify`, which
ends the run with the same verify-until-clean loop as `/relay:verify`. A bare run now stops after
`verify` and does no cleanup at all.**

**The contract:** `/relay:implement --verify` is exactly equivalent to `/relay:implement`
followed by `/relay:verify`. Same nodes, same acpx session names, same state directory. Every
decision below follows from that rule.

- **The loop mechanics moved into one L2 skill.** `skills/verifying-until-clean/SKILL.md` used
  to hold doctrine only. It now also holds the node table, the state files, the fix leaf, the
  commit logic, and the terminal report — the mechanics that used to live only in
  `commands/verify.md`. Both `/relay:verify` and the `--verify` tail call this one skill; neither
  command holds its own copy. **Why one skill, not a copy in each command:** a copy in
  `implement.md` and a copy in `verify.md` drift, and drift already happened once —
  `TestBlockedRetryRouteAgrees` exists because `verify.md` and the skill once disagreed about the
  `BLOCKED` retry route across only two documents. A third copy would make that worse. A new
  anti-drift tripwire test now fails if either command file grows the mechanics back.

- **The loop has one identity, and the skill takes no parameter.** Both callers open the same
  acpx session names (`relay-verify-simplify-r1`, and so on) and write the same state directory
  (`$GIT_DIR/relay-verify`). A per-caller name would make the two paths differ, which the
  equivalence contract forbids.

- **Each loop run now resets its own state, which fixes a silent bug.** `$GIT_DIR/relay-verify`
  survives the run that wrote it. The first node of each round reads the `state` file and records
  itself `skipped` when `EXIT` holds a terminal value, so a second loop run in the same worktree
  did nothing at all and reported a stale result. The report node had the matching fault: it
  reads every round `record`, so a short run reported rounds from an earlier one. The round-1
  simplify leaf now deletes and recreates the state directory before it writes anything. This
  fixes two back-to-back `/relay:verify` runs as well.

- **`commands/verify.md` shrinks to a thin caller.** It keeps its dependency gate, its
  `--rounds` argument parse, and its branch guard. Step 1 invokes `relay:verifying-until-clean`
  to generate the round nodes and the report node. Apart from the state reset above, there is no
  behavior change for `/relay:verify` itself.

- **`/relay:implement` drops `polish-simplify` and `polish-review`, and gains `--verify` and
  `--rounds 1-5`.** Every branch now stops running work at `verify`. With `--verify`, one further
  phase — `verify-loop` — is appended, running the same simplify → code-review → `/verify` → fix
  loop `/relay:verify` runs, for up to 3 rounds by default (bound 1 to 5). **A bare run does no
  cleanup.** 4.23.0 and earlier always ran simplify and code-review once each after `verify`; a
  bare 4.24.0 run runs neither. This is the second reason the release is breaking, and it hits
  the default path. Run `/relay:implement --verify`, or run `/relay:verify` afterwards, to get
  the cleanup back. `--rounds` without `--verify` is now an error, because the round cap means
  nothing with no loop to cap.

- **`--verify` refuses the default branch and a detached `HEAD`.** `/relay:verify` already did,
  because the loop commits every round. Without the same guard, a headless `--verify` run on
  `main` would commit there while `/relay:verify` exited `1` — the two paths would differ.

- **Both modes record the same spine, and a bare run gates `verify-loop` off.** The recorded
  spine is `refine-spec,refine-plan,implement,verify,verify-loop` whether or not `--verify` was
  passed; only `--gates` differs — `verify-loop=false` on a bare run, empty with `--verify`.
  `scripts/retro-run.sh` builds its suppressed set from the roles already in the recorded spine
  (`[role for role in intended if gates.get(role) is False]`), so a role the spine omits can
  never be gated. Recording the role and gating it is what lets the retro tell a phase that was
  deliberately not run from one that went missing.

- **The failure posture changes from silent to escalate.** Before this release, a machine with
  no acpx made `/relay:implement` end successful and print `skipped (acpx unavailable)` — the
  polish phase quietly did nothing, and the run reported success anyway. After this release a
  `--verify` run on the same machine ends `unverified (acpx unavailable)`. Automation that reads
  `/relay:implement --verify` as always-successful will see a new failure mode on any host
  without acpx, on any host where the loop reaches no verdict (`unverified (loop blocked)`), and
  on any branch the loop cannot fully clean (`findings`). All three write the shared
  `RELAY_VERIFY_RESULT` terminal state (`clean`/`findings`/`unverified`) that `/relay:verify`
  already used. A bare run writes no `RELAY_VERIFY_RESULT` at all, and reports that the loop did
  not run — never that the branch is clean.

## 4.23.0 — 2026-08-03

**Minor — `/relay:drive` classifies the task kind like every other L3 command, and the two
enforcement gaps that let the difference persist are closed.**

- **`/relay:drive` now runs `relay:classifying-task-kind` over the oracle document.** It gains
  `## Step 1 — Classify the task kind` and `## Step 2 — Select the policy (branch on kind)`,
  modelled on `/relay:diagnose` — with one deliberate difference in what the classifier reads.
  The four sibling commands classify `$ARGUMENTS` minus the parsed flags, because each takes free
  task text. Drive takes none: its `argument-hint` is the flags plus `<oracle-file>`, and Step 0
  already resolves `RELAY_DRIVE_ORACLE` from `$ARGUMENTS` minus those flags, so `$ARGUMENTS` minus
  the flags and the oracle path is the empty string on every run. Step 1 therefore reads the
  oracle file, which is drive's task text. A new test pins this so the sibling idiom cannot be
  copied back in. Otherwise the shape matches `/relay:diagnose`: the
  kind is **advisory**, biasing the soft zone on the delegate and verify nodes while the hard
  spine — `orient → delegate → verify → branch → record → consecutive-clean-runs → closeout` —
  is identical for every kind. What proves done is still the oracle. A `docs` drive and a
  `feature` drive both close on N consecutive clean runs against a freshly-reset seed; the kind
  only shapes how a step is delegated and how its pass condition is checked along the way.

  **This reverses a deliberate decision, and is worth saying plainly.** drive's exemption was
  recorded in `CLASSIFIER_EXEMPT_COMMANDS = {"drive"}` with the rationale *"drive is
  oracle-driven, not task-kind-classified"*, and a dedicated test asserted the exemption held —
  `assert errs == ["missing task-kind classifier node"]`. That is a design position, not an
  oversight, and the code was self-consistent under it. The position has changed: every L3
  command carries the classifier idiom, with `execute` and now `drive` treating the result as
  advisory rather than spine-selecting.

  The classifier is inserted without disturbing `## Step 3.5 — Record run intent` or
  `## Step 4 — Verify run completeness`, which the retro and completeness-gate suites pin
  verbatim across all five commands; the protocol load moves to `Step 2.5`, following the
  existing fractional-step idiom (`0.2`, `0.25`, `0.5`, `3.5`).

- **`drive` is removed from `CLASSIFIER_EXEMPT_COMMANDS`.** The set is kept rather than emptied,
  because `verify` is still legitimately exempt — its four-step round is identical for every
  kind, so there is nothing for a kind to select. `test_drive_is_not_classifier_exempt` pins
  drive by name, so reintroducing its exemption is an explicit, reviewable edit to a named
  assertion instead of a quiet addition to a set nobody watches.

- **`validate_l3_command.py` validated four of the five L3 commands.** `drive.md` was missing
  from the `checks` map inside `main()`, so the CLI path skipped it entirely. pytest still
  reached drive through the carve-out above, so the gap was CLI-only — but the CLI is what a
  contributor runs before pushing, and this is the same omission shape as the 4.12.0 `CMD_NAMES`
  tuple that left `/relay:diagnose` unable to resolve tiers. The map is now a module-level
  `L3_CHECKS`, and a new test asserts it covers exactly the five L3 commands and that every
  filename in it exists, so a sixth command cannot be added and silently skipped.

- **`main()` accepted arguments and ignored them.** `validate_l3_command.py commands/drive.md`
  re-checked the same hardcoded set, printed nothing, and exited 0 — indistinguishable from
  validating the file it was handed. It now rejects arguments with exit 2. This is how the gap
  was initially misdiagnosed: the CLI reported OK for a command it had never opened.

- **Known vocabulary now includes shipped commands, derived from disk.** `_KNOWN` carried a
  hand-maintained `{"setup"}` for the one sibling command cited in prose, so drive's Step 1
  citing `/relay:diagnose` failed the vocabulary gate. Commands are now read from `commands/`,
  because the set of shipped commands is exactly what is in that directory and a hand-list
  drifts the moment one is added.

- **CI still excludes `drive` from `--l3`, and this release does not withdraw that exclusion.**
  The workflow added in the CI PR excluded `drive` precisely because `--l3 drive` failed on main.
  This branch does not carry `.github/`, so it cannot edit the workflow. `--l3 drive` passes from
  this release on, so the follow-up edit to `.github/workflows/relay.yml` is: add `drive` to the
  `--l3` loop, and add a `python3 scripts/validate_l3_command.py` step below it. Until that edit
  lands, the map-coverage regression is caught in pytest only, not server-side.

- **Two stated-count and stated-behaviour drifts corrected.** `delegate-and-watch/SKILL.md` said
  the sidecar carries 8 vars for codex and 10 for claude; `acpx-dispatch.sh` writes 10 and 11.
  `RELAY_MAX_TURNS` was missing from both lists, and 4.21.0's `CODEX_CONFIG` from the codex list.
  Separately, `docs/language-reference.md` still described `capability-validate` as intersecting
  `requires` against the binding's `provides` — the pairing 4.21.0 proves rejects every dispatch.
  The row now describes the `requires`-against-leaf-tools check the code performs.

## 4.22.0 — 2026-08-03

**Minor — a new command, `/relay:verify`, that repeats simplify, code-review, and `/verify`
over the current branch until the branch verifies clean, and reads only the verdict to decide
when to stop.**

- **`/relay:verify` generates one dynamic Workflow that runs the loop.** Each round runs
  `/simplify` → `/code-review medium --fix` → `/verify` → a fix step, up to a cap of 3 rounds
  by default (`[--rounds 1-5]`). Claude cannot invoke a slash command from inside its own model
  turn, so each step runs as one turn of a child Claude session over `acpx` — the same
  mechanism the two polish leaves of `/relay:implement` already use. No dispatch engine or
  worker is selected, because no role is dispatched; there is nothing for an axis to resolve.

- **The loop refuses to start where its commits cannot survive.** Every round commits, so the
  branch guard rejects two states before any child session opens. The first is the default
  branch. The second is a detached HEAD: `worktree-preflight.sh` classifies it as `stray`, which
  the state check allows, but a commit made on a detached HEAD is reachable from no branch and is
  lost as soon as the user checks out a branch. Without the second check the run reports
  `RELAY_VERIFY_RESULT=clean` over work that has already gone. `TestVerifyBranchGuardExecution`
  runs the shipped guard block against real repositories in each state, rather than reading its
  prose.

- **The verdict is the exit signal, never the findings count.** The built-in `/verify` prompt
  asks for a line per probe even when the probe held nothing, and says a pass with three sharp
  findings is worth more than a bare pass. A `PASS` therefore normally carries findings, and an
  exit rule keyed on "no findings" would never be reached — the findings count would never drop
  to zero and every round would look unfinished forever. This loop reads the verdict alone:
  `PASS` exits clean, `FAIL` runs the fix step and starts the next round, and anything else exits
  as explicitly unverified.

- **`SKIP` and `BLOCKED` are not a pass.** A live run on a clean tree returned
  `Verdict: SKIP — no diff to verify`, which means there was nothing to verify. `BLOCKED` means
  the verification could not be performed. Both map to `no-answer`, and both end the run in the
  terminal state `RELAY_VERIFY_RESULT=unverified` rather than `RELAY_VERIFY_RESULT=clean`. The
  verdict-to-label map lives inside `scripts/parse-verify-verdict.sh` and nowhere else, so no
  caller can reason about `SKIP` freshly and mistake it for a pass.

- **The parser takes the last single-token verdict line, and counts tokens rather than
  anchoring on end-of-line.** The `/verify` report template holds the literal line
  `**Verdict:** PASS | FAIL | BLOCKED | SKIP`, and that line is in the CLI prompt and in the
  files this release adds — the command doc, the skill, and the tests. Running `/verify` over
  this repository echoes the line back, and a first-match search reads the enum template itself
  as the answer. An end-of-line-anchored pattern was tried and rejected: it does reject the
  template, but it also rejects `**Verdict:** SKIP — no diff to verify` and
  `**Verdict:** PASS — everything checks out`, which would silently turn a genuine pass into an
  unverified run and make the loop burn every round without ever reporting clean. The parser
  instead counts whole-word verdict tokens on each candidate line and accepts a line only when
  the count is exactly one, then takes the LAST accepted line — the report is the child's final
  message, so the last single-token verdict is the real one.

- **The fenced region runs from the first begin marker to the last end marker,** because the
  child's own text can hold either marker — a `/verify` run over this repository does. Reading
  from the first `POLISH_CMD_OUTPUT_BEGIN` to the last `POLISH_CMD_OUTPUT_END` is the only region
  that survives an echoed marker without truncating the real verdict. The rc is read from `$?`
  right after the command substitution, never from a grep, because the child's own text can also
  hold the literal `POLISH_CMD_RC=0`.

- **`scripts/run-claude-command.sh` was left untouched**, for two reasons: its contract is
  locked and covered by `TestRunClaudeCommandHelper`, and `/relay:implement`'s polish leaves
  depend on its slash-only guard — the check that keeps a polish leaf from sending prose where a
  slash command is required. Relaxing that guard to also carry free-form text would remove the
  very check that makes it trustworthy. The new sibling `run-claude-prompt.sh` carries the
  free-form fix prompt instead, and reuses the same `POLISH_CMD_*` markers, so one parser reads
  both helpers.

- **Round state lives under the git directory, not in the working tree.** A scratch directory
  inside the working tree would make `git status --short` non-empty on every round, which would
  let `git add -A` sweep the run's own logs into a commit and would silently defeat the
  fix-noop detector — the check that stops the loop after two consecutive rounds whose fix step
  changed nothing.

- **Three terminal states, one printed last.** `RELAY_VERIFY_RESULT=clean` is printed only when
  the last recorded label is `clean`. Cap exhaustion prints `RELAY_VERIFY_RESULT=findings` or
  `RELAY_VERIFY_RESULT=unverified` and names which, rather than reporting a spent budget as a
  pass.

- **New protocol skill `verifying-until-clean`,** registered in `EXPECTED_SKILLS` and in
  `validate_l3_command._KNOWN`, and deliberately left out of `L2_NAMES`: that constant forces a
  `relay-vocab` block, and the only honest `l1-shape` here is `loop-until-clean`, which
  `skills/improve-loop/SKILL.md` already owns. Two skills declaring the same shape would make
  the block stop identifying which one is the real owner.

## 4.21.0 — 2026-07-28

**Minor — three defects on the acpx leg, each of which had been documented as working:
a preamble no code delivered, a codex model encoding the adapter rejects, and a
capability gate wired to nothing.**

- **`preamble.md` was never delivered to any child.** `skills/dispatching-acpx-agents/SKILL.md`
  listed it as a component and `docs/dispatch-contract.md` stated it was prepended, but no code
  in the tree ever read the file — repo-wide, the only references were tests asserting its
  contents. Children received the inline `<<DO_NOT_LOAD_SKILLS>>` block and nothing else: five
  lines saying "don't load skills, act on the task directly."

  Everything else in `preamble.md` went undelivered — the one-shot posture, the do-not-commit
  clause, the `AUTONOMY` modes, and, load-bearing, **the licence to emit `NEEDS_DECISION:`**.
  That is one of the four frozen public sentinels, and it has a complete receiving path: the
  session drivers classify it as terminal, `delegate-and-watch` has a dedicated `needs-decision`
  bucket that calls `sessions detach` and sets `PARKED=1`, and the crash trap gates on that
  flag. All of it waited on a sentinel no child had ever been told it was permitted to emit. The
  receiving half of a documented protocol was unreachable because the sending half was never
  wired.

  Fixed with a single `build_preamble` assembly site used by all three dispatch paths. A missing
  `preamble.md` now aborts with exit 66 rather than silently shipping a prompt without the
  contract. Because `preamble.md` defaults to fire-and-forget when `AUTONOMY` is unset,
  delivering it changes nothing for callers that never set it.

  A third path was worse than stale: the generic `acpx-codex` loop passed `$PROMPT_FILE` raw, so
  its children received neither the isolation block nor the autonomy contract. It now assembles
  the same preamble, once, outside the retry loop.

- **The codex-session driver path sent a model encoding acpx rejects.** It set
  `EFFECTIVE_MODEL="${MODEL}[${EFFORT}]"`. acpx >= 0.12.0 validates `--model` against
  adapter-advertised plain ids and rejects the pre-0.12 bracket form, so every dispatch down
  this path failed at the adapter — and this is the path taken by exactly the four roles that
  declare `verify_artifact`: `implementer`, `test-writer`, `fix-coder`, `plan-writer`. That is
  the entire codex implementation pipeline. The roles that most need the freshness gate were the
  only ones that could not run under `--agent codex`.

  The in-code comment acknowledged the path "remains non-functional under acpx's registry pin
  regardless" rather than fixing it. Now uses the same encoding the fast path and the
  `acpx-codex` loop already used and that 4.15.0's polish work exercised live against acpx
  0.12.1: a plain model id, with effort riding `CODEX_CONFIG` for the codex-acp adapter to merge
  into the session config. `CODEX_CONFIG` is threaded through the driver environment **and** the
  sidecar, so a `delegate-and-watch` re-invocation resolves the same effort rather than silently
  dropping to the adapter default.

- **The capability gate was documented as a check that would have rejected every dispatch.**
  `skills/delegate-leaf/SKILL.md` instructed callers to run
  `validate(roleRequires, bindingProvides)`. Those are **disjoint namespaces**: `requires:` holds
  capabilities (`read_files`, `run_bash`, `write_files`) and `provides:` holds envelope tokens
  (`ROLE_DONE`, `FILES_TOUCHED`). Their set difference is therefore the whole of `requires` for
  every role, so a coordinator that actually performed the documented check would have rejected
  100% of dispatches.

  It never fired because `scripts/capability-validate.js` had no runtime caller anywhere in the
  tree, and `acpx-dispatch.sh` correctly gates its own intersection off for role files — with a
  comment explaining this exact namespace distinction. So the shell was right, the prose was
  wrong, and the helper the prose named was dead. The unit test hid it too: it asserted
  set-difference behaviour over abstract `"a"`/`"b"` strings, passing while saying nothing about
  whether the pairing meant anything.

  `capability-validate.js` now exposes `validateRoleAgainstTools(roleRequires, agentTools)`,
  which checks the pairing that matters — a role's `requires:` against the tool set of the leaf
  its `role-class` derives, so `write_files` on a `reader` is caught because `relay:leaf-reader`
  has no Write or Edit. An unmapped capability fails the gate rather than passing silently, so a
  typo in `requires:` cannot slip through.

  Enforced **statically** over all 22 roles by `tests/unit/skill-structure/test_capability_gate.py`
  rather than at dispatch time. Dispatch is prose a coordinator may skip; a static gate cannot
  be, and a mismatched role now fails the suite before it can ever be dispatched. Same reasoning
  that makes the 4.18.0 `agents/` inventory tests worth more than a runtime registration check.

  The same disjoint-namespace pairing also survived in two sibling sites this pass corrects:
  `acpx-dispatch.sh`'s `--validate-only` mode ran the `requires - provides` set difference with
  no role-class gate, so `--validate-only --role roles/<any>.md` rejected **every** role with a
  `MISSING_CAPABILITY` line per capability; it now skips the intersection for role files exactly
  as the Step 5b mechanism-dispatch gate does, scoping it to legacy native-agent files.
  `dispatching-acpx-agents/SKILL.md` step 2 still instructed coordinators to intersect `requires`
  against `provides`; it now documents the tool-set gate instead.

- **Verification.** These three defects all sit on the acpx-dispatch paths whose ~33 tests skip
  silently when `yq` is absent — which is how they survived. Installing `yq` dropped the suite
  from 54 skips to 18 and put 36 previously-dormant tests onto the modified code.

  The encoding change was then confirmed against **live acpx 0.13.0**, and the result is worth
  recording because it establishes both halves. The pre-fix form is rejected by the adapter:

  ```
  $ acpx --model 'gpt-5.6-luna[high]' codex exec -f p.txt
  Cannot apply --model "gpt-5.6-luna[high]": the ACP agent did not advertise that model.
  Available models: gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, gpt-5.5, gpt-5.4, gpt-5.4-mini.
  ```

  The post-fix form is accepted, and the effort is applied as a separate protocol step rather
  than being smuggled through the model id:

  ```
  $ CODEX_CONFIG='{"model_reasoning_effort":"high"}' acpx --model 'gpt-5.6-luna' … codex exec -f p.txt
  [client] session/set_config_option (running)
  Hi! How can I help?
  [done] end_turn
  ```

  Both fixes also gained **behavioural** tests that execute `acpx-dispatch.sh` down the driver
  path with a stub substituted via `DRIVER_OVERRIDE`, then assert on what the child actually
  received: the isolation block, the autonomy contract, the role body in that order, a
  bracket-free `ACPX_MODEL`, and `model_reasoning_effort` arriving via `CODEX_CONFIG`. Those
  need `yq`, so the static source assertions are kept as an ungated floor — a suite that can
  skip into silence is what hid these defects in the first place.

## 4.20.0 — 2026-08-01

**Minor — the polish-review leaf now runs `/code-review medium --fix`, down from `xhigh`.**
The level is the review's effort ladder, not its scope — `medium` still reviews the same diff
with the same fan-out, at lower token cost per polish run. `xhigh` and `max` remain available
by hand for a release audit.

## 4.19.0 — 2026-07-28

**Minor — the documentation relay never had: an architecture overview, a contributor
guide, eight ADRs, and a test gate that fails when any of them go stale.**

- **`docs/architecture.md` and `docs/contributing.md`.** Relay had four contract documents —
  dispatch, refinement, substrates, language — and no orientation for someone meeting the plugin
  for the first time. There is no `CONTRIBUTING.md` anywhere in this repository at any level.
  Architecture covers the layers, the agent/role split and the three forces behind it, the
  derived-not-declared registration rule, the frozen envelope, the failure-mode tier ladder, the
  dispatch axis, the refinement engine, and the anti-silent-failure spine. Contributing covers
  the local gate, the exact-version-pin ratchet, what the ~1800 assertions actually enforce,
  per-change-type checklists, and the traps — including the `yq` skip trap, where more than
  thirty acpx-dispatch tests opt out silently and a green suite proves nothing about the dispatch
  path.

- **`docs/adr/` — eight Architecture Decision Records.** Relay records decisions well but in
  three places that each answer a different question: a design spec says *what we planned, at a
  date*; the CHANGELOG says *what changed, in order*; the contract docs say *how it works today*.
  None of them says what is **currently decided and whether it still holds**. The gap is not
  hypothetical —
  `docs/superpowers/specs/2026-06-24-relay-worktree-isolation-and-session-rename-design.md`
  still reads `Status: design (approved in substance, pending written-spec review)` and describes
  `Step 0.0 — Session rename (all 6 commands) ← NEW`, a feature that shipped in v4.5.0 and was
  removed two releases later. The `Status:` field existed; nothing maintained it.

  The eight cover the decisions that are hard to reverse, surprising without context, and the
  result of a real trade-off: the single orchestration substrate; the agent/role split behind two
  generic leaves; depth-1 by tool omission rather than instruction; model tiers by failure mode;
  the dispatch axis as a per-role binding rather than a pipeline fork; fail-to-indeterminate and
  the always-on gate; the four frozen envelope tokens; and superpowers as a hard dependency
  rather than a vendored copy. Each records what was rejected — a whole-pipeline engine fork, one
  registered agent per behavior, prompt-level depth enforcement, sizing models by task
  difficulty, an opt-in completeness gate — because the rejected option is the part a future
  reader will otherwise re-propose.

  Format follows the existing house convention in
  `plugins/engineering/skills/grill-with-docs/ADR-FORMAT.md` — `docs/adr/NNNN-slug.md`,
  deliberately minimal, optional sections only where they earn their place — rather than
  introducing a second one. Supersession is a new record plus a status change, never an edit in
  place; a decision has to stay readable after it stops being true.

- **New `tests/unit/skill-structure/test_docs_freshness.py` (36 tests).** Onboarding prose rots
  faster than anything else in a plugin precisely because nothing breaks when it does — it just
  starts lying to the next contributor. Relay already answers that for `roles/README.md`
  (`"22 roles"`) and the roster (`"7 agents total"`); this extends the same mechanism rather than
  inventing a second one. Every repo-relative link must resolve and every backticked repo path
  must exist; the agent and role counts must match the directories; the tier rungs named must be
  exactly the rungs `bindings/presets.yaml` uses; the axis enums must match
  `parse-engine-agent.sh`; `README.md` must link both documents; and the worked version example
  in `contributing.md` must show the version actually shipping. For the ADRs: numbering runs
  `0001..NNNN` with no gaps or duplicates, `status:` must be one of four values, a `superseded`
  record must name an existing successor, and the index must list exactly what is on disk with
  matching statuses.

  Each check first asserts its own extraction found something, so a regex that silently stops
  matching fails loudly instead of turning the module into a no-op — the same guard-against-
  vacuity discipline `tools/fidelity-check.sh` needed in 4.17.0. Two gaps were caught by these
  tests during authoring rather than by review: the README link table was missing, and the
  version example was stale.

- **The plugin `README.md` was wrong in five places, and one of them actively misled.** It
  claimed *"Relay exposes five commands"* while seven exist — `engines` was never added after
  4.9.0 and the table already listed six. It documented the dispatch axis as **positional
  arguments** under a `| Positional |` table header, which stopped being true in 4.11.0 when the
  flag parser was fixed; only `/relay:setup` still reads positionals. It omitted `smart-routing`
  from both enums although `parse-engine-agent.sh` has accepted it on each axis since 4.11.0 and
  every `argument-hint` advertises it. It stated *"any of the four agents"* when there are five.
  And it claimed relay *"delegates six runtime skills"* — the closed upstream set is 14
  `obra/superpowers` rows, of which the operative surface currently names five.

  The active harm was the worked example `/relay:implement acpx hybrid specs/x.md`. No command
  accepts a third positional — `allows_spec_path` is `False` for all of them — and Step 0 scrapes
  flags out of `$ARGUMENTS` with `sed`, so a user copying that line would have had
  `acpx hybrid specs/x.md` silently parsed as the task text, then watched the run proceed
  in-session while appearing to have requested acpx. Replaced with correct flag-form examples,
  and the argument table now also documents `--retro`, `--target` and `--resume`, none of which
  it had ever mentioned.

  Six new checks in the freshness module pin all of it: the spelled-out command count against
  `commands/`, every command being mentioned, the axis being documented as flags with the
  pre-4.11 positional table absent, both enums matching the parser, the absence of a positional
  spec-path example, and the upstream-set size matching the manifest.

- **Root `README.md` was three plugins out of date.** `relay`, `diagram`, `engineering` and
  `pr-flow` are all on disk and in `marketplace.json` but appeared in neither the plugin table
  nor the install-all loop — so the repository's most active plugin was invisible from its front
  page. Added, along with a `## Contributing` section stating the no-CI reality and pointing at
  the per-plugin guides.

- **Corrections from review, before merge.** Five notes, all real, and the two that mattered
  were the module's own failure mode turned back on it. `test_index_status_column_matches_frontmatter`
  asked `status not in row`, satisfied by the status word appearing anywhere in the row — an ADR
  whose *title* contained a status word would have masked a wrong status column; it now compares
  the parsed status cell. And `_counts()` computed a skill total that nothing asserted while
  `architecture.md` claimed the gate checked skill counts: a documented check that did not exist.
  The check is now real, pinning each skill constant's size to the constant it describes and
  their sum to the directory count — which surfaced that ten skill directories sit in no
  constant at all. Three documentation corrections went with them: the skills row named "four
  disjoint class constants in `test_plugin.py`" when they live across two files, the pre-push
  list omitted `doc_reference_scan.py --run-gate` (the repo's one mechanical doc gate), and the
  legitimate-skip list named three categories when `test_flows.py` contributes a fourth.

- **Considered and not done.** Retrofitting ADRs for every past decision was rejected: the
  CHANGELOG already carries that weight far better than a backfilled record would, and a fourth
  scattered location would make the problem worse rather than better. Only decisions meeting all
  three bar criteria are recorded. Extending the freshness gate to the `docs/superpowers/specs/`
  tree was also rejected for now — those are point-in-time artifacts by design, and the right fix
  there is a status convention rather than a test.

## 4.18.0 — 2026-07-28

**Patch-shaped but load-bearing — the two generic execution leaves have never been
dispatchable under the name every dispatch site uses.**

- **`agents/leaf-worker.md` and `agents/leaf-reader.md` registered as
  `relay:relay:leaf-worker` / `relay:relay:leaf-reader`.** Both files declared
  `name: relay:leaf-worker`, and the loader prefixes the plugin namespace on top of whatever
  `name:` says. The five other agents use a bare slug (`name: scout` → `relay:scout`) and were
  always correct; only the two leaves self-namespaced. Dispatching the documented
  `relay:leaf-worker` fails hard with `Agent type 'relay:leaf-worker' not found` — verified
  against a live harness, which also lists the doubled names among the available agents. This is
  the path all 22 roles route through: `role-class: writer` derives `relay:leaf-worker` and
  `role-class: reader` derives `relay:leaf-reader`, and 88 references across `skills/`,
  `commands/`, `docs/` and `roles/` name those strings. Fixed by dropping the prefix from both
  frontmatter `name:` fields, which leaves every existing reference correct — the registration
  was the wrong half, not the references. Introduced in 2f9cbd1 (v4.0.0), the migration that
  created the leaves; shipped broken for seventeen releases.

  The reason it survived that long is worth recording: `TestAgents::test_name_matches_slug`
  **encoded the bug**. It special-cased `LEAF_SLUGS` to expect `relay:<slug>`, so the suite
  asserted the broken value and went green on it. That assertion now holds one rule for all
  seven agents — `name:` is the bare slug, always. The general lesson, and the reason the new
  test module exists: *every other agent test in this suite asserts what a source file says, and
  none of them asserted what the loader would register.*

- **`agents/README.md` registered as `relay:README` with an unrestricted tool grant.** Every
  `*.md` in `agents/` becomes an agent, including one with no frontmatter — and an agent with no
  `tools:` key receives every tool. So the file documenting relay's depth-1 invariant was itself
  an agent holding `Agent` and `Skill`, the two tools the leaves deliberately withhold so a
  subagent cannot spawn subagents. It also made the runtime roster 8 while
  `test_roles.py` asserted 7 by set equality — the test passed because it reads the directory,
  not the harness. Moved to `docs/agent-roster.md`; the four markdown references and the eight
  test path constants move with it. `agents/` now contains exactly the seven agent files.

- **New `tests/unit/skill-structure/test_agent_registration.py` (35 tests).** The invariants
  neither bug could have survived: no agent `name:` may contain a namespace separator; `name:`
  must equal the filename stem; `agents/` may contain only the seven expected slugs and no
  README under any casing; every file there must carry frontmatter with `name`/`description`/
  `tools`; the doubled form must appear nowhere in the tree; and — the guard against the fix
  going vacuous — the singly-namespaced leaf references must still be present, at least ten of
  them. Verified to fail on reintroduction of either defect rather than merely passing today.

- **Considered and not done.** Renaming the 88 references to the doubled form would also have
  produced a working system, and was rejected — the loader's prefixing is the contract, and
  every other agent in the plugin and in every sibling plugin already follows it. Adding
  frontmatter to `agents/README.md` to constrain its tools was rejected for the same reason: it
  would keep a documentation file registered as an agent, which is the actual defect. A CI
  workflow to run any of this automatically is still absent and remains the largest gap in the
  repo's quality story; it is out of scope here.

## 4.17.0 — 2026-07-25

**Minor — `--retro`: a read-only post-run audit on all five L3 commands, plus the run-intent
record that gives it a spine to diff against.**

The always-on completeness gate shipped in 4.16.0 answers one question — did every node
answer. `--retro` answers the rest, after the fact and outside the Workflow, and it audits
the gate itself.

- **New `scripts/retro-run.sh`.** Five comparisons over one finished run, each degrading
  independently: **C1 SPINE** (recorded intent vs actual agent labels, minus gate-suppressed
  roles), **C2 PHASE** (`phases[].title` vs the `phaseTitle` set — `phases[]` is a *static
  pre-scan of `phase()` literals*, which is exactly why it survives its own run's death and
  can name phases that were never reached), **C3 SILENT** (the §0 soft-failure predicate),
  **C4 AXIS** (script `ENGINE`/`AGENT` consts, delegation actually wired, unexpected model
  fallback), **C5 COST** (status, error, retries, `agentCount` drift, duration/token/tool-call
  outliers). Exit `0` clean, `1` deviations, `2` too little evidence survives.
- **C3 delegates to `verify-run-completeness.sh` rather than reimplementing the predicate.**
  One implementation, so the in-run and post-hoc definitions cannot drift.
- **The retro audits the gate.** A non-empty C3 in which every dead node shows `attempt == 1`
  means **the gate did not fire** — the single highest-value finding a retro can produce. It
  does not re-litigate individual node retries; it reports the aggregate.
- **A retro that could not run its SILENT check never reports CLEAN.** It reports `DEGRADED`
  and says the run is unaudited for the exact failure class the check exists to catch. A `?`
  on any other row is benign — C1 is `?` on every pre-4.17 run, which is the common case.
- **Read-only by construction.** It writes no file, re-runs nothing, and never fails a
  command; a retro must not dirty the branch it is auditing. It runs **outside** the Workflow
  because a retro node appended to the generated script would not have executed on the runs
  that most needed one (`wf_429eef41-dff` died two phases before its end), and would itself be
  an `agent({schema})` node subject to the identical failure mode it exists to detect.
- **Degradation ladder, each rung still useful.** No intent record → script-derived intent
  (C2/C3/C5 full, C4 partial, C1 unknown). Stale `scriptPath` → resolve by key then glob by
  runId, and **report the divergence as a finding**: a moved slug means the run crossed a
  worktree boundary. Missing `scripts/*.js` → read the inline `wf.script` copy; the
  double-persist is a feature, not waste. Missing `wf_*.json` → journal-only mode, thin
  because the journal key is `v2:<sha256>` and nodes cannot be named. Everything gone → exit 2.
- **New `scripts/record-run-intent.sh` and a `## Step 3.5 — Record run intent`** on all five
  commands, appending one line to `~/.claude/relay/runs.jsonl` after the `Workflow` tool
  returns (`run_id` exists only then). It records **only what no artifact preserves**:
  `relay_command` (`workflowName` is free text and identifies no command), `kind`,
  `intended_spine`, `gates`, and `axis_source`. It deliberately does **not** record the axis
  values or the task text — both are already persisted as `const ENGINE`/`const AGENT`/
  `const TASK` in the script, and a second copy can disagree with the first. `gates` keys on
  **node labels**, so it can excuse a spine role the run deliberately did not dispatch; no
  command has a skippable role today, so every command records `""`. `intended_spine` snapshots the §4.2.1 row
  **at run time**, so retroing an old run does not diff it against a table that has since
  changed. It lives under `~/.claude` and not the repo's `.claude/` because leaf agents commit
  with `git add -A`-style flows and would sweep run records into the branch under review.
- **Flag plumbing.** `--retro` is extracted from `$ARGUMENTS` in Step 0 and **never forwarded
  to `parse-engine-agent.sh`**, which hard-rejects a third positional and would abort the
  command. It is stripped before Step 1 classification (an unstripped `--retro` changes the
  inferred kind), and stripped out of `drive`'s oracle-path recovery. Only `wf_<id>` or the
  literal word `last` counts as a target, so `--retro add a login form` cannot read "add" as a
  run id. Bare `--retro` runs the command normally then retros this run; `--retro <target>` is
  retro-only and short-circuits before the worktree gate.
- **`diagnose` gains its first Step 0** — it resolves no dispatch axis, so the flag needed a
  home of its own.
- **The 4.16.0 completeness gate gains its own `## Step 4 — Verify run completeness` heading**
  on all five commands. It previously sat unlabelled at the tail of Step 3, and inserting
  Step 3.5 in front of it left the gate reading as part of a section titled "Record run
  intent". The numbering gap between 3.5 and 5 is now closed.
- **`implement.md` documents what actually contains the polish child.** It runs with
  `--approve-all` — unattended polish cannot work otherwise — and `--cwd "$worktree"` is
  *positional* containment, not a sandbox: it decides where the child starts, and nothing stops
  an absolute path or a `git -C` elsewhere. Stated plainly so no later polish step is added on
  the assumption that `--cwd` is a security boundary. A narrower permission set and a
  no-approve mode were both considered and deliberately not implemented.
- **The polish-review leaf now runs `/code-review xhigh --fix`, down from `max`.** The level
  is the review's effort ladder, not its scope — `xhigh` still reviews the same diff with the
  same fan-out and adversarial verification, at meaningfully lower token cost per polish run.
  `max` remains available by hand for a release audit. The 4.15.0 entry below still reads
  `max` because that is what 4.15.0 shipped.

**Reliability-spine fixes found by review before release.** The gate and the retro guard
their *inputs* carefully but were not guarding their own exit-code plumbing, which left three
fail-to-pass holes in code whose stated doctrine is "fail to indeterminate, never to a pass":

- **The retro read any unrecognized gate exit code as SILENT ✓.** The gate normalizes its
  verdicts to 0/1/2, so anything else means it never ran — yet a retro whose gate was absent
  or killed (bash 127) reported `CLEAN` over a run with dead nodes. Now `DEGRADED`, `SILENT ?`,
  exit 1.
- **The gate exited 0 COMPLETE over a run with no node evidence at all.** An empty
  `workflowProgress[]` and an empty journal make the scoped agent set empty, and no agents
  means no dead agents — the COMPLETE branch. A run that died before its first node started
  read as a clean pass, and Step 4 says "0 COMPLETE — proceed". Now `INDETERMINATE`, exit 2.
- **The §3.8 gate audit joined dead nodes to run records by `label`.** `label` is optional
  (rendered `-` when absent) and non-unique (a retry reuses its role's label), and a missed
  join defaulted to `attempt == 1` — which is the audit's own trigger. It therefore
  manufactured its highest-severity finding. Now joined on `agentId`, which the gate already
  prints, and an unjoinable line is treated as no evidence rather than as attempt 1.
- **The mandated wait primitive's liveness escape could never fire.** `pgrep -f
  acpx-dispatch.sh` matches whole command lines, and the poll's own `bash -c` contains that
  pattern, so it always matched itself. A worker that died without writing an envelope burned
  the full 580s budget instead of being detected. Fixed with `"[a]cpx-dispatch.sh"`.
- **`RELAY_LOG_SIGNAL=` was uncapped**, and the retro passes the gate's whole stdout to its
  parser through the environment — roughly 320 matching log entries exceed the 128 KiB exec
  limit and abort the retro with `parser_aborted`, blaming missing evidence for an
  output-size problem. Capped at 20 with a truncation count; the retro only ever read the
  first line.
- **`--retro last <task text>` silently discarded the task.** The trailing-text allowance was
  meant for `wf_<id>`; bare `last` now counts only at end-of-string, so `--retro last night's
  regression in the parser` is task text, not a target. Also, `drive`'s `<oracle-file> is
  required` abort ran before Step 0.2, making retro-only mode unreachable on that command.
- **`--spine` records node labels, not skill names.** Both commands told the caller to record
  the Step 2 branch row verbatim, whose entries are skill-invocation notation
  (`relay:delegate-leaf(implement)`) that never appears as a node label — so every healthy run
  reported a SPINE deviation. The intent record's runId is also normalized on both sides now:
  `wf_abc` and `abc` name the same run, and an unnormalized compare made the whole feature
  inert whenever the harness returned a bare id.
- **Polish-phase shell contract.** Both polish leaves referenced `$WORKTREE`, which nothing
  defines — the helper would have received an empty first argument and exited 66 (`failed`) on
  every run. Each leaf now resolves it via `git rev-parse --show-toplevel`, every `git` call
  in the commit block is scoped with `-C "$WORKTREE"` (a leaf's cwd is not guaranteed to be
  the worktree — that is why the helper takes the path as an argument), `base_ref` no longer
  depends on `origin/HEAD` (written by `clone`, not `fetch`) and takes a single root on a
  grafted history, and the helper now fences the child's reply between
  `POLISH_CMD_OUTPUT_BEGIN`/`END` so a child reviewing a repo that contains the literal
  `POLISH_CMD_RC=` cannot forge the helper's exit status.

- **`tools/fidelity-check.sh` gave a false FAIL on ~6% of runs.** Its `--l3` static check
  piped a captured command body into `grep -q`; `grep -q` exits at its first match and closes
  the pipe, `printf` dies of SIGPIPE (141), and the script's `set -o pipefail` promotes that
  141 into the pipeline's status — so it reported "missing classifier" for a token it had just
  found. The window is proportional to how much of the file is still unwritten when the match
  is hit, which is why it was invisible until now: unchanged, the harness flakes 0/300 against
  main's 114-line `implement.md` and 42/300 against this branch's 379-line one. Latent in main,
  triggered by this branch. Now greps the file directly — no pipe, nothing to race — with a
  regression test asserting stability across repeats and a second guarding the fix against
  going vacuous (grepping a wrong path also "finds nothing", which would turn every FAIL into
  a PASS).

- **99 new tests** (93 of them driving the two new scripts against synthetic fixtures); no real session record is copied into the repo.
  Validated against four real runs: `wf_429eef41-dff` and `wf_f13a44bd-742` both report
  deviations (the second *despite* `status: "completed"`), and two healthy runs come back
  clean.

**The polish phase has now been exercised live against acpx 0.12.1**, closing the design's
listed risk #1 — that a bare slash command through the acpx claude adapter might not trigger
slash-command dispatch at all. It does; the documented `claude -p` fallback is not needed.
Both leaves were run through `scripts/run-claude-command.sh` exactly as the wrapper leaves
invoke it, against a throwaway repo outside this one:

- **`/simplify`** collapsed two accumulator bodies into single return expressions and stopped
  at the API-changing suggestion, as its own guardrail requires.
- **`/code-review xhigh --fix`** found both planted defects (`ZeroDivisionError` on `mean([])`
  and on a zero baseline in `percent_change`), fixed them, added tests, and declined a
  `statistics.mean` swap that would have changed a public function's return and exception
  types.
- The **fence/rc contract holds against a real child**: reply between
  `POLISH_CMD_OUTPUT_BEGIN`/`END`, `POLISH_CMD_RC=0` on the line *after* the fence.
- The **session lifecycle is clean** — `ensure` → turn → `close`, verified in acpx's own
  session store rather than from `sessions list`, which lists underlying Claude Code sessions
  and not acpx's named bindings.
- The **commit shape** produced `refactor: simplify implementation` (no scope in range) and
  `fix(stats): apply code-review findings` (majority scope detected), including the
  root-commit `base_ref` fallback on a repo with no `origin`.
- Cost on a deliberately trivial repo: **~120k tokens** for simplify, **~270k** for review at
  `xhigh`. Real repos will be larger; the phase is not cheap and is meant to run once, after
  `verify`.

## 4.16.0 — 2026-07-25

**Minor — silent-failure reliability: a turn-lifetime rule for watchers, a third
verdict outcome for improve-loop, and an always-on completeness gate on every L3
command.**

Two consecutive `/relay:implement` runs lost half their dispatch nodes and reported no
failure. `wf_429eef41-dff` lost 2 of 5; `wf_f13a44bd-742` lost 2 of 3 and still reported
top-level `status: "completed"` with every node reading `state: "done"`. Diagnosis ran
over **38 workflow runs / 426 agent nodes** across five repositories. Three independent
defects combined to make the loss invisible; all three are fixed here.

- **Turn-lifetime rule in `delegate-and-watch`.** The skill used to say verbatim *"No poll
  loop; no Monitor action; the watcher issues zero tool calls during the wait."* A workflow
  subagent has exactly one turn — turn end is termination, and no completion notification
  is ever delivered to a turn that has ended. The old `## Execution path` section and its
  O(1)-notification claim are gone, replaced by `## TURN-LIFETIME RULE (non-negotiable)`:
  turn end is termination; never end a turn while waiting (with the four banned final-message
  phrasings enumerated); `park` is not available to an agent node; `Monitor` is not a wait
  mechanism here.
- **Backgrounding is permitted; abandoning is not.** This distinction is the correction, and
  it is precise: all four *succeeding* nodes also used `run_in_background: true`, and their
  prose was indistinguishable from the failures' — spec-fixer said *"the harness will notify
  me when it exits"* and still succeeded, because it then issued a blocking foreground poll
  in the same turn. Backgrounding was never the fault. `run_in_background: true` is correct
  only when immediately followed, in the same turn, by the mandated blocking primitive: one
  foreground `timeout "${WATCH_BUDGET:-580}" bash -c 'until grep -qE … sleep 10; done'` call,
  re-issued as many times as the worker needs. A 30-minute dispatch costs about four of them.
  On exhaustion the watcher emits `ROLE_RESULT=ERRORED` with
  `ERRORED_REASON=watcher_budget_exhausted` — a typed failure beats a null node — and never
  parks. `park` is now documented in `docs/language-reference.md` as Workflow-graph control
  flow only, unreachable from a leaf.
- **`improve-loop` gets a third outcome.** The closed *clean-predicate label set* was two
  labels — clean vs findings — with no label for *the critic did not answer*, so generated
  workflows folded no-answer into clean. The set is now `clean` (the critic answered and
  found nothing), `findings` (answered, carries findings), and `no-answer` (produced no
  verdict at all — null, empty, or unparseable). `clean` exits the loop, `findings`
  re-dispatches the worker, and **`no-answer` is a dispatch failure, never a pass**:
  re-dispatch the critic once within the cap, then force exit and surface an explicit
  unverified result. A forced exit now distinguishes *still carries findings* from
  *never judged*. The L1 `loop-until-clean` row carries the same three labels so the
  pattern and the skill that realizes it cannot disagree.
- **Verify-node guard in all five L3 commands.** Generated workflows must separate three
  cases — `if (!verdict) { /* unverified */ } else if (!verdict.blocking) { /* clean */ }`.
  Collapsing them (`if (!verdict || !verdict.blocking) break`) reports an unverified run as
  verified, and a `try/catch` around `agent()` that returns `null` on a schema miss converts
  a hard harness failure into a false success. Both anti-patterns are transcribed from the
  script that actually failed.
- **`scripts/verify-run-completeness.sh` — the completeness gate.** New script implementing
  the soft-failure predicate: a node soft-failed if it has a `started` record in the run's
  `journal.jsonl` and no `result` record for the same `agentId`, scoped to the `agentId`s
  that also appear in `wf_<runId>.json` → `workflowProgress[]` with `type ==
  "workflow_agent"` (the journal carries superseded retry attempts; without the scope
  restriction you get one false positive per affected run). Validated at **35 PASS / 3 FAIL /
  0 INDETERMINATE with zero false positives across 426 nodes**. Exit `0` COMPLETE, `1`
  INCOMPLETE, `2` INDETERMINATE. It never derives the project slug from `$PWD` — the slug is
  fixed at session launch and `EnterWorktree` does not update it, so a pwd-derived slug would
  look in a nonexistent directory and no-op silently. Reporting fields (duration, tool calls,
  tokens, last tool) are optional and print `-` when the older run-file schema omits them,
  because a strict read would crash a real detection into "could not verify". **It fails to
  INDETERMINATE, never to a pass** — a harness format change degrades to *"I could not
  verify"*, never to a silent success.
- **The gate is always-on, not opt-in.** Every L3 command's closing self-check now runs it and
  branches on the exit code. The old self-check verified **shape** (one run, nothing inline)
  and never **completeness**. Always-on because the failure is invisible exactly when it
  matters: an opt-in check is enabled by someone who already suspects a problem, and this
  class produces no symptom to suspect — `wf_f13a44bd-742` reported `completed`. And because
  a soft check reproduces the very bug it fixes: the `safeAgent` try/catch was itself a soft
  mitigation, and its softness is what converted the hard failure into a false success.
  Making the gate advisory would be the same mistake one level up. Cost is two file reads and
  a set difference — no model tokens — against the 150K tokens and 350s the dead nodes burned
  in one run.

Rejected predicates, recorded so they are not re-proposed: `lastToolName !=
"StructuredOutput"` (nine false positives — nodes given no `schema:` legitimately never call
it, and 21 more lack the field), and `state != "done"` (`"done"` on 426/426 nodes, including
all five dead ones — it carries no signal).

## 4.15.0 — 2026-07-25

**Minor — `/relay:implement` now ends verified implementation runs with a polish tail.**

- **Raw slash-command helper.** New `scripts/run-claude-command.sh` runs one bare acpx Claude
  command turn with `sessions ensure`, quiet approve-all execution, cwd pinning, timeout override,
  and a final `POLISH_CMD_RC=<n>` token. It also closes the session it opened, so a polish run no
  longer leaks two permanently open sessions and a same-cwd re-run starts clean instead of
  resuming the prior conversation.
- **Polish spine.** All five `/relay:implement` kind branches append `polish-simplify` then
  `polish-review` after `verify`, unconditionally.
- **No availability gate.** There is no Step 0.1 probe and no second acpx version floor. The
  helper works on acpx 0.10.0 — the `>= 0.12.0` floor exists only for `--model` validation, which
  this path never uses, so gating on it would have made the whole feature dead code. acpx preflight
  belongs to `/relay:setup`; polish runs strictly after `verify`, so an unavailable acpx costs no
  work and is reported from the exit code.
- **Exit code `69`, not `127`, for a missing acpx.** acpx itself exits 127 when it cannot spawn the
  adapter, so passing 127 through made the two indistinguishable. `69` (`EX_UNAVAILABLE`) joins the
  `64`/`66` sysexits the helper already returned; the leaf reports it as
  `skipped (acpx unavailable)`.
- **Literal session names.** `relay-polish-simplify` / `relay-polish-review` replace the
  never-defined `relay-polish-<run-id>-<step>`. acpx scopes sessions by
  `(agentCommand, cwd, name)` and each run gets its own worktree, so cwd already separates runs.
- **Commit and report contract.** Simplify commits as `refactor(<scope>): simplify implementation`;
  review commits as `fix(<scope>): apply code-review findings`; both leaves soft-fail after one
  retry and report ran / skipped / failed status, with `/code-review max --fix` findings summarized
  when available.

## 4.14.0 — 2026-07-24

**Minor — in-session tiers ON by default, an `inherit` rung so a stronger session model
actually reaches the leaves, and one resolution site instead of a prose paragraph.**

Running an L3 command on a frontier model put *every* leaf on that model: `in_session_tiers`
defaulted to `false`, so the per-role tier table shipped in 4.12.0 never applied and each
`agent()` node silently inherited the session model. Four defects behind that, all fixed.

- **In-session tiers default ON.** `parse-engine-agent.sh` now starts from
  `RELAY_IN_SESSION_TIERS=1`; only an explicit `"in_session_tiers": false` in
  `.claude/relay.json` opts out. The gate read is an explicit `has()` check rather than
  `// true`, because the alternative operator cannot distinguish an absent key from a
  literal `false` and would have silently ignored the opt-out.
- **New `inherit` tier rung.** Never-downshift stopped being a hardcoded trio repeated
  across five command bodies and became data: `plan-writer`, `spec-simulator`, and
  `panel-moderator` carry `model: inherit`, which omits `opts.model` so the node runs on
  the session model while still applying its pinned `opts.effort`. This is what makes
  launching a session on a stronger model buy anything at the leaves.
- **Re-curated ladder, chosen by failure mode.** The table had collapsed to 21 sonnet /
  3 opus with `haiku` and `fable` unreachable, so the gate bought almost nothing even when
  on. Now 3 `inherit` / 3 `opus` / 15 `sonnet` / 3 `haiku`: critics and fix-planners whose
  miss mode is a false CLEAN moved up (`spec-reviewer`, `code-reviewer`, `fix-planner`);
  mechanical and script-backed roles moved down (`server-runner`, `navigator`,
  `doc-reference-reviewer`). Simulator mirroring is preserved. A test now asserts every
  rung stays in use so the ladder cannot silently re-collapse.
- **`scripts/resolve-tier.sh` — one resolution site.** Tier assignment was a prose
  paragraph each command re-derived by hand, with no validation; `delegate-leaf` never
  mentioned model at all. The resolver reads `bindings/presets.yaml` and prints the table
  (`--all`) or one role's row; every command body now calls it and transcribes the output.
  It honors `RELAY_IN_SESSION_TIERS` when exported and otherwise reads the config itself.
- **`/relay:diagnose` can resolve tiers at all.** It generates `agent()` nodes but had no
  `Bash` in `allowed-tools` and no Step 0, so it could never apply a tier. It gains `Bash`
  and the Tier note. The 4.12.0 enforcement tuple `CMD_NAMES` excluded `diagnose`, which
  is why CI never saw the gap; tier-note coverage now runs off a separate list that
  includes it.
- **`selecting-the-right-model` rewritten to match reality.** It documented a three-layer
  stack with a live model-inventory query, a staleness detector, and classes
  (`claude-default`, `codex-reasoning`, `codex-mini`) that no code ever implemented, and
  cited a `docs/spikes/` directory that does not exist. Nothing referenced it. It is now an
  accurate map of the three real paths (in-session flat tiers, `modalities.codex`,
  `modalities.opencode`) and names the two scripts that actually resolve them.
- **`delegate-and-watch` watcher nodes pinned to `sonnet`/`low`.** The outer watcher
  `agent()` node — launch the worker turn, await the completion notification, classify the
  five-bucket exit, compose the continuation prompt — inherited the session model, putting
  the frontier model on the one node whose context accumulates O(turns) while the real
  reasoning happens inside the acpx worker session (`modalities.*`). The pin is a node-kind
  constant in `resolve-tier.sh` (`resolve-tier.sh watcher`; also printed in the `--all`
  header), not a 25th presets row, because the watcher's job is identical whatever role it
  delegates. Sonnet rather than haiku: continuation prompts and `blocked`/`needs-decision`
  routing carry judgment nothing downstream reviews. Honors the same `in_session_tiers`
  gate — when tiers are off the watcher inherits like every role.
- **Review hardening (same release).** Both gate readers now derive the
  `.claude/relay.json` path from `git-common-dir` (the primary checkout), so entering a
  worktree at Step 0.5 no longer silently drops an untracked `"in_session_tiers": false`
  opt-out; `RELAY_IN_SESSION_TIERS` is strictly validated as `0`/`1` (exporting `false`
  used to silently mean ON); the config must be a JSON object with its own error message,
  and an explicit `"in_session_tiers": null` — accepted as OFF by 4.13.0's `// false`
  read — now fails loudly as non-boolean; `resolve-tier.sh --help` answers before any
  config I/O, the OFF header names the real gate source and always carries the watcher
  line, and the presets awk drops a malformed role entry instead of misattributing its
  fields to the previous role. `acpx-dispatch.sh` refuses to forward the literal
  `inherit` as a model id; `agents/code-reviewer.md` frontmatter moved to `opus` in
  lockstep with its re-curated binding; and `relay:refining`'s in-session Agent-tool
  dispatch procedure now resolves each role's tier via `resolve-tier.sh` (with the
  `refining-prs` / `refining-ui` adapter `model:` hints re-synced to the bindings they
  mirror).

Not addressed: `modalities.claude` is still `opus` at all 24 roles, so the acpx-claude path
has no model differentiation — only effort varies. Tracked separately.

## 4.13.0 — 2026-07-20

**Minor — repo-grounded simulators, findings-file read-back in the refining loop, and an
in-place default for refine's worktree gate.**

- **Simulator repo-grounding + UNVERIFIED discipline.** `plan-simulator` and
  `spec-simulator` now verify claims about the codebase, environment, dependencies, and
  file contents (Read/Grep/read-only shell) before reporting, cite `file:line` evidence in
  the concern field, prefix anything they cannot verify with `UNVERIFIED:`, and treat a
  confidently-wrong finding as costlier than a missed one.
- **`run_bash` for simulators.** Both simulator roles' frontmatter `requires` gains
  `run_bash` (read-only execution only — never mutate files or state) to back the
  grounding and Executable Claims work.
- **Executable Claims lens.** New cross-cutting lens/gap pattern: run any command, regex,
  or script the document specifies and compare actual output to what it claims.
  plan-simulator now scans eleven lenses (eight cross-cutting + three plan-specific);
  spec-simulator scans eight gap patterns.
- **Findings-file read-back.** `relay:refining`'s coordinator now Reads the critic's
  findings file at the captured `FINDINGS_PATH` — the parsed structured block IS the
  loop's findings list (a missing/empty file is a critic failure for the round via
  `record_failure`, never zero findings) — and populates the fixer's `{{FINDINGS}}` slot
  from that read-back content, keeping `{{FINDINGS_PATH}}` as the file-path fallback.
- **Refine defaults to in-place.** `/relay:refine`'s Step 0.5 worktree gate now carries
  the `(Recommended)` marker on the in-place option (refinement reads and patches in
  place); isolation stays opt-in for refine and remains the default for
  implement/execute/drive, whose behavior is unchanged.

## 4.12.0 — 2026-07-16

**Minor — pinnable dispatch axis with provenance, opt-in in-session tier downshift, and a
dispatch-cost benchmark harness.**

- **Layered axis resolution.** `--engine`/`--agent` on all four L3 commands now resolve
  flag > `.claude/relay.json` pin (new top-level `engine`/`agent` keys) > default, per axis.
  Pins pass the same enum + cross-arg invariants as flags and fail loudly at Step 0. The
  axis echo is provenance-stating — `[relay] dispatch axis: … (source: flags|relay.json|default|…)`
  (note: the previous `resolved dispatch axis` wording is gone; transcripts and greps change).
- **Ask-when-unpinned.** Flagless, pinless, interactive runs get one AskUserQuestion
  (in-session default vs acpx/hybrid; smart-routing deliberately not offered). Headless
  (`claude -p`) and `drive --resume` runs skip it and proceed on the default. Pinning
  engine/agent in `.claude/relay.json` skips it permanently.
- **In-session tier downshift (default OFF).** Every presets.yaml role gains a curated flat
  `effort:` beside a re-curated flat `model:` (Workflow enum: haiku|sonnet|opus|fable). With
  `"in_session_tiers": true` in `.claude/relay.json`, in-session `agent()` nodes are
  generated with `opts.model`/`opts.effort` from those fields — except `plan-writer`,
  `spec-simulator`, and `panel-moderator`, which never downshift (silent-failure roles).
  Flipping the default is a future decision backed by bench data.
- **`bench-dispatch-cost.sh`.** Dev harness benching the same task in-session vs
  acpx+codex via `claude -p --output-format json`: Claude dollars + per-model usage,
  codex tokens from `~/.codex/sessions` (mtime-window, last-cumulative token_count per
  file), wall-clock, markdown report with the two framing caveats (cross-plan billing;
  prompt-cache asymmetry). No runtime coupling; see `--help`.
- **Doc-reference critic silent-no-op fix.** `scripts/doc_reference_scan.py` acquired its
  local diff with a bare `git diff base...HEAD`, so on any machine with `diff.external`
  configured (difftastic/delta) git emitted a non-unified patch, the parser found zero added
  lines, and the introduced-reference critic reported `CLEAN` while checking nothing — a false
  negative in every `relay:refining-prs` run on such machines. Both local-diff invocations now
  pass `--no-ext-diff`. This turns the 6 long-standing `test_doc_reference_scan.py` failures
  green (full suite: 1246 passed, 10 skipped, **0 failed**); it also makes three
  plugin-aware tests that had been passing only because parsing returned nothing actually
  exercise their assertions.

## 4.11.0 — 2026-07-15

**Minor — make the dispatch axis actually reach the UI refine loop, and stop the silent flag drop.** Four stacked defects meant `/relay:refine --engine acpx --agent codex` (and every other engine-axis invocation) silently ran in-session on Claude while reporting success. All four are fixed.

- **The Step 0 flag parser was dead code.** The harness runs each command's Bash block as a standalone script with zero positional parameters, so the old `while [ $# -gt 0 ]` loop never iterated and both flags always resolved to their `in-session`/`claude` defaults — for `refine`, `implement`, `execute`, and `drive` alike (drive additionally lost its oracle path). All four now parse `--engine`/`--agent` from the interpolated `$ARGUMENTS` string, tolerate an optional surrounding quote (`--engine "acpx"` no longer silently defaults), and never touch positionals. The `test_step0_never_reads_positional_parameters` guard is hardened to actually catch `$#`, `$@`, `$*`, `set --`, and `shift` (the previous comment-stripper disabled its own `$#` check).
- **`skills/refining-ui` gained the `engine:`/`agent:` config keys** its three sibling shims already had, and **`commands/refine.md` now lists `relay:refining-ui`** in the axis-propagation set, so the resolved literals reach the UI target instead of falling back with no error.
- **`ui-generator` and `ui-code-evaluator` are now delegation-eligible** (source-only roles; `ui-generator` pins `isolation: none` because the UI adapter is git-backed). The three browser critics — `ui-visual-evaluator`, `ui-ux-evaluator`, `ui-accessibility-evaluator` — deliberately stay in-session: they judge screenshots, and the codex models relay dispatches have no vision.
- **Engine tooling floor:** the codex three-tier models (`gpt-5.6-sol`/`-terra`/`-luna`) require codex CLI ≥ 0.144.4 and `@agentclientprotocol/codex-acp` ≥ 1.1.2; older builds reject `terra` (HTTP 400) and never advertise `sol`/`luna`.

## 4.10.0 — 2026-07-13

**Minor — engine/agent dispatch axis for refine, execute, and drive.** `/relay:refine`, `/relay:execute`, and `/relay:drive` now accept the same `--engine` / `--agent` routing flags as `/relay:implement`; flagless invocations remain in-session Claude runs. Eligible Workflow leaves use `delegate-and-watch` for ACPX and smart-routing requests.

- Refining persists its resolved dispatch axis across rounds and can delegate eligible critics/fixers with the requested Claude, Codex, or OpenCode worker; each OpenCode role uses a fresh session.
- `code-reviewer` and `doc-reference-reviewer` are now delegation-eligible. `server-runner` remains in-session because a delegated server dies with its worker process and would leave downstream users with a dead `BASE_URL`.
- Preset mechanisms, modalities, the aggregator, and panel routing are unchanged at this version; UI-target refine stays in-session here (extended to delegate in 4.11.0). Note: the `--engine`/`--agent` flag parser introduced here was subsequently found to silently drop both flags — fixed in 4.11.0.

## 4.9.0 — 2026-07-13

**Minor — opencode engine presets (OpenCode Go open-weight ladder) + acpx 0.12.0
migration + engine-setup assistant.** All 24 roles in `bindings/presets.yaml` gain a
`modalities.opencode` block mirroring the codex three-slot ladder with open-weight
models served via the OpenCode Go subscription. The `opencode-go/` model-id prefix IS
the provider pin: opencode resolves the serving provider from the prefix, so no other
connected provider can serve (or bill) these dispatches.

- **`opencode-go/kimi-k2.7-code`** (sol-slot) — `plan-writer`, `spec-simulator`,
  `fix-planner`, `panel-moderator`.
- **`opencode-go/minimax-m3`** (luna-slot) — `implementer`, `fix-coder`, `test-writer`,
  `ui-generator`, `server-runner`, `plan-simulator`.
- **`opencode-go/kimi-k2.6`** (terra-slot) — the remaining 14 everyday roles.
- No `effort` key on opencode modalities: open-weight models define no acpx effort
  values (ACP -32602 on `set effort`); the session driver soft-degrades to the model's
  default reasoning. Simulators keep the one-hop mirror rule from 4.8.0.
- **acpx floor raised to 0.12.0** (was 0.7.0 in `setting-up-relay`): 0.10.0 persists an
  opencode `set model` but fails every subsequent prompt (the adapter doesn't advertise
  generic ACP model selection); 0.12.0 applies it correctly — verified end to end with
  the served provider/model confirmed from opencode's sqlite message store. Caveat
  (documented in presets + driver): the model binds at a session's FIRST prompt;
  mid-session `set model` is silently sticky — one session = one role = one model.
- **Codex dispatch migrated to 0.12.0 semantics:** 0.12.0 strictly validates `--model`
  against adapter-advertised plain ids, so the pre-0.12 bracket encoding
  (`gpt-5.6-terra[high]`) is rejected. Both one-shot exec sites now pass the bare model
  id and carry reasoning effort via the `CODEX_CONFIG` adapter env (JSON merged into
  the Codex session config; verified via codex rollout `turn_context`). The
  codex-session multi-turn driver keeps the legacy bracket contract (path pre-existing
  non-functional under acpx's registry pin — see 4.6.1).
- **`acpx-dispatch.sh`:** new `acpx-opencode` case in the modality selector
  (`modalities.opencode.model/effort`, flat fields as fallback).
- **New skill + command:** `setting-up-engines` (`/relay:engines`) — interactive
  assistant that configures and verifies codex + opencode for acpx dispatch: acpx
  version preflight, provider auth checks, live pinned-model probes, and a
  served-model audit against each engine's own session records (codex rollout JSONL,
  opencode sqlite).
- **Tests:** opencode modality allowlist + `opencode-go/` prefix pin + codex-tier
  mirror invariant (`test_plugin.py`); plain-model + `CODEX_CONFIG` cli-shape and
  opencode modality-selection dispatch tests (`test_acpx_dispatch_exec.py`); fixture
  `model-inventory-stub.yaml` gains the opencode inventory.

## 4.8.0 — 2026-07-13

**Minor — migrate codex model routing to the GPT-5.6 tier family.** `gpt-5.3-codex-spark`
is retired (no longer `supported_in_api` on this account/plan); `gpt-5.5` is superseded.
All 24 codex-dispatched roles in `bindings/presets.yaml` now route to one of three
GPT-5.6 tiers, chosen by role demand rather than a flat two-way split.

- **`gpt-5.6-sol`** (flagship) — the most demanding planning/architecture roles:
  `plan-writer`, `spec-simulator`, `fix-planner`, `panel-moderator`.
- **`gpt-5.6-luna`** (fast/affordable) — code-writing roles that execute against an
  already-vetted plan/spec: `implementer`, `fix-coder`, `test-writer`, `ui-generator`,
  `server-runner`, and `plan-simulator`.
- **`gpt-5.6-terra`** (balanced) — the remaining 14 everyday judgment/review roles.
- **Simulator convention:** a simulator role's `(model, effort)` mirrors the role that
  acts on its artifact next, so the simulation reflects the actual execution tier it's
  predicting risk for — `spec-simulator` mirrors `plan-writer` (Sol/xhigh, effort bumped
  from `high`); `plan-simulator` mirrors `implementer` (Luna/high, moved out of Sol and
  effort reduced from `xhigh`). All other roles keep their existing `effort` unchanged.
- **Docs/tests:** updated the `selecting-the-right-model` illustrative example, the
  `model-inventory-stub.yaml` test fixture, and hardcoded model-id assertions in
  `test_plugin.py`/`test_acpx_dispatch_exec.py` to match.

## 4.7.0 — 2026-07-06

**Minor — Per-worktree bootstrap for relay-created worktrees.** Fresh worktrees can now
run a repo-declared setup command before the Step 0.5 gate enters them, so downstream
verification sees installed dependencies and built artifacts.

- **`scripts/worktree-preflight.sh`** reads `.claude/relay.json` from the primary checkout,
  extracts the string `bootstrap` command with `jq`, and runs it in the new worktree after
  `git worktree add` succeeds. Bootstrap output is routed to stderr so stdout remains a
  clean `RELAY_WT_*` block.
- **Failure contract:** invalid JSON fails before worktree creation; `bootstrap failed`
  exits non-zero after creation but prints no `RELAY_WT_CREATED_PATH`, so the existing gate
  aborts and never calls `EnterWorktree`.
- **Observability:** `--create` now prints `RELAY_WT_BOOTSTRAP=ran` or
  `RELAY_WT_BOOTSTRAP=skipped`. Missing config, missing key, and empty string all skip
  cleanly.
- **Docs/tests:** added throwaway-repo pytest coverage for the bootstrap paths, documented
  `.claude/relay.json`, and linked the config reference from `relay:using-relay`.

## 4.6.1 — 2026-07-03

**Patch — bake the confirmed acpx codex-registry workaround into `acpx-dispatch.sh` at the
source, instead of leaving it as one-off prompt text discovered mid-run.** acpx's own
built-in registry pins the codex mechanism to `@agentclientprotocol/codex-acp@^0.0.44`,
which has repeatedly proven incompatible with current `codex-cli` releases and silently
fails the dispatch. Every future `/relay:implement --engine acpx --agent codex` (and any
other acpx/codex dispatch) now picks up the fix automatically.

- **`skills/dispatching-acpx-agents/acpx-dispatch.sh`**: new `ACPX_CODEX_AGENT_OVERRIDE`
  (default `npx -y @agentclientprotocol/codex-acp@latest`) applied to every one-shot codex
  `exec` dispatch — the fast-path branch and the generic `acpx-codex` mechanism's tail
  dispatch — via acpx's `--agent` escape hatch. acpx rejects combining `--agent` with a
  positional engine, so the `codex` positional is dropped from the assembled command
  wherever the override is active. Set the env var to `""` to fall back to acpx's normal
  `codex` resolution. Verified end-to-end 2026-07-03: 5 sequential
  `acpx --agent ... exec -f ...` dispatches landed real commits against `codex-cli 0.142.5`.
- **Deliberately NOT applied** to `codex-session-driver.sh` (the multi-turn session path
  used by folding roles with `verify_artifact`): its `sessions ensure` / `-s <session>`
  calls need the positional `codex` engine to scope sessions correctly — passing `--agent`
  instead falls back to labeling the session as acpx's default agent (`claude`), which
  would corrupt session scoping. Confirmed via manual `acpx` invocation; documented in
  `SKILL.md` as an open risk for a future session to resolve before extending the pattern
  there.
- **`SKILL.md`**: new "Codex registry override" subsection documenting the contract and the
  driver-path caveat.
- **`test_acpx_dispatch_exec.py`**: 3 new tests locking in the `--agent` override shape for
  both the fast-path and generic `acpx-codex` mechanism, plus the disable-via-empty-string
  escape hatch.

## 4.6.0 — 2026-07-01

**Minor — remove the Step 0.0 session-rename preflight (v4.5.0). The built-in `/rename` is
UI-only and is not exposed to `SlashCommand` on any harness, so the "best-effort" step
errored on every run instead of degrading silently.** Step 0.5 worktree isolation is
unaffected.

- **`scripts/session-slug.sh`** (removed) and its unit test `test_session_slug.py` (removed).
- **All 6 commands** drop the `## Step 0.0 — Name this session (best-effort)` block. The
  rename-only `SlashCommand` permission is removed from every command's `allowed-tools`;
  `diagnose` additionally drops `Bash` (its sole Bash use was `session-slug.sh`). Step 0.5's
  `Bash` / `EnterWorktree` / `AskUserQuestion` permissions on the modifying commands are kept.
- **`skills/using-relay/SKILL.md`** preflight section retitled to worktree isolation only; the
  Step 0.0 bullet is removed.
- **`test_worktree_session_steps.py`** drops the Step 0.0 assertions and gains
  `TestSessionRenameRemoved`, a regression guard that no command references `session-slug.sh`,
  carries a `Step 0.0` heading, or lists `SlashCommand`.

## 4.5.0 — 2026-06-24

**Minor — worktree isolation gate (Step 0.5) + session rename (Step 0.0) across the L3
command surface.**

### Session rename — Step 0.0 (all 6 commands, best-effort)

- **`scripts/session-slug.sh`** (new): normalizes a free-text phrase to a valid camelCase
  session slug via the pinned, deterministic transform order — lowercase → strip
  punctuation to boundaries + drop stopwords (`a an the of to and or in on for with`) →
  first ≤3 words → strip leading digits per token → camelCase → ~24-char word-boundary
  cap. Degenerate input (empty / all-stopword / punctuation-only / all-leading-digit)
  emits the caller-provided `--fallback <commandSlug>`. POSIX awk only, prints exactly one
  line to stdout, mirrors `parse-engine-agent.sh`.
- **Every command** gains a `## Step 0.0 — Name this session (best-effort)` preflight: pick
  2-3 salient words, source `session-slug.sh` to normalize, then attempt `SlashCommand`
  `/rename <slug>`. **Rename is best-effort and non-fatal** — if `SlashCommand` errors or
  the built-in `/rename` is unavailable on the running harness, the command continues
  silently (degrades to a no-op). Naming is a convenience (identifiable at a glance), never
  a correctness property. Per-command fallback slugs: `implement→relayImplement`,
  `refine→refineRefine`, `execute→relayExecute`, `drive→relayDrive`,
  `diagnose→relayDiagnose`, `setup→relaySetup` (`refine`/`drive` use the static fallback
  because their salient source is produced inside Step 0).

### Worktree isolation — Step 0.5 (the 4 source-modifying commands)

- **`scripts/worktree-preflight.sh`** (new): `--classify` (read-only) prints a parseable
  `RELAY_WT_*` block classifying git state as `worktree` / `main` / `stray` / `not-git`
  (non-zero on `not-git` to abort the command); `--create <base-ref>` (mutating, only
  post-confirmation) runs `git fetch origin <default>` (the "pull latest from main"
  requirement), creates a worktree under `.claude/worktrees/` on a fresh `relay/<slug>`
  branch off the chosen base (deterministic `git worktree add`, not `EnterWorktree({name})`
  whose base is governed by the global `worktree.baseRef` setting), suffixes `-N` on slug
  collision, and prints `RELAY_WT_CREATED_PATH`.
- **`skills/ensuring-worktree-isolation/SKILL.md`** (new, `user-invocable: false`): owns the
  full confirm/create/enter state machine for Step 0.5. Branches on the printed state,
  drives the per-state `AskUserQuestion` confirmation, creates a fresh worktree off
  `origin/<default>` (`main` state) or `HEAD` (`stray` state) when chosen, and enters it via
  `EnterWorktree({path})` **exactly once** — never re-switching afterward (the Step 1+
  Workflow runs in that single entered worktree). For `drive --resume` it runs
  **verify-only**, reading `RELAY_DRIVE_WORKSPACE` (`worktree`/`in-place`) from
  `loop-state.md` and asserting the cwd matches the recorded mode without prompting or
  creating. Self-contained — does **not** delegate to `superpowers:using-git-worktrees`.
- **`implement`, `refine`, `execute`, `drive`** gain a `## Step 0.5 — Ensure worktree
  isolation` preflight after the dependency/arg gate, before Workflow generation: source
  `worktree-preflight.sh --classify`, read the `RELAY_WT_*` block, invoke
  `relay:ensuring-worktree-isolation`. `execute.md` had no pre-existing Step 0, so it gains
  a brand-new Bash-touching preflight from scratch.

### allowed-tools deltas

- `SlashCommand` added to **all 6** commands (for `/rename`).
- `EnterWorktree` + `AskUserQuestion` added to the **4 modifying** commands.
- `Bash` added to `diagnose` (for `session-slug.sh`) and `execute` (new preflight); the
  other four already permitted it. `setup` **appends** `SlashCommand` without dropping
  `Bash`/`Skill`.

### Validator + roster edits (keep the suite green)

- `scripts/validate_l3_command.py` `_KNOWN` gains `ensuring-worktree-isolation` so the
  modifying command bodies do not fail with `unknown relay vocabulary token`. The skill is
  registered in `test_plugin.py` `EXPECTED_SKILLS` (auto-joining `INTERNAL_SKILLS`) but is
  **not** added to `L2_NAMES` and carries **no** `relay-vocab` block (it is not an L2/L1
  pattern shape).

### Build-time hard-gate proofs (spec §7.2)

1. `SlashCommand` can invoke the **built-in** `/rename` on the build harness (rename
   mechanism is feasible as designed). Runtime stays best-effort regardless.
2. `EnterWorktree({path})` accepts a just-created `git worktree add` worktree under
   `.claude/worktrees/` of the same repo, per the tool's documented precondition (the path
   must appear in `git worktree list`) — satisfied by the `--create` step.
3. `worktree.baseRef` independence — no existing relay test pins a `baseRef`
   (`grep -rn baseRef tests/` is empty), so creating via `git worktree add` does not
   couple to the user's global setting.

## 4.4.0 — 2026-06-23

**Minor — new `/relay:drive` L3 command + `driving-to-done` skill: autonomous oracle-gated run-to-done.**

### Drive to Done (additive)

- **`commands/drive.md`** (new): thin L3 command `/relay:drive` (`disable-model-invocation: true`,
  `allowed-tools: Bash, Workflow, Skill`, `argument-hint: "[--resume] <oracle-file>"`). Step 0
  sources `check-deps.sh` and resolves the oracle path + a self-delimiting `--resume` flag; the
  command loads `relay:driving-to-done`, then (uniquely among L3 commands) MAIN may launch a single
  long-lived process the oracle declares **before** issuing "Call the `Workflow` tool now" to
  generate exactly one dynamic Workflow over the oracle-gated loop.
- **`skills/driving-to-done/SKILL.md`** and **`skills/driving-to-done/templates.md`** (new):
  domain-agnostic protocol for driving a long-running, multi-step process to a verifiable done
  criterion without a human in the loop — surviving `/compact` and worktree loss. Hybrid control
  locus: MAIN owns at most one long-lived process; one dynamic Workflow runs the loop (orient →
  delegate → verify → branch → record → consecutive-clean-runs → closeout) with a fresh-seed reset,
  a per-step circuit breaker, and evidence-before-assertion honesty. `user-invocable: false`.
- **`docs/language-reference.md`**: new L1 shape `drive-to-done` (`acpx-leg-required: false`) plus
  seven L0 keywords — `oracle`, `done-criterion`, `clean-streak`, `fresh-seed-reset`,
  `circuit-breaker`, `evidence-before-assertion`, `closeout` — gated by the language-reference
  validator and its test.
- **`docs/orchestration-substrates.md`**, **`skills/using-relay/SKILL.md`**, **`README.md`**:
  list `/relay:drive` as the fifth L3 command and document the MAIN-owns-one-long-lived-process
  exception to "MAIN holds nothing".

## 4.1.0 — 2026-06-11

**Minor — fixer landing contract: pre-flight base pin + post-flight orchestrator verify.**

### Fixer Landing Contract (additive)

- **`roles/fix-coder.md`**, **`roles/spec-fixer.md`**, **`roles/plan-fixer.md`**: each gains an
  `EXPECTED_HEAD` input slot and a mandatory "Pre-Flight Base Pin" section. On dispatch, the
  fixer immediately runs `git rev-parse HEAD` and aborts with `BLOCKED: base-mismatch
  expected=<sha> actual=<sha> cwd=<path>` if the worktree does not match. Catches Variant B
  (wrong-worktree dispatch) at the earliest possible moment.
- **`skills/dispatching-in-session-agents/SKILL.md`** and **`skills/dispatching-acpx-agents/SKILL.md`**:
  new "Writer-Role Landing Contract" section. Pre-dispatch: coordinator captures `EXPECTED_HEAD`
  via `git rev-parse HEAD` in `WORKTREE`/`REPO_ROOT` and injects it + `WORKTREE_PATH` as slot
  values. Post-return: coordinator runs `git status --short` in the absolute worktree path
  (never the agent's self-reported cwd); edits absent without a valid no-change signal is a
  failure. Closes Variant A (uncommitted edits lost) by committing the dirty tree after a
  writer dispatch.
- **`skills/delegate-leaf/SKILL.md`**: Step 4 gains a mandatory landing-verify sub-step for
  writer-role dispatches.
- **`skills/delegate-and-watch/SKILL.md`**: done-gate gains writer-role landing-verify clause;
  empty-diff without no-change signal reclassifies as `errored` (`landing_verify_failed`).
- **`skills/refining/SKILL.md`**: landing-verify step inserted between `fixer.apply` and
  `adapter.post_fix` in the generic loop algorithm. New "Landing Verify Contract" section.
  Adapter-type branch: `pr` adapter commits with `refine(cycle-N): landing-verify`; spec/plan
  adapters check disk presence (no commit).
- **`skills/refining/adapters/pr.md`**: "Landing Contract Integration" section — `snapshot()`
  SHA is the `EXPECTED_HEAD` injected pre-flight; `persist()` gains clean-tree skip (avoids
  duplicate commits when landing-verify already committed) and destination clause (snapshot SHA
  must be ancestor of HEAD).
- **`skills/refining-prs/SKILL.md`**: banner refreshed — drops stale "behaviorally unproven"
  claim, references two successful live runs (PR #43, PR #44), retains REFINE-4 label.
- **`docs/dispatch-contract.md`** and **`docs/refinement-contract.md`**: new landing contract
  sections codify the cross-skill contract prose.
- **`tests/unit/skill-structure/test_fixer_landing_contract.py`** (new): 34 text/structure
  guards asserting all contract text additions are present, including 3 `WORKTREE_PATH`
  slot-declaration guards and 1 `SLOT_WORKTREE_PATH` materialization guard. Created in Task 0 as a red baseline (all guards fail) before
  any implementation task is applied. Full suite stays at 1027+ passed / 10 skipped.

## 4.0.0 — 2026-06-11

**BREAKING** — registered-agent surface shrinks 27→7.

### Agent-surface migration (PR3)

- **Roster 27→7**: 22 leaked internal agents collapsed to `roles/` directory.
  Registered agents: `code-reviewer`, `scout` (user-facing), `leaf-worker`, `leaf-reader`
  (generic execution leaves), `gatherer`, `strategist`, `analyst` (Workflow-only diagnosis trio).
- **New `roles/` directory**: 22 role files (`roles/*.md`), one per collapsed agent.
  Bodies preserved verbatim; frontmatter rewritten to role format (`role-class`, `output-tokens`,
  `input-slots`, `terminal_token`, `requires`).
- **New `relay:leaf-worker`** (tools: Read/Write/Edit/Bash/Grep/Glob) and
  **`relay:leaf-reader`** (Read/Grep/Glob/Bash) dispatch the injected role body.
- **`bindings/presets.yaml`**: 24 bindings (was 19). Each entry gains `role-class`, `model`,
  `one_shot`, `max_turns`; `code-reviewer`/`scout` gain `role-class: registered` + explicit
  `agentType`; 5 new UI entries added.
- **Breaking capability changes** (§3):
  - Browser/Playwright roles (`navigator`, `ui-visual-evaluator`, `ui-ux-evaluator`,
    `ui-accessibility-evaluator`): Playwright MCP calls replaced by `npx playwright` CLI
    via `Bash`. `relay:running-web-apps` provisions Playwright; `relay:refining-ui`
    pre-flight checks `npx playwright --version` and emits `BLOCKED: playwright-cli-missing`.
  - Panel roles (`panel-member`, `panel-moderator`): WebSearch/WebFetch/perplexity MCP
    dropped. Role bodies rewritten to ground verdicts in repo evidence only.
- **New CI validators** (§10): roles-frontmatter validity, no-de-registered-agentType scan,
  leaf-tool-lists-exact, bindings-bijection, derivation-table presence, roster-pin.
- **Migration note for external consumers**: `RELAY_ROLE_PATH` env var still honored.
  Collapsed slugs (e.g. `relay:spec-fixer`) are no longer registered agentTypes; use
  `relay:leaf-worker` with the assembled role body prompt instead.
- **Documentation**: `docs/dispatch-contract.md` §5.1 amended with agentType derivation
  table; `docs/language-reference.md` audited; `roles/README.md` added.

## 3.5.0 — 2026-06-10

**Minor — relay surface changes required by firework PR 2 (dynamic-workflows rebuild).**

- **`needs-decision` fifth watcher bucket** (`skills/delegate-and-watch/SKILL.md`): the four-bucket
  classification table gains a fifth terminal peer `needs-decision`. The watcher's crash-cleanup
  trap is now conditional (`PARKED=0` initialized before the main loop; trap gates on
  `[[ "$PARKED" != "1" ]]`), leaving sessions open-but-detached on intentional park instead of
  closing them (S1 spike outcome: close + re-ensure silently forks a blank session).
- **`NEEDS_DECISION:` first-line branch** in all three session drivers
  (claude, codex, opencode) and the codex fast-path dispatch script, all in the
  `dispatching-acpx-agents` skill, each emitting `ROLE_RESULT=NEEDS_DECISION` +
  `QUESTION_TEXT`. The fast-path includes a misframed-output guard (co-presence with `ROLE_DONE`
  or multiple `NEEDS_DECISION:` lines demotes to `ROLE_RESULT=BLOCKED`).
- **`RELAY_MAX_TURNS`** integer turn cap (default 10) flows from caller env into the env
  sidecar so the delegate-and-watch watcher receives it. Fixes the dangling §4.3 reference.
- **`ACPX_SESSION_NAME_OVERRIDE`** honored ahead of the `${run}-${slug}` default in both
  dispatch blocks (firework uses `fw-<workflow>-<role>` names for cross-launch continuity).
- **`RELAY_ROLE_PATH`** external role-file override on the dispatch path; typed error on
  missing file rather than silent fallback. Documented external API distinct from the internal
  `ROLE_PATH`.
- **`AUTONOMY=interactive` preamble variant** in the dispatch preamble file (`dispatching-acpx-agents` skill): licenses
  `NEEDS_DECISION: <question>` as a terminal envelope line, forbids `AskUserQuestion` in the
  child, clarifies `ROLE_DONE` is emitted only on full completion.
- **Authoritative `ROLE_RESULT` enum** `{DONE, NOT_DONE, BLOCKED, ERRORED, NEEDS_DECISION}`
  documented in `skills/dispatching-acpx-agents/SKILL.md`; stale `ACPX_MAX_TURNS` and
  `ACPX_NUDGE_PROMPT` references removed.
- **Public envelope contract** section added to `docs/dispatch-contract.md`, declaring the
  four frozen tokens (`ROLE_DONE`, `BLOCKED:`, `NEEDS_DECISION:`, `KEY=VALUE` grammar) and
  reconciling the stale §5.1 content (wrong capture regex, stale vars). Verbatim-token static
  gate at `tests/unit/skill-structure/test_envelope_tokens.py`.
- **`relay:check-readiness`** new thin model-only skill (non-interactive): runs
  `scripts/check-deps.sh --agent <set> --format json` + acpx CLI preflight (version ≥ 0.7.0 +
  flow subcommand), returns structured `{ok, agents[]}` matrix. Firework driver invokes it
  when any preset binding is off-claude.
- **diagnose Workflow-check removed**: the prose in `skills/using-relay/SKILL.md` describing
  conditional degradation when `CLAUDE_CODE_DISABLE_WORKFLOWS=1` is set is removed. The
  Workflow tool is GA; there is no runtime availability check.
- **`agents/README.md` corrections**: count updated 22→27 (adds the 5 UI agents introduced
  in v3.2.0); leaf-enforcement mechanism sentence updated from "denied at runtime" to "absent
  at session initialization" (S2 spike confirmation).

## 3.4.0 — 2026-06-09

**Minor — drop the `--kind` override; task kind is always auto-classified from context.**

- **`--kind` removed from all four L3 commands** (`implement`, `refine`, `execute`, `diagnose`).
  `relay:classifying-task-kind` already inferred the closed kind (`feature | script |
  config-artifact | bugfix | docs`) from the task text; `--kind` was only an override layer on
  top. The plugin now always characterizes the work from context and selects the workflow spine
  accordingly — there is no user-facing flag. The §4.2.1 branch table is unchanged (it keys on
  the classifier's `kind.value`, which is unaffected).
- **Both static gates inverted to forbid the flag.** `validate_l3_command.py` and
  `tools/fidelity-check.sh` previously *required* a `--kind` surface in every L3 body; they now
  flag its *presence* as an error, locking the removal against regression.
- **Classifier skill simplified**: the "honor the override first" step is gone; classification
  is a pure context inference.
- Docs (`README.md`, `using-relay/SKILL.md`) updated; the `/relay:implement` usage line now
  documents `--engine`/`--agent` (the only flags it takes) and no `--kind`.
- **Doc fix**: corrected three references to a non-existent `CLAUDE_CODE_WORKFLOWS=1` enable
  variable (README + using-relay). Dynamic workflows are on by default; they are turned *off*
  via `/config`, `"disableWorkflows": true`, or `CLAUDE_CODE_DISABLE_WORKFLOWS=1`. `/relay:diagnose`
  needs them enabled, and silently degrades to in-session subagent dispatch when they are not.

## 3.3.0 — 2026-06-09

**Minor — restore the engine/agent routing surface on `/relay:implement`.**

- **`--engine` / `--agent` on `/relay:implement`** (acpx-delegation spec §5, §8.8): the
  thin-L3 rewrite (v3.0.0) had dropped the command-level arg wiring while keeping the
  vestigial delegation note, so `--engine acpx` was unreachable. Step 0 now resolves
  `--engine in-session|acpx|smart-routing` and `--agent claude|codex|opencode|hybrid|smart-routing`
  via the (already-extended) `parse-engine-agent.sh`, exports `RELAY_ENGINE`/`RELAY_AGENT`,
  and Step 3 threads `$RELAY_ENGINE` into the `relay:delegate-and-watch` substitution.
  Flag-form (self-delimiting against the free-text task); `in-session` remains the default.
  `refine`/`execute`/`diagnose` stay arg-exempt (spec §8.8 — they route no delegation-eligible roles).

## 3.2.0 — 2026-06-09

**Minor — UI-refinement feature (scored convergence) integrated onto the L3 engine.**

- `convergence_mode: scored` engine extension, `ui` refining adapter + `refining-ui` shim,
  five ported `ui-*` agents, the generic `/relay:refine` command, and the `running-web-apps`
  skill, reconciled with the layered-DSL L3 surface (PRs #37 + #39).

## 3.1.0 — 2026-06-06

**Minor — Phase D (acpx delegation integration) on top of the v3.0.0 Workflow substrate.**

- **`delegate-and-watch` L2 skill** (`skills/delegate-and-watch/SKILL.md`): watcher
  that backgrounds one acpx worker turn, awaits the completion notification, classifies
  the outcome into four buckets (done / not-done / blocked / errored), and routes via a
  park/router-loop. The watcher owns the multi-turn loop, session lifecycle (`sessions
  close` trap on EXIT), and the `${session}.env` sidecar sourcing. Session drivers are
  thinned to single-turn invocations.
- **Session driver two-log contract** (Phase D2): all three thinned drivers
  (`codex-session-driver.sh`, `claude-session-driver.sh`, `opencode-session-driver.sh`)
  now write the full turn stdout to `~/.acpx/sessions/${session}.turn.log` (the
  dedicated turn-content channel the watcher reads at each boundary). The forensic
  metadata log (`${session}.driver.log`) continues to record timestamp/rc/byte-count
  only.
- **`routing-work-to-agents` and `selecting-the-right-model`** resolution/policy skills
  scaffolded under `skills/`; consulted by `mechanism-resolve` at Workflow-generation
  time.
- **`smart-routing` engine/agent** added to `parse-engine-agent.sh`; defaults agent to
  `smart-routing`; enforces `in-session ⇒ claude` invariant; behavioral suite updated.
- **`delegate_eligible` field** in `bindings/presets.yaml` (8 eligible roles, 11
  ineligible); eligibility enforced at Workflow-generation time by `implement.md`.
- **`delegate-and-watch` wired into `implement.md`**: when `--engine acpx` or
  `smart-routing` and the role's `delegate_eligible` is `true`, the L3 command
  selects `relay:delegate-and-watch` over `relay:delegate-leaf`.
- **`validate_l3_command.py`** extended with `check_delegation_wiring()` (verifies
  `delegate-and-watch` wiring in `implement.md`) and `diagnose.md` added to `main()`.
- **L0 vocabulary**: `nudge` removed (count 27 → 26); `multi-turn-dispatch` and
  `router-loop` updated to turn-boundary-only; `session-grounding` replaces `nudge`
  in their `l0-deps`.
- **`plugin.json`** bumped to `3.1.0`.

## 3.0.0 — 2026-06-05

**Breaking — Phase-4 teardown of the three-dispatch-families pipeline fork.**
Removes the `RoleDispatchMap` materialization + threading, `wrapper-setup.sh`, the `implementing` /
`executing-task-cycle` / `resolving-decision` / `verifying-spec` coordinators, and
`workflows/diagnose.js`. The native dynamic Workflow tool is now the single orchestration substrate;
in-session-vs-acpx is demoted to a per-leaf binding resolved per role at Workflow-generation time.
`bindings/presets.yaml` survives as the per-role binding source (pipeline-fork header removed).
`/relay:setup` is unchanged at the command layer (it never bootstrapped the dispatch map).

## 1.2.0 — 2026-05-28

Adds the **`doc-reference-reviewer`** critic — a read-only, one-shot stale-documentation-reference
checker (broken introduced links/paths/anchors + dangling references to renamed/deleted docs)
backed by the stdlib-only `scripts/doc_reference_scan.py` helper. Wired as a non-debated critic in
`refining-prs` and promoted into `bindings/presets.yaml` `roles:`. Roster moves to **19 agents**.

- **Plugin-aware reference resolution.** The scan helper walks up from each doc file toward the
  nearest `.claude-plugin/plugin.json` marker as the canonical plugin root before falling back
  to the repo root, so cites inside a plugin doc (`relay:<X>`, `agents/<X>`, bare paths) resolve
  against `plugins/<plugin>/` rather than only the repo root.
- **Precise `DOC_SCRIPT_RE` matching.** The `package.json` doc-gate discovery regex requires
  `link` to be at the start of the (sub-)script name or after a `:` namespace separator AND
  followed by a separator/terminator or known link-checker suffix. This correctly rejects
  unrelated npm scripts (`unlink`, `npm-link`, `validate-link`, `linkedin-share`) while still
  matching `link`, `link-check`, `link-checker`, `lint:link`, `lint:link-check`, `links`.
  (Pragmatic loss: a script literally named `markdown-link-check` no longer auto-discovers;
  the typical alias `link-check` still does.)
- **Makefile/justfile discovery + test coverage.** `discover_doc_gate` recognises `make`/`just`
  doc targets via `^(docs?[\w-]*):` line-anchored under `re.M`, with `GATE_NAME_RE` validation
  on the captured target name and a `Makefile`-then-`justfile` precedence. The Makefile/justfile
  branch is now exercised by 6 dedicated tests (target discovery, tab-indented-recipe rejection,
  metachar-target rejection, npm-over-Makefile precedence, Makefile-over-justfile precedence).
- **Command-injection hardening.** `_gate_argv` validates discovered names against a strict
  `GATE_NAME_RE` allowlist (`[A-Za-z0-9:_.-]+`) and only accepts the three canonical forms
  (`npm run <name>`, `make <target>`, `just <target>`), so attacker-controlled `package.json`
  keys or `Makefile`/`justfile` target names from untrusted PR content can never reach a shell.

## 1.1.0 — 2026-05-27

Fork-dependency closure: `/relay:implement` now runs against the **unmodified
upstream `obra/superpowers`** instead of the deprecated `404pilo/superpowers`
fork. Roster stays **18 agents**.

- **`relay:verifying-spec`** Phase-6 coordinator + deterministic helpers
  (`normalize-scenarios.py`, `detect-runnable.sh`, `extract-test-verdicts.py`),
  replacing the runtime `superpowers:verify-spec` fork dependency.
- **`relay:scout` agent** owns Phase-0 context gathering, producing the
  `CONTEXT_SUMMARY` consumed by later phases; stale `superpowers:scouting` doc
  labels relabelled to relay-owned primitives. (The thin `scouting` coordinator
  skill was later removed — the `scout` agent is dispatched directly.)
- **Autonomous brainstorming as an acpx flow** (`flows/brainstorm.flow.ts`):
  drives the unmodified `superpowers:brainstorming` skill headless via a warm
  `acp` node ⇄ context-grounded `decide` node, gated on a deterministic on-disk
  spec check. Decisions made where the supplied context is silent carry a
  `[provisional]` marker into the generated spec. Declares an `acpx >=0.7.0`
  floor (lockfile-pinned 0.10.0) and uses the `decision()`/`decisionEdge()`
  sugar. Validated end-to-end (job `c136182f`).
- **`/relay:setup`** command + **`setting-up-relay`** coordinator;
  `install-skill-from-github.py` codex provisioning fallback (traversal-guarded).
- **§7 upstream-compatibility guard** + shared dependency manifest; engine-aware
  `check-deps.sh` probe-set flip (the obra closed set is 14).

## 1.0.0 — 2026-05-21

Initial release. Multi-agent orchestration toolkit ported from and layered on
top of superpowers.

- **4 commands:** `/relay:implement`, `/relay:refine:spec`, `/relay:refine:plan`,
  `/relay:refine:pr` — each gated by a superpowers presence check and a shared
  `engine`/`agent` argument validator.
- **18 ported leaf agents** (`implementer`, `test-writer`, `code-reviewer`,
  `spec-reviewer`, `spec-simulator`, `spec-fixer`, `plan-simulator`, `plan-fixer`,
  `fix-coder`, `fix-planner`, `scout`, `plan-writer`, `navigator`,
  `server-runner`, `scenario-writer`, `panel-member`, `panel-moderator`,
  `panel-synthesizer`) carrying native-subagent frontmatter with no `Agent` tool
  (leaf enforcement).
- **Generic `refining/` loop + 3 adapters** (`refining-specs`, `refining-plans`,
  `refining-prs`) implementing the shared refinement contract.
- **Dual dispatch:** in-session (parent subagent tool) and ACPX
  (`acpx <engine> exec`) backends, resolved through `bindings/presets.yaml`.
- **superpowers delegation:** non-orchestration primitives are delegated to the
  installed `superpowers:*` skills.
- **MIT-licensed** with full attribution to superpowers (Jesse Vincent).
