from pathlib import Path
REPO = Path(__file__).resolve().parents[5]   # confirmed: parents[5] == repo root
def test_deferred_doc_exists():
    p = REPO / "docs" / "superpowers" / "specs" / "fidelity-l3-deferred.md"
    assert p.is_file(), "deferred N=5 fidelity manual check must be documented at one path"
    t = p.read_text()
    assert "N=5" in t and "fidelity-check.sh" in t
