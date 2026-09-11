# Relay v4.5.0 — Worktree Isolation Gate + Session Rename — Implementation Plan

Status: ready-to-execute
Date: 2026-06-24
Spec: `plugins/relay/docs/superpowers/specs/2026-06-24-relay-worktree-isolation-and-session-rename-design.md`
Branch: `feature/relay-worktree-isolation-session-rename` (primary checkout — NEVER switch to main, NEVER create a real git worktree, NEVER push/PR)
Tooling: `python3` (not `python`); `bash` scripts sourced from command bodies.

---

## 0. Discipline & conventions (read before any task)

- **TDD throughout** (superpowers:test-driven-development): for every code/script/structure change, write the failing test FIRST, watch it fail for the right reason, then make it pass. Refactor only on green.
- **Match neighbors exactly.** New bash scripts mirror `scripts/check-deps.sh` / `scripts/parse-engine-agent.sh` (sourced, print `KEY=value` to stdout, `return`/`exit` non-zero on fatal, no reliance on env persisting across Bash calls). New skill mirrors `skills/driving-to-done/SKILL.md` frontmatter idioms (`name:`, `description:`, `user-invocable: false`). New tests live under `plugins/relay/tests/unit/skill-structure/` and import `parse_frontmatter` via the **path-explicit `importlib.util`** loader exactly like `test_l2_skills_present.py` (which warns against the bare `from conftest import parse_frontmatter` form because it relies on the invocation CWD); `parse_frontmatter` and `PLUGIN_ROOT` live in `tests/conftest.py`.
- **State crosses the Bash→Claude boundary as printed stdout, not env vars** (spec §3). Scripts PRINT; Claude READS and makes the tool calls bash cannot (`SlashCommand`, `AskUserQuestion`, `EnterWorktree`).
- **Run the whole suite after each task group**: from repo root, `cd plugins/relay && python3 -m pytest tests/unit -q`. Baseline at plan time: **1119 tests collected, all green.** No task may leave it red.
- **Existing validators that MUST stay green** (touched by this change, verify after each relevant task):
  - `scripts/validate_l3_command.py` (driven by `tests/unit/skill-structure/test_l3_command.py`) — flags any `relay:<token>` not in `_KNOWN`.
  - `scripts/validate_l2_vocab.py` (driven by `test_l2_vocab.py`) — `L2_NAMES` roster + relay-vocab block shape.
  - `scripts/validate_language_reference.py` (driven by `test_language_reference.py`) — L0/L1 doc tables.
  - `scripts/doc_reference_scan.py` (driven by `test_doc_reference_scan.py`) — stale-doc-ref gate.
  - `test_plugin.py` `EXPECTED_SKILLS` / `INTERNAL_SKILLS` rosters + per-skill frontmatter; `TestRenameCompleteness` dropped-skill scan; tree-wide literal guards.
  - `test_setup_command.py` (setup.md must retain `Bash`+`Skill`).
  - `test_marketplace.py`, `test_upstream_guard.py` (unaffected but in the suite).
- **Commit cadence**: one commit per task group below, conventional-commit message `feat(relay): …` / `test(relay): …`, on the feature branch. The final task commits the version bump + CHANGELOG + docs together (version is the cache key — must land in the same PR, per project CLAUDE.md).

### Two design facts the spec pins that the implementer must NOT relitigate
1. **Rename is BEST-EFFORT at runtime** (spec §4 DECISION): every shipped command attempts `SlashCommand /rename <slug>` and, on error/unavailability, **continues silently**. There is NO runtime abort for rename. The only STOP-and-report is the **build-time** design-validation gate in Task 1.
2. **`EnterWorktree` is called EXACTLY ONCE per run, never re-switched** (spec §9 risk-2 caveat): the Step 1+ Workflow runs in that single entered worktree. The skill body must say so explicitly.

---

## TASK GROUP 1 — Build-time hard gates (prove the 3 runtime unknowns) + `session-slug.sh`

> These hard gates (spec §7.2) MUST be proven on THIS build harness before any command is wired. They are not assumptions. If any cannot be made to work, STOP and report — the mechanism is redesigned before proceeding. This is the only STOP-and-report path in the whole plan.

