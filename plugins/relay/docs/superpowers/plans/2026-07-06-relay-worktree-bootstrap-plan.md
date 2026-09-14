# Relay Per-Worktree Bootstrap Implementation Plan

**Goal:** Add opt-in per-repo bootstrap commands for relay-created worktrees so verification roles enter a worktree with dependencies installed and build artifacts present.

**Architecture:** Extend the existing `scripts/worktree-preflight.sh --create` seam, because it is the only path that creates relay worktrees today. The script reads `.claude/relay.json` from the primary checkout, runs a configured `bootstrap` command inside the new worktree before printing `RELAY_WT_CREATED_PATH`, and reports `RELAY_WT_BOOTSTRAP=ran|skipped` on stdout while routing command output to stderr. The existing Step 0.5 gate keeps its current failure contract: if `--create` returns non-zero or prints no path, it aborts before `EnterWorktree`.

**Tech Stack:** Bash, `jq`, git worktrees, Python `pytest`, relay Markdown skills/docs, JSON plugin manifest.

---

## Overview

This plan keeps the runtime change tightly scoped to `_wt_create()` in `plugins/relay/scripts/worktree-preflight.sh`. There is no package-manager detection, no cache layer, and no per-invocation flag; the repo author owns the exact shell command in `.claude/relay.json`.

The tasks are ordered so each commit is independently reviewable and leaves the suite green. The first three tasks build the script behavior with focused tests, the next two update the user-facing relay guidance, and the final task lands the release metadata.

## Task 1: Emit Bootstrap Status for the No-Config Path

**Goal:** Preserve current worktree creation behavior while adding `RELAY_WT_BOOTSTRAP=skipped` observability when no repo config exists.

**Files touched:**
- Modify: `plugins/relay/scripts/worktree-preflight.sh`
- Test: `plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py`

**Steps:**
- [ ] Step 1: Write the failing test by adding this test method to `class TestCreate` in `plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py`.

```python
    def test_create_without_config_prints_bootstrap_skipped(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert "RELAY_WT_CREATED_PATH" in d, r.stdout
        assert d["RELAY_WT_BOOTSTRAP"] == "skipped"
        assert os.path.isdir(d["RELAY_WT_CREATED_PATH"])
```

- [ ] Step 2: Run the test and observe FAIL.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_without_config_prints_bootstrap_skipped -q
```

Expected: pytest exits non-zero with `KeyError: 'RELAY_WT_BOOTSTRAP'`.

- [ ] Step 3: Write the minimal implementation by updating the final print block in `_wt_create()` in `plugins/relay/scripts/worktree-preflight.sh`.

```bash
  # 5. print the absolute created path and bootstrap status.
  local abs bootstrap_status="skipped"
  abs="$(cd "$candidate" && pwd)"
  printf 'RELAY_WT_CREATED_PATH=%s\n' "$abs"
  printf 'RELAY_WT_BOOTSTRAP=%s\n' "$bootstrap_status"
  return 0
```

- [ ] Step 4: Run the test and observe PASS.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_without_config_prints_bootstrap_skipped -q
```

Expected: pytest exits 0 with `1 passed`.

- [ ] Step 5: Commit.

```bash
git add plugins/relay/scripts/worktree-preflight.sh plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py
git commit -m "feat(relay): emit worktree bootstrap status"
```

**Verification:** Run `cd plugins/relay && python3 -m pytest tests/unit/skill-structure/test_worktree_preflight.py::TestCreate -q`. Expected: pytest exits 0 and every `TestCreate` test passes.

## Task 2: Run Successful Bootstrap Commands in the New Worktree

**Goal:** Read `.claude/relay.json` from the primary checkout and run a non-empty `bootstrap` command inside the newly-created worktree, with command output routed to stderr.

**Files touched:**
- Modify: `plugins/relay/scripts/worktree-preflight.sh`
- Test: `plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py`

**Steps:**
- [ ] Step 1: Write the failing tests by adding these test methods to `class TestCreate` in `plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py`.

