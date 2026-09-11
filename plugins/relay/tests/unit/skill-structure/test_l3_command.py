import importlib.util
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_V = PLUGIN_ROOT / "scripts" / "validate_l3_command.py"
_spec = importlib.util.spec_from_file_location("validate_l3_command", _V)
vl3 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(vl3)

CLASSIFIER = PLUGIN_ROOT / "skills" / "classifying-task-kind" / "SKILL.md"

class TestClassifierSkill:
    def test_exists(self):
        assert CLASSIFIER.is_file(), "classifying-task-kind/SKILL.md missing"

    def test_closed_enum_is_exact(self):
        assert vl3.TASK_KINDS == ["feature", "script", "config-artifact", "bugfix", "docs"]

    def test_body_lists_every_kind(self):
        text = CLASSIFIER.read_text()
        for kind in vl3.TASK_KINDS:
            assert kind in text, f"classifier must name kind '{kind}'"

    def test_emits_typed_output_contract(self):
        text = CLASSIFIER.read_text()
        assert "typed-output" in text and "kind:" in text

    def test_no_relay_vocab_block(self):
        # E.1: classifier carries NO relay-vocab block (no honest l1-shape)
        assert "```relay-vocab" not in CLASSIFIER.read_text()

    def test_body_nonempty(self):
        assert len(CLASSIFIER.read_text()) > 200

    def test_not_in_l2_names(self):
        v2p = PLUGIN_ROOT / "scripts" / "validate_l2_vocab.py"
        s = importlib.util.spec_from_file_location("validate_l2_vocab", v2p)
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
        assert "classifying-task-kind" not in m.L2_NAMES

class TestL3Validator:
    def test_kind_enum_constant(self):
        assert vl3.TASK_KINDS == ["feature", "script", "config-artifact", "bugfix", "docs"]

    def test_accepts_well_formed(self):
        good = (
            "run relay:classifying-task-kind to infer the kind from context\n"
            "policy branch on kind.value\n"
            "cite only known vocabulary: relay:panel, relay:delegate-leaf\n"
        )
        assert vl3.check_command(good, require_branch=True) == []

    def test_flags_missing_classifier(self):
        bad = "just generate a workflow with a --kind flag and a branch\n"
        errs = vl3.check_command(bad, require_branch=True)
        assert any("classif" in e.lower() for e in errs)

    def test_worktree_classify_flag_is_not_a_task_kind_classifier(self):
        # v4.5.0: the worktree-gate `--classify` flag (a git-state read) must NOT
        # masquerade as a task-kind classifier node. A body that mentions ONLY the
        # worktree `--classify` flag — no classifying-task-kind skill, no other
        # classif* word — must still flag the missing task-kind classifier.
        # Mutation guard: reverting the `--classify` strip in check_command() (so the
        # full body is probed for the 'classif' stem) makes this case go green-wrong.
        bad = (
            "source worktree-preflight.sh --classify to read the worktree state\n"
            "branch on the printed RELAY_WT_STATE\n"
        )
        errs = vl3.check_command(bad, require_branch=True)
        assert any("classif" in e.lower() for e in errs), errs

    def test_flags_kind_override_present(self):
        # --kind is no longer a supported surface: its presence is an error.
        bad = "run relay:classifying-task-kind, honor --kind, then branch on the result\n"
        errs = vl3.check_command(bad, require_branch=True)
        assert any("--kind" in e for e in errs)

    def test_flags_unknown_vocab(self):
        bad = (
            "run relay:classifying-task-kind\n"
            "policy branch; cite relay:frobnicate-loop\n"
        )
        errs = vl3.check_command(bad, require_branch=True)
        assert any("frobnicate-loop" in e for e in errs)

    def test_require_branch_false_skips_branch_check(self):
        # /relay:execute has classifier + override but NO policy branch
        execlike = "run relay:classifying-task-kind to infer the kind; compose freely\n"
        assert vl3.check_command(execlike, require_branch=False) == []

class TestDelegationWiring:
    def test_passes_when_present(self):
        body = (
            "run relay:classifying-task-kind\n"
            "policy branch on kind.value\n"
            "use relay:delegate-and-watch when acpx engine\n"
        )
        assert vl3.check_delegation_wiring(body) == []

    def test_fails_when_absent(self):
        body = (
            "run relay:classifying-task-kind\n"
            "policy branch; use relay:delegate-leaf only\n"
        )
        errs = vl3.check_delegation_wiring(body)
        assert any("delegate-and-watch" in e for e in errs)

    def test_implement_md_passes(self):
        p = PLUGIN_ROOT / "commands" / "implement.md"
        body = p.read_text().split("---", 2)[-1]
        assert vl3.check_delegation_wiring(body) == []

    def test_diagnose_md_in_main_dict(self):
        # main() must include diagnose.md so the validator covers it
        import inspect, ast
        src = (PLUGIN_ROOT / "scripts" / "validate_l3_command.py").read_text()
        assert "diagnose.md" in src

