"""Unit tests for scripts/bg-liveness.sh (bg dispatch contract §1.5, S4-1, S4-2 —
docs/bg-dispatch-contract.md).

Fixtures live under tests/fixtures/bg-state/. Each fixture carries a placeholder
`updatedAt`; every test rewrites it into a copy under `tmp_path` before running the
script, so staleness is always computed relative to the real clock at test time, never
against a shipped timestamp.
"""

import datetime
import json
import os
import re
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bg-liveness.sh"
FIXTURES = PLUGIN_ROOT / "tests" / "fixtures" / "bg-state"


def _iso(age_seconds):
    ts = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(seconds=age_seconds))
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _place(tmp_path, fixture_name, short_id, age_seconds=0):
    """Copy a fixture into tmp_path/jobs/<short_id>/state.json with a live
    updatedAt."""
    jobs = tmp_path / "jobs"
    job_dir = jobs / short_id
    job_dir.mkdir(parents=True, exist_ok=True)
    src = FIXTURES / fixture_name
    if fixture_name == "malformed.json":
        (job_dir / "state.json").write_text(src.read_text())
    else:
        data = json.loads(src.read_text())
        data["updatedAt"] = _iso(age_seconds)
        (job_dir / "state.json").write_text(json.dumps(data))
    return jobs


def _run(tmp_path, args, jobs_dir=None, stale_seconds=None):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    if jobs_dir is not None:
        env["RELAY_BG_JOBS_DIR"] = str(jobs_dir)
    if stale_seconds is not None:
        env["RELAY_BG_STALE_SECONDS"] = str(stale_seconds)
    else:
        env.pop("RELAY_BG_STALE_SECONDS", None)
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                           text=True, env=env)


def _block_for(stdout, short_id):
    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        if line == f"RELAY_BG_SHORT_ID={short_id}":
            return dict(l.split("=", 1) for l in lines[i:i + 4])
    raise AssertionError(f"no block for {short_id} in:\n{stdout}")


class TestScriptShape:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.is_file()
        assert os.access(SCRIPT, os.X_OK)


