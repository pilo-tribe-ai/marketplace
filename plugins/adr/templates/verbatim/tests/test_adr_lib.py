import json

import pytest

import adr_vendored_conftest as _cf

load_script = _cf.load_script
write = _cf.write

adr_lib = load_script("adr_lib")


# --- Task 1: the frontmatter fence ---------------------------------------

def test_a_line_one_fence_is_frontmatter():
    text = "---\nstatus: accepted\n---\n\n# Title\n"
    front, body = adr_lib.split_frontmatter(text)
    assert front == "status: accepted"
    assert body.lstrip().startswith("# Title")


def test_a_horizontal_rule_below_a_bold_key_block_is_not_frontmatter():
    text = "# ADR-002: Title\n\n**Status:** Accepted\n\n---\n\n## Context\n"
    front, body = adr_lib.split_frontmatter(text)
    assert front is None
    assert body == text


def test_an_unclosed_fence_is_not_frontmatter():
    text = "---\nstatus: accepted\n\n# Title\n"
    front, _ = adr_lib.split_frontmatter(text)
    assert front is None


# --- Task 2: minimal frontmatter reader, PyYAML optional ------------------

FLAT = (
    'type: adr\n'
    'status: accepted\n'
    'date: "2026-04-20"\n'
    'title: Order state machine: part two\n'
    'area: orders\n'
    'supersedes: null\n'
    'related: []\n'
    'superseded_by:\n'
    '  - 0088-retry-backoff.md\n'
)


def test_the_minimal_reader_handles_the_flat_subset():
    data = adr_lib.parse_simple_yaml(FLAT)
    assert data["status"] == "accepted"
    assert data["date"] == "2026-04-20"          # matched quotes stripped
    assert data["title"] == "Order state machine: part two"
    assert data["supersedes"] is None
    assert data["related"] == []
    assert data["superseded_by"] == ["0088-retry-backoff.md"]


def test_both_readers_agree(monkeypatch):
    """PyYAML turns an unquoted date into datetime.date and the minimal reader
    into a string. Normalising here is what keeps one lint rule correct under
    both readers."""
    text = "type: adr\nstatus: accepted\ndate: 2026-04-20\ntitle: T\n"
    with_yaml = adr_lib.load_frontmatter(text)
    monkeypatch.setattr(adr_lib, "HAVE_YAML", False)
    without_yaml = adr_lib.load_frontmatter(text)
    assert with_yaml == without_yaml
    assert with_yaml["date"] == "2026-04-20"


def test_keys_are_lower_cased():
    assert adr_lib.load_frontmatter("Status: Accepted\n")["status"] == "Accepted"


def test_malformed_yaml_falls_back_to_the_minimal_reader():
    """PyYAML rejects a tab-indented mapping with ScannerError. The load
    path degrades to parse_simple_yaml, which recovers the flat keys, so
    a badly-indented file still reports what it can rather than dying."""
    if not adr_lib.HAVE_YAML:
        pytest.skip("PyYAML is not installed; the fallback path is the only path")
    text = "\tstatus: accepted\n\tdate: 2026-04-20\n"
    data = adr_lib.load_frontmatter(text)
    assert isinstance(data, dict)


# --- Task 3: legacy bold-key reader ---------------------------------------

LEGACY = (
    "# ADR-002: Gateway auth\n"
    "\n"
    "**Status:** Accepted\n"
    "**Date:** 2026-02-26\n"
    "\n"
    "**Superseded By:** ADR-004-new.md\n"
    "**Authors:** Someone\n"
    "\n"
    "---\n"
    "\n"
    "## Context\n"
)


def test_the_closed_bold_key_set_parses():
    data = adr_lib.parse_legacy(LEGACY)
    assert data["status"] == "accepted"
    assert data["date"] == "2026-02-26"
    assert data["superseded_by"] == ["ADR-004-new.md"]


def test_a_key_outside_the_set_is_ignored_not_warned():
    assert "authors" not in adr_lib.parse_legacy(LEGACY)


def test_a_status_outside_the_enum_is_kept_verbatim():
    data = adr_lib.parse_legacy("**Status:** Superseded by ADR-002\n")
    assert data["status"] == "superseded by adr-002"


def test_only_the_first_twenty_raw_lines_are_read():
    text = "\n" * 20 + "**Status:** Accepted\n"
    assert adr_lib.parse_legacy(text) == {}


# --- Task 4: title fallback and filename identity --------------------------

@pytest.mark.parametrize("heading,expected", [
    ("# ADR-005 — Title", "Title"),
    ("# adr-001: Title", "Title"),
    ("# ADR-0017 Title", "Title"),
    ("# One orchestration substrate", "One orchestration substrate"),
])
def test_the_heading_marker_is_stripped(heading, expected):
    assert adr_lib.heading_title(heading + "\n\nbody\n") == expected


def test_a_file_with_no_heading_has_no_title_fallback():
    assert adr_lib.heading_title("just body text\n") is None


@pytest.mark.parametrize("name,scheme,expected", [
    ("0007-order-state-machine.md", "sequential", "0007"),
    ("order-state-machine.md", "sequential", None),
    ("2026-04-20-order.md", "date", "2026-04-20"),
    ("order.md", "date", None),
])
def test_the_prefix_comes_from_the_filename(name, scheme, expected):
    assert adr_lib.prefix_of(name, scheme) == expected


