import json
import subprocess

import adr_plugin_conftest as _cf

PLUGIN_ROOT = _cf.PLUGIN_ROOT
SCAFFOLD = _cf.SCAFFOLD
init_git_repo = _cf.init_git_repo
run_python = _cf.run_python
load_module = _cf.load_module


def scaffold(target, *extra):
    return run_python(target, str(SCAFFOLD), "--target", str(target), *extra)


def legacy_repo(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    (target / "docs" / "adr").mkdir(parents=True)
    (target / "docs" / "adr" / "ADR-002-auth.md").write_text(
        "# ADR-002: Gateway auth\n\n**Status:** Accepted\n**Date:** 2026-02-26\n\n---\n",
        "utf-8")
    return target


def gates(target):
    index = run_python(target, "scripts/adr/adr_index.py", "--write",
                       "--repo-root", str(target))
    lint = run_python(target, "scripts/adr/adr_lint.py", "--repo-root", str(target))
    check = run_python(target, "scripts/adr/adr_index.py", "--check",
                       "--repo-root", str(target))
    return index, lint, check


# --- Task 21: scaffold.py manifest and --dry-run ---------------------------

def test_dry_run_prints_the_manifest_and_writes_nothing(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    result = scaffold(target, "--dry-run")
    assert result.returncode == 0, result.stderr
    for expected in ("scripts/adr/adr_lib.py", "scripts/adr/adr_lint.py",
                     "scripts/adr/requirements.txt", "schemas/adr/adr.schema.json",
                     "tests/adr/conftest.py", ".claude/adr.json",
                     "docs/adr/CLAUDE.md", "docs/adr/README.md"):
        assert expected in result.stdout, f"{expected} is not in the manifest"
    assert "CLAUDE.md" in result.stdout
    assert list(target.iterdir()) == [target / ".git"]


def test_every_manifest_source_exists(plugin_root):
    module = load_module("adr_plugin_scaffold", SCAFFOLD)
    for rel in module.VERBATIM_FILES:
        assert (plugin_root / "templates" / "verbatim" / rel).is_file(), rel
    for rel in module.RENDERED_FILES.values():
        assert (plugin_root / "templates" / rel).is_file(), rel


# --- Task 37: migration is vendored with the rest of the toolchain ---------

def test_the_migrate_script_and_its_test_are_vendored(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    assert scaffold(target, "--today", "2026-08-13").returncode == 0
    assert (target / "scripts" / "adr" / "adr_migrate.py").is_file()
    assert (target / "tests" / "adr" / "test_adr_migrate.py").is_file()


# --- Task 22: greenfield write + refuse a clobber ---------------------------

def test_a_greenfield_run_lands_every_manifest_file(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    result = scaffold(target, "--today", "2026-08-13")
    assert result.returncode == 0, result.stderr
    for rel in ("scripts/adr/adr_lib.py", "scripts/adr/requirements.txt",
                "schemas/adr/adr.schema.json", "tests/adr/conftest.py",
                "docs/adr/CLAUDE.md", "docs/adr/README.md",
                ".claude/adr.json", "CLAUDE.md"):
        assert (target / rel).is_file(), f"{rel} did not land"
    config = json.loads((target / ".claude" / "adr.json").read_text("utf-8"))
    assert config == {"version": 1, "dir": "docs/adr",
                      "register": "docs/adr/README.md",
                      "id_scheme": "sequential",
                      "gate": {"deterministic": False, "model": False,
                               "proposed_verdict": "error"},
                      "archive_dir": None}


def test_no_token_survives_the_render(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    scaffold(target, "--today", "2026-08-13")
    for path in list(target.rglob("*.md")) + [target / ".claude" / "adr.json"]:
        if ".git/" in path.as_posix():
            continue
        assert "{{" not in path.read_text(encoding="utf-8"), f"token survives in {path}"


def test_a_second_fresh_run_refuses_and_writes_nothing(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    scaffold(target, "--today", "2026-08-13")
    before = (target / "docs" / "adr" / "CLAUDE.md").read_text("utf-8")
    (target / "docs" / "adr" / "CLAUDE.md").write_text(before + "\nlocal edit\n", "utf-8")
    result = scaffold(target, "--today", "2026-08-13")
    assert result.returncode == 1
    assert ".claude/adr.json" in result.stderr
    assert "local edit" in (target / "docs" / "adr" / "CLAUDE.md").read_text("utf-8")


# --- Task 23: the four write-safety exceptions, under --refresh ------------

def test_refresh_rewrites_the_vendored_tree_and_the_corpus_rules(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    scaffold(target, "--today", "2026-08-13")
    (target / "scripts" / "adr" / "adr_lib.py").write_text("stale\n", "utf-8")
    (target / "docs" / "adr" / "CLAUDE.md").write_text("stale\n", "utf-8")
    result = scaffold(target, "--refresh", "--today", "2026-08-13")
    assert result.returncode == 0, result.stderr
    assert "split_frontmatter" in (target / "scripts" / "adr" / "adr_lib.py").read_text("utf-8")
    assert "expensive to undo" in (target / "docs" / "adr" / "CLAUDE.md").read_text("utf-8")
    assert "refreshed" in result.stdout


def test_refresh_never_appends_the_root_block_twice(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    scaffold(target, "--today", "2026-08-13")
    scaffold(target, "--refresh", "--today", "2026-08-13")
    text = (target / "CLAUDE.md").read_text("utf-8")
    assert text.count("## Architecture decisions") == 1
    assert "already present" in scaffold(target, "--refresh", "--today",
                                         "2026-08-13").stdout


def test_refresh_preserves_the_register_outside_the_markers_and_every_adr(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    scaffold(target, "--today", "2026-08-13")
    run_python(target, "scripts/adr/adr_new.py", "--title", "Gateway auth",
               "--repo-root", str(target))
    run_python(target, "scripts/adr/adr_index.py", "--write", "--repo-root", str(target))
    register = target / "docs" / "adr" / "README.md"
    register.write_text(register.read_text("utf-8").replace(
        "<!-- TODO: summary -->", "Auth sits at the gateway"), "utf-8")
    adr_text = (target / "docs" / "adr" / "0001-gateway-auth.md").read_text("utf-8")

    assert scaffold(target, "--refresh", "--today", "2026-08-13").returncode == 0
    assert (target / "docs" / "adr" / "0001-gateway-auth.md").read_text("utf-8") == adr_text
    after = register.read_text("utf-8")
    assert "Auth sits at the gateway" in after
    assert "0001-gateway-auth.md" in after


def test_refresh_without_a_config_is_refused(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    result = scaffold(target, "--refresh")
    assert result.returncode == 1 and "adr.json" in result.stderr


# --- Task 24: scaffold.py --adopt -------------------------------------------

def test_adopt_writes_the_config_and_touches_no_adr(tmp_path):
    target = legacy_repo(tmp_path)
    before = (target / "docs" / "adr" / "ADR-002-auth.md").read_text("utf-8")
    result = scaffold(target, "--adopt", "--dir", "docs/adr", "--today", "2026-08-13")
    assert result.returncode == 0, result.stderr
    assert (target / "docs" / "adr" / "ADR-002-auth.md").read_text("utf-8") == before
    assert (target / "scripts" / "adr" / "adr_lint.py").is_file()
    assert json.loads((target / ".claude" / "adr.json").read_text("utf-8"))["dir"] == "docs/adr"


def test_adopt_records_the_date_scheme_when_asked(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    (target / "docs" / "architecture" / "adrs").mkdir(parents=True)
    result = scaffold(target, "--adopt", "--dir", "docs/architecture/adrs",
                      "--id-scheme", "date", "--today", "2026-08-13")
    assert result.returncode == 0, result.stderr
    config = json.loads((target / ".claude" / "adr.json").read_text("utf-8"))
    assert config["dir"] == "docs/architecture/adrs"
    assert config["id_scheme"] == "date"
    assert config["register"] == "docs/architecture/adrs/README.md"


# --- Task 25: three fixture repos, end to end -------------------------------

def test_greenfield_runs_green(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    assert scaffold(target, "--today", "2026-08-13").returncode == 0
    index, lint, check = gates(target)
    assert (index.returncode, lint.returncode, check.returncode) == (0, 0, 0), lint.stdout


def test_a_legacy_bold_key_corpus_indexes_and_lints_clean_on_day_one(tmp_path):
    target = legacy_repo(tmp_path)
    assert scaffold(target, "--adopt", "--dir", "docs/adr",
                    "--today", "2026-08-13").returncode == 0
    index, lint, check = gates(target)
    assert (index.returncode, check.returncode) == (0, 0)
    assert lint.returncode == 0, lint.stdout          # warning, never an error
    assert "legacy" in lint.stdout.lower()
    assert "Gateway auth" in (target / "docs" / "adr" / "README.md").read_text("utf-8")


def test_a_date_scheme_corpus_runs_green(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    (target / "docs" / "adr").mkdir(parents=True)
    for slug in ("one", "two"):
        (target / "docs" / "adr" / f"2026-04-20-{slug}.md").write_text(
            f"---\ntype: adr\nstatus: accepted\ndate: 2026-04-20\ntitle: {slug}\n---\n\n"
            f"# {slug}\n", "utf-8")
    assert scaffold(target, "--adopt", "--dir", "docs/adr", "--id-scheme", "date",
                    "--today", "2026-08-13").returncode == 0
    index, lint, check = gates(target)
    assert (index.returncode, lint.returncode, check.returncode) == (0, 0, 0), lint.stdout


def test_the_vendored_suite_passes_inside_the_scaffolded_repo(tmp_path):
    target = init_git_repo(tmp_path / "repo")
    scaffold(target, "--today", "2026-08-13")
    result = run_python(target, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "tests/adr")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "failed" not in result.stdout


# --- Task 40: the optional CI gate is written only when asked for ----------

def test_the_gate_is_written_only_when_the_config_asks_for_it(tmp_path):
    off = init_git_repo(tmp_path / "off")
    scaffold(off, "--today", "2026-08-13")
    assert not (off / ".github" / "workflows" / "adr-gate.yml").exists()

    on = init_git_repo(tmp_path / "on")
    scaffold(on, "--today", "2026-08-13", "--gate-deterministic")
    workflow = on / ".github" / "workflows" / "adr-gate.yml"
    assert workflow.is_file()
    assert json.loads((on / ".claude" / "adr.json").read_text("utf-8"))["gate"]["deterministic"]
    assert "adr_lint.py" in workflow.read_text("utf-8")


# --- Task 43: final acceptance -----------------------------------------------

def test_the_branch_touched_only_the_allowed_paths():
    """The spec allows plugins/adr/, docs/superpowers/, and the marketplace
    file. A file anywhere else is out of scope for this plugin's first
    release."""
    root = PLUGIN_ROOT.parent.parent
    diff = subprocess.run(["git", "diff", "--name-only", "main...HEAD"],
                          cwd=str(root), capture_output=True, text=True)
    # A failed git call prints nothing, and an unchecked return code turns this
    # guard into a test that passes because it never ran.
    assert diff.returncode == 0, f"git diff main...HEAD failed: {diff.stderr}"
    allowed = ("plugins/adr/", "docs/superpowers/", ".claude-plugin/marketplace.json")
    stray = [name for name in diff.stdout.split()
             if name and not name.startswith(allowed)]
    assert not stray, f"files changed outside the plugin: {stray}"