```python
    def test_create_runs_bootstrap_in_new_worktree_not_primary_checkout(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": "touch BOOTSTRAP_RAN"}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        created = d["RELAY_WT_CREATED_PATH"]

        assert d["RELAY_WT_BOOTSTRAP"] == "ran"
        assert os.path.exists(os.path.join(created, "BOOTSTRAP_RAN"))
        assert not (clone / "BOOTSTRAP_RAN").exists()

    def test_create_empty_bootstrap_key_skips(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": ""}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert "RELAY_WT_CREATED_PATH" in d, r.stdout
        assert d["RELAY_WT_BOOTSTRAP"] == "skipped"

    def test_create_bootstrap_stdout_is_routed_to_stderr(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": "echo noise"}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert set(d) == {"RELAY_WT_CREATED_PATH", "RELAY_WT_BOOTSTRAP"}
        assert d["RELAY_WT_BOOTSTRAP"] == "ran"
        assert "noise" not in r.stdout
        assert "noise" in r.stderr
```

- [ ] Step 2: Run the tests and observe FAIL.

```bash
cd plugins/relay
python3 -m pytest \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_runs_bootstrap_in_new_worktree_not_primary_checkout \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_empty_bootstrap_key_skips \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_bootstrap_stdout_is_routed_to_stderr \
  -q
```

Expected: pytest exits non-zero; the first and third tests fail because `RELAY_WT_BOOTSTRAP` is still `skipped` and no bootstrap command runs.

- [ ] Step 3: Write the minimal implementation by adding the helper below after `_wt_default_branch()` in `plugins/relay/scripts/worktree-preflight.sh`.

```bash
_wt_bootstrap_command() {
  local toplevel="$1" config
  config="$toplevel/.claude/relay.json"
  if [ ! -f "$config" ]; then
    printf '%s' ""
    return 0
  fi
  jq -r '.bootstrap // ""' "$config" 2>/dev/null
}
```

Then add the command read immediately after `toplevel` is resolved in `_wt_create()`.

```bash
  local default toplevel bootstrap_cmd
  default="$(_wt_default_branch)"
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null)"
  bootstrap_cmd="$(_wt_bootstrap_command "$toplevel")"
```

Finally, replace the Task 1 print block with this block after `git worktree add` succeeds.

```bash
  # 5. run the per-repo bootstrap command inside the new worktree when configured.
  local bootstrap_status="skipped"
  if [ -n "$bootstrap_cmd" ]; then
    bootstrap_status="ran"
    ( cd "$candidate" && bash -c "$bootstrap_cmd" ) >&2
  fi

  # 6. print the absolute created path and bootstrap status.
  local abs
  abs="$(cd "$candidate" && pwd)"
  printf 'RELAY_WT_CREATED_PATH=%s\n' "$abs"
  printf 'RELAY_WT_BOOTSTRAP=%s\n' "$bootstrap_status"
  return 0
```

Update the `--create` header comment to describe the new steps.

```bash
#   5. read .claude/relay.json from the primary checkout; when `bootstrap` is
#      non-empty, run it in the new worktree and route all output to stderr.
#   6. print RELAY_WT_CREATED_PATH=<absolute path> and RELAY_WT_BOOTSTRAP=<ran|skipped>.
```

- [ ] Step 4: Run the tests and observe PASS.

```bash
cd plugins/relay
python3 -m pytest \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_runs_bootstrap_in_new_worktree_not_primary_checkout \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_empty_bootstrap_key_skips \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_bootstrap_stdout_is_routed_to_stderr \
  -q
```

Expected: pytest exits 0 with `3 passed`.

- [ ] Step 5: Commit.

```bash
git add plugins/relay/scripts/worktree-preflight.sh plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py
git commit -m "feat(relay): run configured worktree bootstrap command"
```

**Verification:** Run `cd plugins/relay && python3 -m pytest tests/unit/skill-structure/test_worktree_preflight.py::TestCreate -q`. Expected: pytest exits 0 and `TestCreate` includes passing coverage for `RELAY_WT_BOOTSTRAP=ran`, `RELAY_WT_BOOTSTRAP=skipped`, and no bootstrap noise in stdout.

## Task 3: Hard-Fail Invalid Config and Failing Bootstrap Commands

**Goal:** Reuse the Step 0.5 abort contract by returning non-zero and printing no `RELAY_WT_CREATED_PATH` when config JSON is invalid or the bootstrap command fails.

**Files touched:**
- Modify: `plugins/relay/scripts/worktree-preflight.sh`
- Test: `plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py`

