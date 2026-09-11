"""Unit tests for scripts/bg-launch.sh (bg dispatch contract §1.3, S4-3, launch traps
1 and 2 — docs/bg-dispatch-contract.md).

Everything here is SYNTHETIC. `HOME` and `RELAY_BG_JOBS_DIR` are pointed at `tmp_path`,
and a stub `claude` executable is put first on `PATH`, so no real background session is
ever launched.
"""

import json
import os
import stat
import subprocess
import time

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bg-launch.sh"
VALID_NAME = "roi-dashboard-implementer-feature-a-7f3c"


def _stub_claude(tmp_path, body):
    """Write an executable `claude` stub. `body` is the script content after the
    shebang line. Returns the bin directory to prepend to PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "claude"
    stub.write_text("#!/usr/bin/env bash\n" + body)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def _argv_capturing_stub(tmp_path, short_id="60b3cbb8"):
    """A stub that records its own argv to argv.txt and reports a short id."""
    argv_file = tmp_path / "argv.txt"
    body = (
        f'printf \'%s\\n\' "$@" > "{argv_file}"\n'
        f'echo "Started background session (short id: {short_id})"\n'
    )
    bindir = _stub_claude(tmp_path, body)
    return bindir, argv_file


def _write_state(home, short_id, state="working", intent="do the thing"):
    job_dir = home / ".claude" / "jobs" / short_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "state.json").write_text(
        json.dumps({"state": state, "intent": intent,
                    "updatedAt": "2026-08-18T12:00:00.000Z"})
    )


def _run(tmp_path, args, bindir=None, env_extra=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    if bindir is not None:
        env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(home)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                           text=True, env=env), home


def _prompt_file(tmp_path, text="Your name is p. Your parent is q.\n"):
    p = tmp_path / "prompt.txt"
    p.write_text(text)
    return p


def _launch_args(tmp_path, name=VALID_NAME, model="sonnet",
                  mode="bypassPermissions", prompt_file=None):
    if prompt_file is None:
        prompt_file = _prompt_file(tmp_path)
    return ["--name", name, "--model", model, "--permission-mode", mode,
            "--prompt-file", str(prompt_file)]


class TestScriptShape:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.is_file(), "scripts/bg-launch.sh is missing"
        assert os.access(SCRIPT, os.X_OK), "scripts/bg-launch.sh is not executable"

    def test_header_declares_executed_and_gives_an_example(self):
        text = SCRIPT.read_text()
        assert "EXECUTED" in text
        assert "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/bg-launch.sh\" --name" in text

    def test_no_variadic_flag_precedes_the_prompt(self):
        """--allowedTools must never appear in this script's body (launch trap 1)."""
        text = SCRIPT.read_text()
        assert "--allowedTools" not in text


class TestUsageErrors:
    REQUIRED_FLAGS = ["--name", "--model", "--permission-mode", "--prompt-file"]

    def _all_args(self, tmp_path):
        return _launch_args(tmp_path)

    def test_missing_required_flag_exits_2(self, tmp_path):
        for missing in self.REQUIRED_FLAGS:
            args = self._all_args(tmp_path)
            # Drop the flag and its value.
            idx = args.index(missing)
            trimmed = args[:idx] + args[idx + 2:]
            result, _ = _run(tmp_path, trimmed)
            assert result.returncode == 2, f"missing {missing} should exit 2: {result.stderr}"
            assert result.stderr.startswith("[relay] error: "), result.stderr

    def test_unknown_flag_exits_2(self, tmp_path):
        result, _ = _run(tmp_path, ["--bogus", "x"])
        assert result.returncode == 2
        assert result.stderr.startswith("[relay] error: ")

    def test_unreadable_prompt_file_exits_2(self, tmp_path):
        args = _launch_args(tmp_path, prompt_file=tmp_path / "does-not-exist.txt")
        result, _ = _run(tmp_path, args)
        assert result.returncode == 2
        assert result.stderr.startswith("[relay] error: ")

    def test_dontask_permission_mode_is_refused(self, tmp_path):
        args = _launch_args(tmp_path, mode="dontAsk")
        result, _ = _run(tmp_path, args)
        assert result.returncode == 2
        assert "S3-1" in result.stderr
        assert "dontAsk" in result.stderr


