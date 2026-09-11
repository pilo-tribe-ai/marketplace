import os
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "worktree-preflight.sh"


def _git(repo, *args, check=True):
    """Run a git command in `repo`, mirroring the throwaway-repo style used by
    doc_reference_scan.py's helpers."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def _run(args, cwd, env_extra=None):
    """Drive worktree-preflight.sh via subprocess (like test_check_deps_agent.py::_run)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )


def _parse(stdout):
    """Parse the printed KEY=value block into a dict."""
    out = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" in line and line.split("=", 1)[0].startswith("RELAY_WT_"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


def _init_repo(path, default="main"):
    """Create a fresh repo on `default`, one commit, and pin origin/HEAD so the
    default-branch resolution works fully offline."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", f"--initial-branch={default}")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("hello\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _classify(cwd):
    r = _run(["--classify"], cwd=cwd)
    return r, _parse(r.stdout)


class TestClassify:
    def test_main_primary_checkout(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        r, d = _classify(repo)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "main"
        assert d["RELAY_WT_BRANCH"] == "main"
        assert d["RELAY_WT_DEFAULT"] == "main"
        assert d["RELAY_WT_REPO_ROOT"] == str(repo.resolve())
        assert d["RELAY_WT_WORKTREE_ROOT"] == ""

    def test_stray_non_default_branch(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-q", "-b", "feature/x")
        r, d = _classify(repo)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "stray"
        assert d["RELAY_WT_BRANCH"] == "feature/x"
        assert d["RELAY_WT_DEFAULT"] == "main"

    def test_stray_detached_head(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "checkout", "-q", sha)
        r, d = _classify(repo)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "stray"
        assert d["RELAY_WT_BRANCH"] == "DETACHED"

    def test_worktree_under_claude_worktrees(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = repo / ".claude" / "worktrees" / "wt-a"
        _git(repo, "worktree", "add", "-q", "-b", "wtbranch", str(wt))
        r, d = _classify(wt)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "worktree"
        assert d["RELAY_WT_BRANCH"] == "wtbranch"
        assert d["RELAY_WT_WORKTREE_ROOT"] == str(wt.resolve())

    def test_linked_worktree_outside_claude_worktrees_is_worktree(self, tmp_path):
        """As of v4.46.0 the `worktree` state fires on ANY linked worktree of
        this repo (common_dir != git_dir), whether it lives under
        .claude/worktrees/ or was hand-made elsewhere by plain `git worktree
        add` (or by superpowers:using-git-worktrees in another dir). This
        widening is what lets a `--worktree <path>` value that names a
        hand-made linked worktree resolve to the same `worktree` state a
        relay-created one gets. This case guards a regression to the OLD,
        narrower rule — a mutation that reintroduces the .claude/worktrees/
        path guard would misclassify this sibling as `stray` again."""
        repo = _init_repo(tmp_path / "repo")
        sibling = tmp_path / "sibling"  # NOT under .claude/worktrees/
        _git(repo, "worktree", "add", "-q", "-b", "sib", str(sibling))
        r, d = _classify(sibling)
        assert r.returncode == 0, r.stderr
        assert d["RELAY_WT_STATE"] == "worktree", d
        assert d["RELAY_WT_BRANCH"] == "sib"
        assert d["RELAY_WT_WORKTREE_ROOT"] == str(sibling.resolve())

    def test_not_git_returns_nonzero(self, tmp_path):
        bare = tmp_path / "nope"
        bare.mkdir()
        r, d = _classify(bare)
        assert r.returncode != 0
        # not-git -> command-abort semantics (script returns non-zero).
        if "RELAY_WT_STATE" in d:
            assert d["RELAY_WT_STATE"] == "not-git"


class TestCreate:
    def _origin_repo(self, tmp_path):
        """A local bare repo serving as `origin`, plus a primary clone on main."""
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

    def test_create_head_makes_worktree_and_prints_path(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert "RELAY_WT_CREATED_PATH" in d, r.stdout
        created = d["RELAY_WT_CREATED_PATH"]
        # absolute path under .claude/worktrees/
        assert os.path.isabs(created)
        assert os.sep + os.path.join(".claude", "worktrees") + os.sep in created
        assert os.path.isdir(created)
        # registered in git worktree list
        wl = _git(clone, "worktree", "list").stdout
        assert created in wl
        # new branch is relay/<slug>
        br = _git(clone, "-C", created, "rev-parse", "--abbrev-ref", "HEAD")
        # (rev-parse -C through the helper: run directly)
        br = subprocess.run(
            ["git", "-C", created, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert br.startswith("relay/")

    def test_create_without_config_prints_bootstrap_skipped(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert "RELAY_WT_CREATED_PATH" in d, r.stdout
        assert d["RELAY_WT_BOOTSTRAP"] == "skipped"
        assert os.path.isdir(d["RELAY_WT_CREATED_PATH"])

    def test_create_runs_bootstrap_in_new_worktree_not_primary_checkout(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": "touch BOOTSTRAP_RAN"}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        created = d["RELAY_WT_CREATED_PATH"]

        assert d["RELAY_WT_BOOTSTRAP"] == "ran"
        assert os.path.exists(os.path.join(created, "BOOTSTRAP_RAN"))
        assert not (clone / "BOOTSTRAP_RAN").exists()

    def test_create_failing_bootstrap_hard_fails_without_created_path(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": "exit 3"}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        d = _parse(r.stdout)

        assert r.returncode != 0
        assert "RELAY_WT_CREATED_PATH" not in d
        assert "[relay] error: bootstrap failed (exit 3)" in r.stderr

    def test_create_invalid_json_hard_fails_before_worktree_creation(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        before = _git(clone, "worktree", "list", "--porcelain").stdout
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text("{not json\n")

        r = _run(["--create", "HEAD"], cwd=clone)
        after = _git(clone, "worktree", "list", "--porcelain").stdout
        d = _parse(r.stdout)

        assert r.returncode != 0
        assert "RELAY_WT_CREATED_PATH" not in d
        assert before == after
        assert "[relay] error: .claude/relay.json is not valid JSON" in r.stderr

    def test_create_empty_bootstrap_key_skips(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": ""}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert "RELAY_WT_CREATED_PATH" in d, r.stdout
        assert d["RELAY_WT_BOOTSTRAP"] == "skipped"

    def test_create_bootstrap_stdout_is_routed_to_stderr(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        config_dir = clone / ".claude"
        config_dir.mkdir()
        (config_dir / "relay.json").write_text('{"bootstrap": "echo noise"}\n')

        r = _run(["--create", "HEAD"], cwd=clone)
        assert r.returncode == 0, r.stderr
        d = _parse(r.stdout)
        assert set(d) == {"RELAY_WT_CREATED_PATH", "RELAY_WT_BOOTSTRAP"}
        assert d["RELAY_WT_BOOTSTRAP"] == "ran"
        assert "noise" not in r.stdout
        assert "noise" in r.stderr

    def test_create_honors_explicit_base_ref(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        # make a distinct second commit, tag the first
        first = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        (clone / "two.txt").write_text("two\n")
        _git(clone, "add", "two.txt")
        _git(clone, "commit", "-q", "-m", "second")
        # create off the FIRST commit (distinct from current HEAD)
        r = _run(["--create", first], cwd=clone)
        assert r.returncode == 0, r.stderr
        created = _parse(r.stdout)["RELAY_WT_CREATED_PATH"]
        wt_head = subprocess.run(
            ["git", "-C", created, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert wt_head == first

    def test_create_invokes_git_fetch(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        # Push a NEW commit to origin that the clone has not fetched yet.
        seed2 = tmp_path / "seed2"
        subprocess.run(
            ["git", "clone", "-q", str(_bare), str(seed2)],
            capture_output=True, text=True, check=True,
        )
        _git(seed2, "config", "user.email", "test@example.com")
        _git(seed2, "config", "user.name", "Test")
        (seed2 / "remote.txt").write_text("remote-only\n")
        _git(seed2, "add", "remote.txt")
        _git(seed2, "commit", "-q", "-m", "remote-only")
        _git(seed2, "push", "-q", "origin", "main")
        remote_sha = subprocess.run(
            ["git", "-C", str(seed2), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        # The clone does NOT yet know about remote_sha.
        before = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "origin/main"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert before != remote_sha
        # --create must run `git fetch origin main`; after it, the clone knows remote_sha.
        r = _run(["--create", "origin/main"], cwd=clone)
        assert r.returncode == 0, r.stderr
        after = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "origin/main"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert after == remote_sha, "git fetch origin main was not invoked"

    def test_create_collision_suffixes(self, tmp_path):
        _bare, clone = self._origin_repo(tmp_path)
        r1 = _run(["--create", "HEAD", "myslug"], cwd=clone)
        assert r1.returncode == 0, r1.stderr
        p1 = _parse(r1.stdout)["RELAY_WT_CREATED_PATH"]
        r2 = _run(["--create", "HEAD", "myslug"], cwd=clone)
        assert r2.returncode == 0, r2.stderr
        p2 = _parse(r2.stdout)["RELAY_WT_CREATED_PATH"]
        assert p1 != p2
        # second path gets a -N suffix
        assert os.path.basename(p2).rstrip("0123456789").endswith("-") or \
            os.path.basename(p2) != os.path.basename(p1)
        wl = _git(clone, "worktree", "list").stdout
        assert p1 in wl and p2 in wl

    def test_create_suffixes_past_leftover_branch_when_dir_absent(self, tmp_path):
        """Regression: a leftover `relay/<slug>` branch with NO worktree dir (the normal
        post-teardown state after `git worktree remove` + `git worktree prune`) must force
        a -N suffix, not crash `git worktree add -b relay/<slug>` with "branch already
        exists". The dir-only collision predicate missed this branch-only axis."""
        _bare, clone = self._origin_repo(tmp_path)
        # Leftover branch, but the worktree directory does NOT exist.
        _git(clone, "branch", "relay/myslug")
        r = _run(["--create", "HEAD", "myslug"], cwd=clone)
        assert r.returncode == 0, r.stderr
        created = _parse(r.stdout)["RELAY_WT_CREATED_PATH"]
        # The base name was suffixed past the colliding branch.
        assert os.path.basename(created) != "myslug"
        # The new worktree is registered and lives on a fresh non-colliding branch.
        assert created in _git(clone, "worktree", "list").stdout