class TestStateToVerdict:
    ROWS = [
        ("working.json", "alive"),
        ("blocked.json", "alive"),
        ("done.json", "alive"),
        ("stopped.json", "stopped"),
        ("failed.json", "stopped"),
    ]

    def _one(self, tmp_path, fixture_name, expected_verdict):
        jobs = _place(tmp_path, fixture_name, "id1", age_seconds=10)
        result = _run(tmp_path, ["--short-id", "id1"], jobs_dir=jobs)
        block = _block_for(result.stdout, "id1")
        assert block["RELAY_BG_VERDICT"] == expected_verdict, result.stdout

    def test_state_maps_to_verdict(self, tmp_path):
        for fixture_name, expected in self.ROWS:
            self._one(tmp_path / fixture_name, fixture_name, expected)

    def test_done_is_alive_not_stopped(self, tmp_path):
        self._one(tmp_path, "done.json", "alive")

    def test_absent_state_file_is_unknown(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        result = _run(tmp_path, ["--short-id", "nosuchid"], jobs_dir=jobs)
        block = _block_for(result.stdout, "nosuchid")
        assert block["RELAY_BG_VERDICT"] == "unknown"
        assert block["RELAY_BG_STATE"] == ""
        assert block["RELAY_BG_AGE_SECONDS"] == "-1"

    def test_malformed_state_file_is_unknown(self, tmp_path):
        jobs = _place(tmp_path, "malformed.json", "id1")
        result = _run(tmp_path, ["--short-id", "id1"], jobs_dir=jobs)
        block = _block_for(result.stdout, "id1")
        assert block["RELAY_BG_VERDICT"] == "unknown"
        # Must not crash: the script still prints a summary line and exits cleanly.
        assert "RELAY_BG_SUMMARY=" in result.stdout


class TestStaleness:
    def test_stale_downgrades_only_alive_states(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        _place(jobs.parent, "working.json", "old-working", age_seconds=2000)
        result = _run(tmp_path, ["--short-id", "old-working", "--stale-seconds", "900"],
                      jobs_dir=jobs)
        block = _block_for(result.stdout, "old-working")
        assert block["RELAY_BG_VERDICT"] == "stale"

    def test_stopped_is_never_reclassified_by_age(self, tmp_path):
        jobs = _place(tmp_path, "stopped.json", "id1", age_seconds=100000)
        result = _run(tmp_path, ["--short-id", "id1", "--stale-seconds", "10"],
                      jobs_dir=jobs)
        block = _block_for(result.stdout, "id1")
        assert block["RELAY_BG_VERDICT"] == "stopped"

    def test_unknown_is_never_reclassified_by_age(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        result = _run(tmp_path, ["--short-id", "ghost", "--stale-seconds", "0"],
                      jobs_dir=jobs)
        block = _block_for(result.stdout, "ghost")
        assert block["RELAY_BG_VERDICT"] == "unknown"

    def test_default_stale_seconds_is_900(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        _place(jobs.parent, "working.json", "young", age_seconds=800)
        _place(jobs.parent, "working.json", "old", age_seconds=1000)
        result = _run(tmp_path, ["--short-id", "young", "--short-id", "old"],
                      jobs_dir=jobs)
        assert _block_for(result.stdout, "young")["RELAY_BG_VERDICT"] == "alive"
        assert _block_for(result.stdout, "old")["RELAY_BG_VERDICT"] == "stale"

    def test_stale_seconds_flag_overrides_the_env_var(self, tmp_path):
        jobs = _place(tmp_path, "working.json", "id1", age_seconds=100)
        result = _run(tmp_path, ["--short-id", "id1", "--stale-seconds", "10"],
                      jobs_dir=jobs, stale_seconds=100000)
        block = _block_for(result.stdout, "id1")
        assert block["RELAY_BG_VERDICT"] == "stale"

    def test_updated_at_with_milliseconds_parses(self, tmp_path):
        jobs = _place(tmp_path, "working.json", "id1", age_seconds=5)
        result = _run(tmp_path, ["--short-id", "id1"], jobs_dir=jobs)
        block = _block_for(result.stdout, "id1")
        assert block["RELAY_BG_AGE_SECONDS"] != "-1"
        assert int(block["RELAY_BG_AGE_SECONDS"]) >= 0


class TestMultipleChildrenAndSummary:
    def test_multiple_children_print_one_block_each_in_order(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        _place(jobs.parent, "working.json", "a", age_seconds=1)
        _place(jobs.parent, "stopped.json", "b", age_seconds=1)
        _place(jobs.parent, "failed.json", "c", age_seconds=1)
        result = _run(tmp_path, ["--short-id", "a", "--short-id", "b", "--short-id", "c"],
                      jobs_dir=jobs)
        ids_in_order = re.findall(r"RELAY_BG_SHORT_ID=(\S+)", result.stdout)
        assert ids_in_order == ["a", "b", "c"]

    def test_summary_line_counts_every_child(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        _place(jobs.parent, "working.json", "a", age_seconds=1)
        _place(jobs.parent, "stopped.json", "b", age_seconds=1)
        result = _run(tmp_path, ["--short-id", "a", "--short-id", "b",
                                 "--short-id", "ghost"], jobs_dir=jobs)
        m = re.search(r"RELAY_BG_SUMMARY=alive=(\d+),stale=(\d+),stopped=(\d+),unknown=(\d+)",
                      result.stdout)
        assert m, result.stdout
        counts = [int(x) for x in m.groups()]
        assert sum(counts) == 3
        assert counts == [1, 0, 1, 1]


class TestExitCodes:
    def test_all_alive_exits_0(self, tmp_path):
        jobs = _place(tmp_path, "working.json", "id1", age_seconds=1)
        result = _run(tmp_path, ["--short-id", "id1"], jobs_dir=jobs)
        assert result.returncode == 0

    def test_any_stopped_exits_1(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        _place(jobs.parent, "working.json", "a", age_seconds=1)
        _place(jobs.parent, "stopped.json", "b", age_seconds=1)
        result = _run(tmp_path, ["--short-id", "a", "--short-id", "b"], jobs_dir=jobs)
        assert result.returncode == 1

    def test_usage_error_exits_2(self, tmp_path):
        result = _run(tmp_path, [])
        assert result.returncode == 2
        assert result.stderr.startswith("[relay] error: ")

    def test_stale_or_unknown_with_no_stopped_exits_3(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        result = _run(tmp_path, ["--short-id", "ghost"], jobs_dir=jobs)
        assert result.returncode == 3


class TestVerdictVocabularyAndScope:
    def test_verdict_vocabulary_is_closed(self, tmp_path):
        jobs = tmp_path / "jobs"
        jobs.mkdir()
        _place(jobs.parent, "working.json", "a", age_seconds=1)
        _place(jobs.parent, "stopped.json", "b", age_seconds=1)
        result = _run(tmp_path, ["--short-id", "a", "--short-id", "b",
                                 "--short-id", "ghost"], jobs_dir=jobs)
        verdicts = set(re.findall(r"RELAY_BG_VERDICT=(\S+)", result.stdout))
        assert verdicts <= {"alive", "stopped", "stale", "unknown"}

    def test_script_never_reads_task_outcome(self):
        """The script body must not consult ROLE_DONE, .output, or .result — the
        state file is not a success oracle (S4-2)."""
        text = SCRIPT.read_text()
        assert "ROLE_DONE" not in text
        assert ".output" not in text
        assert ".result" not in text
