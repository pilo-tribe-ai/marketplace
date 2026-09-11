import os
import re
import shutil
import stat
import subprocess
import textwrap
from types import SimpleNamespace

import pytest

from conftest import PLUGIN_ROOT, deps_ok_env

IMPLEMENT = PLUGIN_ROOT / "commands" / "implement.md"
HELPER = PLUGIN_ROOT / "scripts" / "run-claude-command.sh"
SKILL = PLUGIN_ROOT / "skills" / "verifying-until-clean" / "SKILL.md"
SPINE_SKILL = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"
L3_PREFLIGHT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"
WT_PREFLIGHT = PLUGIN_ROOT / "scripts" / "worktree-preflight.sh"


def _body():
    """4.38.0 moved implement's Steps 3-3.5-4 into relay:running-implement-spine.
    That prose is part of implement's contract wherever it lives."""
    return IMPLEMENT.read_text() + "\n" + _spine_body()


def _skill_body():
    return SKILL.read_text()


def _spine_body():
    return SPINE_SKILL.read_text()


class TestVerifyLoopEscalates:
    """The verify-until-clean loop has no availability gate.

    acpx preflight belongs to /relay:setup; the loop runs strictly after verify, so an
    unavailable acpx costs no work and is classified from the helper's exit code. Where
    the two-node one-shot design used to report a machine with no acpx as successful
    (`skipped (acpx unavailable)`), the loop escalates instead: the run ends unverified,
    and the report names the reason.
    """

    def test_no_polish_gate_variable_anywhere(self):
        body = _body()
        gate_tokens = [
            line for line in body.splitlines()
            if "RELAY_POLISH" in line and "RELAY_POLISH_TIMEOUT" not in line
        ]
        assert not gate_tokens, f"loop availability gate must be gone: {gate_tokens}"

    def test_no_probe_step_and_no_acpx_version_floor(self):
        body = _body()
        for token in (
            "## Step 0.1",
            "acpx --version",
            "acpx claude --help",
            "skipped (gate)",
        ):
            assert token not in body, f"stale polish-probe token still present: {token!r}"

    def test_polish_status_is_classified_from_exit_code(self):
        """Inverted from the pre-loop design: a helper exit of 69 now escalates the
        run to `unverified`, not a quiet `skipped`."""
        body = _body()
        for token in (
            "unverified (acpx unavailable)",
            "unverified (loop blocked)",
            "findings",
            "no availability gate",
        ):
            assert token in body, f"missing loop escalation token: {token!r}"
        assert "skipped (acpx unavailable)" not in body


