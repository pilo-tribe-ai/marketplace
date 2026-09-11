"""Executing tests for acpx-dispatch.sh against the native-agent schema.

These tests run the REAL acpx-dispatch.sh as a subprocess with the shipped
bindings/presets.yaml and real agents/<slug>.md files. They exercise the
native dispatch model (relay.envelope_tokens / bindings roles.<slug>.provides),
NOT the retired fork schema (slug / role-version / input-slots / output-tokens).

The script requires yq (mikefarah v4) and jq on PATH; if either is missing
these tests skip with a clear reason rather than fail.
"""
import json
import os
import shutil
import stat as stat_mod
import subprocess
import textwrap

import pytest

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh"

DRIVER_DIR = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents"
CLAUDE_DRIVER = DRIVER_DIR / "claude-session-driver.sh"
OPENCODE_DRIVER = DRIVER_DIR / "opencode-session-driver.sh"

_TOOLING_MISSING = shutil.which("yq") is None or shutil.which("jq") is None
pytestmark = pytest.mark.skipif(
    _TOOLING_MISSING, reason="acpx-dispatch.sh requires yq (mikefarah v4) and jq on PATH"
)


def run_dispatch(env=None, args=None, cwd=None):
    """Run acpx-dispatch.sh and return the CompletedProcess."""
    full_env = {}
    import os

    full_env.update(os.environ)
    if env:
        full_env.update(env)
    cmd = ["bash", str(SCRIPT)]
    if args:
        cmd += args
    return subprocess.run(
        cmd, capture_output=True, text=True, env=full_env, cwd=cwd
    )


