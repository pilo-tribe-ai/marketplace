import importlib.util
import os
import re
import stat
import subprocess
import textwrap
from types import SimpleNamespace

import pytest

from conftest import (
    PLUGIN_ROOT,
    TEMPLATE_LINE,
    deps_ok_env,
    fenced,
    parse_frontmatter,
    verify_check_command,
)

PARSER = PLUGIN_ROOT / "scripts" / "parse-verify-verdict.sh"
PROMPT_HELPER = PLUGIN_ROOT / "scripts" / "run-claude-prompt.sh"


def parse(text=None, path=None):
    args = ["bash", str(PARSER)]
    if path is not None:
        args.append(str(path))
    return subprocess.run(
        args,
        input=text if path is None else None,
        capture_output=True,
        text=True,
    )


def lines(result):
    return result.stdout.strip().splitlines()


class TestVerdictParser:
    @pytest.mark.parametrize(
        "verdict,label",
        [
            ("PASS", "clean"),
            ("FAIL", "findings"),
            ("BLOCKED", "no-answer"),
            ("SKIP", "no-answer"),
        ],
    )
    def test_each_verdict_maps_to_its_label(self, verdict, label):
        body = fenced(f"## Verification: x\n\n**Verdict:** {verdict}")
        r = parse(text=body)
        assert r.returncode == 0
        assert lines(r) == [f"VERIFY_VERDICT={verdict}", f"VERIFY_LABEL={label}"]

    def test_template_line_does_not_win_over_a_real_verdict(self):
        """Regression: a first-match parser reads the enum template as the verdict."""
        before = fenced(f"The report contract is:\n{TEMPLATE_LINE}\n\n**Verdict:** FAIL\n")
        r = parse(text=before)
        assert r.returncode == 0
        assert lines(r) == ["VERIFY_VERDICT=FAIL", "VERIFY_LABEL=findings"]

        after = fenced(f"**Verdict:** FAIL\n\nFor reference:\n{TEMPLATE_LINE}\n")
        r = parse(text=after)
        assert r.returncode == 0
        assert lines(r) == ["VERIFY_VERDICT=FAIL", "VERIFY_LABEL=findings"]

    def test_template_line_alone_is_no_verdict(self):
        r = parse(text=fenced(TEMPLATE_LINE))
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_last_single_token_verdict_wins(self):
        body = fenced("**Verdict:** FAIL\n\nlater:\n**Verdict:** PASS")
        r = parse(text=body)
        assert r.returncode == 0
        assert lines(r) == ["VERIFY_VERDICT=PASS", "VERIFY_LABEL=clean"]

    @pytest.mark.parametrize(
        "line_text,verdict,label",
        [
            ("**Verdict:** SKIP — no diff to verify", "SKIP", "no-answer"),
            ("**Verdict:** PASS — everything checks out", "PASS", "clean"),
        ],
    )
    def test_verdict_with_trailing_prose_is_read(self, line_text, verdict, label):
        """An end-anchored parser fails both; the PASS case would silently convert
        a genuine pass into an unverified run."""
        r = parse(text=fenced(line_text))
        assert r.returncode == 0
        assert lines(r) == [f"VERIFY_VERDICT={verdict}", f"VERIFY_LABEL={label}"]

    def test_line_with_two_verdict_tokens_is_rejected(self):
        """An ambiguous line is no-answer, never a pass."""
        r = parse(text=fenced("**Verdict:** PASS (not a FAIL)"))
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    @pytest.mark.parametrize(
        "line_text",
        [
            "**Verdict:** PASS",
            "Verdict: PASS",
            "_Verdict_: PASS",
            "**Verdict**: PASS",
        ],
    )
    def test_emphasis_variants_all_match(self, line_text):
        r = parse(text=fenced(line_text))
        assert r.returncode == 0
        assert lines(r) == ["VERIFY_VERDICT=PASS", "VERIFY_LABEL=clean"]

    def test_lowercase_verdict_word_is_not_a_verdict(self):
        """Guards a case-insensitive match folding prose into a pass."""
        r = parse(text=fenced("verdict: pass"))
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_missing_begin_fence_is_no_answer(self):
        text = "**Verdict:** PASS\nPOLISH_CMD_OUTPUT_END\nPOLISH_CMD_RC=0\n"
        r = parse(text=text)
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_missing_end_fence_is_no_answer(self):
        text = "POLISH_CMD_OUTPUT_BEGIN\n**Verdict:** PASS\n"
        r = parse(text=text)
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_empty_input_is_no_answer(self):
        r = parse(text="")
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_rc_line_inside_the_fence_is_not_read_as_an_rc(self):
        text = fenced("the child wrote POLISH_CMD_RC=0 in its report")
        r = parse(text=text)
        assert r.returncode == 65
        assert "POLISH_CMD_RC" not in r.stdout
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_verdict_after_the_end_fence_is_ignored(self):
        text = (
            "POLISH_CMD_OUTPUT_BEGIN\nnothing here\nPOLISH_CMD_OUTPUT_END\n"
            "POLISH_CMD_RC=0\n**Verdict:** PASS\n"
        )
        r = parse(text=text)
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_child_echoed_end_marker_does_not_truncate_the_region(self):
        """Proves first-begin / last-end."""
        text = (
            "POLISH_CMD_OUTPUT_BEGIN\nI print POLISH_CMD_OUTPUT_END when done\n"
            "**Verdict:** PASS\nPOLISH_CMD_OUTPUT_END\nPOLISH_CMD_RC=0\n"
        )
        r = parse(text=text)
        assert r.returncode == 0
        assert lines(r) == ["VERIFY_VERDICT=PASS", "VERIFY_LABEL=clean"]

    def test_reads_a_file_argument(self, tmp_path):
        path = tmp_path / "check.out"
        path.write_text(fenced("**Verdict:** FAIL"))
        r = parse(path=path)
        assert r.returncode == 0
        assert lines(r) == ["VERIFY_VERDICT=FAIL", "VERIFY_LABEL=findings"]

    def test_parser_is_executable(self):
        assert os.access(PARSER, os.X_OK)