@pytest.fixture
def fake_acpx(tmp_path):
    """A stub `acpx` on PATH that logs every invocation and lets each test pick the
    exit code of the *turn* call.

    Any `sessions` subcommand succeeds. That is deliberately looser than checking for
    `ensure` specifically: the helper discards the rc of `sessions close` (`|| true`),
    so the distinction changes no assertion here, and one stub shape across every test
    keeps a difference in the guard from reading as meaningful when it is not.
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    log = tmp_path / "acpx.args"
    binary = fakebin / "acpx"

    def install(turn_rc=0, turn_stdout=None):
        emit = f"printf '%s\\n' {turn_stdout!r}\n" if turn_stdout else ""
        binary.write_text(
            textwrap.dedent(f"""\
                #!/usr/bin/env bash
                printf '%s\\n' "$*" >> {str(log)!r}
                if [ "${{4:-}}" = "sessions" ]; then
                  exit 0
                fi
                """)
            + emit
            + f"exit {turn_rc}\n"
        )
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env = dict(os.environ)
        env["PATH"] = f"{fakebin}:{env['PATH']}"
        return env

    return SimpleNamespace(worktree=worktree, log=log, install=install)


class TestRunClaudeCommandHelper:
    def test_helper_runs_bare_command_prompt_with_cwd_scope_and_rc_token(self, fake_acpx):
        assert HELPER.is_file(), "scripts/run-claude-command.sh missing"

        env = fake_acpx.install(turn_rc=7, turn_stdout="child output")
        env["RELAY_POLISH_TIMEOUT"] = "42"
        worktree = fake_acpx.worktree

        result = subprocess.run(
            [
                "bash",
                str(HELPER),
                str(worktree),
                "relay-polish-run123-simplify",
                "/simplify",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 7
        assert "child output" in result.stdout
        assert "POLISH_CMD_RC=7" in result.stdout
        calls = fake_acpx.log.read_text().splitlines()
        assert calls[0] == f"--cwd {worktree} claude sessions ensure --name relay-polish-run123-simplify"
        assert "--format quiet --approve-all" in calls[1]
        assert f"--cwd {worktree}" in calls[1]
        assert "--timeout 42" in calls[1]
        assert calls[1].endswith(" claude -s relay-polish-run123-simplify /simplify")

    def test_helper_allows_timeout_argument_to_override_env_default(self, fake_acpx):
        assert HELPER.is_file(), "scripts/run-claude-command.sh missing"

        env = fake_acpx.install(turn_rc=0)
        env["RELAY_POLISH_TIMEOUT"] = "42"

        result = subprocess.run(
            [
                "bash",
                str(HELPER),
                str(fake_acpx.worktree),
                "relay-polish-run123-review",
                "/code-review xhigh --fix",
                "99",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "POLISH_CMD_RC=0" in result.stdout
        turn_call = fake_acpx.log.read_text().splitlines()[1]
        assert "--timeout 99" in turn_call
        assert turn_call.endswith(" claude -s relay-polish-run123-review /code-review xhigh --fix")

    def test_missing_acpx_reports_69_not_127(self, tmp_path):
        """acpx exits 127 itself when it cannot spawn the adapter.

        Passing 127 through for "acpx not found" would make the two byte-identical, so
        the helper uses 69 (EX_UNAVAILABLE) — consistent with the 64/66 sysexits it
        already returns. The polish leaf classifies 69 as skipped, 127 as failed.
        """
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        emptybin = tmp_path / "bin"
        emptybin.mkdir()

        # Resolve bash before emptying PATH: everything the script touches before the
        # acpx check is a shell builtin, so an acpx-free PATH is enough.
        bash = shutil.which("bash")
        assert bash, "bash not on PATH"

        env = dict(os.environ)
        env["PATH"] = str(emptybin)

        result = subprocess.run(
            [bash, str(HELPER), str(worktree), "relay-polish-simplify", "/simplify"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 69
        assert "POLISH_CMD_RC=69" in result.stdout
        assert "POLISH_CMD_RC=127" not in result.stdout

    def test_helper_closes_the_session_it_opened(self, fake_acpx):
        """The helper owns the full lifecycle: it called `ensure`, so it closes.

        Without this every polish run leaks two permanently open sessions, and a
        same-cwd re-run resumes the prior conversation instead of starting clean.
        The close must never change the reported rc.
        """
        env = fake_acpx.install(turn_rc=3)
        worktree = fake_acpx.worktree

        result = subprocess.run(
            ["bash", str(HELPER), str(worktree), "relay-polish-review", "/code-review xhigh --fix"],
            capture_output=True,
            text=True,
            env=env,
        )

        calls = fake_acpx.log.read_text().splitlines()
        # `acpx <engine> sessions close [name]` takes the name positionally, unlike
        # `sessions ensure --name <name>`.
        assert calls[-1] == (
            f"--cwd {worktree} claude sessions close relay-polish-review"
        ), calls
        # A failing turn must still be reported as failing, and must still be closed.
        assert result.returncode == 3
        assert "POLISH_CMD_RC=3" in result.stdout


class TestVerifyLoopSpineExtension:
    def test_every_kind_ends_at_verify_not_at_the_loop(self):
        """The loop is opt-in, so no branch row may carry it.

        A row that still ended `verify → verify-loop` would make the tail
        unconditional again, and a bare run would no longer equal the prefix of a
        `--verify` run.
        """
        body = _body()
        for kind in ("feature", "bugfix", "script", "config-artifact", "docs"):
            line = next(
                (line for line in body.splitlines() if line.startswith(f"- `{kind}`")),
                "",
            )
            assert line, f"missing branch-table line for {kind}"
            assert line.rstrip().endswith("verify"), line
            assert "verify-loop" not in line, line

    def test_the_loop_is_appended_only_when_the_flag_was_passed(self):
        body = _body()
        assert "Every branch ends at `verify`." in body
        assert "When Step 0 printed `enabled=1`, and only then" in body
        assert "it never adds or removes the `verify-loop` phase" in body

    def test_the_flag_is_the_only_gate_and_acpx_is_never_probed(self):
        """A missing acpx must escalate, never silently drop the loop. The opt-in
        flag replaced the unconditional tail; it must not smuggle back the
        availability probe the loop design deliberately removed."""
        body = _body()
        assert "no availability gate" in body
        assert "never probes acpx" in body


class TestVerifyLoopIsDelegatedToTheSkill:
    """The command no longer holds any loop mechanics of its own — it names the
    loop, and the mechanics live only in `relay:verifying-until-clean`."""

    def test_command_cites_the_skill_and_declares_no_loop_identity(self):
        """Equivalence rule: `/relay:implement --verify` must produce exactly what
        `/relay:implement` then `/relay:verify` produces. The skill owns one identity
        and takes no parameter, so this command must not name one."""
        body = _body()
        assert "relay:verifying-until-clean" in body
        assert "LOOP_ID" not in body

    def test_no_polish_leaf_tokens_survive_in_the_command(self):
        body = _body()
        for token in ("polish-simplify", "polish-review", "relay-polish-"):
            assert token not in body, f"stale polish-leaf token still present: {token!r}"

    def test_run_id_guard_and_tier_exemption_prose_moved_to_the_skill(self):
        """Regression: `<run-id>` was never defined anywhere and is unreachable — the
        harness runId arrives in the Workflow tool *result*, after the script text is
        submitted. The guard now runs over both command files, because both hand the
        mechanics to the skill. The tier-exemption sentences that used to justify the
        polish leaves' pinned tier now live only in the skill."""
        cmd_body = _body()
        skill_body = _skill_body()
        assert "<run-id>" not in cmd_body, "undefined `<run-id>` placeholder must not appear"
        assert "<run-id>" not in skill_body, "undefined `<run-id>` placeholder must not appear"
        pin = "pinned-tier wrapper nodes deliberately exempt from `resolve-tier.sh --all`"
        assert pin in skill_body
        assert pin not in cmd_body


