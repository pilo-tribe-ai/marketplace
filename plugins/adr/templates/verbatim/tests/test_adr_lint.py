import ast
import json
import sys

import adr_vendored_conftest as _cf

load_script = _cf.load_script
run_script = _cf.run_script
write = _cf.write

adr_lib = load_script("adr_lib")


def repo(tmp_path, config=None):
    (tmp_path / ".git").mkdir(parents=True)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    write(tmp_path / ".claude" / "adr.json",
          json.dumps(config or {"version": 1, "dir": "docs/adr",
                                "register": "docs/adr/README.md",
                                "id_scheme": "sequential"}))
    return tmp_path


def good(root, name, **meta):
    body = {"type": "adr", "status": "accepted", "date": "2026-08-13", "title": "T"}
    body.update(meta)
    write(root / "docs" / "adr" / name,
          "---\n" + adr_lib.dump_frontmatter(body) + "---\n\n# body\n")


def index(root):
    run_script("adr_index", "--write", cwd=root)


# --- Task 15: required fields, enum, legacy warning -------------------------

def test_a_clean_corpus_exits_zero(tmp_path):
    root = repo(tmp_path)
    good(root, "0001-a.md")
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_frontmatter_missing_status_is_the_required_field_error(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "0001-a.md",
          "---\ntype: adr\ndate: 2026-08-13\ntitle: T\n---\n\n# T\n")
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1
    assert "required" in result.stdout.lower()
    assert "legacy" not in result.stdout.lower()


def test_a_legacy_file_is_a_warning_and_exits_zero(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "ADR-002-auth.md",
          "# ADR-002: Gateway auth\n\n**Status:** Accepted\n**Date:** 2026-02-26\n\n---\n")
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 0, result.stdout
    assert "WARN" in result.stdout and "legacy" in result.stdout.lower()


def test_a_stray_note_is_the_same_legacy_warning(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "stray-note.md", "just a note\n")
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 0
    assert "legacy" in result.stdout.lower()


def test_a_status_outside_the_enum_and_an_unparseable_date_are_errors(tmp_path):
    root = repo(tmp_path)
    write(root / "docs" / "adr" / "0001-a.md",
          "---\ntype: adr\nstatus: superseded by adr-002\ndate: last tuesday\n"
          "title: T\n---\n\n# T\n")
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1
    assert "status" in result.stdout.lower() and "date" in result.stdout.lower()


# --- Task 16: identity, cross-references, register staleness ----------------

def test_a_duplicate_numeric_prefix_is_an_error(tmp_path):
    root = repo(tmp_path)
    good(root, "0007-one.md")
    good(root, "0007-two.md")
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1
    assert "duplicate" in result.stdout.lower() and "0007" in result.stdout


def test_same_day_files_are_not_a_duplicate_under_the_date_scheme(tmp_path):
    root = repo(tmp_path, config={"version": 1, "dir": "docs/adr",
                                  "register": "docs/adr/README.md",
                                  "id_scheme": "date"})
    good(root, "2026-08-13-one.md")
    good(root, "2026-08-13-two.md")
    index(root)
    assert run_script("adr_lint", cwd=root).returncode == 0


def test_a_reference_to_a_missing_file_is_an_error(tmp_path):
    root = repo(tmp_path)
    good(root, "0001-a.md", related=["0099-gone.md"])
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1 and "0099-gone.md" in result.stdout


def test_a_one_sided_supersede_is_an_error(tmp_path):
    root = repo(tmp_path)
    good(root, "0001-old.md", status="superseded", superseded_by=["0002-new.md"])
    good(root, "0002-new.md")            # does not name 0001 back
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1 and "one-sided" in result.stdout.lower()


def test_a_one_sided_supersede_is_an_error_from_the_supersedes_side_too(tmp_path):
    """A names B in `supersedes` and B stays silent. Checked from one side
    only, this whole shape lints clean."""
    root = repo(tmp_path)
    good(root, "0001-new.md", supersedes=["0002-old.md"])
    good(root, "0002-old.md")            # does not name 0001 back
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1 and "one-sided" in result.stdout.lower()


def test_superseded_without_superseded_by_is_an_error_and_the_reverse(tmp_path):
    root = repo(tmp_path)
    good(root, "0001-old.md", status="superseded")
    good(root, "0002-live.md", status="accepted", superseded_by=["0001-old.md"])
    index(root)
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1
    assert result.stdout.lower().count("supersede") >= 2


def test_a_stale_register_is_an_error(tmp_path):
    root = repo(tmp_path)
    good(root, "0001-a.md")
    index(root)
    good(root, "0002-b.md")              # written after the register
    result = run_script("adr_lint", cwd=root)
    assert result.returncode == 1 and "register" in result.stdout.lower()


# --- Task 17: the proposed check, requirements.txt, the stdlib gate ---------

def proposed_repo(tmp_path, verdict="error"):
    root = repo(tmp_path, config={"version": 1, "dir": "docs/adr",
                                  "register": "docs/adr/README.md",
                                  "id_scheme": "sequential",
                                  "gate": {"proposed_verdict": verdict}})
    good(root, "0001-draft.md", status="proposed")
    good(root, "0002-settled.md", status="accepted")
    index(root)
    return root


def test_the_proposed_check_is_skipped_when_changed_is_absent(tmp_path):
    result = run_script("adr_lint", cwd=proposed_repo(tmp_path))
    assert result.returncode == 0
    assert "proposed" not in result.stdout.lower()


def test_a_changed_proposed_adr_is_an_error(tmp_path):
    root = proposed_repo(tmp_path)
    result = run_script("adr_lint", "--changed", "docs/adr/0001-draft.md", cwd=root)
    assert result.returncode == 1
    assert "proposed" in result.stdout.lower()


def test_a_changed_list_holding_no_adr_finds_nothing(tmp_path):
    root = proposed_repo(tmp_path)
    result = run_script("adr_lint", "--changed", "src/main.py", cwd=root)
    assert result.returncode == 0


def test_the_verdict_downgrades_to_a_warning_and_switches_off(tmp_path):
    warn = run_script("adr_lint", "--changed", "docs/adr/0001-draft.md",
                      cwd=proposed_repo(tmp_path / "w", "warning"))
    assert warn.returncode == 0 and "WARN" in warn.stdout
    off = run_script("adr_lint", "--changed", "docs/adr/0001-draft.md",
                     cwd=proposed_repo(tmp_path / "o", "off"))
    assert off.returncode == 0 and "proposed" not in off.stdout.lower()


def test_the_vendored_scripts_import_only_the_standard_library(scripts_dir):
    """PyYAML is the one exception, and only inside a try/except ImportError.
    ADRs land in repos that are not Python projects; `python3 adr_lint.py`
    with no install step is the difference between a gate that is enabled and
    one that is not."""
    local = {"adr_lib", "adr_index", "adr_new", "adr_migrate"}
    for path in sorted(scripts_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guarded = {node for guard in ast.walk(tree) if isinstance(guard, ast.Try)
                   for node in ast.walk(guard) if isinstance(node, (ast.Import, ast.ImportFrom))}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            names = ([alias.name.split(".")[0] for alias in node.names]
                     if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]])
            for name in names:
                if name in sys.stdlib_module_names or name in local:
                    continue
                assert name == "yaml" and node in guarded, (
                    f"{path.name} imports third-party `{name}`")
