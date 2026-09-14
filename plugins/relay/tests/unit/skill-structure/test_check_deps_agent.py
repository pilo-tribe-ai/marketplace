import json
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "check-deps.sh"


def _run(args, env_extra=None):
    import os
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", str(SCRIPT), *args],
                          capture_output=True, text=True, env=env)


class TestCheckDepsExecuted:
    def test_codex_set_only_for_agent_codex(self):
        r = _run(["--agent", "codex", "--format", "json"])
        matrix = json.loads(r.stdout)
        assert set(matrix.keys()) == {"codex"}

    def test_hybrid_probes_both_sets(self):
        r = _run(["--agent", "hybrid", "--format", "json"])
        matrix = json.loads(r.stdout)
        assert set(matrix.keys()) == {"claude", "codex"}

    def test_claude_set_for_agent_claude_and_opencode(self):
        for agent in ("claude", "opencode"):
            r = _run(["--agent", agent, "--format", "json"])
            assert set(json.loads(r.stdout).keys()) == {"claude"}

    def test_matrix_values_are_ok_or_missing(self):
        r = _run(["--agent", "codex", "--format", "json"])
        matrix = json.loads(r.stdout)
        for skill, state in matrix["codex"].items():
            assert state in ("ok", "missing")
        # the codex set is the manifest's full skill list
        assert "brainstorming" in matrix["codex"]
        assert "engineering" in matrix["codex"]


class TestCheckDepsSourced:
    def test_sourced_mode_emits_no_stdout(self):
        # The sourced path is the primary use path (every command does `source check-deps.sh || exit 1`).
        # It MUST stay silent on stdout — any leak would corrupt the parent command's output.
        import os
        env = dict(os.environ)
        env["RELAY_AGENT"] = "codex"
        r = subprocess.run(
            ["bash", "-c", f'source "{SCRIPT}"; rc=$?; echo "__RC__=$rc"'],
            capture_output=True, text=True, env=env,
        )
        stray = [l for l in r.stdout.splitlines() if not l.startswith("__RC__=")]
        assert stray == [], f"sourced check-deps.sh leaked stdout: {stray}"
        rc_lines = [l for l in r.stdout.splitlines() if l.startswith("__RC__=")]
        assert rc_lines, "sourced check-deps.sh did not return to the caller"
        assert rc_lines[0].split("=", 1)[1].strip() in ("0", "1")