class TestAcpxDispatchNativeSchema:
    """acpx-dispatch.sh must resolve bindings + tokens from the native shape."""

    def test_a_codex_session_role_resolves_and_dispatches(self, tmp_path):
        """codex-session role (implementer) resolves binding + dispatches via fake child.

        Pre-fix: aborts exit 68 (binding .presets lookup) or exit 66 (role-version).
        Post-fix: exit 0, fake child envelope flows through.
        """
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "implementer",
            "ACPX_BINDING_PRESET": "implementer",
            "ACPX_INPUTS_JSON": json.dumps(
                {"task_text": "do the thing", "repo_root": str(worktree)}
            ),
            "ACPX_RUN_ID": "run-a",
            "WORKTREE": str(worktree),
            "ACPX_FAKE_CHILD_OUTPUT": "STATUS=completed\\nFILES_TOUCHED=[\"a.js\"]\\nROLE_DONE",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, (
            f"expected exit 0, got {result.returncode}\nstderr:\n{result.stderr}"
        )
        assert "exit 66" not in result.stderr
        assert "role-version" not in result.stderr
        assert "binding preset not found" not in result.stderr
        # The implementer is a driver-path codex-session role; the fake child
        # envelope should surface ROLE_DONE in stdout.
        assert "ROLE_DONE" in result.stdout

    def test_b_resolves_from_roles_not_presets(self, tmp_path):
        """Binding resolves from .roles.<slug>; a doctored .presets.* file does NOT."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "implementer",
            "ACPX_BINDING_PRESET": "implementer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-b",
            "WORKTREE": str(worktree),
            "ACPX_DRY_RUN": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, (
            f"binding should resolve from .roles; stderr:\n{result.stderr}"
        )
        assert "binding preset not found" not in result.stderr

        # Prove we read .roles (not .presets): a presets-only file fails to resolve.
        doctored = tmp_path / "relay_doctored"
        shutil.copytree(PLUGIN_ROOT, doctored, ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", "node_modules"))
        presets = doctored / "bindings" / "presets.yaml"
        text = presets.read_text()
        text = text.replace("roles:\n", "presets:\n", 1)
        presets.write_text(text)
        doctored_script = doctored / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh"
        env2 = dict(env)
        result2 = subprocess.run(
            ["bash", str(doctored_script)],
            capture_output=True, text=True,
            env={**__import__("os").environ, **env2},
        )
        assert result2.returncode == 68, (
            f"presets-only file must NOT resolve (we read .roles); got rc="
            f"{result2.returncode}\nstderr:\n{result2.stderr}"
        )
        assert "binding preset not found" in result2.stderr

    def test_c_acpx_claude_token_capture_from_provides(self, tmp_path):
        """code-reviewer (acpx-claude) captures tokens from binding .provides via DRIVER_OVERRIDE."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_driver = _make_fake_driver(tmp_path, [
            "ROLE_RESULT=DONE",
            "TURNS_USED=1",
            "REVIEW=ok",
            "ROLE_DONE",
        ])
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-c",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0; stderr:\n{result.stderr}"
        assert "ROLE_DONE" in result.stdout, result.stdout
        assert "REVIEW=ok" in result.stdout, result.stdout

    def test_c_negative_missing_provides_token_fails_verification(self, tmp_path):
        """Driver envelope missing REVIEW → ROLE_DONE appears but REVIEW absent in output."""
        # NOTE: For driver-path dispatches (acpx-claude/opencode), the dispatcher passes
        # driver stdout through unchanged. verification_failed detection for missing provides
        # tokens is now the orchestrator's responsibility (spec §6), not the dispatcher's.
        # TODO (follow-up): add an orchestrator-level test asserting missing-token detection.
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_driver = _make_fake_driver(tmp_path, [
            "ROLE_RESULT=DONE",
            "TURNS_USED=1",
            "ROLE_DONE",
        ])
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-c-neg",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
        }
        result = run_dispatch(env=env)
        assert "REVIEW" not in result.stdout, (
            f"REVIEW must not appear when driver didn't emit it:\n{result.stdout}"
        )

    def test_c_acpx_claude_soft_degrade_set_effort_failure(self, tmp_path):
        """Soft-degrade: a driver that warns on set effort rc=1 still completes a turn."""
        if not CLAUDE_DRIVER.exists():
            pytest.skip("claude-session-driver.sh not yet created")
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_acpx, log_file = make_fake_acpx(tmp_path, set_effort_rc=1)
        prompt = make_prompt_file(tmp_path)
        env = {
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "ACPX_ENGINE": "claude",
            "ACPX_MODEL": "opus",
            "ACPX_CWD": str(worktree),
            "ACPX_TIMEOUT": "60",
            "ACPX_SESSION_NAME": "run-softdegrade",
            "ACPX_PROMPT_FILE": str(prompt),
            "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
            "ACPX_MAX_TURNS": "1",
            "ACPX_NUDGE_PROMPT": "nudge",
            "ACPX_VERIFY_ARTIFACT": "",
            "ACPX_EFFORT": "high",
            "ACPX_PERMISSIONS": "",
        }
        result = subprocess.run(["bash", str(CLAUDE_DRIVER)], env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, (
            f"driver must soft-degrade on set effort rc=1:\nstdout:{result.stdout}\nstderr:{result.stderr}"
        )
        assert "ROLE_RESULT=DONE" in result.stdout, f"turn did not complete:\n{result.stdout}"
        log_path = tmp_path / ".acpx" / "sessions" / "run-softdegrade.driver.log"
        assert log_path.exists(), f"driver log not created at {log_path}; stderr:\n{result.stderr}"
        log_content = log_path.read_text()
        assert "[warn]" in log_content and "effort" in log_content, (
            f"warn log entry missing:\n{log_content}"
        )

    def test_c_acpx_claude_permissions_approve_reads_still_gets_the_wide_grant(self, tmp_path):
        """A role marked approve-reads still receives the full grant (relay 4.51.0).

        This assertion is the inverse of the 4.50.0 one, and the inversion is the
        point. `permissions` used to gate `--approve-all`, so the three roles bound
        to `approve-reads` ran under acpx's default mode, whose non-TTY fallback is
        `deny` — every write request was refused and nothing reported it. The field
        now records role intent only; a read-only role is held read-only by its role
        body and its agent `tools:` frontmatter.
        """
        if not CLAUDE_DRIVER.exists():
            pytest.skip("claude-session-driver.sh not yet created")
        fake_acpx, log_file = make_fake_acpx(tmp_path)
        prompt = make_prompt_file(tmp_path)
        env = {
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "ACPX_ENGINE": "claude",
            "ACPX_MODEL": "opus",
            "ACPX_CWD": str(tmp_path),
            "ACPX_TIMEOUT": "60",
            "ACPX_SESSION_NAME": "run-perms",
            "ACPX_PROMPT_FILE": str(prompt),
            "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
            "ACPX_MAX_TURNS": "1",
            "ACPX_NUDGE_PROMPT": "nudge",
            "ACPX_VERIFY_ARTIFACT": "",
            "ACPX_EFFORT": "high",
            "ACPX_PERMISSIONS": "approve-reads",
        }
        result = subprocess.run(["bash", str(CLAUDE_DRIVER)], env=env,
                                capture_output=True, text=True)
        log_path = tmp_path / ".acpx" / "sessions" / "run-perms.driver.log"
        assert log_path.exists(), f"driver log not created at {log_path}; stderr:\n{result.stderr}"
        calls = log_file.read_text()
        assert "--approve-all" in calls, (
            f"--approve-all must be passed even for an approve-reads role:\n{calls}"
        )
        assert "--permission-policy" in calls, (
            f"--permission-policy must accompany --approve-all:\n{calls}"
        )

    def test_d_slot_substitution_from_inputs(self, tmp_path):
        """A supplied input key substitutes its {{PLACEHOLDER}} in the materialized prompt."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        # code-reviewer body references {{TASK_TEXT}} and {{REPO_ROOT}} etc.
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": json.dumps(
                {"task_text": "SENTINEL_TASK_VALUE", "repo_root": str(worktree)}
            ),
            "ACPX_RUN_ID": "run-d",
            "WORKTREE": str(worktree),
            "ACPX_DRY_RUN": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, result.stderr
        prompt_file = worktree / ".acpx-prompts" / "run-d" / "code-reviewer.md"
        assert prompt_file.is_file(), f"materialized prompt missing: {prompt_file}"
        body = prompt_file.read_text()
        assert "SENTINEL_TASK_VALUE" in body, body
        assert "{{TASK_TEXT}}" not in body, "supplied placeholder left unsubstituted"
        assert "{{REPO_ROOT}}" not in body, "supplied placeholder left unsubstituted"

    def test_e_validate_only_native_agent(self):
        """--validate-only on a kept registered agent exits 0.

        Uses code-reviewer (still in agents/) which carries no 'requires:' field
        so the capability intersection is trivially satisfied (empty-requires ⊆ anything).
        Pre-fix: exit 3 on missing slug. Post-PR3 §7: collapsed roles moved to roles/;
        this test uses a kept registered agent to verify the zero-exit path.
        """
        result = run_dispatch(args=[
            "--validate-only",
            "--role", str(PLUGIN_ROOT / "agents" / "code-reviewer.md"),
            "--binding", "code-reviewer",
        ])
        assert result.returncode == 0, (
            f"expected exit 0; stderr:\n{result.stderr}"
        )

    def test_e_validate_only_unknown_binding_exits_3(self):
        """--validate-only with a nonexistent binding exits 3 (lookup error).
        Post-PR3 §7: using code-reviewer (kept registered agent in agents/)."""
        result = run_dispatch(args=[
            "--validate-only",
            "--role", str(PLUGIN_ROOT / "agents" / "code-reviewer.md"),
            "--binding", "no-such-binding",
        ])
        assert result.returncode == 3, (
            f"expected exit 3; stderr:\n{result.stderr}"
        )

    def test_e_validate_only_role_file_is_not_rejected_by_the_namespace_error(self):
        """--validate-only on a role file (role-class present) must NOT pair its
        capability `requires:` against the binding's envelope-token `provides:`.

        Those are disjoint namespaces, so the set difference is the whole of
        `requires` — pairing them rejected 100% of role dispatches with a
        MISSING_CAPABILITY per capability. Role-file capability satisfaction is
        enforced statically by test_capability_gate.py, not by this runtime
        intersection, which is scoped to legacy native-agent files only.
        """
        result = run_dispatch(args=[
            "--validate-only",
            "--role", str(PLUGIN_ROOT / "roles" / "implementer.md"),
            "--binding", "implementer",
        ])
        assert result.returncode == 0, (
            "--validate-only must not reject a role file by intersecting "
            f"requires against provides; stderr:\n{result.stderr}"
        )
        assert "MISSING_CAPABILITY" not in result.stderr, (
            "requires (capabilities) vs provides (envelope tokens) is a namespace "
            f"error — no capability should read as missing:\n{result.stderr}"
        )

    def test_task1_no_effort_flag_in_acpx_claude_cmd(self, tmp_path):
        """acpx-claude dispatch must NOT assemble a --effort CLI flag (broken flag deleted)."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-t1",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        # ACPX_PRINT_CMD_ONLY prints assembled command to stderr.
        assert "--effort" not in result.stderr, (
            f"--effort must not appear in assembled cmd:\n{result.stderr}"
        )

    def test_task4_acpx_claude_max_turns_not_validated(self, tmp_path):
        """acpx-claude max_turns binding validation removed — multi-turn management is the
        delegate-and-watch watcher's responsibility (L2 skill). max_turns values that
        previously caused exit 68 (e.g. 0, 25) now pass the dispatcher cleanly.
        """
        worktree = tmp_path / "wt"
        worktree.mkdir()
        # Binding with max_turns=0 (previously invalid) now allowed at the dispatcher level.
        binding = json.dumps({
            "mechanism": "acpx-claude",
            "max_turns": 0,
            "isolation": "none",
            "permissions": "",
            "timeout_seconds": 900,
            "retries": 0,
            "provides": ["ROLE_DONE"],
            "modalities": {"claude": {"model": "opus", "effort": "high"}},
            "compaction": {"threshold": None},
        })
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_JSON": binding,
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-t4",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        # max_turns=0 is no longer rejected (watcher owns the cap).
        assert result.returncode != 68, (
            f"max_turns binding validation was re-introduced (should be removed):\nstderr:\n{result.stderr}"
        )
        assert "max_turns" not in result.stderr, (
            f"max_turns validation error must not appear in dispatcher:\n{result.stderr}"
        )

    def test_task5_acpx_claude_routes_to_driver(self, tmp_path):
        """acpx-claude must route to claude-session-driver.sh (ACPX_PRINT_CMD_ONLY output check)."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-t5",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        # ACPX_PRINT_CMD_ONLY for the driver path prints '<ENGINE>-session-driver.sh' to stderr.
        assert "claude-session-driver.sh" in result.stderr, (
            f"expected claude-session-driver.sh in stderr:\n{result.stderr}"
        )
        assert "--effort" not in result.stderr, (
            f"--effort must not appear in stderr:\n{result.stderr}"
        )
        # stdout must be a valid JSON envelope.
        # NOTE: the json.loads/status==completed assertion is non-discriminating pre-Task-5
        # (current shared-loop ACPX_PRINT_CMD_ONLY already emits that JSON); the stderr
        # assertion ('claude-session-driver.sh' in result.stderr) is the discriminating one.
        envelope = json.loads(result.stdout.strip())
        assert envelope["status"] == "completed", envelope

    def test_codex_fast_path_uses_the_plain_codex_positional(self, tmp_path):
        """The codex fast path passes the bare `codex` positional (relay 4.51.0).

        Relay 4.6.1 replaced it with `--agent "npx -y @agentclientprotocol/codex-acp@latest"`
        because acpx pinned a broken adapter. acpx 0.12.1 moved that pin to a working
        `^1.1.5`, and relay's floor is now 0.13.2, so the override is gone.
        """
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "plan-simulator",
            "ACPX_BINDING_PRESET": "plan-simulator",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-agent-override",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        printed_args = result.stderr.splitlines()
        assert "--agent" not in printed_args, (
            f"the codex --agent override is retired:\n{result.stderr}"
        )
        assert not any("codex-acp" in arg for arg in printed_args), (
            f"no hand-pinned adapter may remain on the command line:\n{result.stderr}"
        )
        assert "codex" in printed_args, (
            f"the plain 'codex' positional must be passed:\n{result.stderr}"
        )

    def test_acpx_codex_mechanism_uses_the_plain_codex_positional(self, tmp_path):
        """The generic acpx-codex one-shot loop passes the plain positional too."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        binding = json.dumps({
            "mechanism": "acpx-codex",
            "isolation": "none",
            "permissions": "approve-all",
            "timeout_seconds": 900,
            "retries": 0,
            "provides": ["ROLE_DONE"],
            "model": "gpt-5.6-terra",
            "effort": "medium",
            "compaction": {"threshold": None},
        })
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_JSON": binding,
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-acpx-codex-override",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        printed_args = result.stderr.splitlines()
        assert "--agent" not in printed_args, (
            f"the codex --agent override is retired:\n{result.stderr}"
        )
        assert not any("codex-acp" in arg for arg in printed_args), (
            f"no hand-pinned adapter may remain on the command line:\n{result.stderr}"
        )
        assert "codex" in printed_args, (
            f"the plain 'codex' positional must be passed:\n{result.stderr}"
        )

    def test_task5_acpx_claude_driver_name_in_print_cmd(self, tmp_path):
        """ACPX_PRINT_CMD_ONLY for acpx-opencode must print opencode-session-driver.sh."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        opencode_binding = json.dumps({
            "mechanism": "acpx-opencode",
            "max_turns": 3,
            "isolation": "none",
            "permissions": "",
            "timeout_seconds": 900,
            "retries": 0,
            "provides": ["ROLE_DONE"],
            "model": "claude-opus-4-5",
            "effort": "medium",
            "compaction": {"threshold": None},
        })
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_JSON": opencode_binding,
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-t5b",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        assert "opencode-session-driver.sh" in result.stderr, (
            f"expected opencode-session-driver.sh in stderr:\n{result.stderr}"
        )


class TestAcpx012CodexModelDispatch:
    """acpx >= 0.12.0 validates --model against adapter-advertised plain ids.
    Codex exec sites must pass the bare model and carry reasoning effort via
    the CODEX_CONFIG adapter env (JSON merged into the Codex session config),
    never the pre-0.12 bracket encoding (`gpt-5.6-terra[high]`)."""

    def test_codex_fast_path_plain_model_with_codex_config_env(self, tmp_path):
        """codex-session fast-path (plan-simulator): plain --model + env CODEX_CONFIG."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        env = {
            "ACPX_ROLE_SLUG": "plan-simulator",
            "ACPX_BINDING_PRESET": "plan-simulator",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-plain-model",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        printed_args = result.stderr.splitlines()
        # plan-simulator codex modality: gpt-5.6-terra / high.
        assert "gpt-5.6-terra" in printed_args, (
            f"plain model id missing from assembled cmd:\n{result.stderr}"
        )
        codex_config = next(
            (a for a in printed_args if a.startswith("CODEX_CONFIG=")), None
        )
        assert codex_config is not None, f"CODEX_CONFIG missing:\n{result.stderr}"
        parsed = json.loads(codex_config[len("CODEX_CONFIG="):])
        assert parsed["model_reasoning_effort"] == "high", parsed
        # `exec` has no `set` subcommand, so the codex sandbox is widened here too.
        assert parsed["approval_policy"] == "never", parsed
        assert parsed["sandbox_mode"] == "danger-full-access", parsed
        bracketed = [a for a in printed_args if "[" in a and "]" in a and a.startswith("gpt-")]
        assert not bracketed, (
            f"bracket-encoded model must not appear (acpx 0.12.0 rejects it): {bracketed}"
        )

    def test_acpx_codex_child_cmd_plain_model_with_codex_config_env(self, tmp_path):
        """Generic acpx-codex one-shot CHILD_CMD: plain --model + env CODEX_CONFIG."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        binding = json.dumps({
            "mechanism": "acpx-codex",
            "isolation": "none",
            "permissions": "approve-all",
            "timeout_seconds": 900,
            "retries": 0,
            "provides": ["ROLE_DONE"],
            "model": "gpt-5.6-terra",
            "effort": "medium",
            "compaction": {"threshold": None},
        })
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_JSON": binding,
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-acpx-codex-plain",
            "WORKTREE": str(worktree),
            "ACPX_PRINT_CMD_ONLY": "1",
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        printed_args = result.stderr.splitlines()
        assert "gpt-5.6-terra" in printed_args, (
            f"plain model id missing from assembled cmd:\n{result.stderr}"
        )
        codex_config = next(
            (a for a in printed_args if a.startswith("CODEX_CONFIG=")), None
        )
        assert codex_config is not None, f"CODEX_CONFIG missing:\n{result.stderr}"
        parsed = json.loads(codex_config[len("CODEX_CONFIG="):])
        assert parsed["model_reasoning_effort"] == "medium", parsed
        assert parsed["approval_policy"] == "never", parsed
        assert parsed["sandbox_mode"] == "danger-full-access", parsed
        assert "gpt-5.6-terra[medium]" not in printed_args, (
            f"bracket-encoded model must not appear:\n{result.stderr}"
        )


class TestAcpxOpencodeModalitySelection:
    """acpx-opencode mechanism selects modalities.opencode (not the flat fallback
    or the claude modality) and hands the provider-qualified model to the driver."""

    def test_opencode_modality_model_reaches_driver(self, tmp_path):
        worktree = tmp_path / "wt"
        worktree.mkdir()
        capture = tmp_path / "captured.env"
        fake_driver = tmp_path / "fake_opencode_driver.sh"
        fake_driver.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            printf 'MODEL=%s\\nEFFORT=%s\\n' "$ACPX_MODEL" "$ACPX_EFFORT" > {capture}
            printf 'ROLE_RESULT=DONE\\nTURNS_USED=1\\nROLE_DONE\\n'
            exit 0
        """))
        fake_driver.chmod(
            fake_driver.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH
        )
        binding = json.dumps({
            "mechanism": "acpx-opencode",
            "isolation": "none",
            "permissions": "",
            "timeout_seconds": 900,
            "retries": 0,
            "provides": ["ROLE_DONE"],
            "model": "flat-decoy-model",
            "effort": "low",
            "modalities": {
                "claude": {"model": "opus", "effort": "high"},
                "opencode": {"model": "opencode-go/kimi-k2.6"},
            },
            "compaction": {"threshold": None},
        })
        env = {
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_JSON": binding,
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-oc-modality",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
        }
        result = run_dispatch(env=env)
        assert result.returncode == 0, f"expected exit 0:\nstderr:\n{result.stderr}"
        captured = capture.read_text()
        assert "MODEL=opencode-go/kimi-k2.6" in captured, (
            f"modalities.opencode.model must win over flat model:\n{captured}"
        )
        # No opencode effort key in the modality → flat .effort is the fallback.
        assert "EFFORT=low" in captured, captured