**Steps:**
- [ ] Step 1: Write the failing tests by adding these methods to `class TestCreate` in `plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py`.

```python
    def test_create_failing_bootstrap_hard_fails_without_created_path(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": "exit 3"}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        d = _parse(r.stdout)

        assert r.returncode != 0
        assert "RELAY_WT_CREATED_PATH" not in d
        assert "[relay] error: bootstrap failed (exit 3)" in r.stderr

    def test_create_invalid_json_hard_fails_before_worktree_creation(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        before = _git(clone, "worktree", "list", "--porcelain").stdout
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text("{not json\n")

        r = _run(["--create", "HEAD"], cwd=clone)
        after = _git(clone, "worktree", "list", "--porcelain").stdout
        d = _parse(r.stdout)

        assert r.returncode != 0
        assert "RELAY_WT_CREATED_PATH" not in d
        assert before == after
        assert "[relay] error: .claude/relay.json is not valid JSON" in r.stderr
```

- [ ] Step 2: Run the tests and observe FAIL.

```bash
cd plugins/relay
python3 -m pytest \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_failing_bootstrap_hard_fails_without_created_path \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_invalid_json_hard_fails_before_worktree_creation \
  -q
```

Expected: pytest exits non-zero; the failing-bootstrap test sees return code 0 with `RELAY_WT_CREATED_PATH`, and the invalid-JSON test sees a registered worktree.

- [ ] Step 3: Write the minimal implementation by replacing `_wt_bootstrap_command()` with this version.

```bash
_wt_bootstrap_command() {
  local toplevel="$1" config cmd
  config="$toplevel/.claude/relay.json"
  if [ ! -f "$config" ]; then
    printf '%s' ""
    return 0
  fi
  if ! cmd="$(jq -r '.bootstrap // ""' "$config" 2>/dev/null)"; then
    echo "[relay] error: .claude/relay.json is not valid JSON" >&2
    return 1
  fi
  printf '%s' "$cmd"
}
```

Replace the bootstrap command read in `_wt_create()` with this checked form.

```bash
  local default toplevel bootstrap_cmd
  default="$(_wt_default_branch)"
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null)"
  if ! bootstrap_cmd="$(_wt_bootstrap_command "$toplevel")"; then
    return 1
  fi
```

Replace the Task 2 bootstrap run block with this checked run block.

```bash
  # 5. run the per-repo bootstrap command inside the new worktree when configured.
  local bootstrap_status="skipped"
  if [ -n "$bootstrap_cmd" ]; then
    bootstrap_status="ran"
    ( cd "$candidate" && bash -c "$bootstrap_cmd" ) >&2
    local bootstrap_rc=$?
    if [ "$bootstrap_rc" -ne 0 ]; then
      echo "[relay] error: bootstrap failed (exit $bootstrap_rc)" >&2
      return 1
    fi
  fi
```

Task 2's header-comment update only renumbered the tail of the `--create` step list (steps
5/6); it never documented that config is now read and validated before step 1 (`git fetch`),
which is where the invalid-JSON fail-fast actually happens as of this task. Update the
header comment again to insert a `0a.` bullet before the existing step 1 line. [inferred]

```bash
#   0a. read .claude/relay.json from the primary checkout; when present but invalid JSON,
#       fail fast here (no worktree is created). Absence or an empty/absent `bootstrap`
#       key is a clean no-op and execution continues to step 1 exactly as today.
#   1. git fetch origin <default>   (existing, soft-degrades offline)
```

- [ ] Step 4: Run the tests and observe PASS.

```bash
cd plugins/relay
python3 -m pytest \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_failing_bootstrap_hard_fails_without_created_path \
  tests/unit/skill-structure/test_worktree_preflight.py::TestCreate::test_create_invalid_json_hard_fails_before_worktree_creation \
  -q
```

Expected: pytest exits 0 with `2 passed`.

- [ ] Step 5: Commit.

```bash
git add plugins/relay/scripts/worktree-preflight.sh plugins/relay/tests/unit/skill-structure/test_worktree_preflight.py
git commit -m "feat(relay): hard fail broken worktree bootstrap"
```