@pytest.fixture
def fake_acpx_argv(tmp_path):
    """A stub `acpx` on PATH that logs one argv-per-element record per call.

    Logging each argument as its own NUL-terminated token (not newline- or
    space-joined) is load-bearing: the load-bearing prompt test feeds a
    prompt that itself contains embedded newlines, and `"$*"` (space-joined)
    or newline-joined logging cannot distinguish one argument holding a
    newline from two arguments — only NUL is guaranteed absent from a bash
    argv element, since bash strings cannot hold a NUL byte at all.
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    log = tmp_path / "acpx.args"
    binary = fakebin / "acpx"

    def install(turn_rc=0, turn_stdout=None, ensure_rc=0, close_rc=0):
        # The stdout a call should emit is written to its own file and cat'd
        # from there, rather than inlined into the stub script as a shell
        # literal: a Python repr() of a multi-line string encodes embedded
        # newlines as the two literal characters `\` `n`, and a single-quoted
        # bash literal built from that repr would print those two characters
        # instead of restoring a real newline. A file has no such problem.
        if turn_stdout is not None:
            stdout_file = tmp_path / f"turn_stdout_{len(list(tmp_path.glob('turn_stdout_*')))}.txt"
            stdout_file.write_text(turn_stdout)
            emit = f"cat {str(stdout_file)!r}\n"
        else:
            emit = ""
        binary.write_text(
            textwrap.dedent(f"""\
                #!/usr/bin/env bash
                printf '%s\\0' "$@" >> {str(log)!r}
                printf '%s\\0' '<<<CALL>>>' >> {str(log)!r}
                if [ "${{4:-}}" = "sessions" ]; then
                  if [ "${{5:-}}" = "ensure" ]; then
                    exit {ensure_rc}
                  fi
                  if [ "${{5:-}}" = "close" ]; then
                    exit {close_rc}
                  fi
                  exit 0
                fi
                """)
            + emit
            + f"exit {turn_rc}\n"
        )
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env = dict(os.environ)
        env["PATH"] = f"{fakebin}:{env['PATH']}"
        return env

    return SimpleNamespace(worktree=worktree, log=log, install=install)


def calls(log):
    """Read the NUL-delimited call log back into a list of argv lists."""
    if not log.exists():
        return []
    data = log.read_bytes()
    tokens = data.split(b"\x00")
    if tokens and tokens[-1] == b"":
        tokens = tokens[:-1]
    tokens = [t.decode("utf-8") for t in tokens]
    result = []
    current = []
    for tok in tokens:
        if tok == "<<<CALL>>>":
            result.append(current)
            current = []
        else:
            current.append(tok)
    return result


class TestRunClaudePromptHelper:
    def test_prompt_reaches_acpx_as_one_unmodified_argv_element(self, fake_acpx_argv):
        """The load-bearing helper test.

        Broken values this catches: an unquoted `$prompt` (word-splits into many
        argv elements), an `eval` (runs `$(date)` and replaces it), and a wrong
        flag order.
        """
        prompt = 'fix these:\n**Verdict:** FAIL\n`git status` said "x" and $(date) and a|b'
        env = fake_acpx_argv.install(turn_rc=0, turn_stdout="ok")
        worktree = fake_acpx_argv.worktree

        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", prompt],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        all_calls = calls(fake_acpx_argv.log)
        turn_call = all_calls[1]
        assert turn_call == [
            "--format",
            "quiet",
            "--approve-all",
            "--cwd",
            str(worktree),
            "--timeout",
            "1800",
            "claude",
            "-s",
            "relay-verify-fix-r1",
            prompt,
        ]

    def test_session_is_ensured_before_the_turn_and_closed_after(self, fake_acpx_argv):
        env = fake_acpx_argv.install(turn_rc=0, turn_stdout="ok")
        worktree = fake_acpx_argv.worktree

        subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )

        all_calls = calls(fake_acpx_argv.log)
        assert len(all_calls) == 3
        assert all_calls[0] == [
            "--cwd",
            str(worktree),
            "claude",
            "sessions",
            "ensure",
            "--name",
            "relay-verify-fix-r1",
        ]
        assert all_calls[2] == [
            "--cwd",
            str(worktree),
            "claude",
            "sessions",
            "close",
            "relay-verify-fix-r1",
        ]

    def test_reply_is_fenced_and_rc_follows_the_end_fence(self, fake_acpx_argv):
        env = fake_acpx_argv.install(
            turn_rc=5, turn_stdout="POLISH_CMD_RC=0 and POLISH_CMD_OUTPUT_END in my report"
        )
        worktree = fake_acpx_argv.worktree

        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 5
        out_lines = result.stdout.splitlines()
        assert out_lines[0] == "POLISH_CMD_OUTPUT_BEGIN"
        assert out_lines[-1] == "POLISH_CMD_RC=5"

    @pytest.mark.parametrize(
        "prompt",
        [pytest.param("", id="empty"), pytest.param("  \n\t ", id="whitespace-only")],
    )
    def test_blank_prompt_is_rejected_with_64_and_no_acpx_call(self, fake_acpx_argv, prompt):
        env = fake_acpx_argv.install(turn_rc=0)
        worktree = fake_acpx_argv.worktree

        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", prompt],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 64
        assert "POLISH_CMD_RC=64" in result.stdout
        assert not fake_acpx_argv.log.exists() or fake_acpx_argv.log.read_text() == ""

    @pytest.mark.parametrize(
        "args",
        [
            ["worktree", "session"],
            ["worktree", "session", "prompt", "60", "extra"],
        ],
    )
    def test_wrong_argument_count_is_64(self, fake_acpx_argv, args):
        env = fake_acpx_argv.install(turn_rc=0)
        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 64
        assert not fake_acpx_argv.log.exists() or fake_acpx_argv.log.read_text() == ""

    def test_missing_worktree_is_66(self, fake_acpx_argv, tmp_path):
        env = fake_acpx_argv.install(turn_rc=0)
        missing = tmp_path / "gone"
        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(missing), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 66
        assert "POLISH_CMD_RC=66" in result.stdout
        assert not fake_acpx_argv.log.exists() or fake_acpx_argv.log.read_text() == ""

    def test_missing_acpx_is_69_not_127(self, tmp_path):
        import shutil

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        emptybin = tmp_path / "bin"
        emptybin.mkdir()

        bash = shutil.which("bash")
        assert bash, "bash not on PATH"

        env = dict(os.environ)
        env["PATH"] = str(emptybin)

        result = subprocess.run(
            [bash, str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 69
        assert "POLISH_CMD_RC=69" in result.stdout
        assert "POLISH_CMD_RC=127" not in result.stdout

    def test_ensure_failure_is_reported_and_no_turn_is_attempted(self, fake_acpx_argv):
        env = fake_acpx_argv.install(ensure_rc=3, turn_rc=0)
        worktree = fake_acpx_argv.worktree

        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 3
        assert "POLISH_CMD_RC=3" in result.stdout
        assert len(calls(fake_acpx_argv.log)) == 1

    @pytest.mark.parametrize(
        "extra_arg,env_vars,expected_timeout",
        [
            (["99"], {"RELAY_VERIFY_TIMEOUT": "42"}, "99"),
            ([], {"RELAY_VERIFY_TIMEOUT": "42"}, "42"),
            ([], {"RELAY_POLISH_TIMEOUT": "77"}, "77"),
            ([], {}, "1800"),
        ],
    )
    def test_timeout_precedence(self, fake_acpx_argv, extra_arg, env_vars, expected_timeout):
        env = fake_acpx_argv.install(turn_rc=0, turn_stdout="ok")
        for key in ("RELAY_VERIFY_TIMEOUT", "RELAY_POLISH_TIMEOUT"):
            env.pop(key, None)
        env.update(env_vars)
        worktree = fake_acpx_argv.worktree

        subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it", *extra_arg],
            capture_output=True,
            text=True,
            env=env,
        )

        all_calls = calls(fake_acpx_argv.log)
        turn_call = all_calls[1]
        idx = turn_call.index("--timeout")
        assert turn_call[idx + 1] == expected_timeout

    def test_close_failure_does_not_change_the_reported_rc(self, fake_acpx_argv):
        env = fake_acpx_argv.install(close_rc=9, turn_rc=0, turn_stdout="ok")
        worktree = fake_acpx_argv.worktree

        result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert result.stdout.splitlines()[-1] == "POLISH_CMD_RC=0"

    def test_helper_is_executable(self):
        assert os.access(PROMPT_HELPER, os.X_OK)

    @pytest.mark.parametrize("path", [PARSER, PROMPT_HELPER])
    def test_both_scripts_pass_bash_syntax_check(self, path):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


class TestHelperAndParserAgree:
    def test_a_report_round_trips_from_helper_to_parser(self, fake_acpx_argv):
        report = (
            "## Verification: x\n\n"
            f"{TEMPLATE_LINE}\n\n"
            "### Findings\n"
            "- one\n- two\n- three\n\n"
            "**Verdict:** PASS"
        )
        env = fake_acpx_argv.install(turn_rc=0, turn_stdout=report)
        worktree = fake_acpx_argv.worktree

        helper_result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert helper_result.returncode == 0

        parsed = subprocess.run(
            ["bash", str(PARSER)],
            input=helper_result.stdout,
            capture_output=True,
            text=True,
        )
        assert parsed.returncode == 0
        assert lines(parsed) == ["VERIFY_VERDICT=PASS", "VERIFY_LABEL=clean"]

    def test_a_silent_child_is_no_answer_not_a_pass(self, fake_acpx_argv):
        env = fake_acpx_argv.install(turn_rc=0, turn_stdout=None)
        worktree = fake_acpx_argv.worktree

        helper_result = subprocess.run(
            ["bash", str(PROMPT_HELPER), str(worktree), "relay-verify-fix-r1", "do it"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert helper_result.stdout == "POLISH_CMD_RC=0\n"

        parsed = subprocess.run(
            ["bash", str(PARSER)],
            input=helper_result.stdout,
            capture_output=True,
            text=True,
        )
        assert parsed.returncode == 65
        assert lines(parsed) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]


# --- command and skill guards are appended below by the command/skill step ---

CMD = PLUGIN_ROOT / "commands" / "verify.md"
SKILL = PLUGIN_ROOT / "skills" / "verifying-until-clean" / "SKILL.md"
L3_PREFLIGHT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"
WT_PREFLIGHT = PLUGIN_ROOT / "scripts" / "worktree-preflight.sh"


def _norm(t):
    return re.sub(r"\s+", " ", t.lower().replace("`", "").replace("*", "").replace("—", "-"))


_spec = importlib.util.spec_from_file_location(
    "validate_l3_command", PLUGIN_ROOT / "scripts" / "validate_l3_command.py"
)
vl3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vl3)


class TestVerifyCommandFrontmatter:
    def test_command_exists(self):
        assert CMD.is_file()

    def test_description_is_an_imperative_menu_label(self):
        fm, _ = parse_frontmatter(CMD)
        desc = str(fm.get("description", ""))
        assert desc
        assert "Use when" not in desc

    def test_argument_hint_names_the_rounds_bound_and_the_two_engines(self):
        """4.32.0: the loop carries a substrate for two engines, so the hint has to
        name them. A hint that still read `[--rounds 1-5]` would hide the flag that
        decides whether the run asks a question at all."""
        fm, _ = parse_frontmatter(CMD)
        hint = fm["argument-hint"]
        assert "[--rounds 1-5]" in hint
        assert "--engine in-session|acpx" in hint
        assert "--agent claude" in hint
        # The three engines the loop cannot run must not be advertised here.
        for absent in ("smart-routing", "bg-sessions", "session-tree"):
            assert absent not in hint

    def test_model_invocation_is_enabled(self):
        # 4.30.0: the model may start /relay:verify through the SlashCommand tool.
        fm, _ = parse_frontmatter(CMD)
        assert "disable-model-invocation" not in fm

    @pytest.mark.parametrize("tool", ["Bash", "Workflow", "Skill"])
    def test_allowed_tools(self, tool):
        fm, _ = parse_frontmatter(CMD)
        assert tool in str(fm["allowed-tools"])


class TestVerifyCommandBody:
    def test_sources_check_deps_guarded(self):
        """Issue #110: verify.md's Step 0 collapsed into one call to
        scripts/l3-preflight.sh, which sources check-deps.sh internally."""
        _, body = parse_frontmatter(CMD)
        assert re.search(r'l3-preflight\.sh"\s+verify\s+"\$ARGUMENTS"[^\n]*\|\|\s*exit 1', body)
        script = L3_PREFLIGHT.read_text()
        assert re.search(r'source\s+"\$HERE/check-deps\.sh"\s*\|\|\s*exit 1', script)

    def test_default_round_cap_and_bound_are_stated(self):
        _, body = parse_frontmatter(CMD)
        assert "RELAY_VERIFY_ROUNDS" in body
        norm = _norm(body)
        assert "the default is 3 rounds" in norm
        assert "from 1 to 5" in norm

    def test_names_the_backing_skill(self):
        _, body = parse_frontmatter(CMD)
        assert "relay:verifying-until-clean" in body

    def test_the_axis_is_resolved_by_the_shared_parser(self):
        """4.32.0 replaces "no axis here". The axis picks a SUBSTRATE, not a worker:
        no role is dispatched, so there is still nothing for an agent to be. It is
        resolved by the one shared script, so an engine pin behaves here exactly as
        it behaves for /relay:implement."""
        _, body = parse_frontmatter(CMD)
        assert "parse-engine-agent.sh" in body
        assert "--engine" in body
        assert "--agent" in body
        assert "RELAY_VERIFY_ENGINE" in body

    def test_the_default_engine_is_acpx(self):
        """4.47.0 moves this command's default to acpx, so the loop keeps this
        session's context by default. The command declares the default in prose.
        4.48.0 moved Step 0's own setting of it out of this file and into
        scripts/l3-preflight.sh's verify) case block."""
        _, body = parse_frontmatter(CMD)
        norm = _norm(body)
        assert "the default is acpx" in norm
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert 'export RELAY_DEFAULT_ENGINE="acpx"' in script
        assert 'export RELAY_DEFAULT_AGENT="claude"' in script

    def test_in_session_is_still_reachable_and_asks_nothing(self):
        """The escape hatch matters more now than it did: an acpx default reaches a
        machine with no acpx installed, and it is also the only engine that turns no
        approval gate off."""
        _, body = parse_frontmatter(CMD)
        norm = _norm(body)
        assert "--engine in-session" in norm
        assert "asks nothing" in norm

    @pytest.mark.parametrize(
        "engine", ["smart-routing", "bg-sessions", "session-tree"]
    )
    def test_the_three_engines_with_no_substrate_are_rejected(self, engine, tmp_path):
        """None of the three carries this loop's deadline, its state directory, or
        its commit per round. Accepting one would be prose with no implementation.

        Issue #110 moved the rejecting `case` into scripts/l3-preflight.sh; run
        the script directly to prove the rejection still fires end to end."""
        _, body = parse_frontmatter(CMD)
        assert "is not supported by /relay:verify" in body
        assert "supported: in-session | acpx" in body
        script = L3_PREFLIGHT.read_text()
        # The rejection is a case over the resolved engine, not a per-name check.
        assert "in-session|acpx) ;;" in script
        result = subprocess.run(
            ["bash", str(L3_PREFLIGHT), "verify", f"--engine {engine}"],
            capture_output=True, text=True, env=deps_ok_env(tmp_path),
        )
        assert result.returncode == 1
        assert "is not supported by /relay:verify" in result.stderr

    def test_branch_guard_reads_the_printed_state(self):
        """Issue #110: verify.md's Step 0.5 collapsed into one call to
        scripts/worktree-preflight.sh --branch-guard verify, which reads the
        RELAY_WT_* block itself."""
        _, body = parse_frontmatter(CMD)
        assert "worktree-preflight.sh" in body
        assert "--branch-guard verify" in body
        script = WT_PREFLIGHT.read_text()
        assert "RELAY_WT_STATE" in script
        assert "refusing to run on the default branch" in _norm(script)

    def test_does_not_create_or_enter_a_worktree(self):
        """It verifies the branch the user is already on."""
        _, body = parse_frontmatter(CMD)
        assert "EnterWorktree" not in body
        assert "--create" not in body

    def test_declares_no_loop_identity_of_its_own(self):
        """The command's whole job, post-extraction, is to hand off to the skill.

        It must NOT name a loop id. The skill owns one identity and takes no
        parameter, because `/relay:implement --verify` has to produce exactly what
        `/relay:implement` then `/relay:verify` produces — same node labels, same acpx
        session names, same state directory. A per-caller name breaks that equality.
        """
        _, body = parse_frontmatter(CMD)
        assert "relay:verifying-until-clean" in body
        assert "LOOP_ID" not in body