def _make_fake_driver(tmp_path, output_lines, exit_code=0):
    """Write a minimal fake driver that emits output_lines to stdout and exits with exit_code."""
    script = tmp_path / "fake_driver.sh"
    script.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        printf '%s\\n' {' '.join(repr(l) for l in output_lines)}
        exit {exit_code}
    """))
    script.chmod(script.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)
    return script


def make_fake_acpx(tmp_path, set_effort_rc=0):
    """Write a fake acpx shim that records argv to a log file and succeeds.

    A turn emits the raw ACP JSON-RPC stream, because since relay 4.51.0 every
    acpx call runs under `--format json --json-strict` and the drivers rebuild the
    reply text with acpx-envelope.sh. A fake that printed bare text would model the
    retired `--format quiet` contract, and the driver would read an empty reply.

    `set_effort_rc` controls the exit code of the effort call. The codex driver
    names that option `reasoning_effort` and the other two name it `effort`, so
    both spellings are matched.
    """
    log_file = tmp_path / "acpx.calls.log"
    fake = tmp_path / "acpx"
    fake.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        printf '%s\\n' "$@" >> {log_file}
        # Detect subcommand type from argv
        for arg in "$@"; do
            case "$arg" in
                sessions)  exit 0 ;;
                set)
                    found_effort=0
                    for a in "$@"; do
                        case "$a" in effort|reasoning_effort) found_effort=1 ;; esac
                    done
                    [ "$found_effort" = "1" ] && exit {set_effort_rc}
                    exit 0 ;;
            esac
        done
        # Turn invocation — one agent_message_chunk carrying the terminal token.
        printf '%s\\n' '{{"jsonrpc":"2.0","method":"session/update","params":{{"sessionId":"s1","update":{{"sessionUpdate":"agent_message_chunk","messageId":"m1","content":{{"type":"text","text":"ROLE_DONE"}},"_meta":null}}}}}}'
        exit 0
    """))
    fake.chmod(fake.stat().st_mode | stat_mod.S_IEXEC | stat_mod.S_IXGRP | stat_mod.S_IXOTH)
    return fake, log_file