### Task 1.1 — Prove the 3 runtime-unknown hard gates (no test file; a recorded proof)
**Verify FIRST (this is the gate, run on the live build harness):**
1. **`SlashCommand` → built-in `/rename`** (spec §7.2.1, §9 risk-1): actually invoke `SlashCommand` with `/rename relayBuildProbe` in THIS session and confirm the session is renamed (do not assume — observe the rename). Also determine whether the harness supports **scoped** `SlashCommand(/rename:*)` frontmatter or only plain `SlashCommand` (spec §4 allowed-tools note) — this decides the exact frontmatter token used in Task 4.
2. **`EnterWorktree({path})`** (spec §7.2.2, §9 risk-2): confirm the tool accepts a just-created `git worktree add` worktree under `.claude/worktrees/` of THIS repo. NOTE: the HARD RULE forbids creating a real git worktree in this implementation session. Satisfy this gate by **reading the EnterWorktree tool schema/docs already available in-harness** (the tool is listed; its description states the path must appear in `git worktree list` for the current repo) and recording that the §5.1-step-4 creation satisfies the stated precondition. Do NOT create a worktree to "test" it.
3. **`worktree.baseRef` independence** (spec §7.2.3, §9 risk-3): grep the relay test tree to confirm **no existing relay test pins a `baseRef`** — `cd plugins/relay && grep -rn "baseRef" tests/ scripts/` returns nothing. Record the clean result.

**Change:** none (proof only). **Record** the three outcomes inline in the Task 1 commit message and in the CHANGELOG entry (Task 6). If gate 1 fails (rename mechanism unusable), STOP and report — do not wire the 5 remaining commands.

**Verify:** the three observations above are captured; gate 1's rename was visually confirmed; gate 3 grep is empty.

### Task 1.2 — `scripts/session-slug.sh` + unit test (spec §4.2, §7 test 1)
**Test FIRST** — `tests/unit/skill-structure/test_session_slug.py` (new). Drive the script via `subprocess.run(["bash", str(SCRIPT), phrase, "--fallback", fb], capture_output=True, text=True)` exactly like `test_check_deps_agent.py::_run`. Assert `r.stdout.strip()` equals the expected slug. Cases (cover every §4.2 transform + the degenerate rule):
- multiword: `"add a dark mode toggle"`, `--fallback relayImplement` → `darkModeToggle` (stopwords `a` dropped, first ≤3 of remaining content words, camelCase).
- punctuation: `"fix: the auth-bug!"`, fb → `fixAuthBug` (punctuation → boundaries; `the` stopword dropped).
- stopwords-only collapse: `"the a of to"`, `--fallback refineRefine` → `refineRefine` (degenerate → fallback verbatim).
- empty: `""`, `--fallback relayDrive` → `relayDrive`.
- punctuation-only: `"!!! --- ???"`, `--fallback relaySetup` → `relaySetup`.
- all-digits / leading-digit strip: `"123 456 migrate"`, fb → `migrate` (leading-digit-only segments removed first, step 4); `"2fast 2furious cars"`, fb → `fastFuriousCars` (leading digits stripped per joined token before camelCase) — pin EXACT expectation to the §4.2 ordering (strip leading digits **before** camelCase and **before** length cap).
- length cap (~24 chars, truncate on word boundary): `"internationalization localization framework setup"`, fb → first ≤3 words camelCased then capped at ≈24 on a word boundary (assert `len(out) <= 24` AND it ends on a whole word, AND no leading digit).
- fallback-not-overriding-good-slug: a non-empty normalized slug is NEVER replaced by fallback (assert the multiword case ignores `--fallback`).

Run it: `python3 -m pytest tests/unit/skill-structure/test_session_slug.py -q` → RED (script absent).

**Change** — write `scripts/session-slug.sh`. Signature `session-slug.sh "<phrase>" --fallback <commandSlug>`. Header comment mirroring `parse-engine-agent.sh` (purpose + sourcing/exec note). Apply the **pinned, deterministic transform order** (spec §4.2, in this exact sequence):
1. lowercase the phrase.
2. strip punctuation → word boundaries; drop a stopword list (`a an the of to and or in on for with` — pin the exact list in a comment so the test is reproducible).
3. take the first ≤3 remaining words.
4. strip leading digits from each surviving token (a leading-digit-only segment is dropped first, so no token begins with a digit).
5. camelCase (first word lowercase, rest capitalized).
6. cap at ≈24 chars, truncate on a word boundary where possible.
7. **degenerate-input rule:** if no usable token survives steps 1–4, print the `--fallback` value verbatim. This is the ONLY path to fallback.
Print exactly ONE line (the slug) to stdout. Pure POSIX `tr`/`sed`/parameter-expansion or a small awk — stdlib only, no python.

