import json
import pytest  # required for pytest.skip() in TestFlowSmoke (added Task 12) [inferred]

from conftest import PLUGIN_ROOT

FLOWS = PLUGIN_ROOT / "flows"
FLOW = FLOWS / "brainstorm.flow.ts"
PKG = FLOWS / "package.json"


class TestFlowArtifact:
    def test_flow_exists(self):
        assert FLOW.is_file()

    def test_uses_decision_sugar(self):
        body = FLOW.read_text()
        assert 'from "acpx/flows"' in body
        assert "decision(" in body and "decisionEdge(" in body
        # the hand-rolled switch-emitter form must be gone from the production flow
        assert "switch: {" not in body

    def test_reads_context_paths_in_flow(self):
        body = FLOW.read_text()
        assert "read_context" in body
        assert "brainstorm_context_paths" in body
        # context is read INSIDE the flow, not passed as an inline prd string
        assert "prd" not in body

    def test_input_type_fields(self):
        body = FLOW.read_text()
        for field in ("task", "brainstorm_context_paths", "guidelines", "specDir", "today"):
            assert field in body, f"flow Input missing {field}"

    def test_drives_unmodified_brainstorming(self):
        body = FLOW.read_text()
        assert "superpowers:brainstorming" in body

    def test_terminal_finish_has_no_outgoing_edge(self):
        body = FLOW.read_text()
        # finish is the terminal compute; no edge should originate from it
        assert 'from: "finish"' not in body


class TestFlowPackage:
    def test_package_declares_acpx_floor(self):
        pkg = json.loads(PKG.read_text())
        assert pkg.get("dependencies", {}).get("acpx") == ">=0.13.2"

    def test_lockfile_pins_resolved_version(self):
        lock = FLOWS / "package-lock.json"
        assert lock.is_file(), "committed package-lock.json must pin the resolved acpx version"
        # Parse the lockfile to find the resolved acpx version and assert it is >= 0.13.2.
        # This tolerates any future published version without requiring a test edit. [inferred]
        import json as _lockjson  # noqa: PLC0415
        data = _lockjson.loads(lock.read_text())
        # package-lock v2/v3: packages."node_modules/acpx".version [inferred]
        acpx_entry = (data.get("packages", {}).get("node_modules/acpx") or
                      (data.get("dependencies", {}).get("acpx")))
        assert acpx_entry is not None, "acpx must appear in package-lock.json"
        ver = acpx_entry.get("version", "")
        parts = ver.lstrip("v").split(".")
        major, minor = int(parts[0]), int(parts[1])
        assert (major, minor) >= (0, 13), f"acpx pinned version {ver} must satisfy >=0.13.2"


import json as _json
import os
import shutil
import subprocess


FIXTURE_DIR = PLUGIN_ROOT / "tests" / "e2e" / "fixtures" / "brainstorm"


class TestFlowSmoke:
    def test_autonomous_flow_writes_provisional_spec(self, tmp_path):
        if shutil.which("acpx") is None:
            pytest.skip("acpx not on PATH")
        if not (FLOWS / "node_modules" / "acpx").exists():
            pytest.skip("flows/ deps not installed (run: npm install in plugins/relay/flows)")
        if os.environ.get("RELAY_RUN_LIVE_FLOW") != "1":
            pytest.skip("live flow smoke disabled (set RELAY_RUN_LIVE_FLOW=1 + network egress)")

        prd = FIXTURE_DIR / "PRD.fixture.md"
        adr1 = FIXTURE_DIR / "ADR-0001-storage.md"
        adr2 = FIXTURE_DIR / "ADR-0002-dedupe.md"
        spec_dir = tmp_path / "docs" / "superpowers" / "specs"
        spec_dir.mkdir(parents=True)
        inp = tmp_path / "input.json"
        inp.write_text(_json.dumps({
            "task": "a personal bookmarks CLI named bm",
            "brainstorm_context_paths": [str(prd), str(adr1), str(adr2)],
            "guidelines": ("Root every decision in the context. NEVER violate an accepted ADR. "
                           "Prefer YAGNI. If the context is silent, choose the minimal option "
                           "and flag it [provisional]."),
            "specDir": str(spec_dir),
            "today": "2026-05-26",
        }))
        result = tmp_path / "result.json"
        r = subprocess.run(
            ["acpx", "--cwd", str(tmp_path), "--approve-all", "--prompt-retries", "3",
             "--timeout", "1800", "--format", "json",
             "flow", "run", str(FLOW), "--input-file", str(inp)],
            capture_output=True, text=True,
        )
        result.write_text(r.stdout)
        assert r.returncode == 0, r.stderr
        data = _json.loads(r.stdout)
        assert data["status"] == "completed", r.stdout[-2000:]
        spec_path = data["outputs"]["finish"]["specPath"]
        assert spec_path and os.path.isfile(spec_path)
        assert "[provisional]" in open(spec_path, encoding="utf-8").read(), (
            "the deliberately-omitted search decision must yield a [provisional] marker"
        )
