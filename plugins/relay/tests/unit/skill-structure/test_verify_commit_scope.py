"""The verify-loop commit script.

`verify-loop-node.sh` commits after every simplify, review, and fix step. The scope
derivation and the commit used to be an inline block in `verifying-until-clean/SKILL.md`
and a second copy inside the node script. They now live once, in
`scripts/verify-commit-scope.sh`, and these tests run that script against a real
checkout so the message shape the skill promises is the shape that lands.
"""

import os
import stat
import subprocess

import pytest

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "verify-commit-scope.sh"
NODE = PLUGIN_ROOT / "scripts" / "verify-loop-node.sh"


def run(*args, env=None):
    merged = dict(os.environ)
    merged.pop("RELAY_BASE_REF", None)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        env=merged,
    )


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def commit(repo, subject, name="f.txt"):
    path = repo / name
    path.write_text(path.read_text() + subject + "\n" if path.exists() else subject + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", subject)


@pytest.fixture
def repo(tmp_path):
    """A real checkout with one root commit that carries no scope."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("one\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def dirty(repo):
    (repo / "a.txt").write_text("changed\n")


def head_subject(repo):
    return git(repo, "log", "-1", "--format=%s").strip()


class TestScriptHygiene:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.is_file()
        assert os.stat(SCRIPT).st_mode & stat.S_IXUSR

    def test_passes_bash_syntax_check(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_wrong_argument_count_is_64(self, repo):
        assert run(repo).returncode == 64
        assert run(repo, "fix", "extra").returncode == 64

    def test_unknown_step_is_64(self, repo):
        r = run(repo, "teleport")
        assert r.returncode == 64
        assert r.stdout == ""

    def test_missing_worktree_is_66(self, tmp_path):
        r = run(tmp_path / "nope", "fix")
        assert r.returncode == 66

    def test_the_node_script_calls_this_script(self):
        """The node script must not keep a second copy of the block."""
        node = NODE.read_text()
        assert "verify-commit-scope.sh" in node
        assert "derive_scope" not in node
        assert "max-parents=0" not in node


class TestCleanTree:
    @pytest.mark.parametrize("step", ["simplify", "review", "fix"])
    def test_a_clean_tree_prints_no_changes_and_commits_nothing(self, repo, step):
        before = git(repo, "rev-parse", "HEAD")
        r = run(repo, step)
        assert r.returncode == 0
        assert r.stdout == "no changes\n"
        assert git(repo, "rev-parse", "HEAD") == before


class TestMessageShape:
    @pytest.mark.parametrize(
        "step,subject",
        [
            ("simplify", "refactor: simplify implementation"),
            ("review", "fix: apply code-review findings"),
            ("fix", "fix: fix problems named by /verify"),
        ],
    )
    def test_no_derivable_scope_omits_the_scope(self, repo, step, subject):
        dirty(repo)
        r = run(repo, step)
        assert r.returncode == 0
        assert r.stdout.strip() == git(repo, "rev-parse", "HEAD").strip()
        assert head_subject(repo) == subject

    @pytest.mark.parametrize(
        "step,subject",
        [
            ("simplify", "refactor(core): simplify implementation"),
            ("review", "fix(core): apply code-review findings"),
            ("fix", "fix(core): fix problems named by /verify"),
        ],
    )
    def test_the_dominant_scope_is_used(self, repo, step, subject):
        commit(repo, "feat(core): one")
        commit(repo, "fix(core): two")
        commit(repo, "docs(other): three")
        dirty(repo)
        r = run(repo, step)
        assert r.returncode == 0
        assert head_subject(repo) == subject

    def test_a_breaking_change_marker_still_yields_the_scope(self, repo):
        commit(repo, "feat(api)!: drop v1")
        dirty(repo)
        run(repo, "simplify")
        assert head_subject(repo) == "refactor(api): simplify implementation"

    def test_most_recent_wins_on_ties(self, repo):
        """`git log` lists newest first, so the scope seen first is the most recent."""
        commit(repo, "feat(old): one")
        commit(repo, "feat(new): two")
        dirty(repo)
        run(repo, "review")
        assert head_subject(repo) == "fix(new): apply code-review findings"

    def test_the_sha_printed_is_the_new_head(self, repo):
        dirty(repo)
        r = run(repo, "fix")
        assert r.stdout.strip() == git(repo, "rev-parse", "HEAD").strip()
        assert git(repo, "status", "--short") == ""


class TestBaseRef:
    def test_relay_base_ref_bounds_the_scan(self, repo):
        commit(repo, "feat(early): one")
        base = git(repo, "rev-parse", "HEAD").strip()
        commit(repo, "feat(late): two")
        dirty(repo)
        run(repo, "simplify", env={"RELAY_BASE_REF": base})
        assert head_subject(repo) == "refactor(late): simplify implementation"

    def test_without_origin_the_scan_falls_back_to_the_root(self, repo):
        """No `origin/HEAD` and no `origin/main` exist here, so the merge-base is empty
        and the root commit is the base. Every commit on the branch is then scanned."""
        commit(repo, "feat(root-scan): one")
        dirty(repo)
        run(repo, "simplify")
        assert head_subject(repo) == "refactor(root-scan): simplify implementation"

    def test_commits_at_or_below_the_default_branch_are_not_scanned(self, repo):
        """A scope that only appears on the default branch must not leak onto a
        feature branch's commit message."""
        commit(repo, "feat(mainline): one")
        git(repo, "branch", "-m", "main")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(repo, "checkout", "-qb", "feature/x")
        dirty(repo)
        run(repo, "fix")
        assert head_subject(repo) == "fix: fix problems named by /verify"


class TestCommitFailure:
    def test_a_failed_commit_prints_commit_failed(self, repo):
        """A pre-commit hook that exits 1 makes the commit fail. The script must say
        so, and must never print a sha or `no changes` for it."""
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        before = git(repo, "rev-parse", "HEAD")
        dirty(repo)
        r = run(repo, "fix")
        assert r.returncode == 0
        assert r.stdout == "commit-failed\n"
        assert git(repo, "rev-parse", "HEAD") == before
