import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "doc_reference_scan.py"

# Load the module directly so unit tests can call internal helpers without
# going through the subprocess boundary.
_spec = importlib.util.spec_from_file_location("doc_reference_scan", str(SCRIPT))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
discover_doc_gate = _mod.discover_doc_gate
_gate_argv = _mod._gate_argv
GATE_NAME_RE = _mod.GATE_NAME_RE


def run_scan(*args, cwd=None):
    """Invoke the helper and return (returncode, parsed_json_or_None, raw_stdout)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = None
    return proc.returncode, parsed, proc.stdout


def git(repo, *args):
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "t@t"
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True, env=env)


def init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    return repo


def commit_all(repo, msg="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


class TestSkeleton:
    def test_script_exists_and_executable_as_module(self):
        assert SCRIPT.is_file()

    def test_non_git_dir_degrades_to_clean_advisory(self, tmp_path):
        rc, out, raw = run_scan("--repo-root", str(tmp_path))
        assert rc == 0, f"helper crashed: {raw}"
        assert out is not None, f"non-JSON stdout: {raw}"
        assert out["verdict"] == "CLEAN"
        assert any("git" in f["why"].lower() for f in out["findings"])

    def test_json_has_required_top_level_keys(self, tmp_path):
        _, out, _ = run_scan("--repo-root", str(tmp_path))
        for key in ("verdict", "diff_source", "base_ref", "findings", "doc_gate"):
            assert key in out, f"missing top-level key {key}"
        assert isinstance(out["findings"], list)
        assert set(out["doc_gate"].keys()) >= {"found", "command", "result"}


class TestDiffAcquisition:
    def test_status_codes_from_local_git_name_status(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "a.md").write_text("# A\n")
        commit_all(repo, "base")
        base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        (repo / "a.md").unlink()
        (repo / "b.md").write_text("# B\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo), "--base-ref", base)
        assert out is not None, raw
        assert out["diff_source"] == "local"
        # base_ref echoed back resolved (non-empty)
        assert out["base_ref"]

    def test_auto_base_ref_resolves_without_explicit_flag(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "a.md").write_text("# A\n")
        commit_all(repo, "base")
        (repo / "a.md").write_text("# A\n\nmore\n")
        commit_all(repo, "head")
        rc, out, raw = run_scan("--repo-root", str(repo))
        assert rc == 0, raw
        assert out["verdict"] in ("CLEAN", "FINDINGS")
        assert out["base_ref"]  # auto-resolved (no origin/main -> first commit fallback)


class TestIntroducedReferences:
    def test_broken_relative_link_flagged(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nSee [other](missing.md).\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "FINDINGS"
        kinds = {f["kind"] for f in out["findings"]}
        assert "introduced-unresolved" in kinds
        assert any("missing.md" in f["reference"] for f in out["findings"])

    def test_resolving_link_not_flagged(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "target.md").write_text("# Target\n")
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nSee [t](target.md).\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "CLEAN", out["findings"]

    def test_template_slot_not_flagged(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nWrite to `{{PLAN_PATH}}` then stop.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "CLEAN", out["findings"]

    def test_bare_relative_path_in_prose_flagged(self, tmp_path):  # [inferred] AC1(b)
        repo = init_repo(tmp_path)
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nSee `plugins/relay/agents/ghost.md` for details.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "FINDINGS"
        assert any("ghost.md" in f["reference"] for f in out["findings"])

    def test_cross_file_anchor_against_headings(self, tmp_path):  # [inferred] AC1(c)
        repo = init_repo(tmp_path)
        (repo / "target.md").write_text("# Target\n\n## Real Heading\n")
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nSee [x](target.md#missing-heading).\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "FINDINGS"
        assert any("missing-heading" in f["reference"] for f in out["findings"])

    def test_skill_and_agent_and_command_name_resolution(self, tmp_path):  # [inferred] AC1(d)
        repo = init_repo(tmp_path)
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        # relay:<skill> with no skills/<skill>/SKILL.md, agents/<slug> with no file,
        # and /plugin:command with no plugins/*/commands/ entry -> all unresolved.
        (repo / "doc.md").write_text(
            "# Doc\n\nRun relay:ghost-skill, see agents/ghost-agent, via /relay:ghost.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "FINDINGS"
        refs = {f["reference"] for f in out["findings"]}
        # [inferred] Assert each NAME-KIND independently by its distinct reference
        # form, so a regression in any single name-kind regex is caught (the weak
        # bare-"ghost" substring would pass on any one match and mask the others).
        assert "relay:ghost-skill" in refs   # relay:<skill> kind
        assert "agents/ghost-agent" in refs  # agents/<slug> kind
        assert "/relay:ghost" in refs        # /plugin:command kind


class TestDanglingReferences:
    def test_surviving_ref_to_deleted_doc_flagged(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "old.md").write_text("# Old\n")
        (repo / "index.md").write_text("# Index\n\nSee [old](old.md).\n")
        commit_all(repo, "base")
        (repo / "old.md").unlink()
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["verdict"] == "FINDINGS"
        dangle = [f for f in out["findings"] if f["kind"] == "dangling-delete"]
        assert dangle, out["findings"]
        assert any(f["location"].startswith("index.md") for f in dangle)

    def test_surviving_ref_to_renamed_doc_flagged(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "old.md").write_text("# Old\n")
        (repo / "index.md").write_text("# Index\n\nSee [old](old.md).\n")
        commit_all(repo, "base")
        git(repo, "mv", "old.md", "new.md")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        kinds = {f["kind"] for f in out["findings"]}
        assert "dangling-rename" in kinds, out["findings"]

    def test_basename_only_ref_to_deleted_nested_doc_flagged(self, tmp_path):  # [inferred]
        # The surviving reference cites only the BASENAME of a deleted nested doc,
        # not its full path, so the path-form needle misses and the basename
        # fallback must fire (conditional-break fix).
        repo = init_repo(tmp_path)
        (repo / "docs").mkdir()
        (repo / "docs" / "guide.md").write_text("# Guide\n")
        (repo / "index.md").write_text("# Index\n\nSee `guide.md` for setup.\n")
        commit_all(repo, "base")
        (repo / "docs" / "guide.md").unlink()
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        dangle = [f for f in out["findings"] if f["kind"] == "dangling-delete"]
        assert any("guide.md" in f["reference"] for f in dangle), out["findings"]


class TestDocGate:
    def test_none_found_reported_explicitly(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nmore\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["doc_gate"]["found"] is False
        assert out["doc_gate"]["command"] is None
        assert out["doc_gate"]["result"] is None

    def test_package_json_doc_script_discovered(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "package.json").write_text(
            '{"scripts": {"docs:check": "echo ok"}}\n')
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nmore\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        assert out["doc_gate"]["found"] is True
        assert "docs:check" in out["doc_gate"]["command"]
        assert out["doc_gate"]["result"] == "not-run"  # prompt runs it, not the helper

    def test_run_gate_executes_and_maps_exit_zero_to_pass(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "package.json").write_text(
            '{"scripts": {"docs:check": "true"}}\n')
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nmore\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo), "--run-gate")
        assert out is not None, raw
        assert out["doc_gate"]["found"] is True
        assert out["doc_gate"]["result"] == "pass"

    def test_package_json_unlink_script_not_picked_as_doc_gate(self, tmp_path):
        """'unlink' script in package.json must NOT be discovered as a doc gate."""
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"unlink": "npm unlink"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert not found, (
            f"'unlink' script should not match DOC_SCRIPT_RE but got command: {command!r}")

    def test_package_json_link_check_script_picked_as_doc_gate(self, tmp_path):
        """'link-check' script in package.json IS a link-checker-style name and must be discovered."""
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"link-check": "markdown-link-check README.md"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert found is True, (
            f"'link-check' script should match DOC_SCRIPT_RE but was not discovered")

    def test_package_json_npm_link_script_not_picked_as_doc_gate(self, tmp_path):
        """'npm-link' script in package.json must NOT be discovered as a doc gate."""
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"npm-link": "npm link"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert not found, (
            f"'npm-link' script should not match DOC_SCRIPT_RE but got command: {command!r}")

    def test_package_json_validate_link_script_not_picked_as_doc_gate(self, tmp_path):
        """'validate-link' script in package.json must NOT be discovered as a doc gate."""
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"validate-link": "validate-link ./docs"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert not found, (
            f"'validate-link' script should not match DOC_SCRIPT_RE but got command: {command!r}")

    def test_package_json_linkedin_share_script_not_picked_as_doc_gate(self, tmp_path):
        """'linkedin-share' script in package.json must NOT be discovered as a doc gate.

        Regression test: round-3 verification revealed that the round-2 regex matched
        any name starting with 'link', including 'linkedin-share'.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"linkedin-share": "node scripts/share.js linkedin"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert not found, (
            f"'linkedin-share' script should not match DOC_SCRIPT_RE but got command: {command!r}")

    def test_package_json_links_script_picked_as_doc_gate(self, tmp_path):
        """'links' script in package.json IS a link-checker-style name and must be discovered."""
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"links": "linkchecker http://localhost:3000"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert found is True, (
            f"'links' script should match DOC_SCRIPT_RE but was not discovered")

    def test_makefile_docs_check_target_discovered(self, tmp_path):
        """A Makefile with a docs-check target (no package.json) must be discovered."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Makefile").write_text("docs-check:\n\techo foo\n")
        found, command = discover_doc_gate(str(repo))
        assert found is True, f"docs-check Makefile target not discovered; got: {command!r}"
        assert command == "make docs-check", f"expected 'make docs-check' but got: {command!r}"

    def test_justfile_docs_validate_target_discovered(self, tmp_path):
        """A justfile with a docs-validate target (no package.json, no Makefile) must be discovered."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "justfile").write_text("docs-validate:\n    echo foo\n")
        found, command = discover_doc_gate(str(repo))
        assert found is True, f"docs-validate justfile target not discovered; got: {command!r}"
        assert command == "just docs-validate", f"expected 'just docs-validate' but got: {command!r}"

    def test_makefile_tab_indented_target_not_matched(self, tmp_path):
        """A docs-check: token that is TAB-indented (a recipe line, not a target definition)
        must NOT be matched — the ^(docs?[\\w-]*): regex with re.M must require line-start."""
        repo = tmp_path / "repo"
        repo.mkdir()
        # This is a recipe line inside the 'build' target, NOT a target definition.
        (repo / "Makefile").write_text("build:\n\tdocs-check: echo foo\n")
        found, command = discover_doc_gate(str(repo))
        assert not found, (
            f"TAB-indented 'docs-check:' should not match as a Makefile target but got: {command!r}")
        assert command is None

    def test_makefile_invalid_target_name_rejected_continues_loop(self, tmp_path):
        """A Makefile target whose name contains a char GATE_NAME_RE rejects (e.g., 'docs|gate')
        must trigger the continue path — discover_doc_gate returns (False, None)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        # docs|gate: is not matched by ^(docs?[\w-]*): so the regex won't capture it at all.
        (repo / "Makefile").write_text("docs|gate:\n\techo foo\n")
        found, command = discover_doc_gate(str(repo))
        assert not found, (
            f"'docs|gate:' target should not be discovered but got: {command!r}")
        assert command is None

    def test_package_json_wins_over_makefile_precedence(self, tmp_path):
        """When BOTH package.json (with a matching script) AND a Makefile (with docs-check)
        exist, the npm script must win — package.json is checked first."""
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"docs:check": "echo ok"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        (repo / "Makefile").write_text("docs-check:\n\techo foo\n")
        found, command = discover_doc_gate(str(repo))
        assert found is True
        assert command.startswith("npm run"), (
            f"npm script should win over Makefile but got: {command!r}")

    def test_makefile_vs_justfile_precedence(self, tmp_path):
        """When BOTH a Makefile (docs-check) AND a justfile (docs-validate) exist,
        Makefile must win — it appears first in the discover_doc_gate loop."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Makefile").write_text("docs-check:\n\techo foo\n")
        (repo / "justfile").write_text("docs-validate:\n    echo foo\n")
        found, command = discover_doc_gate(str(repo))
        assert found is True
        assert command == "make docs-check", (
            f"Makefile should win over justfile but got: {command!r}")


