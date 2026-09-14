"""Guard tests for skills/dispatching-bg-agents/SKILL.md (spec §Deliverable 2,
Dispatch/Completion). Mirror of test_dispatching_acpx_skill.py, adapted to the
bg-sessions dispatcher's own contract."""
from pathlib import Path

import pytest
import yaml

from conftest import PLUGIN_ROOT, parse_frontmatter

SKILL_DIR = PLUGIN_ROOT / "skills" / "dispatching-bg-agents"
SKILL = SKILL_DIR / "SKILL.md"


def _body():
    return SKILL.read_text()


class TestFrontmatter:
    def test_skill_file_exists(self):
        assert SKILL.is_file()

    def test_frontmatter_name_matches_dir(self):
        fm, _ = parse_frontmatter(SKILL)
        assert fm["name"] == "dispatching-bg-agents"

    def test_user_invocable_false(self):
        fm, _ = parse_frontmatter(SKILL)
        assert fm["user-invocable"] is False

    def test_description_names_its_sibling(self):
        fm, _ = parse_frontmatter(SKILL)
        assert "dispatching-acpx-agents" in fm["description"]

    def test_description_non_empty(self):
        fm, _ = parse_frontmatter(SKILL)
        assert fm["description"].strip()


class TestWrapperContract:
    def test_wrapper_contract_block_present(self):
        assert "dispatch(role_slug, binding, inputs) →" in _body()

    def test_six_responsibilities_numbered(self):
        body = _body()
        for lead in (
            "**Resolve bindings.**",
            "**Validate capabilities.**",
            "**Materialize the role body.**",
            "**Wrap with scaffolding.**",
            "**Resolve the modality, then launch.**",
            "**Capture and verify.**",
        ):
            assert lead in body, f"missing responsibility lead term: {lead!r}"

    def test_bindings_are_unchanged_in_v1(self):
        body = _body()
        assert "unchanged in v1" in body
        assert "no new binding field" in body or "No new binding field" in body


class TestLaunchAndSidecar:
    def test_launcher_is_bg_launch_sh(self):
        assert "bg-launch.sh" in _body()
        assert "only sanctioned launcher" in _body()

    def test_sidecar_path_and_all_six_keys(self):
        body = _body()
        assert "~/.claude/relay/bg/${runid}/${role_slug}.env" in body
        for key in (
            "RELAY_BG_NAME", "RELAY_BG_SHORT_ID", "RELAY_BG_HANDOFF",
            "RELAY_BG_MODEL", "RELAY_BG_PERMISSION_MODE", "RELAY_BG_MAX_TURNS",
        ):
            assert key in body, f"sidecar contract missing {key}"

    def test_handoff_path_documented(self):
        body = _body()
        assert "$WORKTREE/.relay-bg/" in body
        assert ".envelope" in body

    def test_truncate_not_append_rule(self):
        body = _body().lower()
        assert "truncate" in body
        assert "never append" in body

    def test_turn_marker_rule(self):
        body = _body()
        assert "TURN=" in body
        assert "discard" in body.lower()


class TestBucketTable:
    @pytest.mark.parametrize("row", [
        "ROLE_DONE", "BLOCKED:", "NEEDS_DECISION:", "not-done", "errored",
    ])
    def test_bucket_table_rows(self, row):
        assert row in _body()

    def test_no_role_result_from_a_bg_child(self):
        assert "No bg child ever emits `ROLE_RESULT=`" in _body() or \
            "no bg child ever emits" in _body().lower()


class TestLifecycleAndStop:
    def test_stop_lifecycle_documented(self):
        body = _body()
        assert "done" in body and "errored" in body and "needs-decision" in body
        assert "finish-and-stop" in body

    def test_stop_mechanism_defers_to_the_contract(self):
        body = _body()
        assert "docs/bg-dispatch-contract.md" in body
        assert "not a second one invented here" in body or "not a second one" in body


class TestPreambleAndScope:
    def test_preamble_replaces_the_parent_line(self):
        assert "write your envelope to" in _body()

    def test_names_no_acpx_env_var(self):
        assert "ACPX_" not in _body()

    def test_unverified_multiturn_and_fallback_recorded(self):
        body = _body()
        assert "[unverified]" in body
        assert "one_shot" in body


class TestFilesSection:
    def test_files_section_matches_the_directory(self):
        body = _body()
        on_disk = {p.name for p in SKILL_DIR.iterdir() if p.is_file()}
        for name in on_disk:
            assert f"`{name}`" in body, f"{name} exists on disk but is not listed in ## Files"

    def test_no_relay_vocab_block(self):
        assert "```relay-vocab" not in _body()


class TestNestedDispatch:
    """The `## Nested dispatch` section documents the skill-leaf primitive, the
    rejected slash-command leaf, and the async-collection rule for a nested Workflow
    result. Slice the section out (heading to the next `## `) so a mention elsewhere
    cannot satisfy the assertions."""

    def _section(self):
        body = _body()
        assert "## Nested dispatch" in body, "SKILL.md is missing the Nested dispatch section"
        return body.split("## Nested dispatch", 1)[1].split("\n## ", 1)[0]

    def test_names_the_skill_leaf_primitive(self):
        assert "skill leaf" in self._section().lower()

    def test_records_the_rejected_slash_command_leaf_reason(self):
        assert "disable-model-invocation: true" in self._section()

    def test_names_the_async_collection_tools(self):
        section = self._section()
        assert "ToolSearch" in section
        assert "TaskOutput" in section


class TestPreambleClassifierRefusal:
    """Pin the exact literal string a bg child must write on a classifier refusal.
    Asserting on a paraphrase would pass for the wrong reason; grepping only for
    `classifier` proves nothing."""

    def test_preamble_pins_the_exact_blocked_wording(self):
        preamble = SKILL_DIR / "preamble.md"
        assert preamble.is_file()
        assert "BLOCKED: classifier refused <tool>: <reason>" in preamble.read_text()
