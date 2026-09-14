"""adr_migrate.py: --frontmatter folds bold-key metadata (filenames untouched
by default), --rename normalises names and carries the register summary,
--dry-run writes nothing, and the tool commits nothing."""
import json
import subprocess

import adr_vendored_conftest as _cf

load_script = _cf.load_script
run_script = _cf.run_script
write = _cf.write

adr_lib = load_script("adr_lib")

LEGACY = (
    "# ADR-002: Gateway auth\n"
    "\n"
    "**Status:** Accepted\n"
    "**Date:** 2026-02-26\n"
    "**Supersedes:** ADR-001 (which documented the original architecture)\n"
    "\n"
    "---\n"
    "\n"
    "## Context\n"
    "\n"
    "Auth was per service.\n"
)


def repo(tmp_path, id_scheme="sequential"):
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    write(tmp_path / ".claude" / "adr.json",
          json.dumps({"version": 1, "dir": "docs/adr",
                      "register": "docs/adr/README.md", "id_scheme": id_scheme}))
    return tmp_path


# --- Task 35: --frontmatter folds bold-key headers ---------------------------

def test_bold_keys_fold_into_frontmatter_and_the_filename_is_untouched(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    result = run_script("adr_migrate", cwd=root)
    assert result.returncode == 0, result.stderr
    path = root / "docs" / "adr" / "ADR-002-auth.md"
    assert path.is_file()                       # name unchanged by default
    adr = adr_lib.parse_adr(path)
    assert adr.source == "frontmatter"
    assert adr.status == "accepted"
    assert adr.date == "2026-02-26"
    assert adr.meta["title"] == "Gateway auth"
    assert "id:" not in path.read_text(encoding="utf-8")


def test_the_heading_is_kept(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    run_script("adr_migrate", cwd=root)
    text = (root / "docs" / "adr" / "ADR-002-auth.md").read_text(encoding="utf-8")
    assert "# ADR-002: Gateway auth" in text
    assert "**Status:**" not in text            # the bold keys are gone
    assert "Auth was per service." in text      # the body survives


def test_an_unresolvable_reference_is_left_for_the_lint(tmp_path):
    """Never guessed at. The converter cannot know which file
    'ADR-001 (which documented the original architecture)' means."""
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    result = run_script("adr_migrate", cwd=root)
    text = (root / "docs" / "adr" / "ADR-002-auth.md").read_text(encoding="utf-8")
    assert "ADR-001 (which documented the original architecture)" in text
    assert "unresolved" in result.stdout.lower()


def test_a_bold_key_shaped_line_in_the_body_is_not_folded_or_dropped(tmp_path):
    """A bold-key-shaped line past parse_legacy's 20-line window is never
    read as metadata, so fold() must not delete it from the body either --
    doing so would be silent content loss with no matching frontmatter
    change."""
    filler = "\n".join(f"Body line {n}." for n in range(1, 20))
    text = (
        "# ADR-002: Gateway auth\n"
        "\n"
        "**Status:** Accepted\n"
        "**Date:** 2026-02-26\n"
        "\n"
        "## Context\n"
        "\n"
        f"{filler}\n"
        "\n"
        "The old doc quoted `**Status:** Rejected` verbatim here.\n"
    )
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", text)
    result = run_script("adr_migrate", cwd=root)
    assert result.returncode == 0, result.stderr
    path = root / "docs" / "adr" / "ADR-002-auth.md"
    written = path.read_text(encoding="utf-8")
    adr = adr_lib.parse_adr(path)
    assert adr.status == "accepted"             # real status, not overwritten
    assert "**Status:** Rejected" in written     # quoted body line survives


def test_a_file_already_carrying_frontmatter_is_left_alone(tmp_path):
    root = repo(tmp_path)
    before = "---\ntype: adr\nstatus: accepted\ndate: 2026-08-13\ntitle: T\n---\n\n# T\n"
    write(root / "docs" / "adr" / "0001-a.md", before)
    run_script("adr_migrate", cwd=root)
    assert (root / "docs" / "adr" / "0001-a.md").read_text(encoding="utf-8") == before


# --- Task 36: --rename carries the register summary --------------------------

def test_rename_normalises_the_filename(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    result = run_script("adr_migrate", "--rename", cwd=root)
    assert result.returncode == 0, result.stderr
    assert (root / "docs" / "adr" / "0002-auth.md").is_file()
    assert not (root / "docs" / "adr" / "ADR-002-auth.md").exists()


def test_rename_carries_the_hand_authored_summary_to_the_new_key(tmp_path):
    """The register keys summaries by filename. Without this rewrite the
    summary is dropped and re-seeded as a TODO on the next regeneration."""
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    run_script("adr_index", "--write", cwd=root)
    register = root / "docs" / "adr" / "README.md"
    write(register, register.read_text("utf-8").replace(
        "<!-- TODO: summary -->", "Auth sits at the gateway"))

    assert run_script("adr_migrate", "--rename", cwd=root).returncode == 0
    after_migrate = register.read_text("utf-8")
    assert "(./0002-auth.md)" in after_migrate

    assert run_script("adr_index", "--write", cwd=root).returncode == 0
    final = register.read_text("utf-8")
    assert "Auth sits at the gateway" in final
    assert "<!-- TODO: summary -->" not in final


def test_rename_refuses_when_the_new_name_is_taken(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    write(root / "docs" / "adr" / "0002-auth.md",
          "---\ntype: adr\nstatus: accepted\ndate: 2026-08-13\ntitle: T\n---\n\n# T\n")
    result = run_script("adr_migrate", "--rename", cwd=root)
    assert result.returncode == 1
    assert (root / "docs" / "adr" / "ADR-002-auth.md").is_file()


# --- Task 37: --dry-run writes nothing, the tool commits nothing -------------

def test_dry_run_reports_and_writes_nothing(tmp_path):
    root = repo(tmp_path)
    before = LEGACY
    write(root / "docs" / "adr" / "ADR-002-auth.md", before)
    result = run_script("adr_migrate", "--rename", "--dry-run", cwd=root)
    assert result.returncode == 0
    assert "ADR-002-auth.md" in result.stdout and "0002-auth.md" in result.stdout
    assert (root / "docs" / "adr" / "ADR-002-auth.md").read_text("utf-8") == before


def test_migration_commits_nothing(tmp_path):
    root = repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=str(root))
    write(root / "docs" / "adr" / "ADR-002-auth.md", LEGACY)
    run_script("adr_migrate", cwd=root)
    log = subprocess.run(["git", "log", "--oneline"], cwd=str(root),
                         capture_output=True, text=True)
    assert log.stdout.strip() == ""
