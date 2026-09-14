# plugins/relay/tests/unit/integration-harness/test_contracts_transcript.py
import json

import pytest


def _write_stream(tmp_path, events):
    p = tmp_path / "stream.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return p


def _bash_event(command):
    return {"type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Bash",
                                     "input": {"command": command}}]}}


def test_result_text_reads_final_result(itest_contracts, tmp_path):
    s = _write_stream(tmp_path, [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}},
        {"type": "result", "result": "all done", "total_cost_usd": 0.01},
    ])
    assert itest_contracts.result_text(s) == "all done"


def test_transcript_text_includes_tool_inputs(itest_contracts, tmp_path):
    s = _write_stream(tmp_path, [_bash_event("echo RELAY_VERIFY_RESULT=clean")])
    assert "RELAY_VERIFY_RESULT=clean" in itest_contracts.transcript_text(s)


def test_provenance_passes_when_preflight_ran_from_plugin_dir(itest_contracts, tmp_path):
    pd = "/wt/plugins/relay"
    s = _write_stream(tmp_path, [_bash_event(f'bash "{pd}/scripts/l3-preflight.sh" verify ""')])
    itest_contracts.assert_plugin_provenance(s, pd)     # no raise


def test_provenance_fails_on_installed_copy_prefix(itest_contracts, tmp_path):
    s = _write_stream(tmp_path, [
        _bash_event('bash "/Users/x/.claude/plugins/relay-local/scripts/l3-preflight.sh" verify ""')])
    with pytest.raises(AssertionError):
        itest_contracts.assert_plugin_provenance(s, "/wt/plugins/relay")


def test_provenance_fails_when_preflight_never_ran(itest_contracts, tmp_path):
    s = _write_stream(tmp_path, [_bash_event("echo hi")])
    with pytest.raises(AssertionError):
        itest_contracts.assert_plugin_provenance(s, "/wt/plugins/relay")