class TestVerifyLoopSkillBody:
    """These assertions moved from TestVerifyCommandBody: the content they pin now
    lives in the skill, under the single hardcoded `verify` identity."""

    @pytest.mark.parametrize(
        "needle",
        [
            "scripts/run-claude-command.sh",
            "scripts/run-claude-prompt.sh",
            "scripts/parse-verify-verdict.sh",
        ],
    )
    def test_names_both_helpers_and_the_parser(self, needle):
        _, body = parse_frontmatter(SKILL)
        assert needle in body

    def test_exit_signal_is_the_verdict_not_the_findings_count(self):
        """The doctrine line; without it a future editor reintroduces a
        findings-count exit that never fires."""
        _, body = parse_frontmatter(SKILL)
        assert "the findings count is never read" in _norm(body)

    def test_state_lives_outside_the_working_tree(self):
        """A scratch directory inside the working tree makes `git status --short`
        non-empty every round, which silently defeats the fix-noop check and lets
        `git add -A` commit the run's own logs."""
        _, body = parse_frontmatter(SKILL)
        assert "rev-parse --absolute-git-dir" in body
        assert ".relay/verify" not in body

    def test_no_undefined_run_id_placeholder(self):
        _, body = parse_frontmatter(SKILL)
        assert "<run-id>" not in body

    @pytest.mark.parametrize(
        "needle", ["phase: 'Verify'", "opts.model: 'sonnet'", "opts.effort: 'low'"]
    )
    def test_wrapper_tier_is_pinned(self, needle):
        _, body = parse_frontmatter(SKILL)
        assert needle in body

    def test_records_a_skipped_node_as_skipped(self):
        _, body = parse_frontmatter(SKILL)
        assert "never as passed" in _norm(body)

    def test_fix_noop_forces_an_honest_exit(self):
        _, body = parse_frontmatter(SKILL)
        assert "fix-noop" in body
        assert "two consecutive" in _norm(body)

    @pytest.mark.parametrize(
        "needle",
        [
            "relay-verify-simplify-r",
            "relay-verify-review-r",
            "relay-verify-check-r",
            "relay-verify-fix-r",
        ],
    )
    def test_session_names_are_literal_and_round_indexed(self, needle):
        """One identity, spelled out. Both callers open these exact session names.

        An earlier design built the names from a `<LOOP_ID>` placeholder so the two
        callers could differ. That is now a defect, not a feature: the two paths must
        be byte-equivalent, so no placeholder may survive.
        """
        _, body = parse_frontmatter(SKILL)
        assert needle in body
        assert "<LOOP_ID>" not in body


