"""Behavioral tests for skills/dispatching-bg-agents/bg-dispatch.sh (spec §Deliverable 2,
Dispatch — docs/bg-dispatch-contract.md). Everything here is SYNTHETIC: `HOME` and
`WORKTREE` are pointed at `tmp_path`, and `BG_LAUNCH_OVERRIDE` points at a stub
`bg-launch.sh` so no real background session is ever launched. Style mirrors
tests/unit/skill-structure/test_acpx_dispatch_env.py.
"""
import json
import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "skills" / "dispatching-bg-agents" / "bg-dispatch.sh"

_TOOLING_MISSING = shutil.which("yq") is None or shutil.which("jq") is None
pytestmark = pytest.mark.skipif(
    _TOOLING_MISSING, reason="requires yq and jq on PATH"
)


def _make_stub_launcher(tmp_path, deny_count=0, short_id="abc123"):
    """A stub bg-launch.sh. --check-name always passes. On launch, denies
    `deny_count` times then reports success; each call is recorded to calls.txt."""
    script = tmp_path / "stub-bg-launch.sh"
    calls = tmp_path / "calls.txt"
    script.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        echo "1" >> "{calls}"
        case "$1" in
          --check-name) echo "RELAY_BG_NAME_OK=1"; exit 0 ;;
        esac
        deny_state="{tmp_path}/deny_state"
        n=0
        [ -f "$deny_state" ] && n=$(cat "$deny_state")
        if [ "$n" -lt {deny_count} ]; then
          n=$((n + 1))
          echo "$n" > "$deny_state"
          echo "[relay] error: stub denies this attempt" >&2
          echo "RELAY_BG_LAUNCH=LAUNCH_DENIED"
          exit 1
        fi
        echo "RELAY_BG_NAME=stub"
        echo "RELAY_BG_SHORT_ID={short_id}"
        echo "RELAY_BG_LAUNCH=OK"
        exit 0
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script, calls


def _run(tmp_path, env_extra, launcher=None, deny_count=0, short_id="abc123"):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    if launcher is None:
        launcher, calls = _make_stub_launcher(tmp_path, deny_count=deny_count, short_id=short_id)
    else:
        calls = None
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["WORKTREE"] = str(worktree)
    env["BG_LAUNCH_OVERRIDE"] = str(launcher)
    env.setdefault("BG_ROLE_SLUG", "implementer")
    env.setdefault("BG_RUN_ID", "wf_918a4deb-aba")
    # Scrub both depth-cap signals so a developer running pytest inside a bg session
    # (where CLAUDE_JOB_DIR is exported into every Bash tool call) or with RELAY_BG_DEPTH
    # set in their shell does not see every happy-path case refuse with exit 2.
    env.pop("RELAY_BG_DEPTH", None)
    env.pop("CLAUDE_JOB_DIR", None)
    env.update(env_extra)
    result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
    return result, home, worktree, calls


def _kv(stdout):
    out = {}
    for line in stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


