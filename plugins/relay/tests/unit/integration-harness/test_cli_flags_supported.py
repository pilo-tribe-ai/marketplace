"""The harness flag set must stay valid against the installed claude CLI.

`claude --help` is NOT the oracle. Some options are registered but hidden from the
help text: `--max-turns` is one, and an earlier draft of the harness removed it after
reading its absence from `--help` as proof it does not exist.

The oracle is the parse-time error. The CLI reports the FIRST unknown option and exits
before it starts a session, so probing `<flag> <value> --<sentinel>` costs nothing:
if the error names the sentinel, the probed flag is registered; if it names the probed
flag, that flag is gone and the harness has drifted.
"""

import shutil
import subprocess

import pytest

SENTINEL = "--zzz-relay-itest-not-a-flag"

# Flags the harness child command line carries (spec §4), with a value where the option
# takes one. A value-less flag is probed on its own.
PROBES = [
    ["--plugin-dir", "/tmp"],
    ["--strict-mcp-config"],
    ["--max-budget-usd", "1"],
    ["--max-turns", "1"],
    ["--output-format", "json"],
    ["--permission-mode", "bypassPermissions"],
]


@pytest.mark.parametrize("probe", PROBES, ids=lambda p: p[0])
def test_claude_cli_registers_the_flag(probe):
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not on PATH — flag-support precondition unmet")
    flag = probe[0]
    result = subprocess.run(["claude", *probe, SENTINEL],
                            capture_output=True, text=True, timeout=60)
    message = (result.stderr or "") + (result.stdout or "")
    assert SENTINEL in message, (
        f"expected the CLI to reject the sentinel and accept {flag!r}; it said: {message.strip()!r}"
    )
    assert flag not in message, (
        f"claude CLI no longer registers {flag!r} — the harness flag set has drifted"
    )
