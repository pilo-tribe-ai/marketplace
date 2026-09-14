import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_script

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN_ROOT / "scripts" / "source_hash.py"


def load():
    return load_script("source_hash")


def write_pair(tmp_path, body="the guide", digest=None):
    """Write a source file and a mission that points at it."""
    source = tmp_path / "guide.md"
    source.write_text(body, encoding="utf-8")
    if digest is None:
        digest = load().hash_file(source)
    mission = tmp_path / "m.feature"
    mission.write_text(
        f"# grounded-in: guide.md\n"
        f"# grounded-in-hash: {digest}\n"
        f"Feature: X\n",
        encoding="utf-8",
    )
    return source, mission


def test_hash_file_is_sha256_hex(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("abc", encoding="utf-8")
    digest = load().hash_file(path)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_hash_file_changes_when_the_file_changes(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("abc", encoding="utf-8")
    first = load().hash_file(path)
    path.write_text("abd", encoding="utf-8")
    assert load().hash_file(path) != first


def test_read_grounding_finds_every_pair():
    text = (
        "# grounded-in: a.md\n"
        "# grounded-in-hash: aaa\n"
        "# grounded-in: b.md\n"
        "# grounded-in-hash: bbb\n"
    )
    pairs = load().read_grounding(text)
    assert [(p.source, p.digest) for p in pairs] == [("a.md", "aaa"), ("b.md", "bbb")]


def test_read_grounding_marks_a_source_with_no_hash():
    pairs = load().read_grounding("# grounded-in: a.md\n")
    assert pairs[0].digest is None


def test_check_reports_ok_when_the_source_is_unchanged(tmp_path):
    _, mission = write_pair(tmp_path)
    results = load().check(mission, tmp_path)
    assert [r.state for r in results] == ["ok"]


def test_check_reports_changed_when_the_source_moved_on(tmp_path):
    source, mission = write_pair(tmp_path)
    source.write_text("the guide, rewritten", encoding="utf-8")
    results = load().check(mission, tmp_path)
    assert [r.state for r in results] == ["changed"]


def test_check_reports_missing_when_the_source_is_gone(tmp_path):
    source, mission = write_pair(tmp_path)
    source.unlink()
    results = load().check(mission, tmp_path)
    assert [r.state for r in results] == ["missing"]


def test_check_reports_unrecorded_when_no_hash_was_stored(tmp_path):
    source = tmp_path / "guide.md"
    source.write_text("the guide", encoding="utf-8")
    mission = tmp_path / "m.feature"
    mission.write_text("# grounded-in: guide.md\nFeature: X\n", encoding="utf-8")
    results = load().check(mission, tmp_path)
    assert [r.state for r in results] == ["unrecorded"]


def test_cli_exits_zero_when_nothing_drifted(tmp_path):
    _, mission = write_pair(tmp_path)
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check", str(mission), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_cli_exits_one_and_says_changed(tmp_path):
    source, mission = write_pair(tmp_path)
    source.write_text("moved on", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check", str(mission), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert done.returncode == 1
    assert "changed" in done.stdout
    assert "guide.md" in done.stdout


# `check` exits 1 when a source drifted. A path that does not exist is a
# different thing, and it must not borrow that code.
def test_hash_of_a_missing_file_does_not_use_the_drift_exit_code(tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "hash", str(tmp_path / "nope.md")],
        capture_output=True, text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "nope.md" in done.stderr
    assert "cannot read" in done.stderr


def test_check_of_a_missing_mission_does_not_use_the_drift_exit_code(tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check", str(tmp_path / "nope.feature"),
         "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "nope.feature" in done.stderr
    assert "cannot read" in done.stderr


def test_a_mission_that_is_not_utf8_does_not_use_the_drift_exit_code(tmp_path):
    """`UnicodeDecodeError` is not an `OSError`. Uncaught it ends the process
    with code 1, which the caller reads as drift and answers by marking the
    mission `needs review` and naming a document that never changed."""
    mission = tmp_path / "m.feature"
    mission.write_bytes(b"# grounded-in: guide.md\nFeature: \xff\xfe\n")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check", str(mission), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "not valid UTF-8" in done.stderr


def test_a_mission_with_no_grounded_in_line_is_drift_not_a_clean_pass(tmp_path):
    """A silent 0 here would read exactly like a clean pass, and the mission
    would be judged as if a person had grounded and approved it."""
    mission = tmp_path / "m.feature"
    mission.write_text("Feature: X\n", encoding="utf-8")
    results = load().check(mission, tmp_path)
    assert [r.state for r in results] == ["ungrounded"]

    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check", str(mission), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "ungrounded" in done.stdout


def test_a_source_that_cannot_be_opened_is_drift_not_an_error(tmp_path):
    """The mission read fine; a source it names will not open. Raising here
    would exit 2, and the caller reads 2 as `the mission could not be read`,
    which is a different fault with a different fix."""
    source, mission = write_pair(tmp_path)
    source.chmod(0o000)
    try:
        if source.read_bytes():  # pragma: no cover - root ignores the mode
            pytest.skip("this user can read a file with mode 000")
    except OSError:
        pass
    try:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "check", str(mission),
             "--root", str(tmp_path)],
            capture_output=True, text=True,
        )
    finally:
        source.chmod(0o644)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "unreadable" in done.stdout
    assert "Traceback" not in done.stderr


def test_a_missing_source_inside_a_mission_is_still_drift_not_an_error(tmp_path):
    """The mission itself is readable; a source it names is gone. That is
    `missing` drift, and it keeps exit code 1. Only an unreadable argument
    is exit code 2."""
    mission = tmp_path / "m.feature"
    mission.write_text(
        "# grounded-in: gone.md\n# grounded-in-hash: abc\nFeature: X\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check", str(mission), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "missing" in done.stdout
