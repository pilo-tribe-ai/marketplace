# plugins/relay/tests/unit/integration-harness/test_acpx_structure.py
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]

EXPECTED = [
    "test_envelope_first_line_sentinel",
    "test_session_driver_blocked_roundtrip",
    "test_floor_script_passes_on_installed_acpx",
]


def test_three_acpx_probes_are_collected(collect_integration):
    # -m integration wins over pytest.ini's addopts, so a missing marker on the
    # tier file would deselect every probe and drop these names — this is also the
    # marker guard.
    out = collect_integration("tests/integration/test_acpx_live.py").stdout
    for name in EXPECTED:
        assert name in out, f"{name} not collected:\n{out}"


def test_acpx_file_skips_loudly_without_acpx():
    # Preconditions unmet -> loud skip, never a silent pass. Not covered by
    # collection, so keep the static check.
    body = (PLUGIN_ROOT / "tests" / "integration" / "test_acpx_live.py").read_text()
    assert "pytest.skip" in body
