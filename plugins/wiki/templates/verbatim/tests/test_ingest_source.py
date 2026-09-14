"""Tests for Ingest steps 1-4: raw/ move and the Source page."""
import pytest

from conftest import (
    CONCEPT_FILES,
    ENTITY_FILES,
    OPEN_QUESTION_FILES,
    SOURCE_FILES,
    SYNTHESIS_FILES,
    WIKI,
    WIKI_ROOT,
    read_frontmatter,
)

FED_HEADING = "## Pages this source fed"
PAGE_DIRS = (
    ("entities", ENTITY_FILES),
    ("concepts", CONCEPT_FILES),
    ("synthesis", SYNTHESIS_FILES),
    ("open-questions", OPEN_QUESTION_FILES),
)

VALID_STATUSES = ("draft", "stable", "deprecated")


def test_every_source_page_resource_resolves():
    """Every Source page's 'resource' must point at a file that actually
    exists under the container -- the raw file that fed it. Discovered from
    disk, not from a hard-coded filename, so this holds for any ingested
    source. Skips cleanly on a freshly scaffolded bundle that has not
    ingested anything yet."""
    if not SOURCE_FILES:
        pytest.skip("empty bundle: no Source pages yet")
    for name in SOURCE_FILES:
        data = read_frontmatter(WIKI / "sources" / name)
        resource = data.get("resource")
        assert resource, f"{name} has no 'resource' field"
        assert (WIKI_ROOT / resource).is_file(), (
            f"{name} 'resource: {resource}' does not resolve under {WIKI_ROOT}"
        )


def test_source_page_exists_with_correct_frontmatter():
    if not SOURCE_FILES:
        pytest.skip("empty bundle: no Source pages yet")
    for name in SOURCE_FILES:
        data = read_frontmatter(WIKI / "sources" / name)
        assert data["type"] == "Source"
        assert data.get("generated", {}).get("by"), f"{name} has no generated.by"
        assert data.get("status") in VALID_STATUSES, (
            f"{name} status {data.get('status')!r} is not one of {VALID_STATUSES}"
        )


def _attributed_source(page):
    """The Source page a page's first sources[] entry points at.

    Mirrors scripts/regen_indexes.py's source_of(): a later Ingest appends a
    second sources[] entry to an existing page, and the page still belongs on
    the fed list of the source that created it."""
    entries = read_frontmatter(page).get("sources") or []
    if isinstance(entries, dict):
        entries = [entries]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("resource"):
            return str(entry["resource"])
    return None


def _fed_section(page):
    _, sep, tail = page.read_text().partition(FED_HEADING)
    assert sep, f"{page} has no '{FED_HEADING}' section"
    return tail


def test_every_source_page_lists_exactly_the_pages_it_fed():
    """Each Source page's fed list must hold every page attributed to it and
    no others.

    Per-source attribution is the invariant that survives a second Ingest. A
    weaker check -- one Source page links every page in the bundle -- holds
    only while the bundle has one source. This check is also stronger: it
    catches a page that appears on the wrong source's list."""
    if not SOURCE_FILES:
        pytest.skip("empty bundle: no Source pages yet")
    for source_name in SOURCE_FILES:
        fed = _fed_section(WIKI / "sources" / source_name)
        self_ref = f"/sources/{source_name}"
        for subdir, files in PAGE_DIRS:
            for name in files:
                link = f"](../{subdir}/{name})"
                if _attributed_source(WIKI / subdir / name) == self_ref:
                    assert link in fed, f"{source_name} must list {link}"
                else:
                    assert link not in fed, f"{source_name} must not list {link}"