class TestLoopCommitAndReportContract:
    def test_commit_tokens_relocated_to_the_skill(self):
        body = _skill_body()
        for token in (
            "dominant conventional-commit scope",
            "most recent wins on ties",
            "refactor(<scope>): simplify implementation",
            "fix(<scope>): apply code-review findings",
            "refactor: simplify implementation",
            "fix: apply code-review findings",
            "commit_sha",
            "no changes",
        ):
            assert token in body, f"missing loop commit token: {token!r}"

    def test_the_spine_skill_carries_the_three_part_d_reasons(self):
        """4.38.0 moved this prose off the command and into the spine skill."""
        body = _spine_body()
        for token in (
            "unverified (acpx unavailable)",
            "unverified (loop blocked)",
            "findings",
        ):
            assert token in body, f"missing Part D report reason: {token!r}"

    def test_recorded_spine_tail_matches_a_generated_node_label(self):
        """The retro's SPINE check is a substring match over the generated node
        labels that ran (`scripts/retro-run.sh`). A `--verify` run records the
        `--spine` tail `verify-loop`, so the skill's report node label must contain
        that tail, or every `--verify` run reports a false SPINE deviation."""
        skill_body = _skill_body()
        assert "verify-loop-report" in skill_body
        assert "verify-loop" in "verify-loop-report"

    def test_the_spine_skill_gates_the_loop_role_a_bare_run_did_not_dispatch(self):
        """The mirror of the test above, and the reason a bare run needs a gate.

        `retro-run.sh` drops a role from `expected` only when that role is in the
        recorded spine AND `gates` holds exactly `False` for it. So a bare run must
        record `verify-loop` in its spine and gate it off; a bare spine that omitted
        `verify-loop` would make the `verify-loop=false` gate suppress nothing (and
        would break the step's own 'record a gate only for a spine role' rule). A
        bare run generates no label containing `verify-loop`, so the gate is what
        keeps every healthy bare run from reporting a SPINE deviation.

        4.38.0 moved this prose off the command and into the spine skill.
        """
        body = _spine_body()
        assert "verify-loop=false" in body
        assert (
            "refine-spec,write-plan,refine-plan,implement,commit,verify,verify-loop` for both a bare run"
            in body
        )

    def test_implement_frontmatter_needs_no_new_tools(self):
        text = IMPLEMENT.read_text()
        frontmatter = text.split("---", 2)[1]
        assert "allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill, SendMessage" in frontmatter


