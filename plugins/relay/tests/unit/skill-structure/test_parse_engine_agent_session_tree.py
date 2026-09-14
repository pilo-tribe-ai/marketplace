"""Pytest-collected behavioral tests for `--engine session-tree` in
scripts/parse-engine-agent.sh (spec §Deliverable 3, Doctrine — "session-tree ⇒ claude,
same shape as bg-sessions ⇒ claude, no codex leg").

tests/unit/skill-structure/test_parse_engine_agent.sh already carries the full
behavioral suite for this script, including a session-tree block, but that suite is
a plain bash script and is explicitly NOT collected by pytest (docs/contributing.md;
tests/conftest.py's own docstring). This file gives the session-tree axis a second,
independent check that DOES run inside the ordinary `pytest tests/ -q` gate, so a
regression here cannot slip through on a day nobody remembers to run the bash suite
by hand.

Every case sources the real script in a clean subshell (`env -i`) rooted at its own
throwaway git repo, mirroring test_parse_engine_agent.sh's own hermeticity rule: the
script locates `.claude/relay.json` via `git rev-parse --git-common-dir`, so a cwd
that is not its own repo could silently pick up an unrelated pin. No claude session
is ever launched — this only sources a bash script.
"""

import os
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh"


def _pinless_repo(tmp_path):
    repo = tmp_path / "pinless"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _source(repo, *positionals, env_extra=None):
    """Source parse-engine-agent.sh with ALL positionals, in a hermetic env -i
    subshell rooted at `repo`. Returns (returncode, stdout, stderr) where stdout
    holds the KEY=VALUE lines the script exports on success."""
    env_prefix = ""
    if env_extra:
        for k, v in env_extra.items():
            env_prefix += f"export {k}={v!r};\n"
    script = (
        f"cd {str(repo)!r}\n"
        f"{env_prefix}"
        f"source {str(SCRIPT)!r} \"$@\"\n"
        'rc=$?\n'
        'printf "RC=%s\\nENGINE=%s\\nAGENT=%s\\nSOURCE=%s\\n" '
        '"$rc" "${RELAY_ENGINE:-}" "${RELAY_AGENT:-}" "${RELAY_AXIS_SOURCE:-}"\n'
    )
    base_env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        ["env", "-i", *[f"{k}={v}" for k, v in base_env.items()],
         "bash", "-c", script, "_", *positionals],
        capture_output=True, text=True,
    )
    return result


def _kv(stdout):
    out = {}
    for line in stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


class TestSessionTreeAccepted:
    def test_session_tree_with_claude_agent_is_accepted(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "session-tree", "claude")
        kv = _kv(result.stdout)
        assert kv["RC"] == "0", result.stderr
        assert kv["ENGINE"] == "session-tree"
        assert kv["AGENT"] == "claude"

    def test_session_tree_with_no_agent_defaults_to_claude(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "session-tree")
        kv = _kv(result.stdout)
        assert kv["RC"] == "0", result.stderr
        assert kv["ENGINE"] == "session-tree"
        assert kv["AGENT"] == "claude"
        assert kv["SOURCE"] == "flags"

    def test_session_tree_is_case_insensitive(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "SESSION-TREE")
        kv = _kv(result.stdout)
        assert kv["RC"] == "0", result.stderr
        assert kv["ENGINE"] == "session-tree"


class TestSessionTreeInvariant:
    def test_session_tree_with_codex_agent_is_rejected(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "session-tree", "codex")
        kv = _kv(result.stdout)
        assert kv.get("RC") != "0"
        assert "engine=session-tree requires agent=claude" in result.stderr
        assert "got 'codex'" in result.stderr

    def test_session_tree_with_hybrid_agent_is_rejected(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "session-tree", "hybrid")
        kv = _kv(result.stdout)
        assert kv.get("RC") != "0"
        assert "engine=session-tree requires agent=claude" in result.stderr

    def test_session_tree_with_opencode_agent_is_rejected(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "session-tree", "opencode")
        kv = _kv(result.stdout)
        assert kv.get("RC") != "0"
        assert "engine=session-tree requires agent=claude" in result.stderr

    def test_session_tree_invariant_matches_bg_sessions_shape(self, tmp_path):
        # spec §Deliverable 3: "session-tree ⇒ claude, same shape as bg-sessions ⇒
        # claude" — the two rejection messages must differ only in the engine name.
        repo = _pinless_repo(tmp_path)
        st = _source(repo, "session-tree", "codex")
        bg = _source(repo, "bg-sessions", "codex")
        st_msg = st.stderr.replace("session-tree", "<engine>")
        bg_msg = bg.stderr.replace("bg-sessions", "<engine>")
        assert st_msg == bg_msg


class TestSessionTreeEnumMembership:
    def test_invalid_engine_error_lists_session_tree(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "bogus")
        assert "session-tree" in result.stderr

    def test_extra_positional_is_still_rejected(self, tmp_path):
        repo = _pinless_repo(tmp_path)
        result = _source(repo, "session-tree", "claude", "extra")
        kv = _kv(result.stdout)
        assert kv.get("RC") != "0"
        assert "too many arguments" in result.stderr


class TestSessionTreePin:
    def test_engine_pin_resolves_to_session_tree(self, tmp_path):
        repo = tmp_path / "pinned"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / ".claude").mkdir()
        (repo / ".claude" / "relay.json").write_text('{"engine": "session-tree"}')
        result = _source(repo)
        kv = _kv(result.stdout)
        assert kv["RC"] == "0", result.stderr
        assert kv["ENGINE"] == "session-tree"
        assert kv["AGENT"] == "claude"
        assert kv["SOURCE"] == "relay.json"

    def test_pinned_engine_plus_flag_codex_still_enforces_the_invariant(self, tmp_path):
        repo = tmp_path / "pinned-clash"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / ".claude").mkdir()
        (repo / ".claude" / "relay.json").write_text('{"engine": "session-tree"}')
        result = _source(repo, "", "codex")
        kv = _kv(result.stdout)
        assert kv.get("RC") != "0"
        assert "engine=session-tree requires agent=claude" in result.stderr
        assert "engine came from .claude/relay.json" in result.stderr