# --- Task 5: parse_adr returns its source and never an id -------------------

def test_a_frontmatter_file_reports_its_source(tmp_path):
    path = write(tmp_path / "0007-order.md",
                 "---\ntype: adr\nstatus: accepted\ndate: 2026-04-20\n"
                 "title: Order state machine\n---\n\n# ADR-0007: Order state machine\n")
    adr = adr_lib.parse_adr(path)
    assert adr.source == "frontmatter"
    assert adr.filename == "0007-order.md"
    assert adr.prefix == "0007"
    assert adr.status == "accepted"
    assert adr.title == "Order state machine"
    assert "id" not in adr.meta


def test_a_bold_key_file_parses_as_legacy(tmp_path):
    path = write(tmp_path / "ADR-002-auth.md", LEGACY)
    adr = adr_lib.parse_adr(path)
    assert adr.source == "legacy"
    assert adr.title == "Gateway auth"
    assert adr.status == "accepted"


def test_refs_accept_a_scalar_or_a_list():
    assert adr_lib.refs({"related": "a.md"}) == ["a.md"]
    assert adr_lib.refs({"related": ["a.md", "b.md"]}) == ["a.md", "b.md"]
    assert adr_lib.refs({}) == []


# --- Task 6: config loading and Discovery -----------------------------------

def _repo(tmp_path, config=None, files=()):
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    if config is not None:
        write(tmp_path / ".claude" / "adr.json", json.dumps(config))
    for name in files:
        write(tmp_path / "docs" / "adr" / name, "# stub\n")
    return tmp_path


def test_defaults_apply_when_there_is_no_config(tmp_path):
    corpus = adr_lib.load_corpus(_repo(tmp_path))
    assert corpus.config["dir"] == "docs/adr"
    assert corpus.config["register"] == "docs/adr/README.md"
    assert corpus.config["id_scheme"] == "sequential"
    assert corpus.config["gate"] == {
        "deterministic": False, "model": False, "proposed_verdict": "error"}
    assert corpus.config["archive_dir"] is None


def test_a_partial_gate_block_merges_over_the_defaults(tmp_path):
    root = _repo(tmp_path, {"version": 1, "gate": {"model": True}})
    gate = adr_lib.load_corpus(root).config["gate"]
    assert gate == {"deterministic": False, "model": True, "proposed_verdict": "error"}


def test_discovery_is_the_top_level_glob_minus_the_register(tmp_path):
    root = _repo(tmp_path, None, ["0001-a.md", "README.md", "CLAUDE.md", "stray-note.md"])
    write(root / "docs" / "adr" / "archive" / "0002-b.md", "# archived\n")
    write(root / "docs" / "adr" / "sub" / "0003-c.md", "# nested\n")
    found = [p.name for p in adr_lib.discover(adr_lib.load_corpus(root))]
    assert found == ["0001-a.md", "stray-note.md"]


def test_a_renamed_register_is_still_excluded(tmp_path):
    root = _repo(tmp_path, {"version": 1, "register": "docs/adr/index.md"},
                 ["0001-a.md", "index.md"])
    found = [p.name for p in adr_lib.discover(adr_lib.load_corpus(root))]
    assert found == ["0001-a.md"]


# --- Task 7: the frontmatter writer -----------------------------------------

def test_the_writer_emits_the_fixed_key_order_and_no_id():
    text = adr_lib.dump_frontmatter({
        "id": 7, "title": "Order state machine", "status": "proposed",
        "date": "2026-08-13", "type": "adr", "related": ["0003-a.md"],
    })
    keys = [line.split(":")[0] for line in text.splitlines() if not line.startswith(" ")]
    assert keys == ["type", "status", "date", "title", "supersedes",
                    "superseded_by", "related"]
    assert "id" not in text


def test_a_title_holding_a_colon_round_trips_through_both_readers(monkeypatch):
    title = "Order state machine: part two"
    text = adr_lib.dump_frontmatter(
        {"type": "adr", "status": "proposed", "date": "2026-08-13", "title": title})
    assert adr_lib.load_frontmatter(text)["title"] == title
    monkeypatch.setattr(adr_lib, "HAVE_YAML", False)
    assert adr_lib.load_frontmatter(text)["title"] == title


def test_an_empty_optional_key_is_omitted_and_null_is_written():
    text = adr_lib.dump_frontmatter(
        {"type": "adr", "status": "proposed", "date": "2026-08-13", "title": "T"})
    assert "area:" not in text
    assert "supersedes: null" in text
    assert "related: []" in text


# --- Task 8: adr.schema.json, bound to the code -----------------------------

def test_the_schema_matches_the_parser_constants(schemas_dir):
    schema = json.loads(
        (schemas_dir / "adr.schema.json").read_text(encoding="utf-8"))
    assert sorted(schema["required"]) == sorted(adr_lib.REQUIRED_KEYS)
    assert schema["properties"]["status"]["enum"] == list(adr_lib.STATUSES)
    assert "id" not in schema["properties"]
    assert schema["additionalProperties"] is False