class TestVerifyCommandValidator:
    def test_validator_reports_only_the_classifier_exemption(self):
        """Broken values this catches: a --kind flag added later, and any cited
        relay:<token> not in _KNOWN."""
        _, body = parse_frontmatter(CMD)
        errs = vl3.check_command(body, require_branch=False)
        assert errs == ["missing task-kind classifier node"]
        assert not any("--kind" in e for e in errs)
        assert not any("unknown relay vocabulary" in e for e in errs)

    def test_body_avoids_the_classifier_stem(self):
        """Pins the prose-to-test coupling directly, so the failure names the
        cause instead of surfacing as a confusing list mismatch in the previous
        test.

        Word-choice note (moved here from verify.md): the command maps the
        verdict to a label. It has no task-kind node, and the four-step round is
        the same for every kind of task, so there is nothing for such a node to
        select. Naming that missing node in the command with the word the
        validator scans for would satisfy the check with prose that does not do
        the job it claims, and it would flip the expected error list in the
        previous test."""
        _, body = parse_frontmatter(CMD)
        assert "classif" not in body.lower().replace("--classify", "")

    def test_skill_is_known_vocabulary(self):
        assert "verifying-until-clean" in vl3._KNOWN

    def test_command_is_not_in_the_validator_checks_dict(self):
        """main()'s dict requires a task-kind classifier node, which this command
        does not have; the guards for it survive through the previous test
        instead."""
        src = (PLUGIN_ROOT / "scripts" / "validate_l3_command.py").read_text()
        assert '"verify.md"' not in src


class TestVerifySkill:
    def test_skill_exists(self):
        assert SKILL.is_file()

    def test_frontmatter(self):
        fm, _ = parse_frontmatter(SKILL)
        assert fm["name"] == "verifying-until-clean"
        assert fm["user-invocable"] is False
        assert fm.get("description")

    @pytest.mark.parametrize("label", ["clean", "findings", "no-answer"])
    def test_description_names_all_three_labels(self, label):
        fm, _ = parse_frontmatter(SKILL)
        assert label in str(fm["description"])

    def test_no_relay_vocab_block(self):
        """The only honest l1-shape is loop-until-clean, which improve-loop
        already declares."""
        _, body = parse_frontmatter(SKILL)
        assert "```relay-vocab" not in body

    def test_names_the_owner_of_the_shape(self):
        _, body = parse_frontmatter(SKILL)
        assert "loop-until-clean" in body
        assert "improve-loop" in body

    @pytest.mark.parametrize("verdict", ["PASS", "FAIL", "BLOCKED", "SKIP"])
    def test_verdict_table_names_every_verdict_as_a_token(self, verdict):
        _, body = parse_frontmatter(SKILL)
        assert f"`{verdict}`" in body

    @pytest.mark.parametrize("label", ["clean", "findings", "no-answer"])
    def test_labels_are_backticked_tokens(self, label):
        _, body = parse_frontmatter(SKILL)
        assert f"`{label}`" in body

    @pytest.mark.parametrize(
        "needle",
        [
            "RELAY_VERIFY_RESULT=clean",
            "RELAY_VERIFY_RESULT=findings",
            "RELAY_VERIFY_RESULT=unverified",
        ],
    )
    def test_carries_the_three_terminal_states(self, needle):
        _, body = parse_frontmatter(SKILL)
        assert needle in body

    def test_documents_the_parser_trap(self):
        _, body = parse_frontmatter(SKILL)
        assert "exactly one verdict token" in _norm(body)

    def test_states_skip_and_blocked_are_not_a_pass(self):
        """Mirrors the identical command-doc assertion, so the command and the
        skill cannot drift apart on the one rule that decides the outcome."""
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "a skip verdict is not a pass" in norm
        assert "a blocked verdict is not a pass" in norm

    def test_body_nonempty(self):
        _, body = parse_frontmatter(SKILL)
        assert len(body) > 200


class TestBlockedRetryRouteIsStated:
    """Regression, reduced to a single-document assertion. Earlier drafts had the
    command doc and the skill disagree about the BLOCKED route — the skill
    discarded the retry's result and always exited unverified, while the command
    doc let the retry's result stand, so a retry that came back PASS could reach
    `clean`. That two-copy drift check is superseded now: the mechanics live in
    the skill only, so there is only one copy left to check, and
    `TestLoopMechanicsLiveOnlyInTheSkill` (the anti-drift tripwire) is what stops
    a second copy from reappearing in either command file."""

    def test_skill_says_the_retry_result_stands(self):
        _, skill_body = parse_frontmatter(SKILL)
        norm = _norm(skill_body)
        assert "retry the verify step once in the same round" in norm
        assert "then let the second result stand" in norm
        assert "then exit as explicitly unverified" not in norm


