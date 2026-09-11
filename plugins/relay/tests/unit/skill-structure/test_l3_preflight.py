"""Issue #110: the six L3 command Step 0 bash blocks moved into
scripts/l3-preflight.sh — a session isolated in a git worktree refuses an
inline Bash command that carries `source`, `$(...)`, `case`, or a line
starting `if`, and sourcing check-deps.sh under a non-bash shell (e.g. zsh)
ends the call silently. Drive the real script by subprocess, like
test_verify_loop_node.py and test_worktree_preflight.py do."""

import os
import shutil
import stat
import subprocess

import pytest

from conftest import PLUGIN_ROOT, deps_missing_env, deps_ok_env

SCRIPT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"

# Both env builders live in tests/conftest.py, because every module that drives
# l3-preflight.sh by subprocess must clear the dependency gate the same way.
_deps_ok_env = deps_ok_env
_deps_missing_env = deps_missing_env


def _run(args, cwd, env, extra_env=None):
    e = dict(env)
    if extra_env:
        e.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd), env=e,
    )


def _run_ok(tmp_path, args, extra_env=None):
    """Run against a fresh non-git cwd with a passing dependency gate."""
    cwd = tmp_path / "cwd"
    cwd.mkdir(exist_ok=True)
    return _run(args, cwd=cwd, env=_deps_ok_env(tmp_path), extra_env=extra_env)


