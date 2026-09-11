# plugins/relay/tests/integration/test_gates.py
"""gates tier (spec §6.1): one short claude -p session per deterministic relay
contract. Cheap, first. Each case reads git state, the transcript, and the result."""
import os

import pytest

import contracts

pytestmark = pytest.mark.integration


@pytest.fixture
def plugin_dir():
    # PLUGIN_DIR lives in conftest; expose it through the rootdir layout.
    # test_gates.py is at plugins/relay/tests/integration/, so parents[2] is
    # plugins/relay — the same value conftest passes as --plugin-dir. [inferred]
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def test_verify_refuses_main(make_sandbox, relay_session):
    sb = make_sandbox(start_on="main", row_id="verify-refuses-main")
    base = contracts.current_head(sb)
    r = relay_session("/relay:verify --engine in-session", sandbox=sb,
                      tier="gates", row_id="verify-refuses-main")
    contracts.assert_refusal(r.stream_path, "refusing to run on the default branch")
    contracts.assert_no_new_commit(sb, base)


def test_verify_refuses_detached_head(make_sandbox, relay_session):
    sb = make_sandbox(start_on="detached", row_id="verify-refuses-detached")
    base = contracts.current_head(sb)
    r = relay_session("/relay:verify --engine in-session", sandbox=sb,
                      tier="gates", row_id="verify-refuses-detached")
    contracts.assert_refusal(r.stream_path, "refusing to run on a detached HEAD")
    contracts.assert_no_new_commit(sb, base)


def test_unsupported_engine(make_sandbox, relay_session):
    sb = make_sandbox(row_id="unsupported-engine")
    r = relay_session("/relay:verify --engine bg-sessions", sandbox=sb,
                      tier="gates", row_id="unsupported-engine")
    contracts.assert_refusal(
        r.stream_path, "is not supported by /relay:verify (supported: in-session | acpx)")


def test_rounds_out_of_range(make_sandbox, relay_session):
    sb = make_sandbox(row_id="rounds-out-of-range")
    r = relay_session("/relay:verify --rounds 9 --engine in-session", sandbox=sb,
                      tier="gates", row_id="rounds-out-of-range")
    contracts.assert_refusal(r.stream_path, "--rounds takes an integer from 1 to 5")


def test_floor_gate(make_sandbox, relay_session, tmp_path):
    # A fake acpx reporting below the floor, first on PATH. The acpx engine triggers
    # l3-preflight's floor gate — a more reliable trigger than /relay:setup. [inferred]
    sb = make_sandbox(row_id="floor-gate")
    shim = tmp_path / "bin"
    shim.mkdir()
    acpx = shim / "acpx"
    acpx.write_text("#!/bin/sh\necho 'acpx 0.12.0'\n")
    acpx.chmod(0o755)
    env = {"PATH": f"{shim}:{os.environ['PATH']}"}
    r = relay_session("/relay:verify --engine acpx", sandbox=sb, tier="gates",
                      extra_env=env, row_id="floor-gate")
    contracts.assert_refusal(r.stream_path, "below the floor 0.13.2")
    contracts.assert_refusal(r.stream_path, "npm install -g acpx@latest")


def test_preflight_provenance(make_sandbox, relay_session, plugin_dir):
    sb = make_sandbox(row_id="preflight-provenance")
    r = relay_session("/relay:verify --engine in-session", sandbox=sb,
                      tier="gates", row_id="preflight-provenance")
    contracts.assert_plugin_provenance(r.stream_path, str(plugin_dir))
