# plugins/relay/tests/integration/contracts.py
"""Black-box assertion helpers over the captured transcript and sandbox git state.
Pure and importable — no pytest fixtures, so the unit self-tests can load it by path."""
import json
import os
import re
import subprocess
from pathlib import Path


def iter_events(stream_path):
    with open(stream_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def result_event(stream_path):
    last = None
    for ev in iter_events(stream_path):
        if ev.get("type") == "result":
            last = ev
    return last


def result_text(stream_path):
    ev = result_event(stream_path)
    return "" if ev is None else (ev.get("result") or "")


def transcript_text(stream_path):
    """Every event serialized and concatenated — so any contract line (tool inputs,
    assistant text, final result) is substring-searchable in one string."""
    return "\n".join(json.dumps(ev) for ev in iter_events(stream_path))


def bash_commands(stream_path):
    cmds = []
    for ev in iter_events(stream_path):
        msg = ev.get("message") or {}
        for block in (msg.get("content") or []):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
                cmd = (block.get("input") or {}).get("command")
                if cmd:
                    cmds.append(cmd)
    return cmds


def assert_plugin_provenance(stream_path, plugin_dir):
    """Spec §10. The Step-0 l3-preflight.sh invocation must carry the --plugin-dir
    prefix exactly; any other prefix means an installed copy loaded."""
    marker = "scripts/l3-preflight.sh"
    expected = f"{plugin_dir}/scripts/l3-preflight.sh"
    hits = [c for c in bash_commands(stream_path) if marker in c]
    assert hits, f"no Step-0 {marker} invocation found in the transcript"
    bad = [c for c in hits if expected not in c]
    assert not bad, (
        f"Step-0 preflight ran from a path that is not {plugin_dir} "
        f"(installed copy?); offending command: {bad[0]!r}"
    )


def git(sandbox, *args):
    return subprocess.run(["git", "-C", str(sandbox), *args],
                          capture_output=True, text=True, check=True).stdout


def current_head(sandbox):
    return git(sandbox, "rev-parse", "HEAD").strip()


def current_branch(sandbox):
    return git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip()


def is_detached(sandbox):
    return current_branch(sandbox) == "HEAD"


def commits_ahead(sandbox, base="main"):
    return int(git(sandbox, "rev-list", "--count", f"{base}..HEAD").strip())


def working_tree_clean(sandbox):
    return git(sandbox, "status", "--porcelain").strip() == ""


def assert_refusal(stream_path, message):
    text = transcript_text(stream_path)
    assert message in text, f"expected refusal message not found: {message!r}"


def assert_no_new_commit(sandbox, baseline_sha):
    assert current_head(sandbox) == baseline_sha, "expected no new commit, but HEAD moved"


def verify_state_root(sandbox):
    """The loop's state root (verify-loop-node.sh: STATE_ROOT="$git_dir/relay-verify")."""
    git_dir = git(sandbox, "rev-parse", "--git-dir").strip()
    gp = Path(git_dir) if os.path.isabs(git_dir) else Path(sandbox) / git_dir
    return gp / "relay-verify"


def _verify_result_hits(stream_path):
    """Every RELAY_VERIFY_RESULT= verdict token in the transcript, in order."""
    return re.findall(r"RELAY_VERIFY_RESULT=([A-Za-z0-9_-]+)", transcript_text(stream_path))


def verify_verdict(stream_path):
    hits = _verify_result_hits(stream_path)
    assert hits, "no RELAY_VERIFY_RESULT= line in the transcript"
    return hits[-1]


def assert_round_records(state_root, round_no=1, keys=("SIMPLIFY", "REVIEW", "CHECK")):
    rec = Path(state_root) / f"round-{round_no}" / "record"
    assert rec.exists(), f"missing round record: {rec}"
    body = rec.read_text()
    for k in keys:
        assert re.search(rf"^{k}=", body, re.M), f"round-{round_no} record missing {k}= key"


def assert_verify_refusal(sandbox, stream_path, baseline_sha, rc=0):
    """documented-refusal (spec §7): no state root, no new commit, and a positive refusal
    signal. A silent no-op — an acpx dispatch failure on a not-logged-in machine, a crash,
    or a wall-clock killpg — makes no commit and no state root too, so those three
    conditions alone would score a total no-op green; require a real signal so they do
    not. A missing RELAY_VERIFY_RESULT line is tolerated only on a clean exit whose final
    result still carries the child's refusal reasoning. [inferred]"""
    root = verify_state_root(sandbox)
    assert not root.exists(), f"refusal row unexpectedly created a state root: {root}"
    assert current_head(sandbox) == baseline_sha, "refusal row made a commit"
    hits = _verify_result_hits(stream_path)  # [inferred]
    if hits:  # [inferred]
        assert hits[-1] == "unverified", "refusal row did not report unverified"  # [inferred]
        return  # [inferred]
    # No verdict line: the spec allows a bare/no-loop run to print no RELAY_VERIFY_RESULT
    # (running-implement-spine/SKILL.md), but only a clean exit with a non-empty final
    # result is a documented refusal; a non-zero exit or an empty transcript is a silent
    # no-op (the exact consent-gate fallback wording is calibration C4). [inferred]
    assert rc == 0, f"refusal row printed no verdict line and exited rc={rc} — silent no-op, not a documented refusal"  # [inferred]
    assert result_text(stream_path).strip(), "refusal row printed no verdict line and no final result reasoning"  # [inferred]


def _decoded_text(stream_path):
    """Every string leaf across every event, decoded and concatenated. Unlike
    transcript_text (which json.dumps each event and so escapes inner quotes), this
    leaves an embedded fenced block like {"status": "ok", ...} literally searchable,
    whether it lands in the final .result or an earlier assistant/tool message."""
    parts = []

    def walk(node):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for ev in iter_events(stream_path):
        walk(ev)
    return "\n".join(parts)


def assert_implement_spine_ok(stream_path):
    """Completion (spec §6.2): the spine's final fenced block {"status": "ok", ...}
    appears in the transcript (searched, not required to be the last message)."""
    text = _decoded_text(stream_path)
    assert re.search(r'"status"\s*:\s*"ok"', text), \
        'spine final block {"status": "ok", ...} not found in the transcript'


def assert_deliverable_linecount(sandbox, workdir):
    """Correctness: scripts/linecount.py prints the count of non-empty lines of argv[1]."""
    script = Path(sandbox) / "scripts" / "linecount.py"
    assert script.exists(), f"missing deliverable: {script}"
    fixture = Path(workdir) / "linecount-fixture.txt"
    fixture.write_text("a\n\nb\nc\n\n")          # 3 non-empty lines
    out = subprocess.run(["python3", str(script), str(fixture)],
                         capture_output=True, text=True, check=True)
    got = out.stdout.strip()
    assert got == "3", f"linecount.py printed {got!r}, expected '3'"


def assert_toy_tests_pass(sandbox):
    r = subprocess.run(["python3", "-m", "pytest", "-q"],
                       cwd=str(sandbox), capture_output=True, text=True)
    assert r.returncode == 0, f"toy test suite failed:\n{r.stdout}\n{r.stderr}"
