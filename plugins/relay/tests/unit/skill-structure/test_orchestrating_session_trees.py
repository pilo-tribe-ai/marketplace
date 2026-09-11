"""Guard tests for skills/orchestrating-session-trees/SKILL.md (spec §Deliverable 3,
Doctrine). The substrate skill for `--engine session-tree` — MAIN spawns the tree,
routes questions, and runs the end-of-run stop protocol."""
from conftest import PLUGIN_ROOT, parse_frontmatter

SKILL_DIR = PLUGIN_ROOT / "skills" / "orchestrating-session-trees"
SKILL = SKILL_DIR / "SKILL.md"


def _body():
    return SKILL.read_text()


class TestFrontmatter:
    def test_skill_exists_and_frontmatter(self):
        assert SKILL.is_file()
        fm, _ = parse_frontmatter(SKILL)
        assert fm["name"] == "orchestrating-session-trees"
        assert fm["user-invocable"] is False
        assert fm.get("description", "").strip()

    def test_no_relay_vocab_block(self):
        assert "```relay-vocab" not in _body()


class TestScope:
    def test_scope_is_implement_only(self):
        body = _body()
        assert "## Scope" in body
        assert "/relay:implement" in body
        assert "only" in body.lower()


class TestTopology:
    def test_spawns_flat(self):
        body = _body()
        assert "spawns every session" in body
        assert "flat" in body

    def test_operators_never_spawn(self):
        body = _body()
        assert "Operators never spawn" in body or "never spawn" in body
        assert "S3-1" in body

    def test_v1_cap_stated(self):
        body = _body()
        assert "one operator per goal" in body
        assert "three workers" in body

    def test_cap_is_reported_when_it_binds(self):
        body = _body()
        assert "report" in body.lower()
        assert "cap" in body.lower()
        assert "name the cap" in body.lower() or "must name the cap" in body.lower()


class TestBookkeeping:
    def test_manifest_path_and_script(self):
        body = _body()
        assert "manifest.json" in body
        assert "bg-manifest.sh" in body

    def test_manifest_write_failure_is_fatal(self):
        body = _body()
        assert "FATAL" in body

    def test_runid_is_orchestrator_allocated(self):
        body = _body()
        assert "record-run-intent.sh" in body
        assert "never runs" in body or "never run" in body


class TestQuestions:
    def test_question_routing_three_hops(self):
        body = _body()
        assert "worker" in body.lower() and "operator" in body.lower()
        assert "worker → operator → orchestrator" in body

    def test_escalation_token_used_for_a_relay(self):
        assert "ESCALATION from" in _body()

    def test_askuserquestion_only_in_an_interactive_run(self):
        body = _body()
        assert "AskUserQuestion" in body
        assert "interactive" in body.lower()

    def test_headless_escalates_to_the_parent_session(self):
        body = _body()
        assert "headless" in body.lower()
        assert "parent session" in body.lower()


class TestEndOfRun:
    def test_end_of_run_names_unstoppable_children(self):
        body = _body()
        assert "## End of run" in body
        assert "named" in body.lower() or "names" in body.lower()

    def test_resume_reads_the_manifest_then_polls_liveness(self):
        body = _body()
        assert "## Resume" in body
        assert "manifest" in body.lower()
        assert "bg-liveness.sh" in body


class TestWaitingAndStopMechanism:
    def test_waiting_section_matches_the_verified_answer(self):
        """The [unverified] check could not run live in this task; the skill must
        state the bounded-poll fallback, and must not also claim free waiting."""
        body = _body()
        assert "## Waiting" in body
        assert "bounded" in body.lower() and "poll" in body.lower()
        assert "unverified" in body.lower()
        # never claims free waiting is the shipped behavior
        assert "the orchestrator ends its turn, an" not in body

    def test_stop_mechanism_defers_to_the_contract(self):
        body = _body()
        assert "§Spawn authority" in body or "Spawn authority" in body
        assert "docs/bg-dispatch-contract.md" in body
        assert "does not restate" in body.lower()
