import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def _run(args, env_overrides):
    import os
    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration/test_marker.py", "-m", "integration", "-q", *args],
        cwd=str(PLUGIN_ROOT), capture_output=True, text=True, env=env,
    )


def test_gate_refuses_without_relay_itest():
    r = _run([], {"RELAY_ITEST": ""})
    assert r.returncode != 0
    assert "RELAY_ITEST" in (r.stdout + r.stderr)


def test_gate_allows_with_relay_itest():
    r = _run([], {"RELAY_ITEST": "1"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_options_are_registered():
    r = _run(["--collect-only", "--relay-cmd", "implement", "--relay-engine", "acpx",
              "--relay-agent", "claude", "--relay-rounds", "2", "--relay-keep"],
             {"RELAY_ITEST": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
