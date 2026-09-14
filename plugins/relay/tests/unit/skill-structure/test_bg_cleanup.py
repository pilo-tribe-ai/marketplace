"""Behavioral tests for scripts/bg-cleanup.sh (bg dispatch contract — Part 2a,
docs/superpowers/plans/2026-08-25-relay-bg-auto-cleanup-nesting-plan.md §Step 4).
Everything here is SYNTHETIC: `HOME` is pointed at `tmp_path`, so no real job
directory, sidecar, manifest, or transcript is ever touched.

Style mirrors tests/unit/skill-structure/test_bg_dispatch_env.py and
test_bg_liveness.py; `_iso()` is copied from test_bg_liveness.py.
"""
import datetime
import json
import os
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bg-cleanup.sh"

RUNID = "7f3c1a2b"


def _iso(age_seconds=0):
    ts = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(seconds=age_seconds))
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sidecar(home, runid, role, name, short_id):
    d = home / ".claude" / "relay" / "bg" / runid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{role}.env").write_text(
        f"RELAY_BG_NAME={name}\nRELAY_BG_SHORT_ID={short_id}\n"
    )


def _manifest(home, runid, sessions):
    d = home / ".claude" / "relay" / "runs" / runid
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "runid": runid,
        "command": "implement",
        "started_at": _iso(100),
        "sessions": [
            {"name": n, "launch_id": sid, "role": "implementer",
             "parent": "MAIN", "phase": "done"}
            for n, sid in sessions
        ],
    }
    (d / "manifest.json").write_text(json.dumps(data))


def _job(home, short_id, state="stopped", age_seconds=10,
          transcript_rel=None, transcript_is_dir=False,
          transcript_outside=False):
    """Build a full job-directory + transcript fixture triple for short_id.

    Returns the transcript path (or None if transcript_rel is None)."""
    job_dir = home / ".claude" / "jobs" / short_id
    job_dir.mkdir(parents=True, exist_ok=True)

    link = ""
    transcript_path = None
    if transcript_rel is not None:
        if transcript_outside:
            transcript_path = home / "outside" / transcript_rel
        else:
            transcript_path = home / ".claude" / "projects" / transcript_rel
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        if transcript_is_dir:
            transcript_path.mkdir(parents=True, exist_ok=True)
        else:
            transcript_path.write_text("{}\n")
        link = str(transcript_path)

    (job_dir / "state.json").write_text(json.dumps({
        "name": short_id,
        "state": state,
        "detail": "x",
        "tempo": "stopped" if state == "stopped" else "active",
        "intent": "",
        "createdAt": _iso(200),
        "updatedAt": _iso(age_seconds),
        "linkScanPath": link,
    }))
    return job_dir, transcript_path


def _full_triple(home, short_id, state="stopped", age_seconds=10):
    """Standard fixture: job dir + state.json + a real transcript under
    ~/.claude/projects/."""
    return _job(home, short_id, state=state, age_seconds=age_seconds,
                transcript_rel=f"proj/{short_id}.jsonl")


def _run(tmp_path, args, home=None):
    home = home or (tmp_path / "home")
    home.mkdir(exist_ok=True, parents=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["RELAY_BG_JOBS_DIR"] = str(home / ".claude" / "jobs")
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                           text=True, env=env)


def _kv_lines(stdout, key):
    return [line[len(key) + 1:] for line in stdout.splitlines()
            if line.startswith(key + "=")]


class TestScriptShape:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.is_file()
        assert os.access(SCRIPT, os.X_OK)


