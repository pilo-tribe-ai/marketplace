"""The gate that stops a revision loop reporting success on an unmoved measurement."""

import json


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


BLOATED = (
    "You are a world-class engineer.\n\n"
    "CRITICAL: You MUST review the code.\n\n"
    "Report only high-severity issues.\n\n"
    "Never use ellipses.\n\n"
    "Run the build.\n\nRun the tests.\n\nRun the linter.\n"
)

SLIM = "Return one paragraph for each issue that can lose data.\n"


def test_a_shrunk_prompt_exits_zero(compare, tmp_path, capsys):
    before = write(tmp_path, "before.md", BLOATED)
    after = write(tmp_path, "after.md", SLIM)
    assert compare.main([before, after]) == 0
    assert "moved at least one count down" in capsys.readouterr().out


def test_an_unchanged_prompt_exits_one_and_says_so(compare, tmp_path, capsys):
    before = write(tmp_path, "before.md", BLOATED)
    after = write(tmp_path, "after.md", BLOATED)
    assert compare.main([before, after]) == 1
    assert "moved no count down" in capsys.readouterr().out


def test_a_reworded_prompt_with_the_same_counts_exits_one(compare, tmp_path):
    """Same instruction count, same finding count: the wording changed, nothing else."""
    before = write(tmp_path, "before.md", "Run the build.\n\nRun the tests.\n")
    after = write(tmp_path, "after.md", "Run the compile.\n\nRun the checks.\n")
    assert compare.main([before, after]) == 1


def test_clearing_a_finding_alone_counts_as_movement(compare, tmp_path):
    """The instruction count holds at 1, and the bare prohibition gains its reason."""
    before = write(tmp_path, "before.md", "Never use ellipses.\n")
    after = write(tmp_path, "after.md", "Never use ellipses, because a speech engine reads this.\n")
    result = compare.compare(
        compare.analyse("Never use ellipses.\n", "before"),
        compare.analyse("Never use ellipses, because a speech engine reads this.\n", "after"),
    )
    assert result["delta"]["instructions"] == 0
    assert result["delta"]["findings"] < 0
    assert compare.main([before, after]) == 0


def test_a_missing_file_exits_two(compare, tmp_path):
    before = write(tmp_path, "before.md", SLIM)
    assert compare.main([before, str(tmp_path / "gone.md")]) == 2


def test_an_empty_file_exits_two(compare, tmp_path):
    before = write(tmp_path, "before.md", SLIM)
    after = write(tmp_path, "after.md", "\n\n")
    assert compare.main([before, after]) == 2


def test_json_output_carries_both_sides_and_the_deltas(compare, tmp_path, capsys):
    before = write(tmp_path, "before.md", BLOATED)
    after = write(tmp_path, "after.md", SLIM)
    compare.main([before, after, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["before"]["instructions"] > payload["after"]["instructions"]
    assert payload["delta"]["instructions"] < 0
    assert payload["moved"] is True
    assert "persona" in payload["cleared_kinds"]


def test_a_new_fault_shows_in_the_added_kinds(compare):
    result = compare.compare(
        compare.analyse("Return 3 sentences.\n", "before"),
        compare.analyse("Return 3 sentences.\n\nYou are a world-class engineer.\n", "after"),
    )
    assert result["added_kinds"] == ["persona"]
    assert result["moved"] is False