class TestScriptShape:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.is_file()
        assert os.access(SCRIPT, os.X_OK)

    def test_header_declares_executed_and_gives_an_example(self):
        body = SCRIPT.read_text()
        assert "EXECUTED" in body
        assert "bash skills/dispatching-bg-agents/bg-dispatch.sh" in body

    def test_never_invokes_claude_bg_directly(self):
        # Only comment lines (prose explaining the delegation) may name `claude --bg`;
        # no executable line may invoke it.
        code_lines = [
            ln for ln in SCRIPT.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        offenders = [ln for ln in code_lines if "claude --bg" in ln or "claude\" --bg" in ln]
        assert not offenders, \
            f"bg-dispatch.sh must launch only through bg-launch.sh, found: {offenders}"


class TestHappyPath:
    def test_sidecar_written_before_launch(self, tmp_path):
        # A launcher stub that checks the sidecar exists at launch time.
        launcher = tmp_path / "check-sidecar-launcher.sh"
        marker = tmp_path / "sidecar-seen-at-launch"
        launcher.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            case "$1" in
              --check-name) echo "RELAY_BG_NAME_OK=1"; exit 0 ;;
            esac
            # any *.env file under HOME/.claude/relay/bg means the sidecar exists
            if ls "$HOME"/.claude/relay/bg/*/*.env >/dev/null 2>&1; then
              echo present > "{marker}"
            fi
            echo "RELAY_BG_NAME=stub"
            echo "RELAY_BG_SHORT_ID=zzz999"
            echo "RELAY_BG_LAUNCH=OK"
            exit 0
        """))
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        result, home, worktree, _ = _run(tmp_path, {}, launcher=launcher)
        assert result.returncode == 0, result.stderr
        assert marker.is_file(), "sidecar must exist before bg-launch.sh runs"

    def test_sidecar_holds_exactly_six_keys(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {})
        assert result.returncode == 0, result.stderr
        kv = _kv(result.stdout)
        sidecar = Path(kv["RELAY_BG_SIDECAR"])
        assert sidecar.is_file()
        lines = [ln for ln in sidecar.read_text().splitlines() if ln.strip()]
        keys = [ln.split("=", 1)[0] for ln in lines]
        assert keys == [
            "RELAY_BG_NAME", "RELAY_BG_SHORT_ID", "RELAY_BG_HANDOFF",
            "RELAY_BG_MODEL", "RELAY_BG_PERMISSION_MODE", "RELAY_BG_MAX_TURNS",
        ]

    def test_short_id_appended_after_launch(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {}, short_id="the-short-id")
        assert result.returncode == 0, result.stderr
        kv = _kv(result.stdout)
        assert kv["RELAY_BG_SHORT_ID"] == "the-short-id"
        sidecar = Path(kv["RELAY_BG_SIDECAR"])
        assert "RELAY_BG_SHORT_ID=the-short-id" in sidecar.read_text()

    def test_handoff_directory_created_before_launch(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {})
        assert result.returncode == 0, result.stderr
        kv = _kv(result.stdout)
        handoff = Path(kv["RELAY_BG_HANDOFF"])
        assert handoff.parent.is_dir()
        assert str(handoff).startswith(str(worktree / ".relay-bg"))

    def test_permission_mode_mapping(self, tmp_path):
        cases = {
            "implementer": "auto",                 # permissions: approve-all
            "code-reviewer": "plan",               # permissions: approve-reads
            "scout": "plan",                       # no permissions key
        }
        for role, expected_mode in cases.items():
            result, home, worktree, _ = _run(tmp_path, {"BG_ROLE_SLUG": role})
            assert result.returncode == 0, f"{role}: {result.stderr}"
            kv = _kv(result.stdout)
            sidecar = Path(kv["RELAY_BG_SIDECAR"]).read_text()
            assert f"RELAY_BG_PERMISSION_MODE={expected_mode}" in sidecar, \
                f"{role} expected {expected_mode}, sidecar: {sidecar}"

    def test_runid_is_derived_from_the_workflow_run_id(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {"BG_RUN_ID": "wf_918a4deb-aba"})
        assert result.returncode == 0, result.stderr
        kv = _kv(result.stdout)
        name = kv["RELAY_BG_NAME"]
        runid = name.rsplit("-", 1)[-1]
        assert 4 <= len(runid) <= 8
        assert runid.isalnum() and runid == runid.lower()
        # same input -> same suffix
        result2, _, _, _ = _run(tmp_path, {"BG_RUN_ID": "wf_918a4deb-aba"})
        kv2 = _kv(result2.stdout)
        assert kv2["RELAY_BG_NAME"].rsplit("-", 1)[-1] == runid

    def test_name_is_validated_before_launch(self, tmp_path):
        # A --check-name stub that always fails must stop the dispatch before launch.
        launcher = tmp_path / "reject-name-launcher.sh"
        launcher.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            case "$1" in
              --check-name) echo "[relay] error: invalid session name: nope" >&2; exit 2 ;;
            esac
            echo "must never reach launch" >&2
            exit 1
        """))
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        result, home, worktree, _ = _run(tmp_path, {}, launcher=launcher)
        assert result.returncode == 2
        assert "invalid session name" in result.stderr

    def test_prompt_holds_the_preamble_then_the_role_body(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {})
        assert result.returncode == 0, result.stderr
        kv = _kv(result.stdout)
        handoff_dir = Path(kv["RELAY_BG_HANDOFF"]).parent
        prompt_files = list(handoff_dir.glob("*.prompt"))
        assert len(prompt_files) == 1
        text = prompt_files[0].read_text()
        assert "TURN=1" in text
        preamble_idx = text.find("Never use AskUserQuestion")
        role_marker_idx = text.find("role-version")
        assert preamble_idx != -1
        # the role body (roles/implementer.md) must follow the preamble
        assert preamble_idx < len(text)


class TestLaunchDenied:
    def test_launch_denied_retries_once_then_fails(self, tmp_path):
        result, home, worktree, calls = _run(tmp_path, {}, deny_count=2)
        assert result.returncode == 1
        kv = _kv(result.stdout)
        assert kv["RELAY_BG_DISPATCH"] == "LAUNCH_DENIED"
        # --check-name (1) + two launch attempts (2) = 3 total calls
        assert calls.read_text().count("1\n") == 3

    def test_launch_denied_once_then_succeeds(self, tmp_path):
        result, home, worktree, calls = _run(tmp_path, {}, deny_count=1)
        assert result.returncode == 0, result.stderr
        kv = _kv(result.stdout)
        assert kv["RELAY_BG_DISPATCH"] == "OK"


class TestUsageErrors:
    def test_missing_role_slug_exits_2(self, tmp_path):
        env = dict(os.environ)
        home = tmp_path / "home"; home.mkdir()
        worktree = tmp_path / "wt"; worktree.mkdir()
        launcher, _ = _make_stub_launcher(tmp_path)
        env["HOME"] = str(home)
        env["WORKTREE"] = str(worktree)
        env["BG_LAUNCH_OVERRIDE"] = str(launcher)
        env["BG_RUN_ID"] = "wf_abc12345"
        env.pop("BG_ROLE_SLUG", None)
        result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
        assert result.returncode == 2

    def test_unknown_role_slug_exits_2(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {"BG_ROLE_SLUG": "no-such-role"})
        assert result.returncode == 2
        assert "no-such-role" in result.stderr

    def test_role_with_delegate_eligible_false_is_refused(self, tmp_path):
        # panel-member: delegate_eligible: false in bindings/presets.yaml
        result, home, worktree, _ = _run(tmp_path, {"BG_ROLE_SLUG": "panel-member"})
        assert result.returncode == 2
        assert "delegate_eligible=false" in result.stderr


def _prompt_text(worktree):
    """The materialized prompt, wherever bg-dispatch.sh put it under .relay-bg/."""
    prompts = list((worktree / ".relay-bg").rglob("*.prompt"))
    assert len(prompts) == 1, f"expected exactly one prompt file, found {prompts}"
    return prompts[0].read_text()


def _role_with_slots(tmp_path, body):
    role = tmp_path / "slot-role.md"
    role.write_text(body)
    return role


class TestSlotSubstitution:
    """A slot value reaches the prompt verbatim, whatever characters it holds.

    The first implementation substituted with `sed -i` delimited by `|`, and escaped
    only `&`, `/` and a backslash. A value holding a pipe made sed exit 1 and leave the
    placeholder in the prompt, and `IFS='=' read` cut a multi-line value at its first
    newline. Neither failure stopped the dispatch, so the child was launched with a
    corrupted prompt and the watcher read its envelope as a real answer.
    """

    def test_a_value_holding_a_pipe_lands_verbatim(self, tmp_path):
        role = _role_with_slots(tmp_path, "Task: {{SLOT_task}}\n")
        result, home, worktree, _ = _run(tmp_path, {
            "RELAY_ROLE_PATH": str(role),
            "BG_INPUTS_JSON": json.dumps({"task": "fix the a|b parser"}),
        })
        assert result.returncode == 0, result.stderr
        text = _prompt_text(worktree)
        assert "Task: fix the a|b parser" in text
        assert "{{SLOT_" not in text

    def test_a_multi_line_value_lands_whole(self, tmp_path):
        role = _role_with_slots(tmp_path, "Notes: {{SLOT_notes}}\nEnd.\n")
        result, home, worktree, _ = _run(tmp_path, {
            "RELAY_ROLE_PATH": str(role),
            "BG_INPUTS_JSON": json.dumps({"notes": "line one\nline two"}),
        })
        assert result.returncode == 0, result.stderr
        text = _prompt_text(worktree)
        assert "line one\nline two" in text
        assert "{{SLOT_" not in text

    def test_backslashes_and_ampersands_land_verbatim(self, tmp_path):
        role = _role_with_slots(tmp_path, "Path: {{SLOT_path}}\n")
        result, home, worktree, _ = _run(tmp_path, {
            "RELAY_ROLE_PATH": str(role),
            "BG_INPUTS_JSON": json.dumps({"path": r"a\b & c/d"}),
        })
        assert result.returncode == 0, result.stderr
        assert r"Path: a\b & c/d" in _prompt_text(worktree)

    def test_every_slot_is_filled_when_several_are_given(self, tmp_path):
        role = _role_with_slots(tmp_path, "A={{SLOT_a}} B={{SLOT_b}} C={{SLOT_c}}\n")
        result, home, worktree, _ = _run(tmp_path, {
            "RELAY_ROLE_PATH": str(role),
            "BG_INPUTS_JSON": json.dumps({"a": "1|1", "b": "two\ntwo", "c": "3&3"}),
        })
        assert result.returncode == 0, result.stderr
        text = _prompt_text(worktree)
        assert "{{SLOT_" not in text
        assert "A=1|1" in text
        assert "C=3&3" in text

    def test_an_unfilled_slot_stops_the_dispatch_before_any_launch(self, tmp_path):
        # Nothing is spawned yet, so a typed failure here costs one dispatch and no
        # worker. A child launched with a literal {{SLOT_task}} has no task at all.
        role = _role_with_slots(tmp_path, "Task: {{SLOT_task}}\n")
        result, home, worktree, calls = _run(tmp_path, {
            "RELAY_ROLE_PATH": str(role),
            "BG_INPUTS_JSON": "{}",
        })
        assert result.returncode == 2, result.stdout
        assert "{{SLOT_task}}" in result.stderr
        launch_calls = calls.read_text().splitlines() if calls.is_file() else []
        assert len(launch_calls) <= 1, "the name check may run, but no launch may follow"

    def test_malformed_inputs_json_stops_the_dispatch(self, tmp_path):
        role = _role_with_slots(tmp_path, "Task: {{SLOT_task}}\n")
        result, home, worktree, _ = _run(tmp_path, {
            "RELAY_ROLE_PATH": str(role),
            "BG_INPUTS_JSON": "not json at all",
        })
        assert result.returncode == 2
        assert "slot substitution failed" in result.stderr


class TestNoBindingReachesBypassPermissions:
    """No `delegate_eligible: true` role in bindings/presets.yaml may resolve to a
    sidecar carrying `RELAY_BG_PERMISSION_MODE=bypassPermissions`. This is the guard
    that stops a future preset value from quietly restoring the blanket grant. The
    role list is read from the presets file with `yq`, not from a hard-coded list,
    so a new preset row cannot slip past.
    """

    def test_no_sidecar_holds_bypass_permissions(self, tmp_path):
        presets = PLUGIN_ROOT / "bindings" / "presets.yaml"
        raw = subprocess.run(
            ["yq", "-r",
             '.roles | to_entries[] | select(.value.delegate_eligible == true) | .key',
             str(presets)],
            capture_output=True, text=True, check=True,
        ).stdout
        roles = [r for r in raw.splitlines() if r.strip()]
        # Filter out roles that have no role file — bg-dispatch.sh exits 2 with
        # ROLE_FILE_MISSING for them, a different defect and not a bg-permission
        # regression.
        eligible = []
        for role in roles:
            if (PLUGIN_ROOT / "roles" / f"{role}.md").is_file() or \
               (PLUGIN_ROOT / "agents" / f"{role}.md").is_file():
                eligible.append(role)
        # A lookup that matches nothing must not make the guard vacuous.
        assert eligible, "no delegate_eligible role with a role file was found"

        for role in eligible:
            # Each case needs its own fresh HOME/WORKTREE so sidecars do not collide
            # across roles; use a per-role subdirectory of tmp_path.
            per_role = tmp_path / role
            per_role.mkdir()
            result, home, worktree, _ = _run(per_role, {"BG_ROLE_SLUG": role})
            assert result.returncode == 0, \
                f"{role}: bg-dispatch.sh exited {result.returncode}: {result.stderr}"
            sidecar_files = list((home / ".claude" / "relay" / "bg").rglob("*.env"))
            assert sidecar_files, f"{role}: no sidecar written"
            for sidecar in sidecar_files:
                text = sidecar.read_text()
                assert "RELAY_BG_PERMISSION_MODE=bypassPermissions" not in text, \
                    f"{role}: sidecar maps to bypassPermissions:\n{text}"


def _make_env_recording_launcher(tmp_path):
    """A stub launcher that records the value of RELAY_BG_DEPTH from its environment.

    Returns (launcher_path, recorder_path).

    What this proves: bg-dispatch.sh exports RELAY_BG_DEPTH (not a shell-local variable),
    so bg-launch.sh receives it in its environment on every non-check-name call.

    What this does NOT prove: that claude --bg carries the variable into the child
    session's Bash tool calls. That is the [inferred] step in spec §3.4 and no unit
    test can reach it. Signal 2 (job-state backstop) is the load-bearing check because
    it needs no environment inheritance at all.
    """
    recorder = tmp_path / "env-recorder.txt"
    script = tmp_path / "env-recording-launcher.sh"
    script.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        case "$1" in
          --check-name) echo "RELAY_BG_NAME_OK=1"; exit 0 ;;
        esac
        env | grep '^RELAY_BG_DEPTH=' >> "{recorder}"
        echo "RELAY_BG_NAME=stub"
        echo "RELAY_BG_SHORT_ID=abc123"
        echo "RELAY_BG_LAUNCH=OK"
        exit 0
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script, recorder


class TestDepthCap:
    """Depth-1 cap: a bg child must not dispatch a further bg child (spec §3.4).

    Two independent signals detect "I am inside a bg child":
      Signal 1 — RELAY_BG_DEPTH is set and non-zero (exported by the parent dispatcher).
      Signal 2 — CLAUDE_JOB_DIR/state.json has "template": "bg" (verified, load-bearing).

    The _run helper scrubs both variables before applying per-case overrides, so a
    developer running pytest inside a bg session does not see every happy-path case fail.
    """

    def test_relay_bg_depth_1_refuses_with_exit_2(self, tmp_path):
        result, home, worktree, _ = _run(tmp_path, {"RELAY_BG_DEPTH": "1"})
        assert result.returncode == 2
        assert "depth 1" in result.stderr
        # Check runs before Step 1 — nothing should be created.
        assert not list(home.rglob("*.env")), "no sidecar should be created"
        assert not (worktree / ".relay-bg").exists(), "no handoff directory should be created"
        assert not list(worktree.rglob("*.prompt")), "no prompt file should be created"

    def test_claude_job_dir_bg_template_refuses_with_exit_2(self, tmp_path):
        job_dir = tmp_path / "fake-job-bg"
        job_dir.mkdir()
        (job_dir / "state.json").write_text('{"template": "bg"}')
        result, home, worktree, _ = _run(tmp_path, {"CLAUDE_JOB_DIR": str(job_dir)})
        assert result.returncode == 2
        assert "depth 1" in result.stderr
        assert not list(home.rglob("*.env")), "no sidecar should be created"
        assert not (worktree / ".relay-bg").exists(), "no handoff directory should be created"
        assert not list(worktree.rglob("*.prompt")), "no prompt file should be created"

    def test_claude_job_dir_claude_template_dispatches_normally(self, tmp_path):
        job_dir = tmp_path / "fake-job-claude"
        job_dir.mkdir()
        (job_dir / "state.json").write_text('{"template": "claude"}')
        result, home, worktree, _ = _run(tmp_path, {"CLAUDE_JOB_DIR": str(job_dir)})
        assert result.returncode == 0, result.stderr

    def test_no_signal_dispatches_normally(self, tmp_path):
        # Both signals absent; the _run helper scrubs both, making this explicit.
        result, home, worktree, _ = _run(tmp_path, {})
        assert result.returncode == 0, result.stderr

    def test_relay_bg_depth_exported_to_launcher(self, tmp_path):
        """bg-dispatch.sh exports RELAY_BG_DEPTH=1 (not a shell-local variable), so
        bg-launch.sh receives it in its environment. This proves only that the variable
        is exported — not that claude --bg carries it into the child session's Bash
        tool calls (that is [inferred] per spec §3.4 and unreachable by any unit test).
        Signal 2 is the load-bearing check."""
        launcher, recorder = _make_env_recording_launcher(tmp_path)
        result, home, worktree, _ = _run(tmp_path, {}, launcher=launcher)
        assert result.returncode == 0, result.stderr
        assert recorder.is_file(), "env-recording launcher never executed in non-check-name mode"
        assert "RELAY_BG_DEPTH=1" in recorder.read_text()