def make_prompt_file(tmp_path, content="do the thing"):
    pf = tmp_path / "prompt.md"
    pf.write_text(f"<<DO_NOT_LOAD_SKILLS>>\n{content}\n")
    return pf


class TestCodexFastPathNeedsDecision:
    """codex fast-path must detect NEEDS_DECISION: in full output and emit the right envelope."""

    def _run_fast_path(self, tmp_path, fake_output):
        """Helper: run dispatch in codex-session/fast-path mode with fake child output."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        role_path = PLUGIN_ROOT / "agents" / "plan-simulator.md"  # max_turns:1, no verify_artifact
        env = {
            "ACPX_ROLE_SLUG": "plan-simulator",
            "ACPX_BINDING_PRESET": "plan-simulator",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "test-fast-nd",
            "WORKTREE": str(worktree),
            "ACPX_FAKE_CHILD_OUTPUT": fake_output,
        }
        return run_dispatch(env=env)

    def test_fast_path_needs_decision_emits_role_result(self, tmp_path):
        result = self._run_fast_path(
            tmp_path,
            "NEEDS_DECISION: Should I use TypeScript or JavaScript?"
        )
        assert "ROLE_RESULT=NEEDS_DECISION" in result.stdout, \
            f"fast-path must emit ROLE_RESULT=NEEDS_DECISION; got: {result.stdout!r}"

    def test_fast_path_needs_decision_emits_question_text(self, tmp_path):
        result = self._run_fast_path(
            tmp_path,
            "NEEDS_DECISION: Should I use TypeScript or JavaScript?"
        )
        assert "QUESTION_TEXT=Should I use TypeScript or JavaScript?" in result.stdout, \
            f"fast-path must emit QUESTION_TEXT=...; got: {result.stdout!r}"

    def test_fast_path_misframed_coexists_role_done_demotes_to_blocked(self, tmp_path):
        result = self._run_fast_path(
            tmp_path,
            "NEEDS_DECISION: ambiguous\nROLE_DONE"
        )
        assert "ROLE_RESULT=BLOCKED" in result.stdout, \
            "co-presence of NEEDS_DECISION: and ROLE_DONE must demote to BLOCKED"
        assert "misframed_output" in result.stdout, \
            "misframed demote must carry BLOCKED_REASON=misframed_output"

    def test_fast_path_multiple_needs_decision_lines_demotes_to_blocked(self, tmp_path):
        result = self._run_fast_path(
            tmp_path,
            "NEEDS_DECISION: question one\nNEEDS_DECISION: question two"
        )
        assert "ROLE_RESULT=BLOCKED" in result.stdout, \
            "multiple NEEDS_DECISION: lines must demote to BLOCKED"

    def test_fast_path_unparseable_envelope_emits_typed_error(self, tmp_path):
        # Spec §9 PR1 item 1: unparseable envelope (no terminal token, no KEY=VALUE lines,
        # raw prose only) must produce a typed terminal error, never not-done.
        result = self._run_fast_path(
            tmp_path,
            "Here is my answer in plain prose with no envelope tokens at all."
        )
        assert "ROLE_RESULT=ERRORED" in result.stdout or "ROLE_RESULT=BLOCKED" in result.stdout, \
            "unparseable envelope (no terminal token, no KEY=VALUE lines) must emit a typed error result, never not-done"
        assert "unparseable" in result.stdout or "BLOCKED_REASON" in result.stdout or "ERRORED_REASON" in result.stdout, \
            "typed error for unparseable envelope must carry a reason token"


def test_task8_run_eval_no_effort_flag():
    """run-eval.sh must not contain --effort (broken flag removed from harness)."""
    from pathlib import Path as _Path
    run_eval = _Path(__file__).parents[3] / "tests" / "e2e" / "run-eval.sh"
    if not run_eval.exists():
        pytest.skip("run-eval.sh not found")
    content = run_eval.read_text()
    assert "--effort" not in content, (
        f"--effort must be removed from run-eval.sh:\n"
        + "\n".join(l for l in content.splitlines() if "--effort" in l)
    )


def test_task2_claude_driver_sequence(tmp_path):
    """claude-session-driver.sh must call: sessions ensure -> set model -> set effort -> turn (no --effort/--model).

    Single-turn only — sessions close is NOT called by the driver; it is the
    delegate-and-watch watcher's responsibility (L2 skill).
    """
    if not CLAUDE_DRIVER.exists():
        pytest.skip("claude-session-driver.sh not yet created")
    fake_acpx, log_file = make_fake_acpx(tmp_path)
    prompt = make_prompt_file(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "ACPX_ENGINE": "claude",
        "ACPX_MODEL": "opus",
        "ACPX_CWD": str(tmp_path),
        "ACPX_TIMEOUT": "60",
        "ACPX_SESSION_NAME": "run-t2-code-reviewer",
        "ACPX_PROMPT_FILE": str(prompt),
        "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
        "ACPX_MAX_TURNS": "1",
        "ACPX_NUDGE_PROMPT": "nudge",
        "ACPX_VERIFY_ARTIFACT": "",
        "ACPX_EFFORT": "high",
        "ACPX_PERMISSIONS": "",
    }
    result = subprocess.run(["bash", str(CLAUDE_DRIVER)], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, f"driver exited non-zero:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    calls = log_file.read_text()
    assert "sessions" in calls, f"sessions ensure not called:\n{calls}"
    assert "ensure" in calls, f"sessions ensure not called:\n{calls}"
    assert "set" in calls and "model" in calls, f"set model not called:\n{calls}"
    assert "effort" in calls, f"set effort not called:\n{calls}"
    assert "--effort" not in calls, \
        f"--effort appeared in turn args:\n{calls}"
    assert "ROLE_RESULT=DONE" in result.stdout, f"turn did not complete (expected ROLE_RESULT=DONE):\n{result.stdout}"


def test_task3_opencode_driver_sequence(tmp_path):
    """opencode-session-driver.sh must call: sessions ensure -> set model -> set effort -> turn (no --effort/--model).

    Single-turn only — sessions close is NOT called by the driver; it is the
    delegate-and-watch watcher's responsibility (L2 skill).
    """
    if not OPENCODE_DRIVER.exists():
        pytest.skip("opencode-session-driver.sh not yet created")
    fake_acpx, log_file = make_fake_acpx(tmp_path)
    prompt = make_prompt_file(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "ACPX_ENGINE": "opencode",
        "ACPX_MODEL": "claude-opus-4-5",
        "ACPX_CWD": str(tmp_path),
        "ACPX_TIMEOUT": "60",
        "ACPX_SESSION_NAME": "run-t3-opencode",
        "ACPX_PROMPT_FILE": str(prompt),
        "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
        "ACPX_MAX_TURNS": "1",
        "ACPX_NUDGE_PROMPT": "nudge",
        "ACPX_VERIFY_ARTIFACT": "",
        "ACPX_EFFORT": "medium",
        "ACPX_PERMISSIONS": "",
    }
    result = subprocess.run(["bash", str(OPENCODE_DRIVER)], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, (
        f"driver exited non-zero:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )
    calls = log_file.read_text()
    assert "sessions" in calls and "ensure" in calls, f"sessions ensure not called:\n{calls}"
    assert "set" in calls and "model" in calls, f"set model not called:\n{calls}"
    assert "effort" in calls, f"set effort not called:\n{calls}"
    assert "ROLE_RESULT=DONE" in result.stdout, f"turn did not complete (expected ROLE_RESULT=DONE):\n{result.stdout}"
    assert "opencode" in calls, f"opencode not found in acpx calls:\n{calls}"