**Verify:** `python3 -m pytest tests/unit/skill-structure/test_session_slug.py -q` GREEN; full suite still green.

**Commit:** `feat(relay): add session-slug.sh + build-time hard-gate proofs (v4.5.0 wt-iso #1)`

---

## TASK GROUP 2 — `scripts/worktree-preflight.sh` (`--classify` + `--create`) + unit tests

### Task 2.1 — `--classify` classification unit (spec §5.1, §7 test 2)
**Test FIRST** — `tests/unit/skill-structure/test_worktree_preflight.py` (new). Use `tmp_path` + `subprocess.run(["git", "-C", repo, ...])` to build throwaway repos (mirror the `_git` helper style in `doc_reference_scan.py`). Helper `_classify(cwd)` runs `bash worktree-preflight.sh --classify` with `cwd=cwd`, parses the printed `KEY=value` block into a dict. Cases asserting `RELAY_WT_STATE`:
- `main` — fresh repo, default branch `main`, primary checkout → `RELAY_WT_STATE=main`, `RELAY_WT_BRANCH=main`, `RELAY_WT_DEFAULT=main`, `RELAY_WT_REPO_ROOT` = toplevel, `RELAY_WT_WORKTREE_ROOT` empty.
- `stray` (non-default branch) — `git checkout -b feature/x` → `RELAY_WT_STATE=stray`, `RELAY_WT_BRANCH=feature/x`.
- `stray` (detached HEAD) — `git checkout <sha>` → `RELAY_WT_STATE=stray`, `RELAY_WT_BRANCH=DETACHED`.
- `worktree` — `git worktree add .claude/worktrees/wt-a -b wtbranch` then classify with `cwd` = that worktree path → `RELAY_WT_STATE=worktree`, `RELAY_WT_WORKTREE_ROOT` = that path. (Set default-branch ref in the temp repo so resolution works offline: create `refs/remotes/origin/HEAD` → `refs/remotes/origin/main`, or rely on the documented `main` fallback — assert against whatever the fallback chain yields and pin it.)
- `not-git` — a bare `tmp_path` dir with no repo → script returns **non-zero** (assert `r.returncode != 0`); command-abort semantics.
RED first (script absent).

**Change** — write `scripts/worktree-preflight.sh` `--classify` branch. Read git via plumbing only:
- `git rev-parse --is-inside-work-tree` fails → print nothing meaningful, `exit 1` (`not-git`).
- compute `--git-common-dir`, `--git-dir`, `--show-toplevel`.
- default branch: `git symbolic-ref refs/remotes/origin/HEAD` (strip `refs/remotes/origin/`) → fallback `origin/main` → `main`.
- `worktree` iff git-common-dir ≠ git-dir AND toplevel is under `.claude/worktrees/`.
- `main` iff on default branch in primary checkout.
- `stray` otherwise (non-default branch OR detached) in primary checkout.
- detached → `RELAY_WT_BRANCH=DETACHED`.
- print the 5-line `KEY=value` block (spec §5.1).

**Verify:** classification test GREEN.

### Task 2.2 — `--create <base-ref>` unit (spec §5.1, §7 test 3)
**Test FIRST** — extend `test_worktree_preflight.py`. In a temp repo with a committed `main`:
- call `bash worktree-preflight.sh --create HEAD` (stray-equivalent base) with `cwd`=repo; assert a worktree dir appears under `.claude/worktrees/`, `git worktree list` includes it, the new branch is `relay/<slug>`, and stdout prints `RELAY_WT_CREATED_PATH=<absolute path>`.
- assert **base ref honored**: create with an explicit base ref distinct from HEAD (e.g. tag/sha) and verify the worktree HEAD resolves to that base.
- assert **`git fetch` is invoked**: since temp repos lack a real `origin`, inject a fake `git` on `PATH` (a shim dir prepended to `PATH` whose `git` logs argv to a file then `exec`s real git) and assert the log contains a `fetch origin <default>` line; OR set up a local bare repo as `origin` and assert fetch succeeds. Pick the local-bare-origin approach (more faithful, no PATH shimming) and pin it.
- assert **slug collision suffixing**: call `--create` twice with the same slug input and assert the second path gets a `-N` suffix and both appear in `git worktree list`.
RED first.