def _kv(stdout):
    out = {}
    for line in stdout.splitlines():
        if "=" in line and not line.startswith("[relay]"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


class TestScriptHygiene:
    def test_file_exists_and_is_executable(self):
        assert SCRIPT.is_file()
        assert os.access(SCRIPT, os.X_OK)
        mode = stat.S_IMODE(SCRIPT.stat().st_mode)
        assert mode & stat.S_IXUSR

    def test_bash_n_is_clean(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


class TestUsage:
    def test_no_argument_exits_2_with_usage_on_stderr(self, tmp_path):
        r = _run_ok(tmp_path, [])
        assert r.returncode == 2
        assert "usage" in r.stderr.lower()

    def test_bogus_command_exits_2(self, tmp_path):
        r = _run_ok(tmp_path, ["bogus"])
        assert r.returncode == 2
        assert "usage" in r.stderr.lower()


class TestDependencyGate:
    def test_implement_blocks_without_superpowers(self, tmp_path):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        r = _run(["implement", ""], cwd=cwd, env=_deps_missing_env(tmp_path))
        assert r.returncode == 1
        assert "BLOCKING" in r.stderr

    def test_diagnose_runs_no_gate(self, tmp_path):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        r = _run(["diagnose", ""], cwd=cwd, env=_deps_missing_env(tmp_path))
        assert r.returncode == 0, r.stdout + r.stderr


class TestImplement:
    def test_no_flags_defaults(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", ""])
        assert r.returncode == 0, r.stdout + r.stderr
        lines = [l for l in r.stdout.splitlines() if l.startswith("[relay]")]
        assert len(lines) == 4
        assert "[relay] implement: verify-loop enabled=0 round-cap=n/a" in lines
        # 4.47.0: implement's default layer moved off in-session onto acpx+claude.
        assert "[relay] dispatch axis: engine=acpx agent=claude (source: default)" in lines
        assert (
            "[relay] model overrides: fixes=<per-role pin> verification=<per-role pin> "
            "(fixes=presets verification=presets)" in lines
        )
        assert "[relay] retro: enabled=0 target=<this run>" in lines
        d = _kv(r.stdout)
        assert d["RELAY_VERIFY"] == "0"
        assert d["RELAY_FIXES_MODEL"] == ""
        assert d["RELAY_VERIFICATION_MODEL"] == ""

    def test_fixes_model_flag_is_read_and_exported(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--fixes-model sonnet"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_FIXES_MODEL"] == "sonnet"
        assert "fixes=sonnet" in r.stdout

    def test_verification_model_flag_is_read_and_exported(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--verification-model opus"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_VERIFICATION_MODEL"] == "opus"
        assert "verification=opus" in r.stdout

    def test_bogus_model_flag_exits_1_with_parser_message(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--fixes-model bogus"])
        assert r.returncode == 1
        assert "invalid fixes-model" in r.stderr

    def test_verify_flag_enables_loop_default_cap(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--verify"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert "enabled=1 round-cap=3" in r.stdout
        assert d["RELAY_VERIFY"] == "1"
        assert d["RELAY_VERIFY_ROUNDS"] == "3"

    def test_verify_with_rounds_5(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--verify --rounds 5"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "round-cap=5" in r.stdout

    def test_verify_with_rounds_7_is_out_of_range(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--verify --rounds 7"])
        assert r.returncode == 1
        assert "implement: --rounds takes an integer from 1 to 5 (got: 7)" in r.stdout

    def test_rounds_without_verify_is_an_error(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--rounds 3"])
        assert r.returncode == 1
        assert "Add --verify, or drop --rounds." in r.stdout

    def test_env_rounds_out_of_range_is_never_clamped(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--verify"], extra_env={"RELAY_VERIFY_ROUNDS": "9"})
        assert r.returncode == 1

    def test_engine_acpx_resolves_hybrid_agent_from_flags(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--engine acpx"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "engine=acpx agent=hybrid (source: flags)" in r.stdout

    def test_bogus_engine_exits_1_with_parser_message(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--engine bogus"])
        assert r.returncode == 1
        assert "invalid engine" in r.stderr

    def test_retro_with_run_id(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--retro wf_ab12"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_RETRO"] == "1"
        assert d["RELAY_RETRO_TARGET"] == "wf_ab12"

    def test_retro_with_task_text_has_no_target(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--retro add a login form"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_RETRO"] == "1"
        assert d["RELAY_RETRO_TARGET"] == ""

    def test_retro_bare_last(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--retro last"])
        d = _kv(r.stdout)
        assert d["RELAY_RETRO_TARGET"] == "last"

    def test_retro_last_with_trailing_text_is_not_a_target(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--retro last night's regression"])
        d = _kv(r.stdout)
        assert d["RELAY_RETRO_TARGET"] == ""

    def test_relay_lines_print_before_key_block(self, tmp_path):
        r = _run_ok(tmp_path, ["implement", "--verify"])
        lines = r.stdout.splitlines()
        relay_idxs = [i for i, l in enumerate(lines) if l.startswith("[relay]")]
        key_idxs = [i for i, l in enumerate(lines) if "=" in l and not l.startswith("[relay]")]
        assert max(relay_idxs) < min(key_idxs)


class TestVerify:
    def test_round_cap_line_text(self, tmp_path):
        r = _run_ok(tmp_path, ["verify", ""])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "[relay] verify: round cap = 3" in r.stdout
        # 4.47.0: verify's default layer moved off in-session onto acpx+claude.
        d = _kv(r.stdout)
        assert d["RELAY_VERIFY_ENGINE"] == "acpx"

    def test_engine_acpx_accepted(self, tmp_path):
        r = _run_ok(tmp_path, ["verify", "--engine acpx"])
        assert r.returncode == 0, r.stdout + r.stderr

    @pytest.mark.parametrize("engine", ["bg-sessions", "smart-routing", "session-tree"])
    def test_unsupported_engines_rejected(self, tmp_path, engine):
        r = _run_ok(tmp_path, ["verify", f"--engine {engine}"])
        assert r.returncode == 1
        assert "is not supported by /relay:verify" in r.stderr

    def test_bad_rounds_message_says_verify(self, tmp_path):
        r = _run_ok(tmp_path, ["verify", "--rounds 9"])
        assert r.returncode == 1
        assert "verify: --rounds takes an integer from 1 to 5 (got: 9)" in r.stdout


class TestRefine:
    def test_axis_line_then_retro_line(self, tmp_path):
        r = _run_ok(tmp_path, ["refine", "--retro wf_ab12"])
        assert r.returncode == 0, r.stdout + r.stderr
        lines = [l for l in r.stdout.splitlines() if l.startswith("[relay]")]
        # 4.48.0: the model-overrides line now sits between the axis line and
        # the retro line for the four flag-accepting commands.
        assert lines[0].startswith("[relay] dispatch axis:")
        assert lines[1].startswith("[relay] model overrides:")
        assert lines[2].startswith("[relay] retro:")

    def test_session_tree_rejected(self, tmp_path):
        r = _run_ok(tmp_path, ["refine", "--engine session-tree"])
        assert r.returncode == 1
        assert "/relay:refine" in r.stderr


class TestExecute:
    def test_axis_line_then_retro_line(self, tmp_path):
        r = _run_ok(tmp_path, ["execute", "--retro wf_ab12"])
        assert r.returncode == 0, r.stdout + r.stderr
        lines = [l for l in r.stdout.splitlines() if l.startswith("[relay]")]
        # 4.48.0: the model-overrides line now sits between the axis line and
        # the retro line for the four flag-accepting commands.
        assert lines[0].startswith("[relay] dispatch axis:")
        assert lines[1].startswith("[relay] model overrides:")
        assert lines[2].startswith("[relay] retro:")

    def test_session_tree_rejected(self, tmp_path):
        r = _run_ok(tmp_path, ["execute", "--engine session-tree"])
        assert r.returncode == 1
        assert "/relay:execute" in r.stderr


class TestDrive:
    def test_axis_line_carries_resume_0(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "oracle.md"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "resume=0" in r.stdout

    def test_resume_flag_gives_resume_1(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "--resume oracle.md"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "resume=1" in r.stdout
        d = _kv(r.stdout)
        assert d["RELAY_DRIVE_RESUME"] == "1"

    def test_oracle_path_survives(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "oracle.md"])
        d = _kv(r.stdout)
        assert d["RELAY_DRIVE_ORACLE"] == "oracle.md"

    def test_engine_flag_is_stripped_and_oracle_survives(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "--engine acpx oracle.md"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_DRIVE_ORACLE"] == "oracle.md"

    def test_fixes_model_flag_is_stripped_and_oracle_survives(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "--fixes-model sonnet oracle.md"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_DRIVE_ORACLE"] == "oracle.md"
        assert d["RELAY_FIXES_MODEL"] == "sonnet"

    def test_resumed_is_not_stripped_as_resume(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "--resumed oracle.md"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert "--resumed" in d["RELAY_DRIVE_ORACLE"]

    def test_no_oracle_and_no_retro_is_an_error(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", ""])
        assert r.returncode == 1
        assert "drive: <oracle-file> is required" in r.stdout

    def test_retro_last_alone_needs_no_oracle(self, tmp_path):
        r = _run_ok(tmp_path, ["drive", "--retro last"])
        assert r.returncode == 0, r.stdout + r.stderr


class TestDiagnose:
    def test_prints_exactly_the_retro_line_and_keys(self, tmp_path):
        r = _run_ok(tmp_path, ["diagnose", "--retro wf_ab12"])
        assert r.returncode == 0, r.stdout + r.stderr
        relay_lines = [l for l in r.stdout.splitlines() if l.startswith("[relay]")]
        assert relay_lines == ["[relay] retro: enabled=1 target=wf_ab12"]
        d = _kv(r.stdout)
        assert d["RELAY_RETRO"] == "1"
        assert d["RELAY_RETRO_TARGET"] == "wf_ab12"
        assert "RELAY_ENGINE" not in d


class TestAxisOnly:
    def test_prints_axis_line_with_given_source(self, tmp_path):
        r = _run_ok(tmp_path, ["--axis-only", "acpx", "hybrid", "--source", "prompt"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "[relay] dispatch axis: engine=acpx agent=hybrid (source: prompt)" in r.stdout
        d = _kv(r.stdout)
        assert d["RELAY_AXIS_SOURCE"] == "prompt"

    def test_invalid_pair_exits_1_with_parser_message(self, tmp_path):
        r = _run_ok(tmp_path, ["--axis-only", "in-session", "codex"])
        assert r.returncode == 1
        assert "requires agent=claude" in r.stderr

    def test_missing_source_defaults_to_prompt(self, tmp_path):
        r = _run_ok(tmp_path, ["--axis-only", "bg-sessions", "claude"])
        assert r.returncode == 0, r.stdout + r.stderr
        d = _kv(r.stdout)
        assert d["RELAY_AXIS_SOURCE"] == "prompt"


class TestShellSafety:
    """§1.1/§1.2 of the fix plan: `set -e` would end the script silently on a
    false `--verify`/`--retro` probe, and `set -o pipefail` would promote a
    `grep -q`-induced SIGPIPE into a false-negative flag read. Neither may run
    as an active statement; both must be named in the reasoning comment."""

    def _active_lines(self, text):
        return [
            line.strip()
            for line in text.splitlines()
            if not line.strip().startswith("#")
        ]

    def test_no_active_set_dash_e(self):
        active = self._active_lines(SCRIPT.read_text())
        assert not any(line == "set -e" or line.startswith("set -e ") or line.startswith("set -e;") for line in active)

    def test_no_active_pipefail(self):
        active = self._active_lines(SCRIPT.read_text())
        assert not any("pipefail" in line for line in active)

    def test_the_reasons_are_documented_in_comments(self):
        text = SCRIPT.read_text()
        assert "set -e" in text  # named in a comment explaining why it is absent
        assert "pipefail" in text  # named in a comment explaining why it is absent