class TestVerifyFlagOptIn:
    """`--verify` opts into the loop. Bare `/relay:implement` stops after `verify`.

    The contract the flag exists to keep: `/relay:implement --verify` is exactly
    `/relay:implement` followed by `/relay:verify`.
    """

    def test_the_flag_is_advertised_in_the_argument_hint(self):
        hint = re.search(r'argument-hint: "(.*)"', _body()).group(1)
        assert "--verify" in hint

    def test_the_flag_is_read_from_the_argument_string_not_positionals(self):
        """The harness runs each block with zero positionals, so a `$1` loop never
        iterates and the flag would silently stay off on every run. The extraction
        itself moved to scripts/l3-preflight.sh (issue #110); implement.md now only
        forwards the raw `$ARGUMENTS` string to it."""
        script = L3_PREFLIGHT.read_text()
        assert "grep -qw -- '--verify'" in script
        assert "_verify=1" in script
        body = _body()
        assert 'l3-preflight.sh" implement "$ARGUMENTS"' in body

    def test_rounds_without_the_flag_is_an_error(self, tmp_path):
        """A round cap with no loop to cap is a mistake worth reporting. Ignoring it
        silently makes the user believe a loop ran."""
        script = L3_PREFLIGHT.read_text()
        assert "this run has no verify loop" in script
        assert "Add --verify, or drop --rounds." in script
        result = subprocess.run(
            ["bash", str(L3_PREFLIGHT), "implement", "--rounds 3"],
            capture_output=True,
            text=True,
            env=deps_ok_env(tmp_path),
        )
        assert result.returncode == 1
        assert "Add --verify, or drop --rounds." in result.stdout

    def test_the_classifier_never_reads_the_flag(self):
        """A stray flag in the task text changes the inferred kind. `--retro` had this
        exact bug, which is why the strip list is asserted rather than assumed."""
        body = _body()
        assert "minus `--verify`" in body
        assert "or `--verify` in the text pollutes what the classifier reads" in body

    def test_the_loop_tail_is_generated_only_behind_the_flag(self):
        """4.39.0: the spine skill gates on its own `verify` input, not on
        `/relay:implement`'s Step 0 — `relay:implementing-spec` has no Step 0 and
        passes `verify=true` directly (design §8 step 5)."""
        body = _body()
        assert "only when `--verify` was passed" in body
        assert "Generate this tail only when the `verify` input is true" in body

    def test_a_bare_run_never_reports_a_clean_result(self):
        """No loop ran, so there is no verdict. Reporting success here would be the
        exact silent pass the escalate posture exists to prevent."""
        body = _body()
        assert "A bare run produces no `RELAY_VERIFY_RESULT` at all" in body
        assert "Never read the absence of the loop as a clean result." in body


class TestVerifyFlagBranchGuard:
    """`/relay:verify` refuses `main` and a detached HEAD, because its loop commits
    every round. The `--verify` tail runs that same loop, so it must refuse both.

    Without this the two paths differ where it matters most: on `main`, in a headless
    run, `/relay:implement --verify` would commit to the default branch while
    `/relay:verify` exits 1.
    """

    def test_the_guard_exists_and_is_scoped_to_the_flag(self):
        body = _body()
        assert "## Step 0.6 — Branch guard, only when `--verify` was passed" in body
        assert "Skip this step entirely when Step 0 printed `enabled=0`." in body

    def test_the_guard_runs_after_the_worktree_gate(self):
        """It must read the branch the run LANDS on, not the one it started on —
        Step 0.5 may enter a fresh worktree."""
        body = _body()
        assert body.index("## Step 0.5") < body.index("## Step 0.6")
        assert body.index("## Step 0.6") < body.index("## Step 1 —")
        assert "runs **after** Step 0.5" in body

    @pytest.mark.parametrize("token", ["RELAY_WT_STATE", "RELAY_WT_BRANCH", "DETACHED"])
    def test_the_guard_reads_the_printed_state_block(self, token):
        """The state read moved into worktree-preflight.sh's --branch-guard mode
        (issue #110); implement.md now only calls it."""
        assert token in WT_PREFLIGHT.read_text()
        assert "--branch-guard" in _body()

    def test_the_guard_refuses_both_states_with_a_reason(self):
        body = _body()
        assert "refuses the default branch" in body
        assert "refuses a detached HEAD" in body
        assert "not on any branch" in WT_PREFLIGHT.read_text()


