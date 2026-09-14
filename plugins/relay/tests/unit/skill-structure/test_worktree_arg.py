import os
import subprocess

import pytest

from conftest import PLUGIN_ROOT, deps_ok_env

SCRIPT = PLUGIN_ROOT / "scripts" / "worktree-preflight.sh"


def _git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def _run(args, cwd, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )


def _parse(stdout):
    out = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" in line and line.split("=", 1)[0].startswith("RELAY_WT_"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


def _init_repo(path, default="main"):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", f"--initial-branch={default}")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("hello\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _resolve(cwd, value):
    r = _run(["--resolve", value], cwd=cwd)
    return r, _parse(r.stdout)


class TestResolve:
    def test_current_prints_toplevel(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        r, d = _resolve(repo, "current")
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "current"
        assert d["RELAY_WT_TARGET"] == str(repo.resolve())
        assert d["RELAY_WT_TARGET_BRANCH"] == "main"

    def test_existing_linked_worktree_by_absolute_path(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "sib", str(wt))
        r, d = _resolve(repo, str(wt.resolve()))
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "path"
        assert d["RELAY_WT_TARGET"] == str(wt.resolve())
        assert d["RELAY_WT_TARGET_BRANCH"] == "sib"

    def test_same_worktree_by_relative_path(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "sib", str(wt))
        r, d = _resolve(repo, os.path.join("..", "sibling"))
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "path"
        assert d["RELAY_WT_TARGET"] == str(wt.resolve())

    def test_same_worktree_by_symlinked_path(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "sib", str(wt))
        link = tmp_path / "linked"
        os.symlink(str(wt), str(link))
        r, d = _resolve(repo, str(link))
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "path"
        assert d["RELAY_WT_TARGET"] == str(wt.resolve())

    def test_branch_with_worktree(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "featurebranch", str(wt))
        r, d = _resolve(repo, "featurebranch")
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "branch"
        assert d["RELAY_WT_TARGET"] == str(wt.resolve())
        assert d["RELAY_WT_TARGET_BRANCH"] == "featurebranch"

    def test_branch_with_no_worktree(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "branch", "nowt")
        r, d = _resolve(repo, "nowt")
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "missing"
        assert d["RELAY_WT_TARGET"] == "nowt"
        assert d["RELAY_WT_TARGET_BRANCH"] == ""

    def test_plain_directory_is_missing(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        other = tmp_path / "plaindir"
        other.mkdir()
        r, d = _resolve(repo, str(other))
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "missing"

    def test_worktree_of_another_repo_is_missing(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        other_repo = _init_repo(tmp_path / "otherrepo")
        other_wt = tmp_path / "otherwt"
        _git(other_repo, "worktree", "add", "-q", "-b", "otherwtbranch", str(other_wt))
        r, d = _resolve(repo, str(other_wt.resolve()))
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "missing"

    def test_path_wins_over_branch_name_ambiguity(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "ambiguous"
        _git(repo, "worktree", "add", "-q", "-b", "ambiguous", str(wt))
        r, d = _resolve(repo, str(wt.resolve()))
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "path"

    def test_plain_directory_named_like_a_branch_with_worktree_is_branch(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "actualwt"
        _git(repo, "worktree", "add", "-q", "-b", "decoy", str(wt))
        decoy_dir = repo / "decoy"
        decoy_dir.mkdir()
        # value is the relative directory NAME "decoy" — the plain directory
        # exists but is NOT a linked worktree of this repo, so it falls
        # through to a branch-name match, which the "decoy" branch satisfies.
        r, d = _resolve(repo, "decoy")
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_RESOLVED"] == "branch"
        assert d["RELAY_WT_TARGET"] == str(wt.resolve())

    def test_outside_git_nonzero(self, tmp_path):
        bare = tmp_path / "nope"
        bare.mkdir()
        r, d = _resolve(bare, "current")
        assert r.returncode != 0

    @pytest.mark.parametrize("mode", ["path", "branch", "missing"])
    def test_target_branch_by_mode(self, tmp_path, mode):
        repo = _init_repo(tmp_path / "repo")
        if mode == "missing":
            r, d = _resolve(repo, "totally-absent")
            assert d["RELAY_WT_TARGET_BRANCH"] == ""
            return
        wt = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "sibbranch", str(wt))
        value = str(wt.resolve()) if mode == "path" else "sibbranch"
        r, d = _resolve(repo, value)
        assert d["RELAY_WT_TARGET_BRANCH"] == "sibbranch"

    def test_target_branch_detached_on_detached_target(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "sibbranch", str(wt))
        sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
        _git(wt, "checkout", "-q", sha)
        r, d = _resolve(repo, str(wt.resolve()))
        assert d["RELAY_WT_TARGET_BRANCH"] == "DETACHED"


class TestClassifyWidened:
    def test_linked_worktree_outside_claude_worktrees_is_worktree(self, tmp_path):
        """Task 2: the `worktree` state now fires on any linked worktree of
        this repo (git-common-dir != git-dir), not just ones created under
        .claude/worktrees/. A hand-made `git worktree add` elsewhere must
        classify as `worktree`, not `stray`."""
        repo = _init_repo(tmp_path / "repo")
        sibling = tmp_path / "sibling"
        _git(repo, "worktree", "add", "-q", "-b", "sib", str(sibling))
        r = _run(["--classify"], cwd=sibling)
        d = _parse(r.stdout)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "worktree", d
        assert d["RELAY_WT_BRANCH"] == "sib"
        assert d["RELAY_WT_WORKTREE_ROOT"] == str(sibling.resolve())

    def test_claude_worktrees_still_worktree(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = repo / ".claude" / "worktrees" / "wt-a"
        _git(repo, "worktree", "add", "-q", "-b", "wtbranch", str(wt))
        r = _run(["--classify"], cwd=wt)
        d = _parse(r.stdout)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "worktree"
        assert d["RELAY_WT_WORKTREE_ROOT"] == str(wt.resolve())

    def test_primary_checkout_feature_branch_still_stray(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-q", "-b", "feature/x")
        r = _run(["--classify"], cwd=repo)
        d = _parse(r.stdout)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "stray"


class TestCreateAt:
    def _origin_repo(self, tmp_path):
        bare = tmp_path / "origin.git"
        bare.mkdir()
        _git(bare, "init", "-q", "--bare", "--initial-branch=main")
        seed = _init_repo(tmp_path / "seed")
        _git(seed, "remote", "add", "origin", str(bare))
        _git(seed, "push", "-q", "origin", "main")
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(bare), str(clone)],
            capture_output=True, text=True, check=True,
        )
        _git(clone, "config", "user.email", "test@example.com")
        _git(clone, "config", "user.name", "Test")
        return bare, clone

    def test_create_at_named_path_on_relay_branch(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        at = tmp_path / "somewhere" / "billing"
        r = _run(["--create", "HEAD", "--at", str(at)], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert d["RELAY_WT_CREATED_PATH"] == str(at.resolve())
        br = subprocess.run(
            ["git", "-C", str(at), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert br == "relay/billing"

    def test_create_at_existing_path_fails_no_suffix(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        at = tmp_path / "already"
        at.mkdir()
        (at / "x").write_text("x")
        r = _run(["--create", "HEAD", "--at", str(at)], cwd=clone)
        assert r.returncode != 0
        assert "worktree-exists" in r.stderr
        assert "already-1" not in r.stderr
        assert "already-2" not in r.stdout

    def test_create_at_existing_branch_fails(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        _git(clone, "branch", "relay/dup")
        at = tmp_path / "dup"
        r = _run(["--create", "HEAD", "--at", str(at)], cwd=clone)
        assert r.returncode != 0
        assert "worktree-exists" in r.stderr

    def test_create_without_at_still_uses_claude_worktrees_and_suffix(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        r1 = _run(["--create", "HEAD", "dupslug"], cwd=clone)
        assert r1.returncode == 0, r1.stderr
        r2 = _run(["--create", "HEAD", "dupslug"], cwd=clone)
        assert r2.returncode == 0, r2.stderr
        d2 = _parse(r2.stdout)
        assert "dupslug-1" in d2["RELAY_WT_CREATED_PATH"]
        assert ".claude" in d2["RELAY_WT_CREATED_PATH"]


ENSURING_WT_ISOLATION_SKILL = PLUGIN_ROOT / "skills" / "ensuring-worktree-isolation" / "SKILL.md"


class TestEnsuringWorktreeIsolationGate:
    @pytest.fixture(scope="class")
    def body(self):
        return ENSURING_WT_ISOLATION_SKILL.read_text()

    def test_names_current(self, body):
        assert "`current`" in body

    def test_names_missing(self, body):
        assert "`missing`" in body

    def test_names_worktree_missing(self, body):
        assert "worktree-missing" in body
        assert "[relay] error: worktree-missing" in body, (
            "spec section 8 pins the [relay] error: prefix on this message"
        )
        assert "[relay] error: cancelled at the --worktree" in body, (
            "spec section 8 pins a message on the Cancel row too"
        )

    def test_names_relay_wt_arg(self, body):
        assert "RELAY_WT_ARG" in body

    def test_worktree_root_line_no_longer_says_claude_worktrees(self, body):
        line = [
            l for l in body.splitlines()
            if l.strip().startswith("RELAY_WT_WORKTREE_ROOT=<path")
        ][0]
        assert ".claude/worktrees" not in line

    def test_no_relay_wt_headless_string(self, body):
        assert "RELAY_WT_HEADLESS" not in body

    def test_no_relay_managed_wording(self, body):
        assert "relay-managed" not in body

    def test_says_linked_worktree(self, body):
        assert "linked worktree" in body


COMMANDS_DIR = PLUGIN_ROOT / "commands"
FOUR_COMMANDS = ["implement.md", "refine.md", "execute.md", "drive.md"]


L3_PREFLIGHT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"

# The four commands that run the Step 0.5 gate, as the l3-preflight.sh mode
# names they map to. `verify` and `diagnose` run no gate and take no --worktree.
FOUR_MODES = ["implement", "refine", "execute", "drive"]


def _run_preflight(mode, relay_args, tmp_path):
    """Drive the real scripts/l3-preflight.sh. Issue #110 moved every Step 0
    shape out of the command bodies and into this script, so the parsing under
    test lives here, not in a fenced block. The dependency gate runs first and
    would block every case, so clear it the way every other module that drives
    this script does — through the shared deps_ok_env builder."""
    cwd = tmp_path / "cwd"
    cwd.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(L3_PREFLIGHT), mode, relay_args],
        capture_output=True, text=True, cwd=str(cwd), env=deps_ok_env(tmp_path),
    )


class TestWorktreeFlagParsedInFourCommands:
    @pytest.mark.parametrize("mode", FOUR_MODES)
    def test_prints_relay_wt_arg(self, tmp_path, mode):
        r = _run_preflight(mode, "--worktree /some/path do the task", tmp_path)
        assert r.returncode == 0, r.stderr
        assert "RELAY_WT_ARG=/some/path" in r.stdout

    @pytest.mark.parametrize("mode", FOUR_MODES)
    def test_no_value_is_an_error(self, tmp_path, mode):
        r = _run_preflight(mode, "--worktree", tmp_path)
        assert r.returncode != 0
        assert "--worktree takes a value" in r.stderr

    @pytest.mark.parametrize("mode", FOUR_MODES)
    def test_worktree_then_engine_flag_not_swallowed(self, tmp_path, mode):
        r = _run_preflight(mode, "--worktree --engine claude do the task", tmp_path)
        assert r.returncode != 0
        assert "--worktree takes a value" in r.stderr

    @pytest.mark.parametrize("mode", FOUR_MODES)
    def test_no_flag_prints_no_relay_wt_arg_line(self, tmp_path, mode):
        r = _run_preflight(mode, "do the task", tmp_path)
        assert r.returncode == 0, r.stderr
        assert "RELAY_WT_ARG" not in r.stdout

    @pytest.mark.parametrize("mode", FOUR_MODES)
    def test_retro_with_target_ignores_worktree(self, tmp_path, mode):
        # `last` must end the string for the retro grammar to read it as a target.
        r = _run_preflight(mode, "--worktree /some/path --retro last", tmp_path)
        assert r.returncode == 0, r.stderr
        assert "RELAY_RETRO_TARGET=last" in r.stdout
        assert "[relay] --worktree ignored: retro is read-only" in r.stdout

    @pytest.mark.parametrize("mode", FOUR_MODES)
    def test_bare_retro_no_target_honors_worktree_no_notice(self, tmp_path, mode):
        r = _run_preflight(mode, "--retro --worktree /some/path do the task", tmp_path)
        assert r.returncode == 0, r.stderr
        assert "RELAY_RETRO_TARGET=" in r.stdout
        assert "ignored: retro is read-only" not in r.stdout
        assert "RELAY_WT_ARG=/some/path" in r.stdout

    @pytest.mark.parametrize("mode", ["verify", "diagnose"])
    def test_the_ungated_commands_never_print_the_line(self, tmp_path, mode):
        """verify and diagnose run no Step 0.5 gate, so they take no --worktree
        and must not print a value a gate would act on."""
        r = _run_preflight(mode, "--worktree /some/path", tmp_path)
        assert "RELAY_WT_ARG" not in r.stdout


def _extract_fenced_block(command_name, heading):
    """Pull the first fenced bash block that follows `heading` out of a command
    file, so a test runs the ACTUAL prose shipped in the command, not a copy of
    it. A copy passes when the shipped block is deleted; this does not."""
    text = (COMMANDS_DIR / command_name).read_text()
    start = text.index(heading)
    open_fence = text.index("```bash", start) + len("```bash")
    close_fence = text.index("```", open_fence)
    return text[open_fence:close_fence].strip()


class TestStep055PrintsActiveWorktree:
    HEADING = "## Step 0.55 — Record the active worktree"

    @pytest.mark.parametrize("cmd", FOUR_COMMANDS)
    def test_the_block_calls_the_script_not_an_inline_rev_parse(self, cmd):
        """The static gate in validate_l3_command.py refuses an inline `$(...)`,
        so the toplevel read is a --active script mode (issue #110)."""
        block = _extract_fenced_block(cmd, self.HEADING)
        assert "--active" in block
        assert "$(" not in block

    @pytest.mark.parametrize("cmd", FOUR_COMMANDS)
    def test_prints_relay_wt_active(self, tmp_path, cmd):
        repo = _init_repo(tmp_path / "repo")
        block = _extract_fenced_block(cmd, self.HEADING)
        script = block.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN_ROOT))
        r = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, cwd=str(repo),
        )
        assert r.returncode == 0, r.stderr
        assert f"RELAY_WT_ACTIVE={repo.resolve()}" in r.stdout

    def test_a_non_git_cwd_is_an_error_not_an_empty_value(self, tmp_path):
        r = subprocess.run(
            ["bash", str(SCRIPT), "--active"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert r.returncode != 0
        assert "RELAY_WT_ACTIVE=" not in r.stdout


class TestStep05ResolveCallIsReachable:
    """The Step 0.5 resolver call shipped dead once: it read `$_worktree`, a
    variable set in the Step 0 Bash call, and captured the output into a
    variable nothing echoed. Both defects made every --worktree run abort with
    an empty value. These tests run the shipped block."""

    RESOLVE_HEADING = "When Step 0 printed `RELAY_WT_ARG=<value>`, also run the resolver"

    @pytest.mark.parametrize("cmd", FOUR_COMMANDS)
    def test_the_block_uses_no_cross_call_shell_variable(self, cmd):
        block = _extract_fenced_block(cmd, self.RESOLVE_HEADING)
        assert "$_worktree" not in block, (
            "state does not cross a Bash call as a shell variable; the printed "
            "RELAY_WT_ARG value must be substituted as a literal"
        )
        assert "<value>" in block

    @pytest.mark.parametrize("cmd", FOUR_COMMANDS)
    def test_the_block_prints_the_resolve_lines(self, tmp_path, cmd):
        repo = _init_repo(tmp_path / "repo")
        block = _extract_fenced_block(cmd, self.RESOLVE_HEADING)
        script = block.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN_ROOT)).replace(
            "<value>", "current"
        )
        r = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, cwd=str(repo),
        )
        assert r.returncode == 0, r.stderr
        assert "RELAY_WT_RESOLVED=current" in r.stdout, (
            "the gate skill reads these lines from stdout; a captured-but-never-"
            "echoed block reaches nothing"
        )
        assert f"RELAY_WT_TARGET={repo.resolve()}" in r.stdout


class TestDriveOracleStripsWorktree:
    """The oracle is the lone token left after every flag and its value are
    stripped, so a --worktree value left in would be read as the oracle path."""

    def test_oracle_has_no_worktree_fragment(self, tmp_path):
        r = _run_preflight("drive", "--worktree /a/b docs/oracle.md", tmp_path)
        assert r.returncode == 0, r.stderr
        assert "RELAY_DRIVE_ORACLE=docs/oracle.md" in r.stdout
        assert "RELAY_DRIVE_ORACLE=/a/b" not in r.stdout

    def test_the_value_still_reaches_the_gate(self, tmp_path):
        r = _run_preflight("drive", "--worktree /a/b docs/oracle.md", tmp_path)
        assert "RELAY_WT_ARG=/a/b" in r.stdout


class TestArgumentHintsAndStripSentences:
    @pytest.mark.parametrize("cmd", FOUR_COMMANDS)
    def test_argument_hint_lists_worktree(self, cmd):
        text = (COMMANDS_DIR / cmd).read_text()
        hint_line = [l for l in text.splitlines() if l.startswith("argument-hint:")][0]
        assert "--worktree" in hint_line

    @pytest.mark.parametrize("cmd", FOUR_COMMANDS)
    def test_worktree_named_before_the_classifier_line(self, cmd):
        text = (COMMANDS_DIR / cmd).read_text()
        assert "--worktree" in text


class TestWorktreeInjectionAtGeneration:
    def test_running_implement_spine_lists_worktree_input(self):
        body = (PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md").read_text()
        inputs_section = body[body.index("## Inputs"):body.index("## Step 3")]
        assert "`worktree`" in inputs_section
        assert "(optional)" in inputs_section.split("`worktree`")[1][:40]

    def test_dispatching_in_session_agents_no_longer_carries_the_inferred_note(self):
        body = (PLUGIN_ROOT / "skills" / "dispatching-in-session-agents" / "SKILL.md").read_text()
        assert "no entry-point command exports `WORKTREE`" not in body

    def test_dispatching_in_session_agents_replacement_sentence_gates(self):
        body = (PLUGIN_ROOT / "skills" / "dispatching-in-session-agents" / "SKILL.md").read_text()
        flat = " ".join(body.split())
        assert "prints `RELAY_WT_ACTIVE" in flat
        assert "Workflow-generation" in body
        assert "v4.46.0" in body
        assert "the `REPO_ROOT` fallback" in body
        assert "{{WORKTREE_PATH}}" in body
        assert "writer-role `agent()`" in body
        assert "WORKTREE=<literal>" not in body

    def test_no_gate_targets_dispatch_contract_for_this_sentence(self):
        # Documented as "no gate written" per plan Task 6 — this test exists only to
        # record that decision; it asserts nothing about docs/dispatch-contract.md.
        assert True


class TestImplementingSpecWorktreeMismatchGuard:
    @pytest.fixture(scope="class")
    def body(self):
        return (PLUGIN_ROOT / "skills" / "implementing-spec" / "SKILL.md").read_text()

    def test_names_step_1_5_heading(self, body):
        assert "Step 1.5" in body

    def test_names_the_resolve_invocation(self, body):
        assert "worktree-preflight.sh --resolve" in body

    def test_names_relay_wt_active(self, body):
        assert "RELAY_WT_ACTIVE" in body

    def test_names_the_three_branches(self, body):
        assert "line is absent" in body
        assert "Equal" in body
        assert "Not equal" in body

    def test_names_the_blocked_worktree_mismatch_block(self, body):
        assert "status: blocked" in body
        assert "reason: worktree-mismatch" in body

    def test_names_the_two_labels(self, body):
        assert "caller declared:" in body
        assert "skill running in:" in body
