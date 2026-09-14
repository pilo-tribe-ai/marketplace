"""Unit tests for scripts/record-run-intent.sh (spec §3.7).

Everything here is SYNTHETIC — the script is driven with $HOME pointed at tmp_path, so
no real ~/.claude/relay/runs.jsonl is read, written, or derived from.
"""

import json
import os
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "record-run-intent.sh"


def record(home, *args, session=None):
    env = dict(os.environ)
    env["HOME"] = str(home)
    if session is None:
        env.pop("CLAUDE_CODE_SESSION_ID", None)
    else:
        env["CLAUDE_CODE_SESSION_ID"] = session
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True,
                          env=env)


def lines(home):
    path = home / ".claude" / "relay" / "runs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_one(home, *extra):
    return record(home, "--run-id", "wf_abc", "--command", "implement",
                  "--task-kind", "feature", *extra)


class TestHappyPath:
    def test_one_run_appends_exactly_one_line(self, tmp_path):
        result = write_one(tmp_path)
        assert result.returncode == 0, result.stdout
        assert "RELAY_INTENT=RECORDED" in result.stdout
        assert len(lines(tmp_path)) == 1

    def test_the_file_is_append_only(self, tmp_path):
        write_one(tmp_path)
        record(tmp_path, "--run-id", "wf_def", "--command", "drive")
        got = lines(tmp_path)
        assert [r["run_id"] for r in got] == ["wf_abc", "wf_def"]

    def test_the_recorded_fields_are_exactly_the_documented_set(self, tmp_path):
        write_one(tmp_path, "--spine", "a,b", "--gates", "polish=true",
                  "--axis-source", "pin")
        assert set(lines(tmp_path)[0]) == {
            "schema", "run_id", "relay_command", "kind", "intended_spine", "gates",
            "axis_source", "plugin_version", "session_dir", "cwd", "started_at",
        }

    def test_spine_is_split_and_trimmed(self, tmp_path):
        write_one(tmp_path, "--spine", " refine-spec , implement ,verify ")
        assert lines(tmp_path)[0]["intended_spine"] == ["refine-spec", "implement",
                                                        "verify"]

    def test_an_empty_spine_records_an_empty_list_not_null(self, tmp_path):
        """execute/drive have no hard spine; C1 must see [] and report descriptively."""
        write_one(tmp_path, "--spine", "")
        assert lines(tmp_path)[0]["intended_spine"] == []

    def test_gates_parse_to_real_booleans(self, tmp_path):
        write_one(tmp_path, "--gates", "polish=true,delegation=false")
        assert lines(tmp_path)[0]["gates"] == {"polish": True, "delegation": False}

    def test_an_unreadable_gate_value_is_kept_verbatim_not_dropped(self, tmp_path):
        """A dropped gate makes the retro emit a false deviation, so keep what we got."""
        write_one(tmp_path, "--gates", "polish=maybe")
        assert lines(tmp_path)[0]["gates"] == {"polish": "maybe"}

    def test_the_plugin_version_is_stamped(self, tmp_path):
        manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
        write_one(tmp_path)
        assert lines(tmp_path)[0]["plugin_version"] == manifest["version"]

    def test_started_at_is_utc_iso8601(self, tmp_path):
        write_one(tmp_path)
        stamp = lines(tmp_path)[0]["started_at"]
        assert stamp.endswith("Z") and "T" in stamp

    def test_json_is_one_line_even_with_awkward_text(self, tmp_path):
        """Hand-built JSON would break the JSONL contract on the first quote."""
        result = record(tmp_path, "--run-id", "wf_abc", "--command",
                        'we"ird\ncommand', "--task-kind", "feature")
        assert result.returncode == 0
        path = tmp_path / ".claude" / "relay" / "runs.jsonl"
        assert len(path.read_text().strip().splitlines()) == 1
        assert lines(tmp_path)[0]["relay_command"] == 'we"ird\ncommand'


class TestWhatIsDeliberatelyNotRecorded:
    """Only provably-unrecoverable fields belong here; a second copy of something
    durable can disagree with the original (spec §3.7)."""

    def test_no_axis_values_only_the_provenance(self, tmp_path):
        write_one(tmp_path, "--axis-source", "prompt")
        got = lines(tmp_path)[0]
        assert got["axis_source"] == "prompt"
        assert "engine" not in got and "agent" not in got

    def test_no_task_text_and_no_phase_list(self, tmp_path):
        write_one(tmp_path)
        got = lines(tmp_path)[0]
        assert "task" not in got and "phases" not in got

    def test_the_script_refuses_flags_for_them(self, tmp_path):
        for flag in ("--engine", "--agent", "--task", "--phases"):
            result = record(tmp_path, "--run-id", "wf_abc", "--command", "implement",
                            flag, "x")
            assert result.returncode == 1, flag
            assert "unexpected argument" in result.stdout


class TestAdvisoryFailure:
    """Bookkeeping must never take down a run that already succeeded."""

    def test_a_missing_run_id_fails_softly_and_says_so(self, tmp_path):
        result = record(tmp_path, "--command", "implement")
        assert result.returncode == 1
        assert "RELAY_INTENT=NOT_RECORDED" in result.stdout
        assert "advisory" in result.stdout
        assert "spine unknown" in result.stdout

    def test_a_missing_command_fails_softly(self, tmp_path):
        result = record(tmp_path, "--run-id", "wf_abc")
        assert result.returncode == 1
        assert "RELAY_INTENT_REASON=usage" in result.stdout

    def test_a_run_id_with_a_path_separator_is_refused(self, tmp_path):
        result = record(tmp_path, "--run-id", "../../evil", "--command", "implement")
        assert result.returncode == 1
        assert "RELAY_INTENT_REASON=bad_run_id" in result.stdout
        assert not (tmp_path / ".claude" / "relay" / "runs.jsonl").exists()

    def test_an_unresolvable_session_dir_records_null_rather_than_guessing(self, tmp_path):
        """NEVER derive the project slug from $PWD — it is fixed at session launch and
        EnterWorktree does not update it."""
        result = write_one(tmp_path)
        assert result.returncode == 0
        assert lines(tmp_path)[0]["session_dir"] is None

    def test_a_resolvable_session_dir_is_recorded(self, tmp_path):
        wanted = tmp_path / ".claude" / "projects" / "-slug" / "sess"
        wanted.mkdir(parents=True)
        result = record(tmp_path, "--run-id", "wf_x", "--command", "implement",
                        session="sess")
        assert result.returncode == 0
        assert lines(tmp_path)[-1]["session_dir"] == str(wanted)

    def test_help_exits_zero(self, tmp_path):
        result = record(tmp_path, "--help")
        assert result.returncode == 0
        assert "usage:" in result.stdout


class TestLocation:
    def test_the_record_lives_under_home_never_in_the_repo(self, tmp_path):
        """Leaf agents commit with `git add -A`-style flows and would sweep run records
        into the branch under review."""
        write_one(tmp_path)
        assert (tmp_path / ".claude" / "relay" / "runs.jsonl").is_file()
        body = SCRIPT.read_text()
        assert '"$HOME/.claude/relay"' in body
        assert "runs.jsonl" in body

    def test_the_script_never_writes_into_the_working_tree(self, tmp_path):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=PLUGIN_ROOT,
                                capture_output=True, text=True).stdout
        write_one(tmp_path)
        after = subprocess.run(["git", "status", "--porcelain"], cwd=PLUGIN_ROOT,
                               capture_output=True, text=True).stdout
        assert before == after