class TestFeatureSpineIsComplete:
    """#86 and #78: the spine must write the plan it refines, and must commit."""

    def _row(self, kind):
        row = next(
            (l for l in _body().splitlines() if l.startswith(f"- `{kind}`")), ""
        )
        assert row, f"missing branch-table row for {kind}"
        return row

    def test_the_feature_row_writes_the_plan_it_refines(self):
        row = self._row("feature")
        assert "write-plan" in row
        assert row.index("write-plan") < row.index("refine-plan")

    @pytest.mark.parametrize(
        "kind", ["feature", "bugfix", "script", "config-artifact", "docs"]
    )
    def test_every_row_commits_before_it_verifies(self, kind):
        row = self._row(kind)
        assert "commit" in row, f"{kind} row records no commit node"
        assert row.index("commit") < row.rindex("verify")

    def test_the_spine_example_matches_the_feature_row(self):
        """A recorded spine that does not match the row makes every feature
        retro report a false SPINE deviation."""
        body = _body()
        example = "refine-spec,write-plan,refine-plan,implement,commit,verify,verify-loop"
        assert example in body
        row = self._row("feature")
        for label in example.split(","):
            if label == "verify-loop":
                continue   # the opt-in tail; no row carries it
            assert label in row, f"the example records {label}, the row does not"

    def test_the_plan_adapter_input_is_assigned_somewhere(self):
        """Lower-case `plan_path` was read and never written. Search the command
        bodies and every SKILL.md, so the check survives a later move."""
        sources = list((PLUGIN_ROOT / "commands").glob("*.md"))
        sources += list((PLUGIN_ROOT / "skills").rglob("SKILL.md"))
        assert any("plan_path = PLAN_PATH" in p.read_text() for p in sources), (
            "nothing binds the plan adapter's `plan_path` from the role's "
            "PLAN_PATH token"
        )

    def test_the_adapter_fails_loudly_on_a_missing_subject(self):
        body = (PLUGIN_ROOT / "skills" / "refining" / "SKILL.md").read_text()
        assert "SUBJECT_MISSING" in body


class TestSpineSkillIsWiredToItsOwnInputs:
    """The apk seam (#75/#77/#78/#86): `relay:running-implement-spine` has two
    callers, and only one of them — `/relay:implement` — runs the command's own
    Step 0/Step 1. `relay:implementing-spec` passes `verify` and `engine` as plain
    object keys and never runs Step 0 at all, so the skill must gate and branch on
    its own declared inputs, never on `/relay:implement`-only facts like Step 0's
    `enabled=1` line or the `$RELAY_ENGINE` environment variable. Regression for
    the bug where an `implementing-spec` run fell through to the loop's `*` arm
    and reported `engine= has no verify-loop substrate` on every healthy run."""

    def test_the_tail_gates_on_the_verify_input(self):
        body = _spine_body()
        assert "Generate this tail only when the `verify` input is true" in body
        assert "Step 0 printed `enabled=1`" not in body

    def test_the_tail_never_reads_relay_engine_from_the_environment(self):
        """The loop-engine case statement must branch on a value this skill set
        from its own `engine` input, not on an ambient `$RELAY_ENGINE` that only
        `/relay:implement`'s Step 0 ever exports."""
        body = _spine_body()
        assert 'RELAY_ENGINE="<this run\'s engine input>"' in body

    def test_the_skill_declares_an_axis_source_input(self):
        """Step 3.5's `--axis-source` flag needs a value from both callers. Only
        `/relay:implement` prints a Step 0 axis line; `relay:implementing-spec`
        never does, so the flag must read a declared input, not that line."""
        body = _spine_body()
        assert "`axis_source`" in body
        assert "the source printed on the last Step 0 axis line" not in body
        assert '--axis-source "<this run\'s axis_source input>"' in body

    @pytest.mark.parametrize("heading", ["## Step 3 —", "## Step 3.5", "## Step 4"])
    def test_every_session_tree_skip_states_it_never_applies_to_the_adapter(self, heading):
        """Steps 3, 3.5, and 4 each open with a `session-tree` precondition that
        names Step 1 — a step that lives only in `commands/implement.md` and that
        `relay:implementing-spec` never runs. Each must say plainly that the
        precondition is always false on the adapter path, or a model asked to
        evaluate it on that path has nothing to evaluate."""
        body = _spine_body()
        section = body.split(heading, 1)[1].split("\n## ", 1)[0]
        collapsed = re.sub(r"\s+", " ", section)
        assert "relay:implementing-spec" in section
        assert "always false for that caller" in collapsed

    def test_implementing_spec_passes_axis_source_to_the_spine(self):
        body = (PLUGIN_ROOT / "skills" / "implementing-spec" / "SKILL.md").read_text()
        assert "axis_source" in body
        assert "relay.json" in body