class TestCleanRun:
    def test_deletes_recorded_ids_and_spares_unrelated(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-7f3c1a2b", "aaaaaa")
        job_dir, transcript = _full_triple(home, "aaaaaa")
        unrelated_dir, unrelated_ts = _full_triple(home, "bbbbbb")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not job_dir.exists()
        assert not transcript.exists()
        assert unrelated_dir.exists()
        assert unrelated_ts.exists()
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result.stdout


class TestFailedRun:
    def test_keeps_everything(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-7f3c1a2b", "aaaaaa")
        job_dir, transcript = _full_triple(home, "aaaaaa")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "failed"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert job_dir.exists()
        assert transcript.exists()
        assert "RELAY_BG_CLEANUP=kept 1 sessions" in result.stdout
        kept = _kv_lines(result.stdout, "RELAY_BG_KEPT")
        assert len(kept) == 1
        assert kept[0].endswith(" outcome-failed")


class TestKeepFlag:
    def test_keeps_even_with_outcome_clean(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-7f3c1a2b", "aaaaaa")
        job_dir, transcript = _full_triple(home, "aaaaaa")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean", "--keep"],
                       home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert job_dir.exists()
        assert transcript.exists()
        kept = _kv_lines(result.stdout, "RELAY_BG_KEPT")
        assert len(kept) == 1
        assert kept[0].endswith(" keep-flag")


class TestBothRegistries:
    def test_sidecar_only_and_manifest_only_both_deleted(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-sidecar", "aaaaaa")
        _manifest(home, RUNID, [("impl-manifest", "bbbbbb")])
        dir_a, ts_a = _full_triple(home, "aaaaaa")
        dir_b, ts_b = _full_triple(home, "bbbbbb")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not dir_a.exists() and not ts_a.exists()
        assert not dir_b.exists() and not ts_b.exists()
        assert "RELAY_BG_CLEANUP=deleted 2 sessions" in result.stdout


class TestDuplicates:
    def test_same_short_id_in_both_registries_counted_once(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-dup", "aaaaaa")
        _manifest(home, RUNID, [("impl-dup", "aaaaaa")])
        job_dir, transcript = _full_triple(home, "aaaaaa")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not job_dir.exists()
        assert not transcript.exists()
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result.stdout


class TestManifestNoJobDir:
    def test_missing_job_dir_reported_not_fatal(self, tmp_path):
        home = tmp_path / "home"
        _manifest(home, RUNID, [("impl-a", "aaaaaa"), ("impl-b", "bbbbbb")])
        # A: no job directory at all.
        dir_b, ts_b = _full_triple(home, "bbbbbb")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        skipped = _kv_lines(result.stdout, "RELAY_BG_CLEANUP_SKIPPED")
        assert any("aaaaaa no-job-directory" in s for s in skipped)
        assert not dir_b.exists()
        assert not ts_b.exists()
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result.stdout


class TestLiveSessionStoppedFirst:
    def test_stop_required_then_deletes_after_stop(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-a", "aaaaaa")
        _sidecar(home, RUNID, "reviewer", "impl-b", "bbbbbb")
        dir_a, ts_a = _full_triple(home, "aaaaaa", state="working", age_seconds=1)
        dir_b, ts_b = _full_triple(home, "bbbbbb", state="stopped")

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 1, result.stdout + result.stderr
        required = _kv_lines(result.stdout, "RELAY_BG_STOP_REQUIRED")
        assert any("aaaaaa" in r for r in required)
        assert dir_a.exists() and dir_b.exists()
        assert ts_a.exists() and ts_b.exists()

        # Flip A to stopped, re-run: both get deleted.
        state_path = dir_a / "state.json"
        data = json.loads(state_path.read_text())
        data["state"] = "stopped"
        data["updatedAt"] = _iso(10)
        state_path.write_text(json.dumps(data))

        result2 = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)
        assert result2.returncode == 0, result2.stdout + result2.stderr
        assert not dir_a.exists() and not dir_b.exists()
        assert not ts_a.exists() and not ts_b.exists()


class TestMissingRegistryNotFatal:
    def test_missing_manifest_ok_for_sidecar_only_missing_sidecar_ok_for_manifest_only(
            self, tmp_path):
        home = tmp_path / "home"
        # sidecar-only runid, no manifest file at all.
        _sidecar(home, RUNID, "implementer", "impl-sidecar", "aaaaaa")
        dir_a, ts_a = _full_triple(home, "aaaaaa")
        # a second runid, manifest-only, no sidecar directory at all.
        runid2 = "8e4a2b1c"
        _manifest(home, runid2, [("impl-manifest", "bbbbbb")])
        dir_b, ts_b = _full_triple(home, "bbbbbb")

        result1 = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)
        assert result1.returncode == 0, result1.stdout + result1.stderr
        assert not dir_a.exists() and not ts_a.exists()
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result1.stdout

        result2 = _run(tmp_path, ["--runid", runid2, "--outcome", "clean"], home=home)
        assert result2.returncode == 0, result2.stdout + result2.stderr
        assert not dir_b.exists() and not ts_b.exists()
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result2.stdout


class TestZeroSessions:
    def test_no_registries_recorded_exits_3(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        # Deliberately create neither the sidecar dir nor the manifest file.

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 3, result.stdout + result.stderr
        assert f"no bg session recorded for runid {RUNID} in either registry" \
            in result.stderr
        assert "RELAY_BG_CLEANUP=deleted 0 sessions" in result.stdout


class TestUsageErrors:
    def test_missing_runid(self, tmp_path):
        result = _run(tmp_path, ["--outcome", "clean"])
        assert result.returncode == 2

    def test_runid_too_short(self, tmp_path):
        result = _run(tmp_path, ["--runid", "ab", "--outcome", "clean"])
        assert result.returncode == 2

    def test_runid_all_stripped_characters(self, tmp_path):
        result = _run(tmp_path, ["--runid", "!!!!", "--outcome", "clean"])
        assert result.returncode == 2

    def test_bad_outcome(self, tmp_path):
        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "bogus"])
        assert result.returncode == 2


class TestRunidNormalization:
    def test_wf_prefixed_and_derived_suffix_find_same_registries(self, tmp_path):
        # lower, strip leading wf_, strip non [a-z0-9], keep last 8:
        # "wf_918a4deb-aba" -> "918a4debaba" -> "a4debaba".
        derived = "a4debaba"
        home = tmp_path / "home"
        _sidecar(home, derived, "implementer", "impl-a", "aaaaaa")
        _full_triple(home, "aaaaaa")

        result = _run(tmp_path, ["--runid", "wf_918a4deb-aba", "--outcome", "failed"],
                       home=home)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "RELAY_BG_CLEANUP=kept 1 sessions" in result.stdout

        result2 = _run(tmp_path, ["--runid", derived, "--outcome", "failed"], home=home)
        assert result2.returncode == 0, result2.stdout + result2.stderr
        assert "RELAY_BG_CLEANUP=kept 1 sessions" in result2.stdout


class TestIdempotence:
    def test_second_clean_run_skips_everything(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-a", "aaaaaa")
        _full_triple(home, "aaaaaa")

        result1 = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)
        assert result1.returncode == 0, result1.stdout + result1.stderr
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result1.stdout

        result2 = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)
        assert result2.returncode == 0, result2.stdout + result2.stderr
        skipped = _kv_lines(result2.stdout, "RELAY_BG_CLEANUP_SKIPPED")
        assert any("aaaaaa no-job-directory" in s for s in skipped)
        assert "RELAY_BG_CLEANUP=deleted 0 sessions" in result2.stdout


class TestTranscriptGuard:
    def test_transcript_outside_projects_root_is_skipped(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-a", "aaaaaa")
        job_dir, ts = _job(home, "aaaaaa", transcript_rel="outside.jsonl",
                            transcript_outside=True)

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not job_dir.exists()
        assert ts.exists()
        skipped = _kv_lines(result.stdout, "RELAY_BG_CLEANUP_SKIPPED")
        assert any("aaaaaa no-transcript" in s for s in skipped)
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result.stdout

    def test_transcript_path_is_a_directory_is_skipped(self, tmp_path):
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-a", "aaaaaa")
        job_dir, ts = _job(home, "aaaaaa", transcript_rel="proj/dirlike.jsonl",
                            transcript_is_dir=True)

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not job_dir.exists()
        assert ts.exists()
        skipped = _kv_lines(result.stdout, "RELAY_BG_CLEANUP_SKIPPED")
        assert any("aaaaaa no-transcript" in s for s in skipped)
        assert "RELAY_BG_CLEANUP=deleted 1 sessions" in result.stdout

    def test_link_with_dot_dot_segment_is_rejected(self, tmp_path):
        # `$HOME/.claude/projects/../../etc/passwd.jsonl` matches the prefix guard
        # but escapes the projects tree. `..` rejection must fire before -f resolves
        # the path; the target file (whether real or not) must never be rm'd.
        home = tmp_path / "home"
        _sidecar(home, RUNID, "implementer", "impl-a", "aaaaaa")
        outside_target = home / "sensitive.jsonl"
        outside_target.write_text("must-not-be-deleted\n")
        traversal = f"{home}/.claude/projects/../sensitive.jsonl"
        job_dir, _ = _job(home, "aaaaaa", transcript_rel="proj/placeholder.jsonl")
        state_path = job_dir / "state.json"
        data = json.loads(state_path.read_text())
        data["linkScanPath"] = traversal
        state_path.write_text(json.dumps(data))

        result = _run(tmp_path, ["--runid", RUNID, "--outcome", "clean"], home=home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert outside_target.exists(), "traversal target must never be deleted"
        skipped = _kv_lines(result.stdout, "RELAY_BG_CLEANUP_SKIPPED")
        assert any("aaaaaa no-transcript (unsafe-path)" in s for s in skipped), skipped
