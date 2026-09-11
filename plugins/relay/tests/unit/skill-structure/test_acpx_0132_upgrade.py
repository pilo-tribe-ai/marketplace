"""Tests for the acpx 0.13.2 upgrade (relay 4.51.0).

Six changes ship together behind one floor, and each one is checked here:

1. `scripts/acpx-floor.sh` is the single site that states the acpx floor, and
   `l3-preflight.sh` enforces it for the acpx engine only.
2. Every acpx turn carries the widest permission grant acpx exposes.
3. The codex `--agent` override is gone.
4. The codex driver applies model, reasoning effort, and sandbox mode through
   session config.
5. `delegate-and-watch` routes a session-config replay failure to `errored`.
6. `acpx-envelope.sh` rebuilds the final assistant text from the JSON stream.

The floor and envelope tests drive real scripts with a fake `acpx` on PATH, so they
never reach the network. The dispatch tests use the existing ACPX_PRINT_CMD_ONLY hook.
"""
import json
import os
import shutil
import subprocess

import pytest

from conftest import PLUGIN_ROOT, deps_ok_env

SCRIPTS = PLUGIN_ROOT / "scripts"
FLOOR = SCRIPTS / "acpx-floor.sh"
PREFLIGHT = SCRIPTS / "l3-preflight.sh"
DISPATCH_DIR = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents"
DISPATCH = DISPATCH_DIR / "acpx-dispatch.sh"
ENVELOPE = DISPATCH_DIR / "acpx-envelope.sh"
POLICY = PLUGIN_ROOT / "bindings" / "acpx-policy.json"
FIXTURES = PLUGIN_ROOT / "tests" / "fixtures" / "acpx-envelope"

CLAUDE_DRIVER = DISPATCH_DIR / "claude-session-driver.sh"
OPENCODE_DRIVER = DISPATCH_DIR / "opencode-session-driver.sh"
CODEX_DRIVER = DISPATCH_DIR / "codex-session-driver.sh"
ALL_DRIVERS = (CLAUDE_DRIVER, OPENCODE_DRIVER, CODEX_DRIVER)

# The floor this release ships. Declared once here and compared against the script,
# so a future bump has to touch the script and this constant together.
EXPECTED_FLOOR = "0.13.2"


def fake_acpx_path(tmp_path, version):
    """A directory holding a fake `acpx` that prints `version`."""
    binaries = tmp_path / "fakebin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "acpx"
    fake.write_text(f"#!/bin/sh\necho {version}\n")
    fake.chmod(0o755)
    return binaries


def run(cmd, env=None, cwd=None, stdin=None):
    full = dict(os.environ)
    if env:
        full.update(env)
    return subprocess.run(
        cmd, capture_output=True, text=True, env=full, cwd=cwd, input=stdin
    )


