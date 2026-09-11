"""The --retro flag and the Step 3.5 intent record, wired into all five L3 commands
(spec §3.2, §3.6, §3.7, §5).

These are contract tests on the command bodies. The failure they guard against is not
hypothetical: `--retro` reaching `parse-engine-agent.sh` as a third positional aborts
the command outright (that script hard-rejects extras), and a `--retro` left in the
text handed to the classifier silently changes the inferred kind.
"""

import re
import subprocess
import sys

from conftest import PLUGIN_ROOT

COMMANDS = ["implement.md", "execute.md", "refine.md", "drive.md", "diagnose.md"]
AXIS_COMMANDS = ["implement.md", "execute.md", "refine.md", "drive.md"]

# The only spine roles a command may gate, keyed by command. A gate is legitimate only
# when the command can genuinely skip that node; anything else records a gate that can
# never fire. `/relay:implement` dispatches `verify-loop` only when `--verify` is passed,
# and dispatches `write-plan` only when no plan under `docs/plans/` matches the spec slug.
GATEABLE_ROLES = {"implement.md": {"verify-loop", "write-plan"}}


SPINE_SKILL = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"
L3_PREFLIGHT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"


def body(name):
    """4.38.0 moved implement's Steps 3-3.5-4 into relay:running-implement-spine.
    That prose is part of implement's contract wherever it lives."""
    text = (PLUGIN_ROOT / "commands" / name).read_text()
    if name == "implement.md":
        text += "\n" + SPINE_SKILL.read_text()
    return text


def script_body():
    """Issue #110 moved the --retro extraction (grep/sed and the target regex,
    one copy per command arm) out of every command body and into
    scripts/l3-preflight.sh."""
    return L3_PREFLIGHT.read_text()


class TestFlagIsDeclared:
    def test_every_command_advertises_retro_in_its_argument_hint(self):
        for name in COMMANDS:
            hint = re.search(r'argument-hint: "(.*)"', body(name)).group(1)
            assert "--retro" in hint, f"{name} does not advertise --retro"

    def test_the_hint_shows_the_target_is_optional(self):
        for name in COMMANDS:
            hint = re.search(r'argument-hint: "(.*)"', body(name)).group(1)
            assert "[--retro [<runId>|last]]" in hint, name


class TestFlagIsExtracted:
    def test_every_command_parses_retro_out_of_the_argument_string(self):
        """Issue #110: the extraction (grep -qw + target regex) moved into
        scripts/l3-preflight.sh, one copy per command arm; each command body
        now only forwards $ARGUMENTS to that script."""
        text = script_body()
        assert "_retro=0" in text, "l3-preflight.sh never initializes the retro flag"
        assert "grep -qw -- '--retro'" in text, "l3-preflight.sh does not detect --retro"
        assert "_retro_target=" in text, "l3-preflight.sh does not extract a target"
        for name in COMMANDS:
            cmd = name[: -len(".md")]
            assert f'l3-preflight.sh" {cmd} "$ARGUMENTS"' in body(name), (
                f"{name} does not forward $ARGUMENTS to scripts/l3-preflight.sh"
            )

    def test_only_a_run_id_or_the_word_last_counts_as_a_target(self):
        """`--retro add a login form` must not read "add" as a run id."""
        text = script_body()
        assert "wf_[A-Za-z0-9._-]+" in text
        assert "(last)" in text

    def test_bare_last_only_counts_when_nothing_follows_it(self):
        """`--retro last night's regression` is task text, not a retro target.

        A `wf_<id>` is unambiguous so trailing text may follow it, but reading the bare
        word `last` mid-sentence puts the command into read-only retro mode and silently
        discards the task the user actually asked for.
        """
        assert "s/.*--retro[ =]+(last) *$/" in script_body()

    def test_the_flag_is_parsed_from_arguments_never_from_positionals(self):
        """The harness runs a command's bash block with ZERO positionals. Issue
        #110 moved the retro extraction into scripts/l3-preflight.sh, which
        parses from its own RAW_ARGS variable, not from $1/$2 — and no command
        body contains a positional parameter at all."""
        text = script_body()
        block = text[text.index("RAW_ARGS=") :]
        assert "$1" not in block and "$2" not in block
        for name in COMMANDS:
            cmd_text = body(name)
            for tok in ("$1", "$2", "$3", "$4", "$5", "$6", "$7", "$8", "$9"):
                assert tok not in cmd_text, f"{name} reads a positional parameter ({tok})"


