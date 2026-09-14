"""Preamble delivery and codex model encoding on the acpx leg (4.20.0).

Static source assertions, deliberately not gated on `yq`/`acpx` being installed.
The behavioural acpx-dispatch suites skip silently on a machine without `yq` — more
than thirty of them — and both defects below lived on exactly those paths, so a gate
that also skips would restate the problem rather than catch it.

Two defects:

1. `preamble.md` was never delivered. `SKILL.md` listed it as a component and
   `docs/dispatch-contract.md` said it was prepended, but no code ever read the file;
   children received only the inline `<<DO_NOT_LOAD_SKILLS>>` block. The file carries
   the one-shot posture, the do-not-commit clause, the AUTONOMY modes and — load
   bearing — the licence to emit `NEEDS_DECISION:`. That sentinel is one of the four
   frozen public tokens with a complete receiving path (driver classification, the
   delegate-and-watch needs-decision bucket, `sessions detach`), and nothing had ever
   told a child it was permitted to emit one.

2. The codex-session driver path baked effort into the model id as
   `${model}[${effort}]`. acpx >= 0.12.0 validates `--model` against plain
   adapter-advertised ids and rejects that form, so the path failed at the adapter —
   and it is the path taken by exactly the four roles declaring `verify_artifact`
   (implementer, test-writer, fix-coder, plan-writer), the whole codex implementation
   pipeline. The in-code comment acknowledged it was non-functional rather than
   fixing it.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
ACPX_SKILL = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents"
DISPATCH = ACPX_SKILL / "acpx-dispatch.sh"
DRIVER = ACPX_SKILL / "codex-session-driver.sh"
PREAMBLE = ACPX_SKILL / "preamble.md"


@pytest.fixture(scope="module")
def dispatch_src():
    return DISPATCH.read_text()


class TestPreambleIsDelivered:
    def test_preamble_file_ships(self):
        assert PREAMBLE.is_file(), "preamble.md missing"
        assert len(PREAMBLE.read_text()) > 500

    def test_dispatch_reads_the_preamble_file(self, dispatch_src):
        assert "preamble.md" in dispatch_src, (
            "acpx-dispatch.sh must read skills/dispatching-acpx-agents/preamble.md — "
            "documenting it as prepended while never reading it is the 4.20.0 defect"
        )

    def test_builder_exists_and_is_the_single_assembly_site(self, dispatch_src):
        assert "build_preamble()" in dispatch_src, "expected a build_preamble helper"
        calls = len(re.findall(r"\{ build_preamble; cat ", dispatch_src))
        assert calls >= 3, (
            f"every dispatch path must assemble its prompt through build_preamble; "
            f"found {calls} call sites (expected codex fast-path, claude/opencode, "
            f"and the generic acpx loop)"
        )

    def test_no_inline_preamble_literal_remains(self, dispatch_src):
        """The isolation block lives inside build_preamble now, nowhere else."""
        assert "preamble='<<DO_NOT_LOAD_SKILLS>>" not in dispatch_src, (
            "an inline preamble literal survives — the assembly must have exactly one site"
        )

    def test_generic_loop_no_longer_passes_the_raw_prompt(self, dispatch_src):
        assert 'exec" "-f" "$PROMPT_FILE"' not in dispatch_src, (
            "the acpx-codex generic loop passed $PROMPT_FILE raw, so its children got "
            "neither the isolation block nor the autonomy contract"
        )
        assert "$GENERIC_PROMPT" in dispatch_src

    def test_missing_preamble_fails_loudly(self, dispatch_src):
        """Fail-to-error, not fail-to-silent-omission."""
        assert "missing required preamble" in dispatch_src, (
            "a missing preamble.md must abort the dispatch, not silently ship a "
            "prompt without the autonomy contract"
        )

    def test_preamble_licenses_needs_decision(self):
        """The receiving path is implemented; the sending side must authorise it."""
        text = PREAMBLE.read_text()
        assert "NEEDS_DECISION:" in text
        assert "AUTONOMY" in text

    def test_preamble_defaults_to_fire_and_forget(self):
        """Delivering it must not change behaviour for callers that never set AUTONOMY."""
        text = PREAMBLE.read_text()
        assert re.search(r"AUTONOMY.{0,40}absent.{0,60}fire-and-forget", text, re.S | re.I), (
            "preamble.md must state the fire-and-forget default, otherwise shipping it "
            "to every existing caller is a behaviour change"
        )


class TestCodexModelEncoding:
    def test_effort_rides_codex_config_on_the_driver_path(self, dispatch_src):
        assert "build_codex_config" in dispatch_src, (
            "driver-path effort must travel via CODEX_CONFIG, encoded by the shared "
            "build_codex_config helper the fast path also uses"
        )
        assert 'CODEX_CONFIG="$CODEX_EXEC_CONFIG"' in dispatch_src, (
            "CODEX_CONFIG must be exported into the driver's environment"
        )

    def test_sidecar_carries_codex_config(self, dispatch_src):
        """delegate-and-watch re-invokes from the sidecar; effort must survive that."""
        assert "printf 'CODEX_CONFIG=%q\\n'" in dispatch_src, (
            "the sidecar must carry CODEX_CONFIG or a watcher re-invocation loses effort"
        )

    def test_no_bracket_encoding_anywhere_in_the_leg(self):
        for path in (DISPATCH, DRIVER):
            src = path.read_text()
            live = [
                ln for ln in src.splitlines()
                if re.search(r'\$\{?MODEL\}?\[\$\{?EFFORT', ln) and not ln.strip().startswith("#")
            ]
            assert not live, f"{path.name} still builds a bracket-encoded model: {live}"

    def test_driver_comment_no_longer_claims_effort_is_baked_in(self):
        src = DRIVER.read_text()
        assert "Codex reasoning effort is baked into ACPX_MODEL" not in src, (
            "codex-session-driver.sh still documents the removed bracket contract"
        )


# --------------------------------------------------------------------------- #
# Behavioural coverage — runs the dispatcher for real.
#
# The static assertions above are the ungated floor; these actually execute
# acpx-dispatch.sh down the driver path (the one both defects lived on) with a stub
# driver substituted via DRIVER_OVERRIDE, then inspect what the child would have
# received. They need yq/jq, so they skip where the tooling is absent — which is
# exactly why the static block above exists and is not gated.
#
# Observed against acpx 0.13.0 while writing these, and recorded here because it is
# the evidence the encoding change was necessary AND sufficient:
#
#   $ acpx --model 'gpt-5.6-luna[high]' codex exec -f p.txt
#   Cannot apply --model "gpt-5.6-luna[high]": the ACP agent did not advertise that
#   model. Available models: gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, ...
#
#   $ CODEX_CONFIG='{"model_reasoning_effort":"high"}' acpx --model 'gpt-5.6-luna' ...
#   [client] session/set_config_option (running)
#   Hi! How can I help?
#   [done] end_turn
# --------------------------------------------------------------------------- #

_TOOLING = shutil.which("yq") is not None and shutil.which("jq") is not None
behavioural = pytest.mark.skipif(
    not _TOOLING, reason="acpx-dispatch.sh requires yq (mikefarah v4) and jq on PATH"
)

STUB_DRIVER = """#!/usr/bin/env bash
cp "$ACPX_PROMPT_FILE" "$PROBE_OUT/captured-prompt.txt"
{
  echo "MODEL_SEEN=$ACPX_MODEL"
  echo "CODEX_CONFIG_SEEN=$CODEX_CONFIG"
} > "$PROBE_OUT/captured-env.txt"
echo "ROLE_DONE"
"""


@behavioural
class TestDriverPathBehaviour:
    """implementer declares verify_artifact, so it takes the driver path — the path
    the bracket encoding broke and the one the raw-prompt bug never touched."""

    @pytest.fixture(scope="class")
    @staticmethod
    def probe(tmp_path_factory):
        # One dispatch serves every assertion in this class — the run is
        # deterministic and each test only reads the captured artifacts. Class
        # scope runs git init + the dispatch subprocess once, not per test.
        tmp_path = tmp_path_factory.mktemp("probe")
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
        (repo / "a.js").write_text("x\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
            cwd=repo, check=True,
        )

        out = tmp_path / "out"
        out.mkdir()
        stub = tmp_path / "stub-driver.sh"
        stub.write_text(STUB_DRIVER)
        stub.chmod(0o755)

        env = {
            **os.environ,
            "DRIVER_OVERRIDE": str(stub),
            "PROBE_OUT": str(out),
            "ACPX_ROLE_SLUG": "implementer",
            "ACPX_BINDING_PRESET": "implementer",
            "ACPX_INPUTS_JSON": json.dumps(
                {"task_text": "probe", "repo_root": str(repo)}
            ),
            "ACPX_RUN_ID": "probe-behavioural",
            "WORKTREE": str(repo),
        }
        proc = subprocess.run(
            ["bash", str(DISPATCH)], capture_output=True, text=True, env=env
        )
        return proc, out

    def test_dispatch_succeeds(self, probe):
        proc, _ = probe
        assert proc.returncode == 0, f"stderr:\n{proc.stderr[-1500:]}"

    def test_child_receives_the_isolation_block(self, probe):
        _, out = probe
        text = (out / "captured-prompt.txt").read_text()
        assert text.startswith("<<DO_NOT_LOAD_SKILLS>>")

    def test_child_receives_the_autonomy_contract(self, probe):
        """The regression: pre-4.20.0 the child got the isolation block ONLY."""
        _, out = probe
        text = (out / "captured-prompt.txt").read_text()
        assert "## Autonomy mode" in text, (
            "preamble.md content did not reach the child — the 4.20.0 defect"
        )
        assert "NEEDS_DECISION:" in text, (
            "the child was not licensed to emit NEEDS_DECISION:, so the driver's "
            "needs-decision branch and delegate-and-watch's bucket are unreachable"
        )

    def test_role_body_still_follows_the_preamble(self, probe):
        """Guards against the preamble displacing the actual task."""
        _, out = probe
        text = (out / "captured-prompt.txt").read_text()
        assert "## Output Contract" in text or "ROLE_DONE" in text
        assert text.index("<<DO_NOT_LOAD_SKILLS>>") < text.index("## Autonomy mode")

    def test_driver_receives_a_plain_model_id(self, probe):
        _, out = probe
        env_seen = (out / "captured-env.txt").read_text()
        model = re.search(r"MODEL_SEEN=(.*)", env_seen).group(1).strip()
        assert model and "[" not in model, (
            f"driver received a bracket-encoded model {model!r}; acpx >= 0.12.0 "
            f"rejects that form with 'the ACP agent did not advertise that model'"
        )

    def test_driver_receives_effort_via_codex_config(self, probe):
        _, out = probe
        env_seen = (out / "captured-env.txt").read_text()
        cfg = re.search(r"CODEX_CONFIG_SEEN=(.*)", env_seen).group(1).strip()
        assert "model_reasoning_effort" in cfg, (
            f"effort did not reach the driver via CODEX_CONFIG (got {cfg!r}) — "
            f"dropping it silently falls back to the adapter default"
        )
