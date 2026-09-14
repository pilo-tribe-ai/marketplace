import json
import os
import shlex
import shutil
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE.parents[1]          # .../plugins/relay
SEEDS_DIR = HERE / "seeds"
RESULTS_DIR = HERE / "results"


def pytest_addoption(parser):
    g = parser.getgroup("relay-itest")
    g.addoption("--relay-cmd", default=None, help="implement|verify|implement-verify")
    g.addoption("--relay-engine", default=None)
    g.addoption("--relay-agent", default=None)
    g.addoption("--relay-rounds", type=int, default=None)
    g.addoption("--relay-keep", action="store_true", default=False)


@pytest.fixture(autouse=True)
def _require_relay_itest():
    """Second gate (spec §3). Errors, never skips — a casual
    `pytest -m integration` must not start paid sessions."""
    if os.environ.get("RELAY_ITEST") != "1":
        raise RuntimeError(
            "relay integration tests start paid claude -p / acpx sessions. "
            "Run them via:  make itest TIER=gates  (the Makefile sets RELAY_ITEST=1). "
            "Refusing to run with RELAY_ITEST unset."
        )


@pytest.fixture(scope="session")
def relay_results_dir():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    d = RESULTS_DIR / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


def child_env(base=None):
    """Environment for the child `claude -p` (spec §4).

    Scrub every RELAY_* (the caller's shell must not preset the axis), CLAUDECODE,
    and every CLAUDE_CODE_* variable (running the harness from inside a Claude Code
    session must behave like a plain shell). Keep the real HOME so the child finds
    the developer's login and the installed superpowers plugin — the deliberate
    divergence from the unit conftest's hermetic-HOME policy.
    """
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key.startswith("RELAY_") or key.startswith("CLAUDE_CODE_") or key == "CLAUDECODE":
            del env[key]
    return env


# Calibration values (spec §4). C2 settles whether --max-budget-usd enforces on a
# subscription login. Until it does, --max-turns is the real ceiling and the budget flag
# is a best-effort second line; the wall-clock killpg is the last line.
#
# --max-turns IS a valid flag. It is hidden from `claude --help`, which is why an earlier
# draft removed it. `--help` is not the oracle for a hidden flag: the CLI errors on an
# unknown option at parse time, so the parse-time probe in
# tests/unit/integration-harness/test_cli_flags_supported.py is the oracle instead.
TIER_CAPS = {
    "gates": {"budget_usd": 1, "max_turns": 40, "wall_clock": 600},
    "e2e": {"budget_usd": 10, "max_turns": 300, "wall_clock": 7200},
}


def build_command(prompt, plugin_dir, caps):
    """The single child command line (spec §4). --plugin-dir is the seam the whole
    harness exists for; --strict-mcp-config with no --mcp-config gives zero MCP
    servers; bypassPermissions is contained by the throwaway sandbox."""
    return [
        "claude", "-p", prompt,
        "--plugin-dir", str(plugin_dir),
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "bypassPermissions",
        "--strict-mcp-config",
        "--max-budget-usd", str(caps["budget_usd"]),
        "--max-turns", str(caps["max_turns"]),
    ]


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _commit(cwd, message):
    _git(cwd, "add", "-A")
    _git(cwd, "-c", "user.email=itest@relay.local", "-c", "user.name=relay itest",
         "commit", "-q", "-m", message)


def build_sandbox(dest, seeds_dir, *, variant="implement", start_on="feature", pin=None):
    """Build a throwaway git repo at `dest` from seeds/toy-project (spec §5).

    start_on: 'feature' -> feature/itest (where a real run starts); 'main' ->
    stay on the default branch; 'detached' -> detach HEAD. Refusal gate rows use
    'main'/'detached'. variant 'verify'/'implement-verify' commit one small change
    on the feature branch so the loop has a diff to polish.
    """
    dest = Path(dest)
    shutil.copytree(Path(seeds_dir) / "toy-project", dest)
    cmds = dest / ".claude" / "commands"
    cmds.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(seeds_dir) / "commands" / "verify.md", cmds / "verify.md")
    if pin is not None:
        (dest / ".claude" / "relay.json").write_text(json.dumps(pin, indent=2) + "\n")
    _git(dest, "init", "-q", "-b", "main")
    _commit(dest, "seed: toy project")
    if start_on == "feature":
        _git(dest, "checkout", "-q", "-b", "feature/itest")
        if variant in ("verify", "implement-verify"):
            readme = dest / "README.md"
            readme.write_text(readme.read_text() + "\nitest: line to polish\n")
            _commit(dest, "itest: seed change for the verify loop")
    elif start_on == "detached":
        _git(dest, "checkout", "-q", "--detach")
    # start_on == "main": leave HEAD on main.
    return dest