**Verification:** Run `cd plugins/relay && python3 -m pytest tests/unit/skill-structure/test_worktree_preflight.py -q`. Expected: pytest exits 0; invalid JSON fails before `git worktree add`, failing bootstrap returns non-zero, and no failure path prints `RELAY_WT_CREATED_PATH`.

## Task 4: Document Bootstrap Behavior in the Worktree Gate Skill

**Goal:** Update `relay:ensuring-worktree-isolation` so the Step 0.5 gate documents the new `--create` bootstrap side effect, `RELAY_WT_BOOTSTRAP`, and timeout guidance.

**Files touched:**
- Modify: `plugins/relay/skills/ensuring-worktree-isolation/SKILL.md`
- Test: `plugins/relay/tests/unit/skill-structure/test_ensuring_worktree_isolation.py`

**Steps:**
- [ ] Step 1: Write the failing tests by adding this class to `plugins/relay/tests/unit/skill-structure/test_ensuring_worktree_isolation.py`.

```python
class TestBootstrapContract:
    def test_bootstrap_status_and_failure_contract_documented(self):
        _, body = _parse()
        lower = body.lower()
        assert "relay_wt_bootstrap" in lower
        assert "bootstrap" in lower
        assert "no `RELAY_WT_CREATED_PATH`" in body or "no RELAY_WT_CREATED_PATH" in body
        assert "stderr" in lower
        assert "EnterWorktree" in body

    def test_bootstrap_timeout_guidance_documented(self):
        _, body = _parse()
        lower = body.lower()
        assert "longest timeout" in lower
        assert "bootstrap" in lower
```

- [ ] Step 2: Run the tests and observe FAIL.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_ensuring_worktree_isolation.py::TestBootstrapContract -q
```

Expected: pytest exits non-zero because the skill does not yet mention `RELAY_WT_BOOTSTRAP` or bootstrap timeout guidance.

- [ ] Step 3: Write the minimal implementation. There is no existing standalone fenced
"printed block" for `--create`'s output in this file today (unlike the `--classify` block
above) — `RELAY_WT_CREATED_PATH` currently appears only as inline backtick mentions inside
each Create branch's prose. The two key lines below are not a separate insertion; they land
inline, once per Create branch, via the prose rewrite immediately after. [inferred]

```markdown
RELAY_WT_CREATED_PATH=<absolute path>
RELAY_WT_BOOTSTRAP=<ran|skipped>
```

In both Create branches, replace the single-line `--create` description with this wording.

```markdown
- this runs `git fetch origin <default>`, creates `.claude/worktrees/<name>` on a fresh
`relay/<slug>` branch, reads any primary-checkout `.claude/relay.json` `bootstrap`
command, runs that command in the new worktree with output on stderr, and prints
`RELAY_WT_CREATED_PATH=<absolute path>` plus `RELAY_WT_BOOTSTRAP=<ran|skipped>`.
```

Then update each failure-contract bullet for Create branches with this sentence.

```markdown
Bootstrap failures are covered by the same contract: a non-zero `--create` or no
`RELAY_WT_CREATED_PATH` means abort, surface stderr, and never call `EnterWorktree`.
```

Add this operational note near the load-bearing invariant section.

```markdown
Because a cold bootstrap can take minutes, invoke `--create` with the longest timeout the
calling tool allows. Relay imposes no internal timeout; repo authors should keep the
cold-cache bootstrap runtime comfortably below the external command-execution ceiling.
```

- [ ] Step 4: Run the tests and observe PASS.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_ensuring_worktree_isolation.py::TestBootstrapContract -q
```

Expected: pytest exits 0 with `2 passed`.

- [ ] Step 5: Commit.

```bash
git add plugins/relay/skills/ensuring-worktree-isolation/SKILL.md plugins/relay/tests/unit/skill-structure/test_ensuring_worktree_isolation.py
git commit -m "docs(relay): document worktree bootstrap gate contract"
```

**Verification:** Run `cd plugins/relay && python3 -m pytest tests/unit/skill-structure/test_ensuring_worktree_isolation.py -q`. Expected: pytest exits 0 and the skill structure tests still prove the four states, exactly-once `EnterWorktree`, drive resume reconciliation, and the new bootstrap contract.

## Task 5: Add Repo Config Reference Documentation

**Goal:** Document `.claude/relay.json` for repo authors and link it from `relay:using-relay`.

