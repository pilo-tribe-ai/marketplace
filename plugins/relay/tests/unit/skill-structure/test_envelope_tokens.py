"""Verbatim-token static gate (spec §5.4).

Each of the four frozen public envelope tokens must appear verbatim in all three
session driver files and in the codex fast-path section of acpx-dispatch.sh.
This file IS the canonical pin — if a token changes here, it was intentionally
updated; if a driver drifts it fails here.
"""
from pathlib import Path
import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DRIVER_DIR = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents"

# The four frozen tokens (spec §5.4 public envelope contract).
FROZEN_TOKENS = [
    "ROLE_DONE",
    "BLOCKED:",
    "NEEDS_DECISION:",
    "^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$",
]

DRIVER_FILES = [
    DRIVER_DIR / "claude-session-driver.sh",
    DRIVER_DIR / "codex-session-driver.sh",
    DRIVER_DIR / "opencode-session-driver.sh",
    DRIVER_DIR / "acpx-dispatch.sh",
]


@pytest.mark.parametrize("driver", [f.name for f in DRIVER_FILES])
@pytest.mark.parametrize("token", FROZEN_TOKENS)
def test_frozen_token_verbatim_in_driver(driver, token):
    driver_path = DRIVER_DIR / driver
    assert driver_path.is_file(), f"{driver} not found"
    body = driver_path.read_text()
    assert token in body, (
        f"Frozen token {token!r} missing from {driver}. "
        "This is the verbatim-token static gate (spec §5.4). "
        "If the token string genuinely changed, update FROZEN_TOKENS in this file."
    )