class TestNoInlineShapesInCommandBlocks:
    """Issue #110: a session isolated in a git worktree refuses an inline Bash
    command that carries `$(...)`, `source`/`.` sourcing, a `case` statement,
    or a line starting `if`. Every fenced bash block in commands/*.md (except
    the pre-existing setup.md exemption) must be free of all four shapes."""

    def test_flags_command_substitution(self):
        body = "```bash\nx=\"$(echo 1)\"\n```\n"
        assert vl3.check_inline_shapes(body) != []

    def test_flags_source(self):
        body = "```bash\nsource foo.sh\n```\n"
        assert vl3.check_inline_shapes(body) != []

    def test_flags_case(self):
        body = '```bash\ncase "$x" in\n  a) ;;\nesac\n```\n'
        assert vl3.check_inline_shapes(body) != []

    def test_flags_if(self):
        body = '```bash\nif [ -z "$x" ]; then\n  echo hi\nfi\n```\n'
        assert vl3.check_inline_shapes(body) != []

    def test_anti_vacuity_axis_source_line_is_not_a_source_false_positive(self):
        """`--axis-source in-session` contains the substring `source ` — the
        anchored source rule must not flag it."""
        body = "```bash\nbash script.sh --axis-source in-session\n```\n"
        assert vl3.check_inline_shapes(body) == []

    def test_comment_only_line_is_not_flagged(self):
        body = '```bash\n# case "$x" in\necho hi\n```\n'
        assert vl3.check_inline_shapes(body) == []

    @pytest.mark.parametrize(
        "name",
        sorted(
            p.name
            for p in (PLUGIN_ROOT / "commands").glob("*.md")
            if p.name != "setup.md"
        ),
    )
    def test_every_command_except_setup_is_clean(self, name):
        body = (PLUGIN_ROOT / "commands" / name).read_text()
        assert vl3.check_inline_shapes(body) == [], name

    def test_exemption_set_is_exactly_setup_md(self):
        assert vl3.INLINE_SHAPE_EXEMPT == {"setup.md"}

    def test_validator_still_exits_0(self):
        import subprocess

        result = subprocess.run(
            ["python3", str(PLUGIN_ROOT / "scripts" / "validate_l3_command.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_all_l3_commands_pass_validator():
    cmds = {"implement": True, "refine": True, "execute": False, "diagnose": True}
    for name, rb in cmds.items():
        p = PLUGIN_ROOT / "commands" / f"{name}.md"
        body = p.read_text().split("---", 2)[-1]
        errs = vl3.check_command(body, require_branch=rb)
        assert errs == [], (name, errs)


# --- spec 2026-07-25 §2.2 + §2.4 — silent-failure wiring in every L3 command -------
#
# Two runs lost half their dispatch nodes and reported success. The in-run layer
# (§2.2) is the only thing that can see a node return nothing; the post-Workflow gate
# (§2.4) is the only thing that can see a node that never returned at all. Both must
# be present in all five commands, uniformly — a command that carries neither ships
# the original bug.

L3_COMMANDS = ["diagnose", "drive", "execute", "implement", "refine"]

# The shape of the closing self-check is identical across the five; the parenthesized
# spine-role list is not. Assert only the shared prefix.
SELF_CHECK_PREFIX = "Before reporting completion, confirm: exactly one `Workflow` run was launched"


SPINE_SKILL = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"


def _command_body(name):
    """4.38.0 moved implement's Steps 3-3.5-4 into relay:running-implement-spine.
    The generation prose is part of the command's contract wherever it lives, so
    read both files for implement. Order is command-then-skill, which keeps the
    tier < guard < self-check ordering assertion meaningful."""
    text = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
    if name == "implement":
        text += "\n" + SPINE_SKILL.read_text()
    return text


@pytest.mark.parametrize("name", L3_COMMANDS)
class TestVerifyNodeGuard:
    """§2.2 — a verify node's guard must keep the 'no verdict' case reachable."""

    def test_three_case_guard_present(self, name):
        body = _command_body(name)
        assert "if (!verdict)" in body, \
            f"{name}.md must show the absent-verdict case as its own branch"
        assert "!verdict.blocking" in body, \
            f"{name}.md must show the clean case as a separate branch"

    def test_collapsed_guard_named_as_the_anti_pattern(self, name):
        body = _command_body(name)
        assert "if (!verdict || !verdict.blocking)" in body, \
            f"{name}.md must name the collapsed guard as the anti-pattern it is"
        assert "unverified run as verified" in body, \
            f"{name}.md must say what collapsing costs: an unverified run reported as verified"

    def test_swallowing_catch_named_as_the_anti_pattern(self, name):
        # The second run's `safeAgent` wrapper caught the harness's own hard error and
        # returned null. The mitigation caused the silent failure it was added to survive.
        body = _command_body(name)
        assert "try/catch" in body, f"{name}.md must warn about a try/catch around agent()"
        assert "re-raise" in body, f"{name}.md must require re-raising or recording the miss"
        assert "never as an absent field" in body, \
            f"{name}.md must forbid recording a schema miss as an absent field"

    def test_guard_lives_inside_the_workflow_generation_step(self, name):
        # Structural, not positional: the generation step runs between the tier
        # resolution and the closing self-check. drive.md and execute.md number that
        # step "Step 2", so anchoring on the string "Step 3" would skip two of five.
        body = _command_body(name)
        tier = body.index('"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" --all')
        guard = body.index("if (!verdict)")
        check = body.index(SELF_CHECK_PREFIX)
        assert tier < guard < check, \
            f"{name}.md: the verify-node guard must sit inside the Workflow-generation step"


@pytest.mark.parametrize("name", L3_COMMANDS)
class TestCompletenessGate:
    """§2.4 — the existing self-check proves shape only. The gate proves completeness."""

    def test_self_check_survives(self, name):
        assert SELF_CHECK_PREFIX in _command_body(name), \
            f"{name}.md must keep the one-Workflow self-check; the gate is appended to it"

    def test_gate_invoked_with_plugin_root_quoting(self, name):
        body = _command_body(name)
        assert '"${CLAUDE_PLUGIN_ROOT}/scripts/verify-run-completeness.sh"' in body, (
            f"{name}.md must invoke the completeness gate using the same "
            '"${CLAUDE_PLUGIN_ROOT}/scripts/..." quoting as the resolve-tier block'
        )

    def test_gate_takes_the_run_id(self, name):
        assert "<runId>" in _command_body(name), \
            f"{name}.md must pass the runId from the Workflow tool result"

    @pytest.mark.parametrize("verdict", ["COMPLETE", "INCOMPLETE", "INDETERMINATE"])
    def test_every_exit_code_is_handled(self, name, verdict):
        assert verdict in _command_body(name), \
            f"{name}.md must handle the {verdict} exit code"

    def test_incomplete_blocks_the_success_report(self, name):
        body = _command_body(name)
        assert "do not report success" in body, \
            f"{name}.md must refuse to report success on INCOMPLETE"
        assert "Name each dead node" in body, \
            f"{name}.md must name each dead node and the phase output it was to produce"

    def test_indeterminate_is_never_a_pass(self, name):
        body = _command_body(name)
        assert "could not be verified" in body, \
            f"{name}.md must report INDETERMINATE as 'completeness could not be verified'"
        assert "Never treat it as a pass" in body, \
            f"{name}.md must forbid treating INDETERMINATE as a pass"

    def test_gate_is_appended_to_the_self_check(self, name):
        # Ordering, not adjacency — the gate must belong to the closing self-check
        # rather than float somewhere earlier in the command.
        body = _command_body(name)
        assert body.index("verify-run-completeness.sh") > body.index(SELF_CHECK_PREFIX), \
            f"{name}.md: the completeness gate must follow the closing self-check"


def test_completeness_gate_script_is_referenced_by_a_real_path():
    # The wiring is inert until the script exists (spec §2.3).
    assert (PLUGIN_ROOT / "scripts" / "verify-run-completeness.sh").is_file(), \
        "all five commands invoke scripts/verify-run-completeness.sh; it must exist"


def test_all_five_commands_declare_bash():
    # The gate is a Bash call. A command that cannot run Bash cannot run the gate.
    for name in L3_COMMANDS:
        head = _command_body(name).split("---", 2)[1]
        tools = next(ln for ln in head.splitlines() if ln.startswith("allowed-tools:"))
        assert "Bash" in tools, f"{name}.md must declare Bash in allowed-tools"
