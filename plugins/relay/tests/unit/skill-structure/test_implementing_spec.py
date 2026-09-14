"""The relay:implementing-spec adapter (#75).

`apk/bin/check-deps.sh` looks on disk for
<relay-root>/skills/implementing-spec/SKILL.md and blocks when it is absent, and
apk/tests/unit/test_cross_plugin_skill_names.py pins the name. The path and the
name are a cross-repository contract: do not rename either.
"""

import pytest

from conftest import PLUGIN_ROOT, parse_frontmatter

SKILL = PLUGIN_ROOT / "skills" / "implementing-spec" / "SKILL.md"


class TestTheProbedPath:
    def test_the_file_is_where_apk_looks(self):
        assert SKILL.is_file()

    def test_the_name_matches_the_directory(self):
        fm, _ = parse_frontmatter(SKILL)
        assert fm["name"] == "implementing-spec"

    def test_it_is_internal(self):
        fm, _ = parse_frontmatter(SKILL)
        assert fm.get("user-invocable") is False


class TestTheCallerContract:
    @pytest.mark.parametrize("key", ["spec_path", "branch_hint", "closes_issue", "worktree"])
    def test_it_reads_the_four_keys(self, key):
        _, body = parse_frontmatter(SKILL)
        assert key in body

    def test_body_names_worktree_mismatch_and_the_two_labels(self):
        """`worktree-mismatch` is a status reason word inside the `blocked` block
        (Step 1.5), not an input key — checked separately from the four keys above."""
        _, body = parse_frontmatter(SKILL)
        assert "worktree-mismatch" in body
        assert "caller declared:" in body
        assert "skill running in:" in body

    def test_it_asks_nothing(self):
        """The call is a node inside an autonomous Workflow. AskUserQuestion is
        stripped there, so a skill that waits for an answer hangs the run."""
        fm, body = parse_frontmatter(SKILL)
        assert "AskUserQuestion" not in str(fm)
        assert "never waits for an answer" in body

    def test_it_makes_no_worktree_and_keeps_the_branch(self):
        _, body = parse_frontmatter(SKILL)
        assert "Make no worktree" in body
        assert "branch_hint" in body
        assert "stale" in body

    def test_it_pins_the_kind_and_the_verify_flag(self):
        _, body = parse_frontmatter(SKILL)
        assert "kind" in body and "feature" in body
        assert "verify" in body and "true" in body

    def test_it_calls_the_spine_skill(self):
        _, body = parse_frontmatter(SKILL)
        assert "relay:running-implement-spine" in body


class TestTheReturnedObject:
    @pytest.mark.parametrize("status", ["ok", "blocked", "error"])
    def test_every_status_has_a_condition(self, status):
        _, body = parse_frontmatter(SKILL)
        assert f"`{status}`" in body

    def test_ok_needs_a_commit(self):
        _, body = parse_frontmatter(SKILL)
        assert "Never return `ok` for a run that made no commit." in body

    def test_a_missing_or_wrong_spec_blocks(self):
        _, body = parse_frontmatter(SKILL)
        assert "lifecycle_state: specified" in body
        assert "blocked" in body

    def test_findings_and_unverified_are_errors(self):
        _, body = parse_frontmatter(SKILL)
        for token in ("findings", "unverified"):
            assert token in body

    def test_the_pull_request_gap_is_stated(self):
        """Relay opens no pull request. pr_url stays in the object for
        compatibility and is always absent."""
        _, body = parse_frontmatter(SKILL)
        assert "pr_url" in body
        assert "always absent" in body

    def test_the_issue_link_survives_in_the_commit(self):
        _, body = parse_frontmatter(SKILL)
        assert "Closes #" in body