class TestFlagIsNotForwarded:
    def test_parse_engine_agent_still_receives_exactly_two_arguments(self):
        """That script hard-rejects a third positional — forwarding --retro aborts the
        command before any work happens. Issue #110 moved every such call into
        scripts/l3-preflight.sh."""
        calls = re.findall(r'parse-engine-agent\.sh"(.*)', script_body())
        assert calls
        for call in calls:
            args = re.findall(r'"([^"]*)"', call)
            assert len(args) == 2, f"l3-preflight.sh: parse-engine-agent.sh got {args}"
            assert "retro" not in " ".join(args)

    def test_diagnose_still_does_not_source_the_axis_parser_at_all(self):
        assert "parse-engine-agent.sh" not in body("diagnose.md")


class TestFlagIsStrippedBeforeClassification:
    def test_every_command_strips_retro_from_the_classifier_input(self):
        for name in COMMANDS:
            text = body(name)
            assert re.search(r"minus[^.\n]*`--retro`|minus `--retro`", text), (
                f"{name} does not document stripping --retro before Step 1")

    def test_drive_strips_retro_out_of_the_oracle_path(self):
        """drive recovers its oracle by stripping recognized flags out of the string;
        an unstripped --retro would be read as the oracle file. Issue #110 moved
        this extraction into scripts/l3-preflight.sh."""
        text = script_body()
        oracle = next(line for line in text.splitlines() if "--resume( |" in line)
        assert "--retro[ =]+(wf_[A-Za-z0-9._-]+|last)" in oracle
        assert "--retro( |" in oracle


class TestRetroOnlyMode:
    def test_every_command_documents_the_retro_only_short_circuit(self):
        for name in COMMANDS:
            text = body(name)
            assert "## Step 0.2 — Retro-only mode" in text, name
            assert "do **not** generate a Workflow" in text, name

    def test_retro_only_runs_before_the_worktree_gate(self):
        """A retro is read-only; it must not create or enter a worktree to audit a run."""
        for name in ("implement.md", "execute.md", "refine.md", "drive.md"):
            text = body(name)
            assert text.index("## Step 0.2 — Retro-only mode") < \
                   text.index("## Step 0.5 — Ensure worktree isolation"), name
            assert "do **not** enter a worktree" in text, name


class TestRetroRunsAfterTheGate:
    def test_every_command_invokes_the_retro_script(self):
        for name in COMMANDS:
            assert "scripts/retro-run.sh" in body(name), name

    def test_the_retro_runs_after_the_completeness_gate(self):
        for name in COMMANDS:
            if name == "implement.md":
                # The gate now runs inside the skill Step 3 calls, before Step 5's
                # retro — not textually after it in the command's own bytes.
                cmd = (PLUGIN_ROOT / "commands" / name).read_text()
                assert "verify-run-completeness.sh" in SPINE_SKILL.read_text()
                assert cmd.index("relay:running-implement-spine") < cmd.rindex("retro-run.sh")
                continue
            text = body(name)
            assert text.index("verify-run-completeness.sh") < \
                   text.rindex("retro-run.sh"), name

    def test_the_retro_is_documented_as_advisory_and_read_only(self):
        for name in COMMANDS:
            text = body(name)
            assert "advisory and strictly read-only" in text, name
            assert "never fails the command" in text, name

    def test_the_retro_must_run_outside_the_workflow(self):
        """Two independent reasons: a retro node appended to the script would not have
        executed on the runs that most needed one, and it would itself be an
        agent({schema}) node subject to the same failure mode."""
        for name in COMMANDS:
            text = body(name)
            assert "outside** the Workflow" in text, name
            assert "agent({schema})" in text, name

    def test_the_gate_audit_finding_is_surfaced(self):
        """A non-empty C3 where every node shows attempt == 1 means the gate did not
        fire — the single highest-value finding a retro can produce."""
        for name in COMMANDS:
            assert "the completeness gate did not fire" in body(name), name


