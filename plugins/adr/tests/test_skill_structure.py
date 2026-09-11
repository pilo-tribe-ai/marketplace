"""Every skill and command is registered under the name its dispatch site
uses, and the model-invocation split holds in both directions."""
import adr_plugin_conftest as _cf

frontmatter = _cf.frontmatter

EXPECTED_SKILLS = ["scaffolding-adr-corpora", "authoring-adrs", "consulting-decisions",
                   "amending-adrs", "indexing-adrs", "reviewing-adr-adherence",
                   "grooming-adrs"]
EXPECTED_COMMANDS = ["setup", "new", "ask", "index", "migrate", "check", "groom"]


def meta(path):
    return frontmatter(path.read_text(encoding="utf-8"), path.name)


def body(plugin_root, name):
    return (plugin_root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_every_expected_skill_exists_with_a_description(plugin_root):
    for name in EXPECTED_SKILLS:
        path = plugin_root / "skills" / name / "SKILL.md"
        assert path.is_file(), f"skills/{name}/SKILL.md is missing"
        data = meta(path)
        assert data["name"] == name, f"{name} registers under {data['name']!r}"
        assert data["description"].strip()


def test_the_skill_directory_holds_nothing_unexpected(plugin_root):
    found = sorted(p.name for p in (plugin_root / "skills").iterdir() if p.is_dir())
    assert found == sorted(EXPECTED_SKILLS)


def test_every_expected_command_exists_and_nothing_else(plugin_root):
    found = sorted(p.stem for p in (plugin_root / "commands").glob("*.md"))
    assert found == sorted(EXPECTED_COMMANDS)


def test_every_command_disables_model_invocation(plugin_root):
    for name in EXPECTED_COMMANDS:
        data = meta(plugin_root / "commands" / f"{name}.md")
        assert data.get("disable-model-invocation") is True, (
            f"/adr:{name} is user-typed and must disable model invocation")


def test_no_skill_disables_model_invocation(plugin_root):
    """Skills are what a session reaches for on its own. This split is the
    mechanism that makes the plugin engage without being asked."""
    for name in EXPECTED_SKILLS:
        data = meta(plugin_root / "skills" / name / "SKILL.md")
        assert "disable-model-invocation" not in data, (
            f"{name} would never fire on its own")


def test_the_setup_command_invokes_the_setup_skill(plugin_root):
    text = (plugin_root / "commands" / "setup.md").read_text(encoding="utf-8")
    assert "scaffolding-adr-corpora" in text
    assert "$ARGUMENTS" in text


def test_setup_never_declares_success_with_a_red_gate(plugin_root):
    text = (plugin_root / "skills" / "scaffolding-adr-corpora" / "SKILL.md").read_text("utf-8")
    assert "adr_index.py --write" in text and "adr_lint.py" in text
    assert "only when" in text.lower() and "green" in text.lower()


# --- Task 28: authoring-adrs -------------------------------------------------

def test_capture_writes_proposed_and_keeps_working(plugin_root):
    """Asking was rejected: it breaks flow, and in an unattended session nobody
    is there to answer, so the decision is lost anyway."""
    text = body(plugin_root, "authoring-adrs")
    assert "status: proposed" in text
    assert "Do not stop to ask" in text
    assert "keep working" in text.lower()


def test_capture_states_the_bar(plugin_root):
    text = body(plugin_root, "authoring-adrs")
    assert "expensive to undo" in text
    assert "cheap to change your mind" in text.lower()


def test_capture_is_model_invocable_from_its_description(plugin_root):
    data = meta(plugin_root / "skills" / "authoring-adrs" / "SKILL.md")
    assert "disable-model-invocation" not in data
    assert "/adr:new" in data["description"]


def test_capture_never_writes_an_id_and_says_the_filename_is_the_identity(plugin_root):
    text = body(plugin_root, "authoring-adrs")
    assert "filename is the identity" in text.lower()
    assert "never write an `id`" in text.lower() or "no `id` field" in text.lower()


def test_capture_runs_the_index_and_the_lint_after_it_writes(plugin_root):
    text = body(plugin_root, "authoring-adrs")
    assert "scripts/adr/adr_new.py" in text
    assert "scripts/adr/adr_index.py --write" in text
    assert "scripts/adr/adr_lint.py" in text


def test_the_distillation_standard_lists_all_four_tells(plugin_root):
    text = (plugin_root / "skills" / "authoring-adrs" / "distillation.md").read_text("utf-8")
    for tell in ("since landed", "struck-through", "justifying why something was kept",
                 "## Update"):
        assert tell in text, f"the distillation standard does not name: {tell}"
    assert "rewrite in place" in text.lower() and "never append" in text.lower()


# --- Task 29: /adr:new -------------------------------------------------------

def test_new_invokes_the_authoring_skill(plugin_root):
    text = (plugin_root / "commands" / "new.md").read_text(encoding="utf-8")
    assert "authoring-adrs" in text and "$ARGUMENTS" in text


def test_new_holds_no_write_procedure_of_its_own(plugin_root):
    """The command is a door, not a second copy of the procedure."""
    text = (plugin_root / "commands" / "new.md").read_text(encoding="utf-8")
    assert "adr_new.py" not in text


# --- Task 30: consulting-decisions -------------------------------------------

def test_recall_has_no_tool_that_can_change_the_repo(plugin_root):
    """The firewall is the tool list, not a promise in the prose. A skill that
    holds Write can write, whatever its body says."""
    data = meta(plugin_root / "skills" / "consulting-decisions" / "SKILL.md")
    tools = {tool.strip() for tool in str(data["allowed-tools"]).split(",")}
    assert tools <= {"Read", "Grep", "Glob"}, f"recall holds a mutating tool: {tools}"


def test_recall_reads_the_register_before_any_adr(plugin_root):
    """A corpus of 122 ADRs costs about 122 lines to rule out, instead of 122
    file reads."""
    text = body(plugin_root, "consulting-decisions")
    lowered = text.lower()
    assert "read the register first" in lowered
    assert "open only the" in lowered
    assert lowered.index("register") < lowered.index("open only the")


def test_recall_cites_path_and_line(plugin_root):
    text = body(plugin_root, "consulting-decisions")
    assert "path:line" in text


def test_recall_states_what_the_corpus_does_not_cover(plugin_root):
    text = body(plugin_root, "consulting-decisions").lower()
    assert "does not cover" in text
    assert "what was recorded" in text and "not what the code" in text


def test_recall_fires_before_architectural_work(plugin_root):
    data = meta(plugin_root / "skills" / "consulting-decisions" / "SKILL.md")
    assert "why did we" in data["description"].lower()
    assert "/adr:ask" in data["description"]


# --- Task 31: /adr:ask -------------------------------------------------------

def test_ask_invokes_the_recall_skill_and_stays_read_only(plugin_root):
    data = meta(plugin_root / "commands" / "ask.md")
    tools = {tool.strip() for tool in str(data["allowed-tools"]).split(",")}
    assert tools <= {"Read", "Grep", "Glob", "Skill"}, (
        f"/adr:ask can change the repo through {tools}")
    text = (plugin_root / "commands" / "ask.md").read_text(encoding="utf-8")
    assert "consulting-decisions" in text and "$ARGUMENTS" in text


# --- Task 32: amending-adrs ---------------------------------------------------

def test_amend_rewrites_in_place_and_never_appends(plugin_root):
    text = body(plugin_root, "amending-adrs").lower()
    assert "rewrite" in text and "in place" in text
    assert "never append" in text
    assert "git holds the history" in text


def test_amend_sets_both_sides_of_a_supersede(plugin_root):
    """A one-sided supersede is a lint error. The skill that creates the link
    must set both halves, or every amend leaves the corpus red."""
    text = body(plugin_root, "amending-adrs")
    assert "superseded_by" in text and "supersedes" in text
    assert "both" in text.lower()


def test_amend_holds_filenames_not_numbers(plugin_root):
    text = body(plugin_root, "amending-adrs").lower()
    assert "filename" in text
    assert "not a number" in text or "never a number" in text


def test_amend_runs_the_index_and_the_lint(plugin_root):
    text = body(plugin_root, "amending-adrs")
    assert "adr_index.py --write" in text and "adr_lint.py" in text


def test_amend_applies_the_distillation_standard(plugin_root):
    text = body(plugin_root, "amending-adrs")
    assert "distillation.md" in text


# --- Task 33: indexing-adrs ---------------------------------------------------

def test_indexing_runs_the_write_then_the_lint(plugin_root):
    text = body(plugin_root, "indexing-adrs")
    assert text.index("adr_index.py --write") < text.index("adr_lint.py")


def test_indexing_forbids_hand_editing_between_the_markers(plugin_root):
    text = body(plugin_root, "indexing-adrs")
    assert "between the markers" in text
    assert "ADR-INDEX:BEGIN" in text


def test_indexing_says_what_to_do_with_a_dropped_row(plugin_root):
    """A dropped summary is reported in the receipt. A skill that ignores the
    receipt turns that report into a silent loss."""
    text = body(plugin_root, "indexing-adrs").lower()
    assert "dropped row" in text
    assert "unparsed row" in text


def test_indexing_never_reports_success_on_a_red_lint(plugin_root):
    text = body(plugin_root, "indexing-adrs").lower()
    assert "never" in text and ("red" in text or "non-zero" in text)


def test_indexing_tells_the_reader_to_write_summaries_by_hand(plugin_root):
    text = body(plugin_root, "indexing-adrs")
    assert "<!-- TODO: summary -->" in text


# --- Task 34: /adr:index -------------------------------------------------------

def test_index_invokes_the_indexing_skill(plugin_root):
    text = (plugin_root / "commands" / "index.md").read_text(encoding="utf-8")
    assert "indexing-adrs" in text


def test_every_command_this_node_ships_is_in_the_readme(plugin_root):
    text = (plugin_root / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED_COMMANDS:
        assert f"/adr:{name}" in text, f"the README does not name /adr:{name}"


# --- Task 38: /adr:migrate and the migrate path inside setup -----------------

def test_migrate_invokes_the_setup_skill(plugin_root):
    text = (plugin_root / "commands" / "migrate.md").read_text(encoding="utf-8")
    assert "scaffolding-adr-corpora" in text


def test_migrate_names_both_levers_and_warns_that_one_breaks_links(plugin_root):
    text = (plugin_root / "commands" / "migrate.md").read_text(encoding="utf-8")
    assert "--frontmatter" in text and "--rename" in text
    assert "link" in text.lower()


def test_setup_migrate_adopts_first_then_converts(plugin_root):
    text = body(plugin_root, "scaffolding-adr-corpora")
    assert "adr_migrate.py" in text
    assert "adopts, then converts" in text.lower() or "adopt, then convert" in text.lower()


def test_setup_stages_the_migration_for_review(plugin_root):
    text = body(plugin_root, "scaffolding-adr-corpora").lower()
    assert "commits nothing" in text or "never commits" in text


# --- Task 39: reviewing-adr-adherence and /adr:check -------------------------

def test_the_model_tier_reads_the_branch_diff(plugin_root):
    text = body(plugin_root, "reviewing-adr-adherence")
    assert "git diff" in text and "...HEAD" in text
    assert ".claude/adr.json" in text


def test_the_model_tier_runs_both_checks(plugin_root):
    text = body(plugin_root, "reviewing-adr-adherence").lower()
    assert "contradicts an accepted adr" in text
    assert "no adr" in text and "hard to reverse" in text


def test_the_model_tier_is_advisory_and_always_exits_zero(plugin_root):
    """Both model checks can cry wolf. They report findings; they do not block
    on their own judgement. The deterministic tier is what the gate blocks on."""
    text = body(plugin_root, "reviewing-adr-adherence")
    assert "exit 0" in text
    assert "advisory" in text.lower()
    assert "never block" in text.lower() or "does not block" in text.lower()


def test_the_model_tier_names_the_file_and_the_adr_in_each_finding(plugin_root):
    text = body(plugin_root, "reviewing-adr-adherence").lower()
    assert "one bullet" in text
    assert "naming the file" in text or "name the file" in text


def test_check_invokes_the_review_skill(plugin_root):
    text = (plugin_root / "commands" / "check.md").read_text(encoding="utf-8")
    assert "reviewing-adr-adherence" in text


# --- Task 40: the optional CI gate --------------------------------------------
# See test_templates.py and test_scaffold.py for the gate template and the
# scaffold.py wiring. Nothing here is skill-structure specific.


# --- Task 41: grooming-adrs and /adr:groom ------------------------------------

def test_grooming_always_plans_and_diffs_first(plugin_root):
    text = body(plugin_root, "grooming-adrs").lower()
    assert "plan" in text and "diff" in text
    assert "never rewrite" in text or "never rewrites" in text


def test_grooming_lists_all_four_jobs(plugin_root):
    text = body(plugin_root, "grooming-adrs").lower()
    for job in ("merge", "retire", "compress", "archive"):
        assert job in text, f"grooming does not name the {job} job"


def test_grooming_is_invoked_by_a_human_not_by_the_model(plugin_root):
    """Grooming rewrites a corpus. The spec says a human invokes it."""
    text = body(plugin_root, "grooming-adrs").lower()
    assert "invoked by a human" in text or "a human invokes" in text


def test_archiving_rewrites_the_register_key_before_the_next_regeneration(plugin_root):
    text = body(plugin_root, "grooming-adrs")
    assert "archive_dir" in text
    assert "./archive/" in text or "archive/" in text
    assert "summary" in text.lower()
    assert "adr_index.py --write" in text


def test_grooming_repairs_inbound_links_when_it_moves_a_file(plugin_root):
    text = body(plugin_root, "grooming-adrs").lower()
    assert "inbound link" in text


def test_grooming_applies_the_distillation_standard_in_job_three(plugin_root):
    assert "distillation.md" in body(plugin_root, "grooming-adrs")


def test_groom_invokes_the_grooming_skill(plugin_root):
    text = (plugin_root / "commands" / "groom.md").read_text(encoding="utf-8")
    assert "grooming-adrs" in text


# --- Task 42: the full surface, the README, and the CHANGELOG ----------------

def test_the_surface_is_seven_skills_and_seven_commands(plugin_root):
    assert len(EXPECTED_SKILLS) == 7
    assert len(EXPECTED_COMMANDS) == 7
    assert sorted(p.name for p in (plugin_root / "skills").iterdir() if p.is_dir()) \
        == sorted(EXPECTED_SKILLS)
    assert sorted(p.stem for p in (plugin_root / "commands").glob("*.md")) \
        == sorted(EXPECTED_COMMANDS)


def test_every_command_maps_to_a_skill_that_exists(plugin_root):
    """A command naming a skill by the wrong name is unreachable, and the run
    reports no error."""
    for name in EXPECTED_COMMANDS:
        text = (plugin_root / "commands" / f"{name}.md").read_text(encoding="utf-8")
        named = [skill for skill in EXPECTED_SKILLS if skill in text]
        assert named, f"/adr:{name} names no skill in the roster"


def test_the_readme_names_every_command_and_the_invariants(plugin_root):
    text = (plugin_root / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED_COMMANDS:
        assert f"/adr:{name}" in text
    for invariant in ("filename is an ADR's identity", "standard library",
                      "survive every regeneration", "status: proposed"):
        assert invariant in text, f"the README does not state: {invariant}"


def test_the_changelog_records_the_manifest_version_and_the_surface(plugin_root, plugin_json):
    text = (plugin_root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert plugin_json["version"] in text
    for name in EXPECTED_COMMANDS:
        assert f"/adr:{name}" in text