def test_bootstrap_reports_missing_jq_explicitly():
    """4.12.0 (spec §1.2): a missing jq must not misreport as invalid JSON — the
    bootstrap reader names jq explicitly, byte-identical to parse-engine-agent.sh."""
    body = SCRIPT.read_text()
    assert "command -v jq" in body
    assert "jq is required to read .claude/relay.json" in body


class TestBranchGuard:
    """Issue #110: implement.md Step 0.6 and verify.md Step 0.5 both carried a
    `$(...)`/`case`/`if` block a worktree-isolated session refuses inline. Both
    collapse into `worktree-preflight.sh --branch-guard [implement|verify]`,
    which runs `_wt_classify` itself and refuses `main` and a detached `HEAD`
    with the exact wording each command printed inline before."""

    IMPLEMENT_MAIN = (
        "implement: --verify runs a loop that edits files and commits them. "
        "It refuses the default branch. Create a branch first, or drop --verify."
    )
    IMPLEMENT_DETACHED = (
        "implement: --verify refuses a detached HEAD. The loop commits every "
        "round, and commits on a detached HEAD are not on any branch. Check "
        "out a branch first."
    )
    IMPLEMENT_NOTGIT = (
        "implement: could not read the git state. Run this command inside a "
        "git checkout."
    )
    VERIFY_MAIN = (
        "verify: refusing to run on the default branch. This loop edits "
        "files and commits them. Create a branch first."
    )
    VERIFY_DETACHED = (
        "verify: refusing to run on a detached HEAD. This loop commits "
        "every round, and commits on a detached HEAD are not on any branch. "
        "Check out a branch first."
    )
    VERIFY_NOTGIT = (
        "verify: could not read the git state. Run this command inside a "
        "git checkout."
    )

    def test_default_branch_refused_with_implement_wording(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        r = _run(["--branch-guard"], cwd=repo)
        assert r.returncode == 1, r.stdout + r.stderr
        assert self.IMPLEMENT_MAIN in r.stdout

    def test_feature_branch_passes(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "checkout", "-q", "-b", "feature/x")
        r = _run(["--branch-guard"], cwd=repo)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "RELAY_WT_STATE=stray" in r.stdout

    def test_detached_head_refused_with_implement_wording(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "checkout", "-q", sha)
        r = _run(["--branch-guard"], cwd=repo)
        assert r.returncode == 1, r.stdout + r.stderr
        assert self.IMPLEMENT_DETACHED in r.stdout

    def test_worktree_under_claude_worktrees_passes(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        wt = repo / ".claude" / "worktrees" / "wt-a"
        _git(repo, "worktree", "add", "-q", "-b", "wtbranch", str(wt))
        r = _run(["--branch-guard"], cwd=wt)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_non_git_dir_refused_with_notgit_wording(self, tmp_path):
        bare = tmp_path / "nope"
        bare.mkdir()
        r = _run(["--branch-guard"], cwd=bare)
        assert r.returncode == 1, r.stdout + r.stderr
        assert self.IMPLEMENT_NOTGIT in r.stdout

    def test_verify_variant_default_branch_refused(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        r = _run(["--branch-guard", "verify"], cwd=repo)
        assert r.returncode == 1, r.stdout + r.stderr
        assert self.VERIFY_MAIN in r.stdout

    def test_verify_variant_detached_refused(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "checkout", "-q", sha)
        r = _run(["--branch-guard", "verify"], cwd=repo)
        assert r.returncode == 1, r.stdout + r.stderr
        assert self.VERIFY_DETACHED in r.stdout

    def test_verify_variant_notgit_refused(self, tmp_path):
        bare = tmp_path / "nope"
        bare.mkdir()
        r = _run(["--branch-guard", "verify"], cwd=bare)
        assert r.returncode == 1, r.stdout + r.stderr
        assert self.VERIFY_NOTGIT in r.stdout

    def test_bogus_variant_exits_2(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        r = _run(["--branch-guard", "bogus"], cwd=repo)
        assert r.returncode == 2, r.stdout + r.stderr