class TestAcpxFloorScript:
    """scripts/acpx-floor.sh is the only place that states the floor number."""

    def test_script_exists_and_is_executable(self):
        assert FLOOR.is_file()
        assert os.access(FLOOR, os.X_OK), "acpx-floor.sh must be executable"

    def test_declares_the_expected_floor_once(self):
        body = FLOOR.read_text()
        assert f"RELAY_ACPX_MIN={EXPECTED_FLOOR}" in body

    @pytest.mark.parametrize("version", ["0.13.2", "0.14.0", "1.0.0"])
    def test_version_at_or_above_the_floor_passes(self, tmp_path, version):
        binaries = fake_acpx_path(tmp_path, version)
        result = run(
            ["bash", str(FLOOR)], env={"PATH": f"{binaries}:{os.environ['PATH']}"}
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"RELAY_ACPX_VERSION={version}"

    @pytest.mark.parametrize("version", ["0.12.0", "0.13.1", "0.7.0", "0.9.9"])
    def test_version_below_the_floor_fails_with_the_remedy(self, tmp_path, version):
        binaries = fake_acpx_path(tmp_path, version)
        result = run(
            ["bash", str(FLOOR)], env={"PATH": f"{binaries}:{os.environ['PATH']}"}
        )
        assert result.returncode == 1
        assert f"acpx {version} is below the floor {EXPECTED_FLOOR}" in result.stderr
        assert "npm install -g acpx@latest" in result.stderr

    @pytest.mark.parametrize(
        "banner,version",
        [("acpx 0.12.0", "0.12.0"), ("acpx v0.13.1", "0.13.1"), ("v0.9.9", "0.9.9")],
    )
    def test_a_version_banner_still_fails_the_floor(self, tmp_path, banner, version):
        """`acpx --version` may print a name before the number.

        Stripping whitespace alone leaves `acpx0.12.0`, which `sort -V` orders ABOVE
        `0.13.2`, so a stale acpx would pass the gate. The number is extracted, not
        the whole line.
        """
        binaries = fake_acpx_path(tmp_path, banner)
        result = run(
            ["bash", str(FLOOR)], env={"PATH": f"{binaries}:{os.environ['PATH']}"}
        )
        assert result.returncode == 1, f"{banner!r} must not pass the floor"
        assert f"acpx {version} is below the floor {EXPECTED_FLOOR}" in result.stderr

    def test_absent_acpx_fails_with_the_remedy(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        # /usr/bin and /bin keep the shell's own tools reachable while hiding acpx.
        result = run(["bash", str(FLOOR)], env={"PATH": f"{empty}:/usr/bin:/bin"})
        assert result.returncode == 1
        assert "acpx is not on PATH" in result.stderr
        assert "npm install -g acpx@latest" in result.stderr


def preflight_env(tmp_path, version):
    """`deps_ok_env`, with a fake `acpx` reporting `version` ahead of everything else.

    The fixture already puts an acpx at the floor on PATH so the gate never reads this
    machine's install; prepending here lets one test choose the version under test.
    """
    env = deps_ok_env(tmp_path)
    env["PATH"] = f"{fake_acpx_path(tmp_path, version)}:{env['PATH']}"
    return env


class TestPreflightEnforcesTheFloor:
    """The gate runs for the acpx engine and only for the acpx engine."""

    def test_acpx_engine_below_the_floor_aborts(self, tmp_path):
        result = run(
            ["bash", str(PREFLIGHT), "implement", "--engine acpx --agent claude"],
            env=preflight_env(tmp_path, "0.12.0"),
        )
        assert result.returncode == 1
        assert "is below the floor" in result.stderr

    @pytest.mark.parametrize("engine", ["in-session", "bg-sessions"])
    def test_non_acpx_engines_never_pay_the_check(self, tmp_path, engine):
        """These engines never call the acpx CLI, so a stale acpx must not block them."""
        result = run(
            ["bash", str(PREFLIGHT), "implement", f"--engine {engine} --agent claude"],
            env=preflight_env(tmp_path, "0.12.0"),
        )
        assert result.returncode == 0, result.stderr
        assert "is below the floor" not in result.stderr
        assert f"engine={engine}" in result.stdout

    def test_acpx_engine_at_the_floor_passes(self, tmp_path):
        result = run(
            ["bash", str(PREFLIGHT), "implement", "--engine acpx --agent claude"],
            env=preflight_env(tmp_path, EXPECTED_FLOOR),
        )
        assert result.returncode == 0, result.stderr
        assert "engine=acpx" in result.stdout


class TestNoStaleFloorNumbers:
    """The floor number lives in one script; no other shipped file restates it."""

    def test_no_stale_floor_declarations(self):
        stale = []
        roots = [SCRIPTS, PLUGIN_ROOT / "skills", PLUGIN_ROOT / "flows"]
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".sh", ".md", ".json"}:
                    continue
                if path.name == "acpx-floor.sh" or "node_modules" in str(path):
                    continue
                for number, line in enumerate(path.read_text().splitlines(), 1):
                    lowered = line.lower()
                    if "acpx" not in lowered:
                        continue
                    # A floor DECLARATION pairs acpx with a >= comparison. Prose that
                    # dates a past behaviour change ("acpx >= 0.12.0 rejects brackets")
                    # is history, not a floor, and stays.
                    for marker in (">= 0.7.0", ">=0.7.0", "≥0.7.0", "≥ 0.7.0"):
                        if marker in line:
                            stale.append(f"{path.relative_to(PLUGIN_ROOT)}:{number}: {line.strip()}")
        assert not stale, "stale acpx floor of 0.7.0 still shipped:\n" + "\n".join(stale)

    def test_flows_package_and_lock_agree_with_the_floor(self):
        pkg = json.loads((PLUGIN_ROOT / "flows" / "package.json").read_text())
        assert pkg["dependencies"]["acpx"] == f">={EXPECTED_FLOOR}"
        lock = json.loads((PLUGIN_ROOT / "flows" / "package-lock.json").read_text())
        entry = lock["packages"]["node_modules/acpx"]
        got = tuple(int(part) for part in entry["version"].split(".")[:2])
        want = tuple(int(part) for part in EXPECTED_FLOOR.split(".")[:2])
        assert got >= want, f"lock pins acpx {entry['version']}, below {EXPECTED_FLOOR}"


class TestCodexAgentOverrideIsGone:
    """acpx >= 0.12.1 pins a working codex adapter; the override is retired."""

    def test_no_shipped_file_sets_or_reads_the_override(self):
        """Prose may name the retired variable; no file may still set or expand it.

        The removal note in SKILL.md, the CHANGELOG entry, and the spec all mention
        `ACPX_CODEX_AGENT_OVERRIDE` on purpose, so someone grepping for it finds the
        explanation. Only a live assignment or expansion is a defect.
        """
        live_uses = ("$ACPX_CODEX_AGENT_OVERRIDE", "${ACPX_CODEX_AGENT_OVERRIDE",
                     "ACPX_CODEX_AGENT_OVERRIDE=")
        offenders = []
        for path in PLUGIN_ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in {".sh", ".md", ".yaml", ".json"}:
                continue
            if "node_modules" in str(path) or "docs/superpowers/specs" in str(path):
                continue
            if path.name == "CHANGELOG.md":
                continue
            body = path.read_text()
            if any(use in body for use in live_uses):
                offenders.append(str(path.relative_to(PLUGIN_ROOT)))
        assert not offenders, f"ACPX_CODEX_AGENT_OVERRIDE still live in {offenders}"

    def test_dispatch_never_passes_an_agent_override_flag(self):
        body = DISPATCH.read_text()
        assert '"--agent"' not in body
        assert '--agent "$ACPX_CODEX_AGENT_OVERRIDE"' not in body


class TestWidePermissionGrant:
    """Every acpx turn gets --approve-all AND the policy file, unconditionally."""

    def test_policy_file_is_the_widest_default(self):
        policy = json.loads(POLICY.read_text())
        assert policy["defaultAction"] == "approve"

    def test_no_shipped_command_gates_approve_all_on_the_binding(self):
        """The 4.50.0 gate silently denied writes for the three approve-reads roles."""
        for path in (DISPATCH, *ALL_DRIVERS):
            body = path.read_text()
            assert '[ "$PERMISSIONS" = "approve-all" ]' not in body, path.name
            assert '[ "$ACPX_PERMISSIONS" = "approve-all" ]' not in body, path.name

    @pytest.mark.parametrize("driver", ALL_DRIVERS, ids=lambda p: p.name)
    def test_every_driver_turn_carries_both_flags(self, driver):
        body = driver.read_text()
        assert "--permission-policy" in body, f"{driver.name} misses the policy flag"
        assert "--approve-all" in body, f"{driver.name} misses --approve-all"
        assert "ACPX_POLICY_FILE" in body, f"{driver.name} misses the policy path var"

    @pytest.mark.parametrize("driver", ALL_DRIVERS, ids=lambda p: p.name)
    def test_driver_falls_back_to_the_shipped_policy_path(self, driver):
        """A hand-run driver with no sidecar must still find the policy file."""
        body = driver.read_text()
        assert 'ACPX_POLICY_FILE:=${SCRIPT_DIR}/../../bindings/acpx-policy.json' in body

    @pytest.mark.skipif(
        shutil.which("yq") is None or shutil.which("jq") is None,
        reason="acpx-dispatch.sh requires yq and jq",
    )
    def test_generic_loop_command_carries_the_grant(self, tmp_path):
        """A role bound to approve-reads still gets the wide grant on the command line."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        result = run(
            ["bash", str(DISPATCH)],
            env={
                "ACPX_ROLE_SLUG": "code-reviewer",
                "ACPX_BINDING_PRESET": "code-reviewer",
                "ACPX_MECHANISM_OVERRIDE": "acpx-codex",
                "ACPX_INPUTS_JSON": json.dumps(
                    {"task_text": "review", "repo_root": str(worktree)}
                ),
                "ACPX_RUN_ID": "run-policy",
                "WORKTREE": str(worktree),
                "ACPX_PRINT_CMD_ONLY": "1",
            },
        )
        assert result.returncode == 0, result.stderr
        argv = result.stderr.splitlines()
        assert "--approve-all" in argv
        assert "--permission-policy" in argv
        policy_arg = argv[argv.index("--permission-policy") + 1]
        assert os.path.isfile(policy_arg), f"policy path does not exist: {policy_arg}"
        assert json.loads(open(policy_arg).read())["defaultAction"] == "approve"
        assert "--agent" not in argv

    def test_codex_config_carries_the_sandbox_grant(self):
        """`exec` has no `set` subcommand, so the sandbox rides CODEX_CONFIG."""
        probe = (
            f'source_file="{DISPATCH}"\n'
            "eval \"$(sed -n '/^build_codex_config()/,/^}/p' \"$source_file\")\"\n"
            'printf "%s\\n" "$(build_codex_config low)"\n'
            'printf "%s\\n" "$(build_codex_config)"\n'
        )
        result = run(["bash", "-c", probe])
        assert result.returncode == 0, result.stderr
        with_effort, without_effort = result.stdout.strip().splitlines()
        parsed = json.loads(with_effort)
        assert parsed["model_reasoning_effort"] == "low"
        assert parsed["approval_policy"] == "never"
        assert parsed["sandbox_mode"] == "danger-full-access"
        # The grant must not depend on the role pinning an effort.
        bare = json.loads(without_effort)
        assert bare["approval_policy"] == "never"
        assert bare["sandbox_mode"] == "danger-full-access"
        assert "model_reasoning_effort" not in bare


class TestCodexSettleBlock:
    """The codex driver applies model, effort, and mode through session config."""

    def test_sets_all_three_options_in_order(self):
        body = CODEX_DRIVER.read_text()
        positions = {
            key: body.index(f"set {key}")
            for key in ("model", "reasoning_effort", "mode agent-full-access")
        }
        assert positions["model"] < positions["reasoning_effort"], (
            "model must be set first: the adapter rebuilds effort options on model change"
        )
        assert positions["reasoning_effort"] < positions["mode agent-full-access"]

    def test_each_settle_call_soft_degrades(self):
        body = CODEX_DRIVER.read_text()
        assert body.count("[warn]") >= 3, "each set call must soft-degrade on rc!=0"

    def test_turn_no_longer_passes_model(self):
        """The session record holds the model, matching the claude/opencode contract."""
        body = CODEX_DRIVER.read_text()
        turn = body[body.index("TURN_NDJSON_FILE="):]
        assert "--model" not in turn, "the codex turn must not re-pass --model"

    def test_driver_no_longer_reads_codex_config(self):
        body = CODEX_DRIVER.read_text()
        code = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("#")
        )
        assert "CODEX_CONFIG" not in code, "effort now rides session config"


class TestSidecarContract:
    """A delegate-and-watch re-invocation must carry the new vars."""

    def test_both_sidecars_write_the_policy_path(self):
        body = DISPATCH.read_text()
        assert body.count("printf 'ACPX_POLICY_FILE=%q\\n'") == 2

    def test_codex_sidecar_writes_effort(self):
        body = DISPATCH.read_text()
        codex_block = body[body.index("printf 'ACPX_ENGINE=%q\\n' \"codex\""):]
        codex_block = codex_block[: codex_block.index("} > \"$sidecar_file\"")]
        assert "ACPX_EFFORT" in codex_block, "the codex driver now needs the effort"

    def test_codex_sidecar_keeps_codex_config_for_one_release(self):
        """An in-flight watcher on the 4.50.0 contract must still source cleanly."""
        body = DISPATCH.read_text()
        assert "printf 'CODEX_CONFIG=%q\\n'" in body


class TestEnvelopeScript:
    """acpx-envelope.sh turns the raw ACP JSON stream into the final assistant text."""

    def extract(self, fixture):
        result = run(["bash", str(ENVELOPE)], stdin=(FIXTURES / fixture).read_text())
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_script_exists_and_is_executable(self):
        assert ENVELOPE.is_file()
        assert os.access(ENVELOPE, os.X_OK)

    def test_codex_final_answer_rebuilds_the_envelope(self):
        assert self.extract("codex-final-answer.ndjson") == "STATUS=ok\nsecond line\nROLE_DONE\n"

    def test_claude_chunks_split_mid_token_rebuild_exactly(self):
        """Live 0.13.2 claude splits "STATUS" into "ST" + "ATUS=ok\\nROLE_DONE"."""
        assert self.extract("claude-split-chunks.ndjson") == "STATUS=ok\nROLE_DONE\n"

    def test_codex_commentary_is_dropped_and_last_message_wins(self):
        out = self.extract("codex-commentary-and-split.ndjson")
        assert "Let me check the repo" not in out, "commentary must not reach the envelope"
        assert out == 'STATUS=ok\nFILES_TOUCHED=["a.js"]\nROLE_DONE\n'

    def test_narration_message_never_reaches_the_envelope(self):
        """A tool-using role narrates under its own messageId; only the last one is the reply.

        The `BLOCKED:` / `NEEDS_DECISION:` sentinels are read from the FIRST line of
        this output, so a leading narration message would demote every one of them.
        The fixture is the shape a live acpx 0.13.2 claude turn produced.
        """
        out = self.extract("claude-narration-then-envelope.ndjson")
        assert out == "BLOCKED: probe reason\n"
        assert out.splitlines()[0].startswith("BLOCKED:"), (
            "the sentinel must stay on the first line"
        )

    def test_replay_failure_is_reported_first(self):
        out = self.extract("replay-failure.ndjson")
        assert out.splitlines()[0] == "ERRORED_REASON=config_replay_failed"

    def test_a_non_json_line_is_skipped_not_fatal(self):
        assert self.extract("non-json-line.ndjson") == "STATUS=ok\nROLE_DONE\n"

    def test_empty_input_yields_empty_output(self):
        result = run(["bash", str(ENVELOPE)], stdin="")
        assert result.returncode == 0
        assert result.stdout == ""

    def test_output_satisfies_the_frozen_capture_regex(self):
        """The envelope contract is unchanged; only the source of the text moved."""
        import re

        pattern = re.compile(r"^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$")
        out = self.extract("codex-commentary-and-split.ndjson")
        captured = [line for line in out.splitlines() if pattern.match(line)]
        assert captured == ["STATUS=ok", 'FILES_TOUCHED=["a.js"]', "ROLE_DONE"]


class TestReplayFailureReachesTheWatcher:
    """Section 5: the reason line must route to `errored`, never to `not-done`."""

    @pytest.mark.parametrize("driver", ALL_DRIVERS, ids=lambda p: p.name)
    def test_driver_classifies_replay_failure_as_errored(self, driver):
        body = driver.read_text()
        assert "ERRORED_REASON=config_replay_failed" in body, driver.name
        # It must be decided before the token check, or it would fall through to NOT_DONE.
        assert body.index("config_replay_failed") < body.index("ROLE_RESULT=NOT_DONE"), (
            f"{driver.name} must classify the replay failure before the not-done fallthrough"
        )

    def test_watcher_doc_lists_the_reason_in_the_errored_bucket(self):
        body = (PLUGIN_ROOT / "skills" / "delegate-and-watch" / "SKILL.md").read_text()
        errored_row = next(
            line for line in body.splitlines() if line.strip().startswith("| `errored` |")
        )
        assert "config_replay_failed" in errored_row


class TestEveryAcpxCallUsesTheJsonStream:
    """No shipped call site may fall back to the unstructured quiet format."""

    @pytest.mark.parametrize("path", (DISPATCH, *ALL_DRIVERS), ids=lambda p: p.name)
    def test_no_command_uses_format_quiet(self, path):
        code = "\n".join(
            line for line in path.read_text().splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "--format quiet" not in code, f"{path.name} still captures unstructured text"

    @pytest.mark.parametrize("path", (DISPATCH, *ALL_DRIVERS), ids=lambda p: p.name)
    def test_json_strict_accompanies_json_format(self, path):
        """--json-strict is what suppresses non-JSON stderr, so it is never optional."""
        # The generic loop builds the flags as separate quoted array elements
        # (`"--format" "json" "--json-strict"`), so strip shell quoting before counting.
        code = path.read_text().replace('"', " ")
        code = " ".join(code.split())
        assert code.count("--format json") == code.count("--json-strict"), (
            f"{path.name}: --format json must always carry --json-strict"
        )
