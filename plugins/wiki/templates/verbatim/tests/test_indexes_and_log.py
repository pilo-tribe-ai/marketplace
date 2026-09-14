"""Tests for Ingest steps 7-9: index regeneration, the log entry, and the
final full-bundle conformance gate."""
import json
import re

import pytest

from conftest import (
    CONCEPT_FILES,
    ENTITY_FILES,
    OPEN_QUESTION_FILES,
    SOURCE_FILES,
    SYNTHESIS_FILES,
    WIKI,
    read_frontmatter,
    run_checker,
)


@pytest.mark.parametrize(
    "subdir, files",
    [
        ("entities", ENTITY_FILES),
        ("concepts", CONCEPT_FILES),
        ("open-questions", OPEN_QUESTION_FILES),
        ("synthesis", SYNTHESIS_FILES),
        ("sources", SOURCE_FILES),
    ],
)
def test_subdir_index_lists_all_pages(subdir, files):
    text = (WIKI / subdir / "index.md").read_text()
    for name in files:
        assert f"]({name})" in text


# Discovered from disk rather than hard-coded, so this test runs against
# whatever the bundle actually holds instead of asserting fixed filenames
# that don't exist on a freshly scaffolded, zero-page bundle.
_DESCRIPTION_CASES = (
    [("concepts", name) for name in CONCEPT_FILES]
    + [("entities", name) for name in ENTITY_FILES]
    + [("synthesis", name) for name in SYNTHESIS_FILES]
)


@pytest.mark.parametrize(
    "subdir, name",
    _DESCRIPTION_CASES
    or [
        pytest.param(
            None,
            None,
            marks=pytest.mark.skip(
                reason="empty bundle: no concept/entity/synthesis pages yet"
            ),
        )
    ],
)
def test_index_descriptions_match_frontmatter_verbatim(subdir, name):
    data = read_frontmatter(WIKI / subdir / name)
    index_text = (WIKI / subdir / "index.md").read_text()
    description = " ".join(data["description"].split())
    assert description in index_text


def test_log_has_initialization_then_ingest_in_order():
    if not SOURCE_FILES:
        pytest.skip("empty bundle: no Ingest has run yet")
    text = (WIKI / "log.md").read_text()
    date_block = re.split(r"^## \d{4}-\d{2}-\d{2}$", text, flags=re.M)[1]
    init_pos = date_block.find("**Initialization**")
    ingest_pos = date_block.find("**Ingest**")
    assert init_pos != -1 and ingest_pos != -1
    assert init_pos < ingest_pos


@pytest.mark.parametrize(
    "name",
    SOURCE_FILES
    or [pytest.param(None, marks=pytest.mark.skip(reason="empty bundle: no Source pages yet"))],
)
def test_log_records_an_ingest_for_every_source(name):
    """Every Source page must be traceable to a log entry. Asserted per
    source rather than as one total-count string, so a later Ingest of a
    second source does not invalidate the first one's entry."""
    text = (WIKI / "log.md").read_text()
    assert f"](sources/{name})" in text, f"log.md has no Ingest entry linking {name}"


def test_log_ingest_entry_reports_page_counts():
    total = (
        len(ENTITY_FILES) + len(CONCEPT_FILES)
        + len(SYNTHESIS_FILES) + len(OPEN_QUESTION_FILES)
    )
    if total == 0:
        pytest.skip("empty bundle: no ingest yet, nothing to count")
    text = (WIKI / "log.md").read_text()
    counted = sum(int(n) for n in re.findall(r"(\d+) (?:entity|concept|synthesis|open)", text))
    assert counted == total, (
        f"log.md accounts for {counted} pages but the bundle holds {total}"
    )


def test_full_bundle_conforms_strict():
    result = run_checker(WIKI, "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors, 0 warnings" in result.stdout


def test_full_bundle_has_expected_file_count():
    result = run_checker(WIKI, "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["files_checked"] > 0
    assert payload["errors"] == 0
    assert payload["warnings"] == 0
