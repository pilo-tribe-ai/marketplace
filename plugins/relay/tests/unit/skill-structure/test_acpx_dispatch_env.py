"""Guard tests for the three new acpx-dispatch.sh env vars: RELAY_MAX_TURNS,
ACPX_SESSION_NAME_OVERRIDE, RELAY_ROLE_PATH."""
import os
import shutil
import stat as stat_mod
import subprocess
import textwrap
from pathlib import Path
import pytest

from conftest import PLUGIN_ROOT
SCRIPT = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh"


def _make_fake_driver(tmp_path, exit_code=0):
    """Write a minimal fake driver that exits with exit_code."""
    script = tmp_path / "fake_driver.sh"
    script.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        exit {exit_code}
    """))
    script.chmod(script.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)
    return script

_TOOLING_MISSING = shutil.which("yq") is None or shutil.which("jq") is None
pytestmark = pytest.mark.skipif(
    _TOOLING_MISSING, reason="requires yq and jq on PATH"
)


def run_dispatch(env=None, args=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    cmd = ["bash", str(SCRIPT)]
    if args:
        cmd += args
    return subprocess.run(cmd, capture_output=True, text=True, env=full_env)


class TestRelayMaxTurnsSidecar:
    def test_script_references_relay_max_turns(self):
        body = SCRIPT.read_text()
        assert "RELAY_MAX_TURNS" in body, \
            "acpx-dispatch.sh must reference RELAY_MAX_TURNS for the sidecar"

    def test_sidecar_includes_relay_max_turns(self, tmp_path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_driver = _make_fake_driver(tmp_path)
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "test-max-turns",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
            "RELAY_MAX_TURNS": "5",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, \
            f"dispatch must exit 0; stderr: {result.stderr!r}"
        sidecar = Path.home() / ".acpx" / "sessions" / "test-max-turns-code-reviewer.env"
        assert sidecar.is_file(), \
            f"sidecar must be written at {sidecar}"
        content = sidecar.read_text()
        assert "RELAY_MAX_TURNS" in content, \
            "sidecar must carry RELAY_MAX_TURNS"


class TestAcpxSessionNameOverride:
    def test_script_references_override_var(self):
        body = SCRIPT.read_text()
        assert "ACPX_SESSION_NAME_OVERRIDE" in body, \
            "acpx-dispatch.sh must honor ACPX_SESSION_NAME_OVERRIDE"

    def test_override_takes_precedence_in_sidecar(self, tmp_path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_driver = _make_fake_driver(tmp_path)
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "test-override",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
            "ACPX_SESSION_NAME_OVERRIDE": "fw-myworkflow-designer",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, \
            f"dispatch must exit 0; stderr: {result.stderr!r}"
        # The override session name must govern the sidecar path
        sidecar = Path.home() / ".acpx" / "sessions" / "fw-myworkflow-designer.env"
        assert sidecar.is_file(), \
            f"sidecar must be written under the override session name at {sidecar}"
        content = sidecar.read_text()
        assert "fw-myworkflow-designer" in content, \
            "sidecar ACPX_SESSION_NAME must reflect ACPX_SESSION_NAME_OVERRIDE"


class TestRelayRolePath:
    def test_script_references_relay_role_path(self):
        body = SCRIPT.read_text()
        assert "RELAY_ROLE_PATH" in body, \
            "acpx-dispatch.sh must honor RELAY_ROLE_PATH for external role files"

    def test_missing_relay_role_path_errors_not_falls_back(self, tmp_path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "plan-simulator",
            "ACPX_BINDING_PRESET": "plan-simulator",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "test-relay-role",
            "WORKTREE": str(worktree),
            "RELAY_ROLE_PATH": str(tmp_path / "nonexistent-role.md"),
        }
        result = run_dispatch(env=env)
        assert result.returncode != 0, \
            "RELAY_ROLE_PATH pointing to a nonexistent file must cause a non-zero exit"
        assert "RELAY_ROLE_PATH" in result.stderr or "not found" in result.stderr or "missing" in result.stderr, \
            "error message must reference the RELAY_ROLE_PATH issue"

    def test_valid_relay_role_path_is_used(self, tmp_path):
        """If RELAY_ROLE_PATH is set to a valid file it is used instead of roles/<slug>.md."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        # Copy an existing role file to a custom path to verify the override is accepted
        import shutil
        # post-PR3 §7: plan-simulator lives in roles/ not agents/
        src = PLUGIN_ROOT / "roles" / "plan-simulator.md"
        custom = tmp_path / "custom-role.md"
        shutil.copy(src, custom)
        env = {
            "ACPX_ROLE_SLUG": "plan-simulator",
            "ACPX_BINDING_PRESET": "plan-simulator",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "test-custom-role",
            "WORKTREE": str(worktree),
            "ACPX_FAKE_CHILD_OUTPUT": "ROLE_DONE",
            "RELAY_ROLE_PATH": str(custom),
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, \
            f"valid RELAY_ROLE_PATH must succeed; stderr: {result.stderr!r}"