class TestIntentRecordStep:
    def test_every_command_records_run_intent(self):
        for name in COMMANDS:
            text = body(name)
            assert "## Step 3.5 — Record run intent" in text, name
            assert "scripts/record-run-intent.sh" in text, name

    def test_the_record_is_written_after_the_workflow_returns(self):
        """run_id exists only in the tool RESULT, never echoed back from the input."""
        for name in COMMANDS:
            text = body(name)
            assert "immediately after the `Workflow` tool returns" in text, name
            assert "--run-id \"<runId>\"" in text, name

    def test_every_command_passes_gates(self):
        """Without gates the retro cannot tell an omitted node from a dropped one."""
        for name in COMMANDS:
            assert "--gates" in body(name), name

    def test_no_command_gates_on_anything_but_a_node_label(self):
        """The retro suppresses a role via `gates.get(role)`, so a gate keyed on anything
        that is not a spine node label matches nothing and suppresses nothing.

        `delegation=` was the specific regression: it reads as a gate, records fine, and
        excuses no role — because delegation changes HOW a node runs, not WHETHER it
        runs. Every spine role still dispatches with it off. A gate that can never fire
        is worse than no gate: the docs called this field essential while it was inert.
        """
        for name in COMMANDS:
            call = body(name).split("record-run-intent.sh")[1].split("```")[0]
            gates = call.split("--gates")[1].split("\\")[0].strip()
            allowed = GATEABLE_ROLES.get(name, set())
            if not allowed:
                assert gates == '""', (
                    f"{name} records a non-empty --gates ({gates}). This command has no "
                    "skippable spine role; if one now exists, key the gate on that role's "
                    "node label and add it to GATEABLE_ROLES."
                )
                continue
            keyed = set(re.findall(r"([a-z][a-z0-9-]*)=(?:true|false)", gates))
            assert keyed, (
                f"{name} may gate {sorted(allowed)}, but its --gates value ({gates}) "
                "records no `label=false` pair. A gate the retro cannot parse is inert."
            )
            assert not keyed - allowed, (
                f"{name} gates on {sorted(keyed - allowed)}, which is not a skippable "
                f"spine role. Only {sorted(allowed)} may be gated."
            )
            for role in keyed:
                assert role in body(name), (
                    f"{name} gates on {role!r}, which its own body never names as a "
                    "spine node label. The retro would suppress nothing."
                )

    def test_no_command_records_the_axis_values_or_the_task_text(self):
        for name in COMMANDS:
            call = body(name).split("record-run-intent.sh")[1].split("```")[0]
            for forbidden in ("--engine", "--agent", "--task ", "--phases"):
                assert forbidden not in call, f"{name} records {forbidden}"

    def test_the_flag_is_task_kind_not_kind(self):
        """`--kind` is forbidden in an L3 body: the task kind is always auto-classified
        and must never be user-overridable. The record flag is named around that."""
        for name in COMMANDS:
            text = body(name)
            assert "--task-kind" in text, name
            assert "--kind" not in text, name

    def test_the_intent_record_step_is_advisory(self):
        for name in COMMANDS:
            assert "advisory bookkeeping" in body(name), name


class TestValidatorsStillPass:
    def test_validate_l3_command_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "validate_l3_command.py")],
            capture_output=True, text=True)
        assert result.returncode == 0, result.stdout

    def test_retro_is_an_inline_step_not_a_relay_vocabulary_token(self):
        """Keeping retro as an inline command step avoids touching the validator's
        _KNOWN token set."""
        for name in COMMANDS:
            assert "relay:retro" not in body(name), name