class TestLaunchConstruction:
    def test_prompt_is_the_last_argument(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        bindir, argv_file = _argv_capturing_stub(tmp_path)
        _write_state(home, "60b3cbb8")
        prompt = _prompt_file(tmp_path, "the exact prompt body\n")
        args = _launch_args(tmp_path, prompt_file=prompt)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 0, result.stderr
        argv_lines = argv_file.read_text().splitlines()
        assert argv_lines[-1] == "the exact prompt body"

    def test_no_variadic_flag_in_argv(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        bindir, argv_file = _argv_capturing_stub(tmp_path)
        _write_state(home, "60b3cbb8")
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 0, result.stderr
        assert "--allowedTools" not in argv_file.read_text()

    def test_fork_from_adds_resume_and_fork_session(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        bindir, argv_file = _argv_capturing_stub(tmp_path)
        _write_state(home, "60b3cbb8")
        args = _launch_args(tmp_path) + ["--fork-from", "parent-session-id"]
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 0, result.stderr
        argv_lines = argv_file.read_text().splitlines()
        assert "--resume" in argv_lines
        assert argv_lines[argv_lines.index("--resume") + 1] == "parent-session-id"
        assert "--fork-session" in argv_lines
        assert argv_lines[-1] == "Your name is p. Your parent is q."


class TestLaunchOutcomes:
    def test_launch_ok_prints_three_lines_in_order(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        bindir = _stub_claude(tmp_path, 'echo "short id: 60b3cbb8"\n')
        _write_state(home, "60b3cbb8")
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            f"RELAY_BG_NAME={VALID_NAME}",
            "RELAY_BG_SHORT_ID=60b3cbb8",
            "RELAY_BG_LAUNCH=OK",
        ]

    def test_every_stdout_line_is_key_value(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        bindir = _stub_claude(
            tmp_path,
            'echo "short id: 60b3cbb8"\n'
        )
        # Pre-seed the state file so the wait loop resolves immediately.
        _write_state(home, "60b3cbb8")
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 0, result.stderr
        lines = [l for l in result.stdout.splitlines() if l]
        assert lines, "no stdout produced"
        for line in lines:
            assert __import__("re").match(r"^[A-Z][A-Z0-9_]*=.*$", line), line
        assert lines == [
            f"RELAY_BG_NAME={VALID_NAME}",
            "RELAY_BG_SHORT_ID=60b3cbb8",
            "RELAY_BG_LAUNCH=OK",
        ]

    def test_unparseable_short_id_is_launch_denied(self, tmp_path):
        bindir = _stub_claude(tmp_path, 'echo "no id here"\n')
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 1
        assert result.stdout.strip() == "RELAY_BG_LAUNCH=LAUNCH_DENIED"
        assert "OK" not in result.stdout

    def test_classifier_refusal_is_launch_denied(self, tmp_path):
        bindir = _stub_claude(
            tmp_path,
            'echo "Blocked by classifier" >&2\nexit 1\n'
        )
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert result.returncode == 1
        assert result.stdout.strip() == "RELAY_BG_LAUNCH=LAUNCH_DENIED"

    def test_empty_intent_at_ceiling_is_launch_denied(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        bindir = _stub_claude(tmp_path, 'echo "short id: deadbeef"\n')
        _write_state(home, "deadbeef", state="working", intent="")
        args = _launch_args(tmp_path)
        start = time.time()
        result, _ = _run(tmp_path, args, bindir=bindir,
                          env_extra={"RELAY_BG_LAUNCH_TIMEOUT_SECONDS": "1"})
        elapsed = time.time() - start
        assert result.returncode == 1
        assert result.stdout.strip() == "RELAY_BG_LAUNCH=LAUNCH_DENIED"
        assert elapsed < 5

    def test_absent_state_file_is_not_an_immediate_failure(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        # The stub writes the state file itself, after a short delay, simulating a
        # child that takes a moment to report intent.
        bindir = _stub_claude(
            tmp_path,
            'echo "short id: feedface"\n'
            '(sleep 1; mkdir -p "$HOME/.claude/jobs/feedface"; '
            'printf \'{"state":"working","intent":"go"}\' '
            '> "$HOME/.claude/jobs/feedface/state.json") &\n'
        )
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir,
                          env_extra={"RELAY_BG_LAUNCH_TIMEOUT_SECONDS": "10"})
        assert result.returncode == 0, result.stderr

    def test_never_resolves_the_short_id_by_name(self, tmp_path):
        """Two job directories share the `name` field; only the launched short id has
        a non-empty intent. The wrong one must not satisfy the check (S4-3)."""
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        # A stale job dir with the SAME name but a different short id and non-empty
        # intent — if the script ever scanned by name, it would find this one.
        stale = home / ".claude" / "jobs" / "aaaaaaaa"
        stale.mkdir(parents=True)
        (stale / "state.json").write_text(json.dumps({
            "name": VALID_NAME, "state": "working", "intent": "STALE — must be ignored",
        }))
        bindir = _stub_claude(tmp_path, 'echo "short id: bbbbbbbb"\n')
        args = _launch_args(tmp_path)
        start = time.time()
        result, _ = _run(tmp_path, args, bindir=bindir,
                          env_extra={"RELAY_BG_LAUNCH_TIMEOUT_SECONDS": "1"})
        elapsed = time.time() - start
        assert result.returncode == 1, "must not treat the stale same-name job as a match"
        assert elapsed < 5

    def test_reason_goes_to_stderr_not_stdout(self, tmp_path):
        bindir = _stub_claude(tmp_path, 'echo "no id here"\n')
        args = _launch_args(tmp_path)
        result, _ = _run(tmp_path, args, bindir=bindir)
        assert "[relay]" not in result.stdout
