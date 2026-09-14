import shutil
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
HARNESS = PLUGIN_ROOT / "tools" / "fidelity-check.sh"

def test_fidelity_prompt_exists():
    assert (PLUGIN_ROOT / "tools" / "fixtures" / "fidelity-prompt.txt").is_file(), (
        "tools/fixtures/fidelity-prompt.txt must exist as a fixture file"
    )  # [inferred]

def test_smoke_mode_passes():
    if shutil.which("jq") is None:  # [inferred]
        import pytest; pytest.skip("jq not on PATH")  # [inferred]
    result = subprocess.run(
        ["bash", str(HARNESS), "--smoke"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"smoke fidelity check must pass (exit 0):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "PASS" in result.stdout

def test_non_smoke_mode_exits_nonzero():  # [inferred]
    """Non-smoke mode is a stub in Phase 2; it must exit non-zero (code 2)."""  # [inferred]
    result = subprocess.run(  # [inferred]
        ["bash", str(HARNESS)],  # [inferred]
        capture_output=True, text=True,  # [inferred]
    )  # [inferred]
    assert result.returncode != 0, (  # [inferred]
        f"non-smoke mode must exit non-zero (Phase 2 stub):\n"  # [inferred]
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"  # [inferred]
    )  # [inferred]

def test_smoke_still_passes_after_l3():
    if shutil.which("jq") is None:
        import pytest; pytest.skip("jq not on PATH")
    r = subprocess.run(["bash", str(HARNESS), "--smoke"], capture_output=True, text=True)
    assert r.returncode == 0 and "PASS" in r.stdout

def test_l3_known_command_static_check_passes():
    r = subprocess.run(["bash", str(HARNESS), "--l3", "implement"], capture_output=True, text=True)
    assert r.returncode == 0, f"--l3 implement must pass static check:\n{r.stderr}"

def test_l3_execute_static_check_passes():
    r = subprocess.run(["bash", str(HARNESS), "--l3", "execute"], capture_output=True, text=True)
    assert r.returncode == 0, f"--l3 execute (no-branch) must pass:\n{r.stderr}"

def test_l3_unknown_command_exits_2():
    r = subprocess.run(["bash", str(HARNESS), "--l3", "bogus"], capture_output=True, text=True)
    assert r.returncode == 2, "--l3 <unknown> must exit 2 (mirrors non-implemented-mode)"

def test_bare_run_still_exits_nonzero():
    # E.4: bare run (no flag) unchanged — Phase-2 stub still exits 2
    r = subprocess.run(["bash", str(HARNESS)], capture_output=True, text=True)
    assert r.returncode != 0


def test_l3_check_is_not_flaky():
    """The --l3 check must give the same answer every time it is asked.

    It did not. `printf '%s' "$body" | grep -q <token>` races: `grep -q` exits at its
    FIRST match and closes the pipe, `printf` dies of SIGPIPE (141), and the script's
    `set -o pipefail` promotes that 141 into the pipeline's exit status — so the check
    reported "missing classifier" for a token it had just successfully found.

    It stayed invisible because the window is proportional to how much of the file is
    still unwritten when the match is hit. At main's 114-line implement.md the whole body
    fits the pipe buffer and it never fired (0/300); at this branch's 379-line version it
    fired on 42/300 runs. Growing a command file is not supposed to be able to break the
    harness that checks it, so this asserts stability rather than the absence of a pattern.
    """
    for _ in range(40):
        r = subprocess.run(["bash", str(HARNESS), "--l3", "implement"],
                           capture_output=True, text=True)
        assert r.returncode == 0, (
            f"--l3 implement returned {r.returncode} on a repeat run: {r.stderr}\n"
            "The static check is non-deterministic; see this test's docstring."
        )


def test_l3_check_still_fails_on_a_command_missing_its_classifier():
    """Guards the other direction: the flake fix must not make the check vacuous.

    Grepping a path that does not exist also 'finds nothing' — a fix that silently
    stopped reading the right file would turn every FAIL into a PASS and this suite
    would not notice, since every real command file passes.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        (root / "commands").mkdir()
        shutil.copy(HARNESS, root / "tools" / HARNESS.name)
        (root / "commands" / "faux.md").write_text("branch table, but no classifier\n")
        r = subprocess.run(["bash", str(root / "tools" / HARNESS.name), "--l3", "faux"],
                           capture_output=True, text=True)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "missing classifier" in r.stderr, r.stderr