def _extract_branch_guard(body):
    """Pull the Step 0.5 bash block out of the command doc.

    The guard is executable shell that ships inside a markdown fence, so the
    only honest way to test it is to run the same text the command runs. An
    assertion on the prose alone passes even when the `case` arm it describes
    was deleted.
    """
    for block in re.findall(r"```bash\n(.*?)```", body, re.DOTALL):
        if "worktree-preflight.sh" in block and "--branch-guard" in block:
            return block
    raise AssertionError("verify.md has no Step 0.5 bash block")


def _init_guard_repo(path, default="main"):
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ("init", "-q", f"--initial-branch={default}"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", "-C", str(path), *args], capture_output=True, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"], capture_output=True, check=True
    )
    return path


def _run_branch_guard(cwd):
    _, body = parse_frontmatter(CMD)
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    return subprocess.run(
        ["bash", "-c", _extract_branch_guard(body)],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


class TestVerifyBranchGuardExecution:
    """Run the shipped Step 0.5 block, rather than asserting on its prose."""

    def test_feature_branch_is_allowed(self, tmp_path):
        repo = _init_guard_repo(tmp_path / "repo")
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-q", "-b", "feature/x"],
            capture_output=True,
            check=True,
        )
        r = _run_branch_guard(repo)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_default_branch_is_refused(self, tmp_path):
        repo = _init_guard_repo(tmp_path / "repo")
        r = _run_branch_guard(repo)
        assert r.returncode == 1
        assert "refusing to run on the default branch" in r.stdout

    def test_detached_head_is_refused(self, tmp_path):
        """A detached HEAD classifies as `stray`, which the state `case` allows.

        The loop commits every round, and a commit made on a detached HEAD is
        reachable from no branch: the moment the user checks out a branch the
        verified work is gone. Without this guard the run reports
        RELAY_VERIFY_RESULT=clean over commits that have already been lost.
        """
        repo = _init_guard_repo(tmp_path / "repo")
        sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-q", sha], capture_output=True, check=True
        )
        r = _run_branch_guard(repo)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "detached HEAD" in r.stdout

    def test_outside_a_git_checkout_is_refused(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        r = _run_branch_guard(plain)
        assert r.returncode == 1


IMPLEMENT_CMD = PLUGIN_ROOT / "commands" / "implement.md"
# 4.38.0 moved implement's Steps 3-3.5-4 (including the verify-until-clean tail
# mechanics) into this skill. Any check that reads IMPLEMENT_CMD for that tail's
# prose must read this file instead — the prose moved, it did not disappear.
SPINE_SKILL = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"

# Every one of these strings names a piece of loop mechanics that now lives only in
# `skills/verifying-until-clean/SKILL.md`. A copy of any of them in either command file
# is the two-copy drift Part A1 of the spec rejects.
_MECHANICS_NEEDLES = (
    "scripts/run-claude-command.sh",
    "scripts/run-claude-prompt.sh",
    "scripts/parse-verify-verdict.sh",
    "POLISH_CMD_",
    "rev-parse --absolute-git-dir",
    "STATE_ROOT",
    "ROUND_DIR",
    "fix-noop",
    "RELAY_VERIFY_RESULT=",
    "phase: 'Verify'",
    "opts.model:",
)


class TestLoopMechanicsLiveOnlyInTheSkill:
    """The anti-drift tripwire. `TestBlockedRetryRouteIsStated` explains why a
    two-copy drift check is no longer enough on its own: once the mechanics live in
    one place, there is only one copy to check for the wording it pins. This class
    covers the other half — that no command file has quietly grown a second copy of
    the mechanics themselves. Break this on purpose (append any one needle to a
    command file) to see it fail red, then restore the file."""

    @pytest.mark.parametrize(
        "path", [CMD, IMPLEMENT_CMD, SPINE_SKILL],
        ids=["verify.md", "implement.md", "running-implement-spine/SKILL.md"],
    )
    @pytest.mark.parametrize("needle", _MECHANICS_NEEDLES)
    def test_tripwire_no_command_restates_the_mechanics(self, path, needle):
        body = path.read_text()
        assert needle not in body, (
            f"{path.name} restates loop mechanics ({needle!r}); this belongs only in "
            "skills/verifying-until-clean/SKILL.md"
        )

    @pytest.mark.parametrize("needle", _MECHANICS_NEEDLES)
    def test_tripwire_needles_are_real_not_vacuous(self, needle):
        """Each needle must actually exist in the skill, so the tripwire above proves
        something: a needle missing everywhere would pass the negative test above
        even after the whole mechanics block was deleted rather than copied."""
        _, body = parse_frontmatter(SKILL)
        assert needle in body, f"needle {needle!r} is not in the skill; the tripwire is vacuous"

    @pytest.mark.parametrize("path", [CMD, IMPLEMENT_CMD], ids=["verify.md", "implement.md"])
    def test_both_commands_cite_the_skill(self, path):
        body = path.read_text()
        assert "relay:verifying-until-clean" in body


class TestOneLoopIdentity:
    """`/relay:implement --verify` must be exactly equivalent to `/relay:implement`
    followed by `/relay:verify` — same node labels, same acpx session names, same
    state directory.

    Equivalence holds only while there is exactly one identity. An earlier design
    parameterized the skill so each caller could name its own; reintroducing that
    breaks the contract silently, because both paths still work and only their
    side effects diverge.
    """

    def test_no_loop_id_placeholder_survives_anywhere_in_the_plugin(self):
        offenders = []
        for path in PLUGIN_ROOT.rglob("*.md"):
            if "LOOP_ID" in path.read_text():
                offenders.append(str(path.relative_to(PLUGIN_ROOT)))
        assert not offenders, (
            "a per-caller loop identity reappeared in: "
            f"{offenders}. The skill takes the engine and nothing else."
        )

    def test_the_skill_takes_the_engine_and_nothing_else(self):
        """4.32.0 replaces "takes no parameter". The engine is the one input, and it
        picks a node shape. It must not become a way to rename anything, or the two
        callers stop producing the same run."""
        _, body = parse_frontmatter(SKILL)
        assert "takes the engine and nothing else" in body
        norm = _norm(body)
        assert "no\ncaller may rename a node, a session, or the state directory" in body or (
            "caller may rename a node, a session, or the state directory" in norm
        )
        assert "it does not rename a node, a session or the state directory" in norm

    @pytest.mark.parametrize(
        "needle",
        ["relay-verify-simplify-r", "relay-verify-check-r", "verify-loop-report"],
    )
    def test_both_callers_reach_the_same_literal_names(self, needle):
        """The names live in the skill, once. Neither command may restate them,
        because a restated name is a name that can drift."""
        _, skill_body = parse_frontmatter(SKILL)
        assert needle in skill_body
        for cmd in (CMD, IMPLEMENT_CMD, SPINE_SKILL):
            assert needle not in cmd.read_text(), (
                f"{cmd.name} restates the loop name {needle!r}; only the skill may."
            )


class TestEachRunResetsItsOwnState:
    """Regression: the state directory outlives the run that wrote it.

    `$STATE_ROOT/state` carries the terminal `EXIT` of the previous run, and every
    node that reads a non-`continue` `EXIT` records itself `skipped`. So a second
    loop run in the same worktree did nothing and still reported. The report node
    had the matching fault, reading round records that belonged to the earlier run.
    Both failures are silent: the run looks finished.
    """

    def test_the_reset_clears_only_the_round_directories(self):
        """`rm -rf "$STATE_ROOT"` removed the whole directory, including anything
        this loop does not own. The literal `round-*` pattern names what goes."""
        _, body = parse_frontmatter(SKILL)
        assert 'rm -rf "$STATE_ROOT"/round-*' in body
        assert "EXIT=continue" in body
        assert 'rm -rf "$STATE_ROOT"\n' not in body, (
            "the bare form deletes files outside the round directories"
        )

    def test_the_reset_is_pinned_to_the_start_of_the_run(self):
        """A reset in any later node destroys the evidence of the round that just
        ran, which is the opposite of the bug being fixed."""
        _, body = parse_frontmatter(SKILL)
        assert "Do not move it into a later" in body

    def test_the_reset_explains_the_silent_failure_it_prevents(self):
        _, body = parse_frontmatter(SKILL)
        assert "reads the first run's state file" in body


def _section(body, heading):
    """The slice of the skill under one heading, up to the next heading of any depth."""
    assert heading in body, f"heading {heading!r} is not in the skill"
    rest = body.split(heading, 1)[1]
    return rest.split("\n## ", 1)[0].split("\n### ", 1)[0]


class TestTheResetRunsInAnAgentlessNode:
    """Regression: one refused node ended a whole thirteen-node run.

    `verify-simplify-r1` used to hold the reset AND start a child Claude session
    with the approvals off. Claude Code's auto-mode rule `Create Unsafe Agents`
    refused exactly that node in a live run (`wf_55ed608d-904`). A refused node
    never runs, so it wrote no state file, and the twelve nodes after it read a
    missing file and recorded themselves skipped.

    Splitting the reset into a node that starts no child agent removes the single
    point of failure: the rule has nothing in `verify-init` to match, and a refused
    simplify leaf now costs one step instead of the whole tail.
    """

    NODE_HEADING = "### The `verify-init` node"

    def test_the_init_node_runs_before_round_one(self):
        _, body = parse_frontmatter(SKILL)
        assert "`verify-init` runs first, before round 1." in body
        assert body.index("verify-init") < body.index("Each round `N` then holds four nodes")

    def test_the_init_node_starts_no_child_agent(self):
        """The whole reason the node exists. A helper call here would put the
        approvals-off child back into the node that seeds the state."""
        _, body = parse_frontmatter(SKILL)
        section = _section(body, self.NODE_HEADING)
        assert "This node starts no child agent." in section
        assert "runs no `acpx` command" in section
        for helper in ("run-claude-command.sh", "run-claude-prompt.sh"):
            assert helper not in section, (
                f"{helper} in the init node reintroduces the refused shape"
            )

    def test_the_init_node_seeds_the_state_file(self):
        _, body = parse_frontmatter(SKILL)
        section = _section(body, self.NODE_HEADING)
        assert "EXIT=continue" in section
        assert 'rm -rf "$STATE_ROOT"/round-*' in section

    def test_the_skill_records_why_the_reset_moved(self):
        """Without the reason, a later editor folds the reset back into the
        simplify leaf to save a node and silently restores the failure."""
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "a stopped simplify leaf costs one step and not the run" in norm
        assert "Create Unsafe Agents" in body


class TestMissingStateIsNotASkip:
    """A skipped node says the loop decided to stop. A node that finds no state
    file says the loop never started. Recording both as `skipped` hides a refused
    or dead init node behind an orderly-looking record."""

    def test_the_two_conditions_are_distinguished(self):
        _, body = parse_frontmatter(SKILL)
        section = _section(body, "### A missing state file is not a skip")
        assert "failed:no-state" in section
        assert "verify-init-did-not-run" in section

    def test_no_state_is_a_recorded_node_value(self):
        _, body = parse_frontmatter(SKILL)
        assert "`failed:no-state`" in body.split("### Round state", 1)[1]

    def test_the_evidence_rules_carry_the_distinction(self):
        _, body = parse_frontmatter(SKILL)
        rules = _section(body, "## Evidence rules")
        assert "failed:no-state" in rules
        assert "never as\n  skipped" in rules or "never as skipped" in _norm(rules)

    def test_the_report_names_an_absent_record_rather_than_dropping_it(self):
        """A refused node writes no line at all. A report that prints only the
        keys it found shows a short round as a complete one."""
        _, body = parse_frontmatter(SKILL)
        report = _section(body, "### The report node")
        assert "missing" in report
        assert "RELAY_VERIFY_MISSING=" in report
        assert "never read as a pass" in report


class TestApprovalGateConsent:
    """Step 0 asks the user to agree to the approvals-off child sessions.

    Claude Code's auto-mode rule `Create Unsafe Agents` is a soft block that
    clears at the [named+specifics] bar: the user must name the agent that runs
    with sandbox or approvals off. A bare `/relay:verify` names the task, and the
    rule states that naming the enclosing task does not name the dangerous step.
    So the loop was refused mid-run with no way to clear.

    The question is consent that did not exist before, not wording aimed at the
    classifier. These tests pin that it stays truthful and stays refusable.
    """

    HEADING = "## Step 0 — get agreement for the approval gate"

    def _step0(self):
        _, body = parse_frontmatter(SKILL)
        return body.split(self.HEADING, 1)[1].split("\n## ", 1)[0]

    def test_step_0_precedes_node_generation(self):
        _, body = parse_frontmatter(SKILL)
        assert body.index(self.HEADING) < body.index("## Generating the loop nodes")

    @pytest.mark.parametrize(
        "needle",
        [
            "--approve-all",
            "no person approves each step",
            "every round of this run",
        ],
        ids=["approvals-off", "no-per-action-gate", "standing-grant"],
    )
    def test_the_question_names_what_makes_the_loop_dangerous(self, needle):
        """The three items are the rule's must-name slot. Drop any one and the
        question stops being informed consent."""
        assert needle in self._step0()

    def test_the_question_uses_the_ask_tool(self):
        assert "AskUserQuestion" in self._step0()

    def test_step_0_runs_only_under_acpx(self):
        """4.32.0. The rule fires on an approvals-off child process. In-session starts
        none, so there is no danger to name. A question that names an absent danger is
        not consent, and the next editor deletes it as ceremony."""
        step0 = self._step0()
        norm = _norm(step0)
        assert "only when the engine is acpx" in norm
        assert "ask nothing" in norm

    def test_the_skill_states_the_engine_does_not_rename_anything(self):
        """Equivalence rests on this: /relay:implement --verify and /relay:verify must
        still produce the same nodes and the same state directory under either engine."""
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "does not rename a node, a session or the state directory" in norm

    def test_the_skill_retires_the_stale_slash_command_claim(self):
        """The acpx-for-every-step choice rested on one sentence that 4.30.0 already
        contradicted. Leaving it in place would send the next editor back to acpx."""
        _, body = parse_frontmatter(SKILL)
        # The bare claim must not stand as a live statement any more.
        assert "Claude cannot invoke a slash command from inside its own\nmodel turn. So each step" not in body
        norm = _norm(body)
        assert "that is no longer true" in norm
        assert "4.30.0" in body

    def test_a_refusal_generates_no_node_and_reports_unverified(self):
        """Fail-closed. A refused run verified nothing, so it must not report
        clean, and it must not quietly run anyway."""
        step0 = self._step0()
        assert "generate no node" in step0
        assert "RELAY_VERIFY_RESULT=unverified" in step0
        assert "must\nnot report a clean result" in step0 or (
            "must not report a clean result" in _norm(step0)
        )

    def test_the_skill_names_the_rule_the_question_answers(self):
        """Without the rule name, the next editor reads the question as
        ceremony and deletes it."""
        _, body = parse_frontmatter(SKILL)
        why = _section(body, "### Why this question is necessary")
        assert "Create Unsafe Agents" in why
        assert "soft block" in why

    def test_the_skill_forbids_writing_the_question_to_pass_the_check(self):
        """The one line that keeps this a consent step and not an evasion."""
        _, body = parse_frontmatter(SKILL)
        why = _section(body, "### Why this question is necessary")
        assert "Do not write it to get past the check." in why
        assert "the answer is no, and the loop does not run" in why

    def test_the_containment_note_points_at_the_question(self):
        """The containment note lives where only an editor reads it. The two must
        stay linked so neither is read as the whole story."""
        _, body = parse_frontmatter(SKILL)
        assert "Step 0 tells the user this same fact" in body

    @pytest.mark.parametrize(
        "path", [CMD, SPINE_SKILL],
        ids=["verify.md", "running-implement-spine/SKILL.md"],
    )
    def test_both_callers_require_the_question(self, path):
        """Equivalence: `/relay:implement --verify` must ask exactly what
        `/relay:verify` asks, or the two paths differ at the gate. 4.38.0 moved
        the implement-side tail (and this question) off the command and into
        `relay:running-implement-spine`."""
        body = _norm(path.read_text())
        assert "the approval gate off" in body
        assert "report the run as unverified" in body

    @pytest.mark.parametrize(
        "path", [CMD, SPINE_SKILL],
        ids=["verify.md", "running-implement-spine/SKILL.md"],
    )
    def test_both_callers_scope_the_question_to_acpx(self, path):
        """4.32.0. Both callers must gate the question on the same engine, or the two
        paths differ at the gate again — the fault 4.25.0 was written to close.
        4.38.0 moved the implement-side tail into `relay:running-implement-spine`."""
        body = _norm(path.read_text())
        assert "when the engine is acpx" in body or "when the loop engine is acpx" in body
        assert "when the engine is in-session" in body or "when the loop engine is in-session" in body

    def test_the_implement_tail_forwards_its_engine(self):
        """The tail must run the engine the run resolved, or /relay:implement --verify
        stops matching /relay:implement followed by /relay:verify. 4.38.0 moved this
        tail off the command and into `relay:running-implement-spine`."""
        _, body = parse_frontmatter(SPINE_SKILL)
        assert "RELAY_VERIFY_ENGINE" in body
        norm = _norm(body)
        assert "pass this run's engine to the loop" in norm

    def test_the_implement_tail_prints_its_fallback(self):
        """/relay:implement accepts three engines the loop cannot run. The tail may
        substitute in-session, but a silent substitution would report a substrate the
        run never used. 4.38.0 moved this tail off the command and into
        `relay:running-implement-spine`."""
        _, body = parse_frontmatter(SPINE_SKILL)
        assert "has no verify-loop substrate" in body
        norm = _norm(body)
        assert "the substitution is printed, never silent" in norm

    @pytest.mark.parametrize(
        "path", [CMD, SPINE_SKILL],
        ids=["verify.md", "running-implement-spine/SKILL.md"],
    )
    def test_neither_caller_may_answer_for_the_user(self, path):
        """A caller that pre-answers turns informed consent back into the bare
        invocation the rule already refuses. 4.38.0 moved the implement-side tail
        into `relay:running-implement-spine`."""
        body = _norm(path.read_text())
        assert "do not answer it for the user" in body.lower()

    @pytest.mark.parametrize(
        "path", [CMD, IMPLEMENT_CMD], ids=["verify.md", "implement.md"]
    )
    def test_both_callers_may_ask(self, path):
        """A command that cannot call the tool cannot run the step."""
        fm, _ = parse_frontmatter(path)
        assert "AskUserQuestion" in str(fm["allowed-tools"])

    @pytest.mark.parametrize(
        "path", [CMD, IMPLEMENT_CMD, SPINE_SKILL],
        ids=["verify.md", "implement.md", "running-implement-spine/SKILL.md"],
    )
    def test_no_command_restates_the_three_question_items(self, path):
        """The wording lives in the skill, once. Two copies drift, which is the
        lesson TestLoopMechanicsLiveOnlyInTheSkill already encodes. `--approve-all`
        is not checked here: both commands already name it in their own
        containment note, which is a different statement to a different reader."""
        body = _norm(path.read_text())
        for item in ("no person approves each step", "every round of this run"):
            assert item not in body, f"{path.name} restates the question item {item!r}"


class TestNodeBodiesLiveInAScript:
    """The node bodies moved out of the generated Workflow script.

    Inline bash could not be tested, was restated in every node prompt at roughly
    35k tokens each, and was refused outright by a worktree-isolated session's Bash
    check — which cost one live run 13 of its 14 nodes.
    """

    def test_the_skill_names_the_node_script(self):
        _, body = parse_frontmatter(SKILL)
        assert "scripts/verify-loop-node.sh" in body

    def test_the_node_script_exists_and_is_the_implementation(self):
        """A needle naming a script that does not exist would make every assertion
        below vacuous."""
        assert (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").is_file()

    @pytest.mark.parametrize(
        "kind", ["init", "simplify", "review", "check", "fix", "report"]
    )
    def test_every_documented_kind_is_a_kind_the_script_accepts(self, kind):
        """Anti-drift: the skill is the spec and the script is the implementation,
        so a kind named in one and missing from the other is a silent break."""
        _, body = parse_frontmatter(SKILL)
        assert kind in body
        script = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        assert kind in script

    def test_the_worktree_is_passed_as_an_argument(self):
        """A node's cwd is not guaranteed to be the worktree. Deriving the path
        inside the node instead of passing it lands the git calls on whatever
        checkout the node happened to start in."""
        _, body = parse_frontmatter(SKILL)
        assert "RELAY_WT_WORKTREE_ROOT" in body
        assert "never derived from the node's own directory" in _norm(body)

    def test_the_skill_states_the_static_check_consequence(self):
        """The move puts the git calls where the session's Bash check cannot read
        them. That is a real consequence and the skill must not bury it."""
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "does not read this script" in norm
        assert (
            "do not use this file as a place to put work that you would not put in a node"
            in norm
        )

    def test_the_skill_records_why_a_short_command_is_needed(self):
        """Without the reason, the next editor inlines the body again to save a
        file and silently restores the refusal."""
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "does not need to contain git" in norm
        assert "lost 13 of its 14 nodes" in norm

    @pytest.mark.parametrize(
        "path", [CMD, IMPLEMENT_CMD, SPINE_SKILL],
        ids=["verify.md", "implement.md", "running-implement-spine/SKILL.md"],
    )
    def test_no_command_names_the_node_script(self, path):
        """Node names and mechanics live in the skill, once."""
        assert "verify-loop-node.sh" not in path.read_text()


class TestTheNodeGetsTheLongestBashTimeout:
    """Regression: a two-minute default cost one run 9 of its 12 steps.

    A round starts a child Claude session that runs three slash commands over a whole
    branch. At the Bash tool's default timeout the call gives up, the node reports that
    it backgrounded the command, and the child is killed before the script writes its
    record. Every round directory held one 12-byte record. The loop reported
    `unverified` — fail-closed held — but named no cause.
    """

    def test_the_skill_tells_the_node_to_use_the_maximum_timeout(self):
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "600000" in norm
        assert "do not leave it to the default" in norm

    def test_the_skill_says_why_the_default_is_too_short(self):
        """Without the reason, the next editor drops the instruction as noise."""
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "120000" in norm
        assert "lost 9 of its 12 steps" in norm

    def test_the_script_budget_is_below_the_callers_ceiling(self):
        """The script has to lose the race. If its budget were the higher of the two,
        the caller would cut the node off first and no `failed:timeout` would ever be
        written — which is the whole point of having a budget."""
        script = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        m = re.search(r'NODE_TIMEOUT="\$\{RELAY_VERIFY_NODE_TIMEOUT:-(\d+)\}"', script)
        assert m, "the script does not set a default node budget"
        assert int(m.group(1)) * 1000 < 600000

    def test_a_timeout_is_documented_as_unverified_and_not_a_skip(self):
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "failed:timeout" in norm
        assert "it is not a skip, and it is never a pass" in norm

    def test_the_budget_bounds_the_node_not_each_child(self):
        """Regression: a per-child limit let the check node's retry run two
        children of `NODE_TIMEOUT` seconds against the caller's 600-second
        ceiling — the exact shape that broke run `wf_918a4deb-aba`."""
        script = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        assert "NODE_DEADLINE" in script
        assert 'timeout -k 10 "$NODE_TIMEOUT"' not in script
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "deadline for the whole node" in norm
        assert "wf_918a4deb-aba" in norm


class TestANodesReturnIsNarrationNotEvidence:
    """Regression: the loop's own failure mode, one layer above the records.

    In run wf_8ad76eec-5ac the node wrappers summarised the command instead of relaying
    its status line. Several returned invented `detail` values, one the literal word
    `placeholder`, and two reported `ran` for a step that had run nothing. The records on
    disk were correct throughout, and the report node reads only those, so the verdict
    stayed honest — but a reader of the run's node list was told the opposite of what
    happened.
    """

    def test_the_skill_gives_the_node_a_verbatim_return_contract(self):
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "verbatim" in norm
        assert "node_status=absent" in norm

    def test_the_skill_names_backgrounded_as_not_ran(self):
        """This is the exact mis-mapping the run produced, so the skill must close it
        by name rather than by implication."""
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "none of them is ran" in norm

    def test_the_skill_says_the_verdict_comes_only_from_the_report(self):
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "narration, never evidence" in norm
        assert "where the two disagree, the records are right" in norm

    def test_the_skill_records_the_run_that_showed_this(self):
        """Without the evidence, the next editor reads the contract as fussiness and
        relaxes it."""
        norm = _norm(parse_frontmatter(SKILL)[1])
        assert "wf_8ad76eec-5ac" in norm
        assert "placeholder" in norm

    def test_the_script_prints_the_status_line_last(self):
        """The contract is only followable if the line is mechanically findable. Every
        `NODE_STATUS=` echo must be the final statement of its exit path."""
        script = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        lines = script.splitlines()
        for i, line in enumerate(lines):
            if not line.strip().startswith('echo "NODE_STATUS='):
                continue
            following = [
                l.strip()
                for l in lines[i + 1 : i + 3]
                if l.strip() and not l.strip().startswith("#")
            ]
            assert following and following[0] in ("exit 0", "exit 64", "exit 66", ";;"), (
                f"line {i + 1} prints NODE_STATUS and then keeps printing: {following!r}"
            )


class TestTheVerdictContract:
    """`/verify` resolves to whatever the repository defines. The check node must
    state the verdict line it needs, and the two places that carry that text — the
    script and the skill — must never drift apart."""

    _contract = staticmethod(verify_check_command)

    def test_the_contract_line_is_never_read_as_a_verdict(self):
        """A child that copies the contract back writes four verdict tokens on one
        line. The one-token rule in parse-verify-verdict.sh must reject that line,
        so a copied contract is never read as a real pass."""
        contract = self._contract()
        r = parse(text=fenced(contract))
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]

    def test_the_skill_states_the_same_contract_the_script_sends(self):
        contract = self._contract()
        _, skill_body = parse_frontmatter(SKILL)
        assert contract in skill_body, (
            "the skill's copy of the verdict contract has drifted from the script"
        )


class TestTheParserNamesWhyItFoundNoVerdict:
    """The two NONE paths must be told apart on stderr, without changing stdout or
    the exit code: a missing fence is temporary (a second child can answer), while a
    fenced reply with no verdict line is deterministic (a second child answers the
    same way)."""

    @pytest.mark.parametrize(
        "body,fence,expected_reason,expected_rc",
        [
            (None, False, "no-output-fence", 65),
            ("## Verify result: productivity v0.7.0 — PASS", True, "no-verdict-line", 65),
            ("**Verdict:** PASS", True, None, 0),
        ],
        ids=["no-fence", "fenced-no-verdict", "fenced-with-verdict"],
    )
    def test_each_none_path_names_its_reason(self, body, fence, expected_reason, expected_rc):
        text = fenced(body) if fence else "no fence here at all\n"
        r = parse(text=text)
        assert r.returncode == expected_rc
        assert len(lines(r)) == 2
        if expected_reason:
            assert f"VERIFY_REASON={expected_reason}" in r.stderr
        else:
            assert "VERIFY_REASON=" not in r.stderr

    def test_a_wrong_call_also_names_its_reason(self):
        """The usage path prints the same two NONE lines and the same 65. Without a
        reason of its own a caller reads a wrong call as a missing fence, and retries
        a child over an argument mistake that a second child cannot change."""
        r = subprocess.run(
            ["bash", str(PARSER), "one", "two"],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 65
        assert lines(r) == ["VERIFY_VERDICT=NONE", "VERIFY_LABEL=no-answer"]
        assert "VERIFY_REASON=bad-arguments" in r.stderr


class TestVerdictTableSeparatesTheTwoNoAnswerShapes:
    def test_a_missing_verdict_line_is_not_routed_like_blocked(self):
        _, body = parse_frontmatter(SKILL)
        assert "absent, empty, or unparseable" not in body
        assert "Same treatment as `BLOCKED`" in body
        assert "Do not retry" in body
        assert "VERIFY_REASON=no-output-fence" in body
        assert "VERIFY_REASON=no-verdict-line" in body


class TestTheInSessionNodePromptIsExecutable:
    """A live in-session run found the first node prompt unexecutable. It said to pass the
    block between the markers to the `Skill` tool as a name. Only `simplify` holds a bare
    command: `review` carries arguments, `check` adds a verdict contract under the command,
    and `fix` holds no command at all. A started command also returns its instructions
    rather than its result, so a node that wrote back what the tool returned wrote
    instruction text. For `check` that means no verdict line, `no-answer` every round, and
    `unverified` on every run of the default engine."""

    def test_the_block_is_a_prompt_to_carry_out_not_a_name(self):
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "is a prompt to carry out" in norm
        assert "it is not a name to pass to a" in norm
        # The reason has to travel with the rule, or the next editor re-reads the block as a name.
        assert "would fail on three of the four kinds" in norm

    def test_a_started_command_returns_instructions_not_a_result(self):
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "returns its instructions, not its result" in norm
        # The step ends with the work, not with the tool call that started it.
        assert "it is done when the work is done" in norm

    def test_the_reply_is_the_nodes_own_closing_answer(self):
        _, body = parse_frontmatter(SKILL)
        norm = _norm(body)
        assert "write your own closing answer" in norm
        # `check` is the kind that must add a line after doing the work.
        assert "the verdict line the block asks for" in norm
        # The fence stays the script's job, so guard 4 still holds.
        assert "do not add a fence" in norm

    def test_no_caller_says_the_in_session_node_uses_the_skill_tool(self):
        """The `Skill` tool takes a skill name. Naming it as the way a step reaches its
        command is what produced the unexecutable prompt, so no caller may say it again."""
        for path in (SKILL, CMD):
            meta, body = parse_frontmatter(path)
            whole = _norm(str(meta.get("description", "")) + " " + body)
            assert "invokes the command through the skill tool" not in whole
            assert "invokes each command through the skill tool" not in whole
        assert "slashcommand" in _norm(parse_frontmatter(SKILL)[1])
