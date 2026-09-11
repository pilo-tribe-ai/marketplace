"""The reference corpus and the linter must name the same rules.

A finding cites a rule identifier. When the identifier has no entry, the reader
cannot find out what the finding means, and the review sends them nowhere.
"""

import re

ENTRY = re.compile(r"^### ([PLU]\d+) — (.+)$", re.M)
CHECK_LINE = re.compile(r"^\*\*Check\.\*\* (.+)$", re.M)
NAMED_CHECK = re.compile(r"`([a-z-]+)`")


def principles(plugin_root):
    return (plugin_root / "reference" / "principles.md").read_text(encoding="utf-8")


def entries(plugin_root):
    return dict(ENTRY.findall(principles(plugin_root)))


def test_every_rule_the_linter_knows_has_an_entry(lint, plugin_root):
    assert set(entries(plugin_root)) == set(lint.RULES)


def test_every_entry_title_matches_the_linter(lint, plugin_root):
    for rule, title in entries(plugin_root).items():
        assert title.strip() == lint.RULES[rule], f"{rule} title drifted"


def test_no_entry_appears_twice(plugin_root):
    found = ENTRY.findall(principles(plugin_root))
    assert len(found) == len({rule for rule, _ in found})


def test_every_entry_declares_a_check_line(plugin_root):
    text = principles(plugin_root)
    bodies = re.split(r"^### ", text, flags=re.M)[1:]
    for body in bodies:
        rule = body.split(" ", 1)[0]
        assert CHECK_LINE.search(body), f"{rule} declares no Check line"


def test_every_entry_declares_a_confidence_line(plugin_root):
    text = principles(plugin_root)
    bodies = re.split(r"^### ", text, flags=re.M)[1:]
    for body in bodies:
        rule = body.split(" ", 1)[0]
        found = re.search(r"^\*\*Confidence\.\*\* (.+)$", body, re.M)
        assert found, f"{rule} declares no Confidence line"
        assert re.search(
            r"\b(measured|vendor|directional)\b", found.group(1)
        ), f"{rule} confidence is not one of the three words"


def test_the_checks_named_in_the_corpus_are_the_checks_the_linter_raises(lint, plugin_root):
    """A check renamed in code and not in the corpus would cite a rule that
    documents a different check."""
    documented = {}
    for body in re.split(r"^### ", principles(plugin_root), flags=re.M)[1:]:
        rule = body.split(" ", 1)[0]
        line = CHECK_LINE.search(body).group(1)
        for name in NAMED_CHECK.findall(line):
            documented[name] = rule

    # P2 reports the band on every file rather than raising a finding, so it
    # names no check in CHECKS.
    assert documented == dict(lint.CHECKS)


def test_a_rule_with_no_check_says_judgement_only(lint, plugin_root):
    for body in re.split(r"^### ", principles(plugin_root), flags=re.M)[1:]:
        rule = body.split(" ", 1)[0]
        line = CHECK_LINE.search(body).group(1)
        has_check = rule in set(lint.CHECKS.values())
        if not has_check and "the instruction count" not in line:
            assert "judgement only" in line, f"{rule} has no check and does not say so"


def test_the_corpus_states_its_own_date(plugin_root):
    assert "August 2026" in principles(plugin_root)


def test_the_band_table_matches_the_linter(lint, plugin_root):
    """The bands are printed on every file, so a drifted table misleads."""
    text = principles(plugin_root)
    assert f"{lint.BAND_HEALTHY:.0%}".rstrip("%") + "%" in text
    assert "0 to 11" in text and "12 to 25" in text and "26 and above" in text
    assert lint.band_of(lint.PER_RULE_DEFAULT**11) == "healthy"
    assert lint.band_of(lint.PER_RULE_DEFAULT**12) == "watch"
    assert lint.band_of(lint.PER_RULE_DEFAULT**26) == "at-risk"