class TestDocGateInjectionPrevention:
    """Regression tests: shell metacharacters in gate names must never reach execution."""

    def test_package_json_injection_name_not_returned_as_gate(self, tmp_path):
        # A package.json whose doc-script key contains shell metacharacters must be
        # silently skipped — discover_doc_gate must NOT return an injectable command.
        repo = tmp_path / "repo"
        repo.mkdir()
        # Write a package.json with an injection attempt that matches DOC_SCRIPT_RE
        # (contains "docs:check") but also contains the shell metachar ";".
        pkg = {"scripts": {"docs:check; touch /tmp/pwned": "echo injected"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        # Either no gate is found, or the command must not contain the injection string.
        if found:
            assert GATE_NAME_RE.fullmatch(command.split(" ", 2)[-1]), (
                f"injection string leaked into gate command: {command!r}"
            )
        else:
            assert command is None

    def test_package_json_clean_name_still_accepted(self, tmp_path):
        # A clean script name must still be discovered normally.
        repo = tmp_path / "repo"
        repo.mkdir()
        pkg = {"scripts": {"docs:check": "echo ok"}}
        (repo / "package.json").write_text(json.dumps(pkg))
        found, command = discover_doc_gate(str(repo))
        assert found is True
        assert command == "npm run docs:check"

    def test_gate_argv_rejects_injection_string(self):
        # _gate_argv must return None for any string containing shell metacharacters.
        assert _gate_argv("npm run docs:check; rm -rf x") is None
        assert _gate_argv("npm run docs:check && evil") is None
        assert _gate_argv("npm run docs:check|cat /etc/passwd") is None
        assert _gate_argv("make docs; touch /tmp/pwned") is None
        assert _gate_argv("just docs`id`") is None

    def test_gate_argv_accepts_clean_forms(self):
        # Known safe forms must parse to a valid argv.
        assert _gate_argv("npm run docs:check") == ["npm", "run", "docs:check"]
        assert _gate_argv("make docs-validate") == ["make", "docs-validate"]
        assert _gate_argv("just doc.check") == ["just", "doc.check"]

    def test_gate_argv_returns_none_for_unknown_form(self):
        assert _gate_argv(None) is None
        assert _gate_argv("bash -c evil") is None
        assert _gate_argv("") is None


class TestPortabilityAndBaseline:
    def test_clean_diff_is_clean_with_empty_findings(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "t.md").write_text("# T\n")
        (repo / "doc.md").write_text("# Doc\n\nSee [t](t.md).\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\nSee [t](t.md).\n\nNew prose, no refs.\n")
        commit_all(repo, "head")
        rc, out, raw = run_scan("--repo-root", str(repo))
        assert rc == 0, raw
        assert out["verdict"] == "CLEAN"
        assert out["findings"] == []

    def test_no_gh_uses_local_git_path(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "doc.md").write_text("# Doc\n")
        commit_all(repo, "base")
        (repo / "doc.md").write_text("# Doc\n\n[x](missing.md)\n")
        commit_all(repo, "head")
        # Make gh unfindable so the auto tier falls back to local git.
        #
        # This used to drop every PATH entry containing a `gh` binary, which is not
        # portable: on macOS gh lives in /opt/homebrew/bin and git in /usr/bin, so
        # only gh was removed — but on Linux both are /usr/bin, so `git` went with
        # it. Every _git call in the scanner then failed, no diff was computed, and
        # the verdict came back CLEAN. The assertion below caught it, but only
        # because this test expects FINDINGS; the sibling tests that expect CLEAN
        # would have passed for entirely the wrong reason.
        #
        # Instead, hand the child a PATH containing exactly one directory that holds
        # exactly the tools the scanner legitimately needs. gh is absent by
        # construction rather than by subtraction, on every platform.
        bin_dir = tmp_path / "sanitized-bin"
        bin_dir.mkdir()
        real_git = shutil.which("git")
        assert real_git, "git must be on PATH to run this test"
        os.symlink(real_git, bin_dir / "git")
        env = dict(os.environ)
        env["PATH"] = str(bin_dir)
        assert shutil.which("gh", path=env["PATH"]) is None
        assert shutil.which("git", path=env["PATH"]) is not None
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo-root", str(repo),
             "--pr-ref", "999", "--diff-source", "auto"],
            capture_output=True, text=True, env=env)
        out = json.loads(proc.stdout)
        assert proc.returncode == 0, proc.stderr
        assert out["diff_source"] == "local"
        assert out["verdict"] == "FINDINGS"