**Change** — add the `--create <base-ref>` branch (spec §5.1 steps): (1) `git fetch origin <default>`; (2) resolve base = the passed `<base-ref>` (caller passes `origin/<default>` or `HEAD`); (3) generate slug-based name under `.claude/worktrees/`, suffix `-N` on collision (reuse the session slug — accept it as input or derive from a second positional; pin the calling contract in the header comment); (4) `git worktree add .claude/worktrees/<name> -b relay/<slug> <base-ref>`; (5) print `RELAY_WT_CREATED_PATH=<absolute path>`. Document WHY `git worktree add` (deterministic base) not `EnterWorktree({name})` (spec §5.1 closing note + §9 risk-3).

**Verify:** `--create` test GREEN; full suite green.

**Commit:** `feat(relay): add worktree-preflight.sh (--classify/--create) + units (v4.5.0 wt-iso #2)`

---

## TASK GROUP 3 — `skills/ensuring-worktree-isolation/SKILL.md`

### Task 3.1 — Skill-structure test (spec §7 test 5)
**Test FIRST** — `tests/unit/skill-structure/test_ensuring_worktree_isolation.py` (new), mirroring `test_driving_to_done.py` structure-presence style. Assertions:
- `SKILL.md` exists at `skills/ensuring-worktree-isolation/SKILL.md`.
- frontmatter `name: ensuring-worktree-isolation`, non-empty `description`, `user-invocable: false`.
- body > 200 chars.
- body has **NO** ```` ```relay-vocab ```` block (it is NOT an L2 pattern skill — same rule as routing/selecting policy skills).
- body documents all four states `worktree` / `main` / `stray` / `not-git` (case-insensitive substrings).
- body documents the load-bearing invariant: **`EnterWorktree` is called exactly once / never re-switch** (assert a substring like `exactly once` and `EnterWorktree`).
- body references `worktree-preflight.sh` `--classify` and `--create`, and the path-form `EnterWorktree({path:` for entry.
- body documents the `drive --resume` **verify-only** mode + `RELAY_DRIVE_WORKSPACE` (`worktree` / `in-place`) reconciliation (spec §5.3).
- body states it does NOT delegate to `superpowers:using-git-worktrees` (spec §6).
RED first.

### Task 3.2 — Roster registration edits (keep `test_plugin.py` green)
**Test:** these are covered by existing parametrized tests once the name is registered — no NEW test, but they are mandatory edits or the suite goes red:
- Add `"ensuring-worktree-isolation"` to `EXPECTED_SKILLS` in `tests/unit/skill-structure/test_plugin.py` (it then auto-joins `INTERNAL_SKILLS = EXPECTED_SKILLS - {"using-relay"}`, which asserts `user-invocable: false` — satisfied by the skill frontmatter).
- It must NOT be added to `L2_NAMES` (validate_l2_vocab) and must NOT carry a relay-vocab block (it is not an L1 shape).

**Change** — write `skills/ensuring-worktree-isolation/SKILL.md`. Frontmatter exactly:
```
---
name: ensuring-worktree-isolation
description: >-
  Use as the Step 0.5 preflight of relay's source-modifying L3 commands … (one
  crisp trigger-style description in the driving-to-done voice)
user-invocable: false
---
```
Body owns the **full state machine** (spec §5.2 table) — confirm/create/enter logic with the exact `AskUserQuestion` prompts per state, the on-accept actions, and:
- `worktree` → Yes proceed / No abort-with-guidance.
- `main` → Create (`--create origin/<default>` → `EnterWorktree({path: RELAY_WT_CREATED_PATH})` → proceed) / Proceed-on-main-in-place / Cancel.
- `stray` → Create from HEAD (`--create HEAD` → enter → proceed) / Proceed-here-in-place / Cancel.
- `not-git` → already aborted by the script's non-zero return.
- the **call-EnterWorktree-exactly-once / never-re-switch** invariant (spec §9 risk-2), and "the Step 1+ Workflow runs in the single entered worktree".
- the `drive --resume` verify-only branch + `RELAY_DRIVE_WORKSPACE` recording/asserting (spec §5.3): initial run records `worktree`(path) or `in-place`(branch) into `loop-state.md`; resume asserts cwd matches the recorded mode, no prompt/create; only a genuine mismatch errors+aborts.
- explicit non-delegation to `superpowers:using-git-worktrees` (spec §6).

**Verify:** `python3 -m pytest tests/unit/skill-structure/test_ensuring_worktree_isolation.py tests/unit/skill-structure/test_plugin.py -q` GREEN.

**Commit:** `feat(relay): add ensuring-worktree-isolation skill + roster registration (v4.5.0 wt-iso #3)`

---

## TASK GROUP 4 — Validator allowlist edits (do BEFORE wiring command bodies)

> The command-body edits in Group 5 introduce the token `relay:ensuring-worktree-isolation`; without these allowlist edits, `validate_l3_command.py` fails every modifying command with `unknown relay vocabulary token`. Land the allowlist FIRST so Group 5 lands green.

### Task 4.1 — `validate_l3_command.py` `_KNOWN` += token
**Test FIRST** — add to `tests/unit/skill-structure/test_l3_command.py` a case asserting `vl3.check_command("run relay:ensuring-worktree-isolation\n", require_branch=False)` returns `[]` (token is known). RED first (token unknown).
**Change** — in `scripts/validate_l3_command.py`, extend the `_KNOWN` set with `{"ensuring-worktree-isolation"}` (mirror the existing `driving-to-done` line + comment).
**Verify:** new case GREEN; existing `test_l3_command.py` 26 baseline still green.

### Task 4.2 — L2 vocab allowlist (spec §7.1)
The spec says add to `validate_l2_vocab` `L2_NAMES` **or** the validator the L3 `_KNOWN` consults. **Decision (pin):** `_KNOWN` already pulls `L2_NAMES`, but adding the skill to `L2_NAMES` would force a relay-vocab block (validated by `test_l2_vocab.py` + `test_l2_skills_present.py`), which this skill must NOT have. **Therefore add it via `_KNOWN` directly in Task 4.1 (done) — do NOT add it to `L2_NAMES`.** This satisfies §7.1's "whichever that validator consults" by the most consistent route and keeps `test_l2_skills_present.py` green. No L2_NAMES edit. Add a one-line code comment in `validate_l3_command.py` recording this rationale.
**Verify:** `python3 -m pytest tests/unit/skill-structure/test_l2_vocab.py tests/unit/skill-structure/test_l2_skills_present.py -q` GREEN (unchanged).

**Commit:** `feat(relay): allow ensuring-worktree-isolation token in L3 validator (v4.5.0 wt-iso #4)`

---

## TASK GROUP 5 — Command-body edits (all 6) + allowed-tools

> Order inside each command (spec §3): **Step 0.0 rename (NEW) → Step 0 dep/arg gate (existing where present) → Step 0.5 worktree gate (NEW, 4 modifying) → Step 1+ existing.** Rename runs first and is best-effort.

### Task 5.1 — Structure/validator test FIRST (spec §7 test 4)
**Test FIRST** — `tests/unit/skill-structure/test_worktree_session_steps.py` (new). For each of the 6 commands, parse frontmatter+body via `conftest.parse_frontmatter`:
- **All 6** bodies contain a Step 0.0 rename: assert presence of `session-slug.sh`, `/rename`, and `SlashCommand`; assert the body states rename is best-effort/non-fatal (substring like `best-effort` or `continue silently`).
- **All 6** `allowed-tools` contain `SlashCommand`.
- **All 6** `allowed-tools` contain `Bash` (the new requirement for `diagnose.md` and `execute.md`; spec §4 + §5.4).
- **The 4 modifying** (`implement`, `refine`, `execute`, `drive`) bodies invoke `relay:ensuring-worktree-isolation` and contain a `Step 0.5`; their `allowed-tools` contain `EnterWorktree` and `AskUserQuestion`. Assert `AskUserQuestion` as a **substring** (not an exact token-match): the harness accepts either the plain `AskUserQuestion` or the scoped `AskUserQuestion(*)` form — `diagnose.md` already carries the scoped form, so a substring check matches both and avoids a false RED.
- **`execute.md`** specifically: assert it now has a `Bash` fence (it had none) AND `Bash` in allowed-tools.
- **`drive.md`**: assert the `--resume` verify-only note (substring `verify-only` and `RELAY_DRIVE_WORKSPACE`).
- **`diagnose.md` / `setup.md`**: assert they do NOT invoke `relay:ensuring-worktree-isolation` (read-only / provisioning — no worktree gate) but DO have Step 0.0 rename + `SlashCommand` + `Bash`.
- Pin each command's per-command fallback slug appears in its Step 0.0 `session-slug.sh` call: `implement→relayImplement`, `refine→refineRefine`, `execute→relayExecute`, `drive→relayDrive`, `diagnose→relayDiagnose`, `setup→relaySetup` (spec §4.2).
RED first.

### Task 5.2 — Edit `implement.md`
- Add `## Step 0.0 — Name this session (best-effort)`: instruct Claude to pick 2-3 salient words from the task text, run `source "${CLAUDE_PLUGIN_ROOT}/scripts/session-slug.sh" "<phrase>" --fallback relayImplement` (Bash) and read the printed slug, then attempt `SlashCommand /rename <slug>` — on error/unavailability, continue silently (no abort).
- After the existing Step 0 dep gate, add `## Step 0.5 — Ensure worktree isolation`: source `worktree-preflight.sh --classify`, read the printed state, invoke `relay:ensuring-worktree-isolation` to drive confirm/create/enter; abort the command on the skill's abort paths.
- Frontmatter `allowed-tools`: from `Bash, Workflow, Skill` → add `SlashCommand`, `EnterWorktree`, `AskUserQuestion`. (Bash already present.) Use the scoped `SlashCommand(/rename:*)` form iff Task 1.1 confirmed harness scoping support, else plain `SlashCommand`.

### Task 5.3 — Edit `refine.md`
- Step 0.0 rename with **static fallback** `refineRefine` (spec §4.2 ordering: salient source is only produced inside Step 0, so rename-first uses the static fallback; richer slug is a non-goal here).
- Step 0.5 worktree gate after the existing Step 0 dep gate (same as 5.2).
- allowed-tools `Bash, Skill, Workflow` → add `SlashCommand`, `EnterWorktree`, `AskUserQuestion`.

### Task 5.4 — Edit `execute.md` (gains a brand-new preflight — spec §3 / §5.4)
`execute.md` has NO Step 0 today (classifier-only, 100% soft). Add from scratch:
- `## Step 0.0 — Name this session (best-effort)`: a NEW `Bash` fence sourcing `session-slug.sh "<phrase>" --fallback relayExecute`, read slug, best-effort `SlashCommand /rename`.
- `## Step 0.5 — Ensure worktree isolation`: a NEW `Bash` fence sourcing `worktree-preflight.sh --classify`, then invoke `relay:ensuring-worktree-isolation`.
- Keep existing `## Step 1 — Classify (advisory)` / `## Step 2 — Compose freely` intact and renumber-free (they are already Step 1/2; the new steps slot ahead).
- allowed-tools `Workflow, Skill` → `Bash, SlashCommand, EnterWorktree, AskUserQuestion, Workflow, Skill`.
- Watch `validate_l3_command.check_command(body, require_branch=False)` still passes (execute keeps `require_branch=False`; adding the worktree token is now allowed by Task 4).

### Task 5.5 — Edit `drive.md`
- Step 0.0 rename with **static fallback** `relayDrive` (oracle basename not yet parsed at Step 0.0; spec §4.2).
- Step 0.5 worktree gate after the existing Step 0 dep+arg gate. Add the **`--resume` verify-only** path: when `$RELAY_DRIVE_RESUME=1`, the gate runs verify-only — reads `RELAY_DRIVE_WORKSPACE` from `loop-state.md` and asserts cwd matches the recorded mode (`worktree` path or `in-place` branch), proceeding without prompt/create; genuine mismatch errors+aborts (spec §5.3). On the **initial** run, the gate records the resolved `RELAY_DRIVE_WORKSPACE` into `loop-state.md`. Keep the Step 1 long-lived-process launch AFTER the worktree gate (so the process starts in the right cwd).
- allowed-tools `Bash, Workflow, Skill` → add `SlashCommand`, `EnterWorktree`, `AskUserQuestion`.

### Task 5.6 — Edit `diagnose.md` (rename only — NO worktree gate)
- Step 0.0 rename, salient source = task text, `--fallback relayDiagnose`, best-effort `SlashCommand /rename`. Add a NEW `Bash` fence for `session-slug.sh`.
- allowed-tools `AskUserQuestion(*), Workflow, Skill` → add `Bash`, `SlashCommand`. (`AskUserQuestion` already present; do NOT add `EnterWorktree` — read-only, no gate.)

### Task 5.7 — Edit `setup.md` (rename only — NO worktree gate)
- Step 0.0 rename, constant salient → `--fallback relaySetup` (slug `relaySetup`; spec §4.2). Reuse the existing `Bash` fence area.
- allowed-tools `Bash, Skill` → **append** `SlashCommand` (do NOT drop `Bash`/`Skill` — `test_setup_command.py` asserts both remain; spec §7.1).

**Verify (whole group):** `python3 -m pytest tests/unit/skill-structure/test_worktree_session_steps.py tests/unit/skill-structure/test_l3_command.py tests/unit/skill-structure/test_setup_command.py -q` GREEN; then full suite `python3 -m pytest tests/unit -q` GREEN. Manually re-read each command body to confirm step ordering (0.0 → 0 → 0.5 → 1+) and best-effort rename wording.

**Commit:** `feat(relay): wire Step 0.0 rename (6) + Step 0.5 worktree gate (4) into commands (v4.5.0 wt-iso #5)`

---

## TASK GROUP 6 — Version bump, CHANGELOG, docs (single PR — version is the cache key)

### Task 6.1 — `plugin.json` → 4.5.0
**Test:** `test_plugin.py` reads `plugin_json["version"]`; bump must not break it. (If a test pins `4.4.0` literally, update it — grep `grep -rn "4.4.0" tests/`.) 
**Change** — `.claude-plugin/plugin.json` `"version": "4.4.0"` → `"4.5.0"`.
**Verify:** `python3 -m pytest tests/unit/skill-structure/test_plugin.py -q` GREEN.

### Task 6.2 — CHANGELOG entry
**Change** — prepend a `## 4.5.0 — 2026-06-24` section (mirror the 4.4.0 entry's structure): new `scripts/session-slug.sh`, `scripts/worktree-preflight.sh`, `skills/ensuring-worktree-isolation/SKILL.md`; Step 0.0 rename on all 6 commands; Step 0.5 worktree gate on the 4 modifying commands; allowed-tools deltas (`SlashCommand`×6, `EnterWorktree`+`AskUserQuestion`×4, `Bash` added to `diagnose`+`execute`); validator allowlist edit; the 3 build-time hard-gate proofs from Task 1.1. Note rename is best-effort/non-fatal.

### Task 6.3 — `skills/using-relay/SKILL.md` doc update (spec §8)
**Change** — in the command-descriptions/pipelines section, document Step 0.0 (every command renames the session to a camelCase slug, best-effort) and Step 0.5 (the 4 modifying commands run the `relay:ensuring-worktree-isolation` gate before generating their Workflow). Keep wording consistent with neighbors so `doc_reference_scan.py` finds no stale refs.
**Verify:** `python3 -m pytest tests/unit/skill-structure/test_doc_reference_scan.py tests/unit/skill-structure/test_language_reference.py -q` GREEN.

### Task 6.4 — Final full-suite gate
**Verify:** from repo root `cd plugins/relay && python3 -m pytest tests/unit -q` — ALL green (≥1119 + the new tests). Confirm no tree-wide literal-guard regressions in `test_plugin.py`.

**Commit:** `feat(relay): bump to 4.5.0 + CHANGELOG + using-relay docs (v4.5.0 wt-iso #6)`

---

## Verification matrix (must all hold at the end)

| Concern | Command |
|---|---|
| New unit tests pass | `pytest tests/unit/skill-structure/test_session_slug.py test_worktree_preflight.py test_ensuring_worktree_isolation.py test_worktree_session_steps.py` |
| L3 validator green | `pytest tests/unit/skill-structure/test_l3_command.py` |
| L2 vocab untouched/green | `pytest tests/unit/skill-structure/test_l2_vocab.py test_l2_skills_present.py` |
| Lang-ref + doc-scan green | `pytest tests/unit/skill-structure/test_language_reference.py test_doc_reference_scan.py` |
| setup invariant green | `pytest tests/unit/skill-structure/test_setup_command.py` |
| plugin roster + version green | `pytest tests/unit/skill-structure/test_plugin.py` |
| Whole suite green | `cd plugins/relay && python3 -m pytest tests/unit -q` |
| Branch discipline | `git branch --show-current` == `feature/relay-worktree-isolation-session-rename`; no `git worktree add` ran in the impl session; nothing pushed |

## Out of scope (spec non-goals — do NOT do)
Orchestration-logic changes; new flags/config knobs; Workflow-spine edits; auto-stash on "proceed in place"; richer task-derived slugs for `refine`/`drive` (static fallback only); modifying `diagnose`/`setup` beyond the session rename.
