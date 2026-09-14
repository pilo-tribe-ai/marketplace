"""Structure + behavioral tests for scripts/bench-dispatch-cost.sh (spec 4.12.0 §3, §8.5)."""
import shutil
import subprocess

import pytest

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bench-dispatch-cost.sh"


class TestBenchDispatchCostStructure:
    def test_exists_and_executable(self):
        assert SCRIPT.is_file(), "scripts/bench-dispatch-cost.sh missing"
        assert SCRIPT.stat().st_mode & 0o111, "must be executable"

    def test_shebang_and_strict_mode(self):
        body = SCRIPT.read_text()
        assert body.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in body

    def test_measurement_tokens_present(self):
        body = SCRIPT.read_text()
        for token in (
            "total_cost_usd", "modelUsage", "token_count", ".codex", "--help",
            "--output-format json", "--skip-variant", "--claude-args",
            "--codex-home", "duration_api_ms",
        ):
            assert token in body, f"harness missing token {token!r}"

    def test_variant_composition(self):
        body = SCRIPT.read_text()
        assert "--engine in-session" in body
        assert "--engine acpx --agent codex" in body

    def test_mandatory_caveats(self):
        body = SCRIPT.read_text()
        assert "bill to a different plan" in body
        assert "Prompt-cache asymmetry" in body
        assert "overstate delegation savings" in body

    def test_estimate_disclaimer(self):
        body = SCRIPT.read_text()
        assert "client-side estimate" in body
        assert "It is not a bill." in body

    def test_worktree_recommendation(self):
        assert "disposable git worktree" in SCRIPT.read_text()

    def test_clean_workspace_contract(self):
        body = SCRIPT.read_text()
        assert "git status --porcelain" in body
        assert "git reset --hard" in body
        assert "git clean -fd" in body

    def test_cumulative_aggregation_documented(self):
        body = SCRIPT.read_text()
        assert "last cumulative token_count per file" in body


class TestBenchDispatchCostBehavior:
    def test_help_exits_zero_and_carries_recommendation(self):
        r = subprocess.run(
            ["bash", str(SCRIPT), "--help"], capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr
        assert "disposable git worktree" in r.stdout

    def test_missing_prompt_rejected_rc2(self):
        r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
        assert r.returncode == 2

    def test_extra_positional_rejected_rc2(self):
        r = subprocess.run(
            ["bash", str(SCRIPT), "task one", "task two"],
            capture_output=True, text=True,
        )
        assert r.returncode == 2

    def test_shellcheck_clean(self):
        if shutil.which("shellcheck") is None:
            pytest.skip("shellcheck not installed")
        r = subprocess.run(
            ["shellcheck", str(SCRIPT)], capture_output=True, text=True
        )
        assert r.returncode == 0, r.stdout + r.stderr
