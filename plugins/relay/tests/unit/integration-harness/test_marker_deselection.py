import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def _collect(extra_args):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration", "--collect-only", "-q", *extra_args],
        cwd=str(PLUGIN_ROOT), capture_output=True, text=True,
    )


def test_integration_is_deselected_by_a_bare_run():
    # addopts = -m "not integration" in pytest.ini must hide the canary.
    out = _collect([])
    assert "test_marker_canary" not in out.stdout, out.stdout


def test_integration_is_collected_under_dash_m_integration():
    # An explicit -m integration comes after addopts and wins.
    out = _collect(["-m", "integration"])
    assert "test_marker_canary" in out.stdout, out.stdout