**Files touched:**
- Create: `plugins/relay/docs/superpowers/references/relay-repo-config.md`
- Create: `plugins/relay/tests/unit/skill-structure/test_relay_repo_config_docs.py`
- Modify: `plugins/relay/skills/using-relay/SKILL.md`

**Steps:**
- [ ] Step 1: Write the failing test by creating `plugins/relay/tests/unit/skill-structure/test_relay_repo_config_docs.py`.

```python
from conftest import PLUGIN_ROOT


DOC = PLUGIN_ROOT / "docs" / "superpowers" / "references" / "relay-repo-config.md"
USING_RELAY = PLUGIN_ROOT / "skills" / "using-relay" / "SKILL.md"


def test_relay_repo_config_reference_exists_and_documents_bootstrap():
    assert DOC.is_file(), "relay repo config reference doc missing"
    body = DOC.read_text()
    assert ".claude/relay.json" in body
    assert '"bootstrap"' in body
    assert "pnpm install --frozen-lockfile && pnpm build:ts" in body
    assert "primary checkout" in body
    assert "new worktree" in body
    assert "stderr" in body
    assert "RELAY_WT_BOOTSTRAP=ran" in body
    assert "RELAY_WT_BOOTSTRAP=skipped" in body
    assert "No package-manager auto-detection" in body


def test_using_relay_points_to_repo_config_reference():
    body = USING_RELAY.read_text()
    assert "relay-repo-config.md" in body
    assert ".claude/relay.json" in body
```

- [ ] Step 2: Run the test and observe FAIL.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_relay_repo_config_docs.py -q
```

Expected: pytest exits non-zero with an assertion that `relay-repo-config.md` is missing.

- [ ] Step 3: Write the minimal implementation by creating `plugins/relay/docs/superpowers/references/relay-repo-config.md`.

```markdown
# Relay Repo Config

Relay reads optional per-repo settings from `.claude/relay.json` in the primary checkout.
The file is intentionally repo-local and author-controlled; relay does not infer package
manager commands from lockfiles.

## `bootstrap`

`bootstrap` is a string shell command that relay runs after `git worktree add` creates a
fresh `.claude/worktrees/<name>` worktree and before `RELAY_WT_CREATED_PATH` is printed.
The command runs with cwd set to the new worktree, not the primary checkout.

```json
{
  "bootstrap": "pnpm install --frozen-lockfile && pnpm build:ts"
}
```

No package-manager auto-detection is performed. Use the exact command your project needs.
For pnpm workspaces, `pnpm install --frozen-lockfile && pnpm build:ts` is a typical strict
bootstrap command when the new worktree needs local workspace package links and compiled
TypeScript output before verification.

Relay reads `.claude/relay.json` from the primary checkout because many repos gitignore
`.claude/`. The config does not need to be committed into the branch checked out inside the
new worktree.

Bootstrap stdout and stderr are routed to stderr so stdout remains a clean parseable
`RELAY_WT_*` block. On success relay prints `RELAY_WT_BOOTSTRAP=ran`. If the file is
absent, the key is absent, or the value is an empty string, relay prints
`RELAY_WT_BOOTSTRAP=skipped` and creates the worktree as before.

Invalid JSON fails before worktree creation. A non-zero bootstrap command fails after the
worktree is created but before `RELAY_WT_CREATED_PATH` is printed, allowing the Step 0.5
gate to abort and avoid `EnterWorktree`.
```

Then add this paragraph to the Step 0.5 worktree-isolation section of `plugins/relay/skills/using-relay/SKILL.md`.

```markdown
When a repo needs newly-created worktrees to install dependencies or build generated
artifacts before verification, configure `.claude/relay.json` with a `bootstrap` command.
See `docs/superpowers/references/relay-repo-config.md` for the supported config shape.
```

- [ ] Step 4: Run the test and observe PASS.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_relay_repo_config_docs.py -q
```

Expected: pytest exits 0 with `2 passed`.

- [ ] Step 5: Commit.

```bash
git add plugins/relay/docs/superpowers/references/relay-repo-config.md plugins/relay/skills/using-relay/SKILL.md plugins/relay/tests/unit/skill-structure/test_relay_repo_config_docs.py
git commit -m "docs(relay): add repo bootstrap config reference"
```