class TestPluginAwareResolution:
    """Plugin-aware resolution: refs inside a plugin doc resolve relative to the
    plugin root (identified by .claude-plugin/plugin.json), not just the repo root."""

    def _make_plugin_repo(self, tmp_path):
        """Create a minimal repo with a plugin layout mirroring the relay plugin."""
        repo = init_repo(tmp_path)
        plugin = repo / "plugins" / "relay"
        plugin.mkdir(parents=True)
        marker = plugin / ".claude-plugin"
        marker.mkdir()
        (marker / "plugin.json").write_text('{"name": "relay"}')
        # skills and agents dirs
        (plugin / "skills" / "refining-specs").mkdir(parents=True)
        (plugin / "skills" / "refining-specs" / "SKILL.md").write_text("# refining-specs\n")
        (plugin / "agents").mkdir()
        (plugin / "agents" / "code-reviewer.md").write_text("# code-reviewer\n")
        (plugin / "CHANGELOG.md").write_text("# Changelog\n")
        return repo, plugin

    def test_skill_in_plugin_doc_resolves(self, tmp_path):
        """relay:refining-specs cited in a plugins/relay/... doc resolves (skill at plugin path)."""
        repo, plugin = self._make_plugin_repo(tmp_path)
        doc = plugin / "docs" / "overview.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Overview\n")
        commit_all(repo, "base")
        doc.write_text("# Overview\n\nUses relay:refining-specs skill.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        introduced = [f for f in out["findings"] if f.get("reference") == "relay:refining-specs"]
        assert not introduced, (
            f"relay:refining-specs should resolve at plugin path but got finding: {introduced}")

    def test_agent_in_plugin_doc_resolves(self, tmp_path):
        """agents/code-reviewer cited in a plugins/relay/... doc resolves (agent at plugin path)."""
        repo, plugin = self._make_plugin_repo(tmp_path)
        doc = plugin / "docs" / "overview.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Overview\n")
        commit_all(repo, "base")
        doc.write_text("# Overview\n\nDelegates to agents/code-reviewer.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        introduced = [f for f in out["findings"] if f.get("reference") == "agents/code-reviewer"]
        assert not introduced, (
            f"agents/code-reviewer should resolve at plugin path but got finding: {introduced}")

    def test_bare_changelog_in_plugin_doc_resolves(self, tmp_path):
        """CHANGELOG.md bare cite in a plugins/relay/... doc resolves (plugin-relative file)."""
        repo, plugin = self._make_plugin_repo(tmp_path)
        doc = plugin / "docs" / "overview.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Overview\n")
        commit_all(repo, "base")
        doc.write_text("# Overview\n\nSee `CHANGELOG.md` for history.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        introduced = [f for f in out["findings"] if "CHANGELOG.md" in f.get("reference", "")]
        assert not introduced, (
            f"CHANGELOG.md should resolve at plugin path but got finding: {introduced}")

    def test_nonexistent_skill_in_plugin_doc_still_flagged(self, tmp_path):
        """relay:ghost-skill cited in a plugins/relay/... doc when no skills/ghost-skill/SKILL.md
        exists at any root must produce a finding — plugin-aware walk-up must not suppress it."""
        repo, plugin = self._make_plugin_repo(tmp_path)
        doc = plugin / "docs" / "overview.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Overview\n")
        commit_all(repo, "base")
        doc.write_text("# Overview\n\nUses relay:ghost-skill skill.\n")
        commit_all(repo, "head")
        _, out, raw = run_scan("--repo-root", str(repo))
        assert out is not None, raw
        flagged = [f for f in out["findings"] if f.get("reference") == "relay:ghost-skill"]
        assert flagged, (
            f"relay:ghost-skill should be flagged (no SKILL.md exists) but no finding was emitted; "
            f"all findings: {out['findings']}")
