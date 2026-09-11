# plugins/relay/tests/integration/test_acpx_live.py
"""acpx tier (spec §6.3): live envelope/driver contract probes. Real acpx, no
claude -p. Minutes and cents, not tens of minutes and dollars."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# test_acpx_live.py is at plugins/relay/tests/integration/, so parents[2] is
# plugins/relay — where skills/ and scripts/ live. [inferred]
SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "dispatching-acpx-agents"
FLOOR = Path(__file__).resolve().parents[2] / "scripts" / "acpx-floor.sh"


def _need_acpx():
    if shutil.which("acpx") is None:
        pytest.skip("acpx not on PATH — acpx-tier precondition unmet")


def test_envelope_first_line_sentinel():
    _need_acpx()
    prompt = "Reply with exactly one line and nothing else: BLOCKED: probe reason"
    proc = subprocess.run(
        ["acpx", "--format", "json", "--json-strict", "--approve-all", "claude", "exec", prompt],
        capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        pytest.skip(f"acpx claude exec unavailable (login?): {proc.stderr[:200]}")
    env = subprocess.run(["bash", str(SKILL_DIR / "acpx-envelope.sh")],
                         input=proc.stdout, capture_output=True, text=True)
    first_line = next((ln for ln in env.stdout.splitlines() if ln.strip()), "")
    assert first_line.startswith("BLOCKED:"), f"envelope first line was {first_line!r}"


def test_session_driver_blocked_roundtrip(tmp_path):
    _need_acpx()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text(
        "<<DO_NOT_LOAD_SKILLS>>\n"
        "Reply with exactly one line and nothing else: BLOCKED: probe\n")
    env = dict(os.environ)
    env.update({
        "ACPX_ENGINE": "claude", "ACPX_MODEL": "opus", "ACPX_CWD": str(tmp_path),
        "ACPX_TIMEOUT": "180", "ACPX_SESSION_NAME": "relay-itest-acpx",
        "ACPX_PROMPT_FILE": str(prompt_file), "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
    })
    proc = subprocess.run(["bash", str(SKILL_DIR / "claude-session-driver.sh")],
                          capture_output=True, text=True, env=env, timeout=300)
    if "acpx sessions ensure failed" in proc.stdout:
        pytest.skip("acpx session could not open (login?)")
    assert "ROLE_RESULT=BLOCKED" in proc.stdout, proc.stdout


def test_floor_script_passes_on_installed_acpx():
    _need_acpx()
    import re
    proc = subprocess.run(["bash", str(FLOOR)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert re.search(r"RELAY_ACPX_VERSION=\d+\.\d+", proc.stdout), proc.stdout