**Verification:** Run `cd plugins/relay && python3 -m pytest tests/unit/skill-structure/test_relay_repo_config_docs.py tests/unit/skill-structure/test_doc_reference_scan.py -q`. Expected: pytest exits 0, the reference doc exists, the `using-relay` pointer resolves, and doc-reference scanning reports no broken introduced references.

## Task 6: Bump Relay to 4.7.0 and Add the Changelog Entry

**Goal:** Release the per-worktree bootstrap feature as relay `4.7.0`.

**Files touched:**
- Modify: `plugins/relay/.claude-plugin/plugin.json`
- Modify: `plugins/relay/CHANGELOG.md`
- Test: `plugins/relay/tests/unit/skill-structure/test_plugin.py`

**Steps:**
- [ ] Step 1: Write the failing release-metadata tests by appending this class to `plugins/relay/tests/unit/skill-structure/test_plugin.py`.

```python
class TestVersion470:
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_plugin_json_version_is_470(self, plugin_json):
        assert plugin_json["version"] == "4.7.0"

    def test_changelog_has_470_entry(self):
        body = self.CHANGELOG.read_text()
        assert "## 4.7.0" in body
        assert "Per-worktree bootstrap" in body
        assert ".claude/relay.json" in body
        assert "RELAY_WT_BOOTSTRAP" in body
        assert "bootstrap failed" in body
```

- [ ] Step 2: Run the tests and observe FAIL.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_plugin.py::TestVersion470 -q
```

Expected: pytest exits non-zero because `plugin.json` still reports `4.6.0` and `CHANGELOG.md` has no `4.7.0` entry.

- [ ] Step 3: Write the minimal implementation by changing the version in `plugins/relay/.claude-plugin/plugin.json`.

```json
  "version": "4.7.0",
```

Add this entry above `## 4.6.0 — 2026-07-01` in `plugins/relay/CHANGELOG.md`.

```markdown
## 4.7.0 — 2026-07-02

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
```

- [ ] Step 4: Run the tests and observe PASS.

```bash
cd plugins/relay
python3 -m pytest tests/unit/skill-structure/test_plugin.py::TestVersion470 -q
```

Expected: pytest exits 0 with `2 passed`.

- [ ] Step 5: Commit.

```bash
git add plugins/relay/.claude-plugin/plugin.json plugins/relay/CHANGELOG.md plugins/relay/tests/unit/skill-structure/test_plugin.py
git commit -m "chore(relay): release worktree bootstrap v4.7.0"
```

**Verification:** Run `cd plugins/relay && python3 -m pytest tests/unit -q`. Expected: pytest exits 0 with no failing tests. Then run `grep -nE '^## Task [0-9]+:' docs/superpowers/plans/2026-07-06-relay-worktree-bootstrap-plan.md`; expected task headings are `Task 1` through `Task 6` with no numbering gaps.

## Refinement Status

**Refinement: CONVERGED round 2**

Round 2: convergence check found no critical/important findings remaining. One minor
observation remains unaddressed by design choice: neither this plan nor `check-deps.sh`
verifies `jq` is on `PATH` before `_wt_bootstrap_command()` runs; a missing `jq` binary
would be misreported as "not valid JSON" rather than "command not found." Left as a
documented limitation rather than new pre-check scope, matching the spec's own choice not
to add package-manager/tooling auto-detection.

Round 1 changes: closed two important gaps found by plan-simulation. (1) Task 3's
`_wt_bootstrap_command()` moves invalid-JSON fail-fast validation to before `git fetch`
(step 1), but Task 2's header-comment update (the only header-comment edit in the plan)
never documented this — a reader of the header alone would wrongly conclude config
parsing happens at step 5/6, after `git worktree add`. Added a `0a.` header-comment bullet
to Task 3 documenting the early fail-fast read, matching spec §3's step ordering.
[inferred] (2) Task 4 Step 3's instruction to "update the printed block ... to include
`RELAY_WT_BOOTSTRAP`" implied an existing standalone fenced `--create` output block to
edit; no such block exists in `ensuring-worktree-isolation/SKILL.md` today (only inline
mentions inside each Create branch's prose, already handled by the next sub-instruction).
Clarified that the two-line snippet lands inline via that next rewrite, not as a separate
insertion. [inferred]
