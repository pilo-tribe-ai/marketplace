import subprocess
import sys


def test_toy_project_suite_passes(plugin_root):
    toy = plugin_root / "tests" / "integration" / "seeds" / "toy-project"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                       cwd=str(toy), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_verify_seed_reports_a_parseable_verdict(plugin_root):
    verify = plugin_root / "tests" / "integration" / "seeds" / "commands" / "verify.md"
    body = verify.read_text()
    assert "**Verdict:** PASS" in body
    assert "**Verdict:** FAIL" in body
    assert "python3 -m pytest" in body


def test_seeds_carry_no_personal_data(plugin_root):
    import re
    seeds = plugin_root / "tests" / "integration" / "seeds"
    # Scan only committed-style source. __pycache__/.pytest_cache are gitignored
    # build artifacts a bare `pytest` run drops into the tree; their .pyc embed the
    # absolute source path but never reach a commit, so scanning them is a false
    # positive that makes the check nondeterministic.
    ignored = {"__pycache__", ".pytest_cache"}
    files = [p for p in seeds.rglob("*")
             if p.is_file() and not (ignored & set(p.parts))]
    blob = "\n".join(p.read_text(errors="ignore") for p in files)
    assert not re.search(r"/Users/[A-Za-z0-9._-]+", blob), "machine path leaked into seeds"
    emails = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob))  # [inferred]
    assert emails <= {"itest@relay.local"}, f"unexpected email(s) leaked into seeds: {sorted(emails)}"  # [inferred]
