# plugins/relay/tests/unit/integration-harness/test_makefile.py
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def _make(args):
    return subprocess.run(["make", *args], cwd=str(PLUGIN_ROOT),
                          capture_output=True, text=True)


def test_itest_requires_a_tier():
    r = _make(["itest"])
    assert r.returncode == 2, r.stdout + r.stderr
    assert "TIER is required" in (r.stdout + r.stderr)


def test_gates_dry_run_builds_the_pytest_line():
    r = _make(["-n", "itest", "TIER=gates"])
    out = r.stdout
    assert "RELAY_ITEST=1" in out
    assert "-m integration" in out
    assert "tests/integration/test_gates.py" in out


def test_all_dry_run_orders_gates_acpx_e2e():
    out = _make(["-n", "itest", "TIER=all"]).stdout
    g = out.index("test_gates.py")
    a = out.index("test_acpx_live.py")
    e = out.index("test_e2e.py")
    assert g < a < e, out


def test_single_row_options_are_forwarded():
    out = _make(["-n", "itest", "TIER=e2e", "CMD=implement", "ENGINE=acpx",
                 "AGENT=claude", "ROUNDS=2", "KEEP=1"]).stdout
    for frag in ["--relay-cmd implement", "--relay-engine acpx",
                 "--relay-agent claude", "--relay-rounds 2", "--relay-keep"]:
        assert frag in out, f"missing {frag!r} in:\n{out}"