@dataclass
class SessionResult:
    rc: int
    stream_path: Path
    sandbox: Path


def parse_session_names(listing):
    """First-column session names from an `acpx ... sessions list` table, skipping
    the header. The exact list format is confirmed on the first acpx-tier run
    (spec calibration); this parser is defensive and teardown tolerates a miss. [inferred]"""
    names = []
    for line in listing.splitlines():
        tok = line.split()
        if not tok or tok[0] in ("NAME", "SESSION"):
            continue
        names.append(tok[0])
    return names


def _close_acpx_sessions(sandbox):
    """Best-effort: close acpx sessions scoped to the sandbox cwd. killpg already
    reaps the child's process tree; this clears session records. Never fails teardown."""
    try:
        out = subprocess.run(["acpx", "--cwd", str(sandbox), "claude", "sessions", "list"],
                             capture_output=True, text=True, timeout=30).stdout
        for name in parse_session_names(out):
            subprocess.run(["acpx", "--cwd", str(sandbox), "claude", "sessions", "close", name],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        pass


@pytest.fixture
def make_sandbox(relay_results_dir):
    def _factory(*, variant="implement", start_on="feature", pin=None, row_id="row"):
        dest = relay_results_dir / f"row-{row_id}" / "sandbox"
        return build_sandbox(dest, SEEDS_DIR, variant=variant, start_on=start_on, pin=pin)
    return _factory


@pytest.fixture
def relay_session(request, relay_results_dir):
    keep = request.config.getoption("--relay-keep")
    started = []  # (proc, sandbox)

    def _run(prompt, *, sandbox, tier="gates", extra_env=None, row_id="row"):
        # Preconditions unmet ⇒ loud skip, never a FileNotFoundError ERROR (spec §7):
        # a machine without the claude binary skips the row naming the missing piece. [inferred]
        if shutil.which("claude") is None:  # [inferred]
            pytest.skip("claude CLI not on PATH — relay integration precondition unmet")  # [inferred]
        caps = TIER_CAPS[tier]
        cmd = build_command(prompt, PLUGIN_DIR, caps)
        env = child_env()
        if extra_env:
            env.update(extra_env)
        rowdir = relay_results_dir / f"row-{row_id}"
        rowdir.mkdir(parents=True, exist_ok=True)
        (rowdir / "command.txt").write_text(" ".join(shlex.quote(c) for c in cmd) + "\n")
        stream_path = rowdir / "stream.jsonl"
        with open(stream_path, "w") as out:
            proc = subprocess.Popen(cmd, cwd=str(sandbox), env=env,
                                    stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            started.append((proc, Path(sandbox)))
            try:
                rc = proc.wait(timeout=caps["wall_clock"])
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                rc = proc.wait()
        _git_dump(sandbox, rowdir / "sandbox-git.txt")
        return SessionResult(rc=rc, stream_path=stream_path, sandbox=Path(sandbox))

    yield _run

    for proc, sandbox in started:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        _close_acpx_sessions(sandbox)
        if not keep and sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)


def _git_dump(sandbox, path):
    try:
        log = subprocess.run(["git", "-C", str(sandbox), "log", "--oneline", "-n", "20"],
                             capture_output=True, text=True).stdout
        status = subprocess.run(["git", "-C", str(sandbox), "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        path.write_text(f"# git log\n{log}\n# git status --porcelain\n{status}\n")
    except Exception:
        pass
