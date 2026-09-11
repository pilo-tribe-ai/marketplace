#!/usr/bin/env python3
"""Validate L3 command bodies: each must (1) invoke the task-kind classifier,
(2) NOT expose a --kind override (the kind is always auto-classified from context),
(3) — when require_branch — carry a policy-selection branch, (4) cite only known
vocabulary (L0+L1 from the language-reference doc, the 6 L2 skill names, plus
'classifying-task-kind'). Does NOT add the classifier to L2_NAMES (it has no
relay-vocab block)."""
import importlib.util, re
from pathlib import Path

TASK_KINDS = ["feature", "script", "config-artifact", "bugfix", "docs"]
_HERE = Path(__file__).resolve().parent

def _load(name):
    s = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

_v2 = _load("validate_l2_vocab")
_KNOWN = set(_v2._L0_NAMES) | set(_v2._L1_NAMES) | set(_v2.L2_NAMES) | {"classifying-task-kind"}
# The refining-* shims and the implementing coordinator are real shipped skills
# (EXPECTED_SKILLS) that L3 command bodies cite as critic/spine owners.
_KNOWN |= {"refining-specs", "refining-plans", "refining-prs", "refining-ui", "implementing"}
# delegate-and-watch is the acpx/smart-routing counterpart to delegate-leaf
_KNOWN |= {"delegate-and-watch"}
# dispatching-bg-agents is the background-session counterpart to
# dispatching-acpx-agents, cited by the bg-sessions arm of each command's
# delegation-wiring note (spec §Deliverable 2, Dispatch)
_KNOWN |= {"dispatching-bg-agents"}
# orchestrating-session-trees is the session-tree substrate skill: MAIN's Step 1
# invokes it directly (spec §Deliverable 3, Doctrine) — /relay:implement only.
_KNOWN |= {"orchestrating-session-trees"}
# driving-to-done is the autonomous run-to-done protocol skill backing /relay:drive
_KNOWN |= {"driving-to-done"}
# ensuring-worktree-isolation is the Step 0.5 worktree-isolation gate skill (v4.5.0)
# invoked by the 4 source-modifying L3 commands. Added via _KNOWN directly (NOT
# L2_NAMES): adding it to L2_NAMES would force a relay-vocab block, which this skill
# must not carry (it is not an L1-shape pattern) — keeps test_l2_skills_present green.
_KNOWN |= {"ensuring-worktree-isolation"}
# Shipped COMMANDS (not skills) are legitimate vocabulary: a command body may cite a
# sibling, as the Step 0.25 ask-when-unpinned text cites /relay:setup (4.12.0) and as
# drive's Step 1 cites /relay:diagnose for the advisory-kind precedent.
#
# 4.23.0: this was a hand-maintained `{"setup"}`, so citing any other sibling failed
# the vocabulary gate. Derived from disk instead — the set of shipped commands is
# exactly what is in commands/, and a hand-list drifts the moment a command is added.
_KNOWN |= {p.stem for p in (_HERE.parent / "commands").glob("*.md")}
# verifying-until-clean is the protocol skill backing /relay:verify (v4.22.0).
# Added via _KNOWN directly (NOT L2_NAMES): L2_NAMES membership forces a
# relay-vocab block, and the only honest l1-shape here is loop-until-clean,
# which skills/improve-loop/SKILL.md already declares. Two skills declaring one
# L1 shape makes the vocab block stop identifying the pattern owner.
_KNOWN |= {"verifying-until-clean"}
# running-implement-spine holds the Workflow-generation, run-intent, and
# completeness-gate steps /relay:implement's Step 3 now delegates to (v4.38.0).
# implementing-spec needs no entry here: this validator reads command bodies
# only, and no command body cites that adapter skill.
_KNOWN |= {"running-implement-spine"}
_TOKEN = re.compile(r"\brelay:([a-z][a-z0-9-]+)\b")

def check_delegation_wiring(body: str) -> list[str]:
    """Check that the body documents delegation wiring for acpx/smart-routing."""
    errs = []
    if "delegate-and-watch" not in body:
        errs.append("missing delegation-wiring note (relay:delegate-and-watch)")
    return errs

def check_command(body: str, require_branch: bool) -> list[str]:
    errs = []
    # The task-kind classifier is detected by the classifier skill name or a bare
    # 'classif' stem (classify/classification). Strip the worktree-gate '--classify'
    # flag first (v4.5.0 Step 0.5) so that flag never masquerades as a task-kind
    # classifier node — it is a git-state read, unrelated to task classification.
    _probe = body.lower().replace("--classify", "")
    if "classifying-task-kind" not in body and "classif" not in _probe:
        errs.append("missing task-kind classifier node")
    if "--kind" in body:
        errs.append("--kind override is no longer supported (kind is always auto-classified)")
    if require_branch and "branch" not in body.lower():
        errs.append("missing policy-selection branch")
    for tok in _TOKEN.findall(body):
        if tok not in _KNOWN:
            errs.append(f"unknown relay vocabulary token: {tok}")
    return errs

# The five L3 commands and whether each requires a policy-selection branch.
# `execute` is the sole False: it is open-ended composition with no required spine,
# so it has no branch table to select from.
#
# 4.4.0: drive.md joined the L3 set but was never added to this map, so the CLI path
# validated four of five commands and reported success. pytest still reached drive through a dedicated
# carve-out, so the gap was CLI-only — but the CLI is what a contributor runs, and it
# is the same omission shape as the 4.12.0 CMD_NAMES gap that left /relay:diagnose
# unable to resolve tiers. test_plugin.py now asserts this map covers every L3
# command, so a sixth cannot be added and silently skipped.
L3_CHECKS = {
    "implement.md": True,
    "refine.md": True,
    "execute.md": False,
    "drive.md": True,
    "diagnose.md": True,
}

# /relay:setup still sources parse-engine-agent.sh with "$@" and then reads the
# exported $RELAY_ENGINE / $RELAY_AGENT in prose — it prints nothing, so `bash`
# cannot replace `source` there. test_setup_command.py pins that exact "$@" shape.
# Fixing setup is a separate change (issue #110, out of scope). engines.md needs
# no entry — it has no bash block.
INLINE_SHAPE_EXEMPT = {"setup.md"}

_FENCE_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
_SOURCE_RE = re.compile(r"\s*(source|\.)\s")
_CASE_RE = re.compile(r"(?:^|[;&|]\s*)case\s")
_IF_RE = re.compile(r"\s*if\s")


def _strip_comment(raw_line: str) -> str:
    """Strip a trailing shell comment, but only a `#` that is actually outside
    single/double quotes — the naive `re.sub(r"(^|\\s)#.*$", "", line)` this
    replaced also stripped a quoted `#`, e.g. `echo "value #not-a-comment"`,
    silently deleting whatever inline shape followed it inside the string and
    letting it slip past this gate undetected."""
    in_single = in_double = False
    for i, ch in enumerate(raw_line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or raw_line[i - 1].isspace():
                return raw_line[:i]
    return raw_line


def check_inline_shapes(body: str) -> list[str]:
    """No fenced bash block may carry a shape a worktree-isolated session refuses:
    command substitution `$(...)`, `source`/`.` sourcing, a `case` statement, or a
    line starting `if`. Issue #110 moved every such shape in the six L3 command
    Step 0 blocks into scripts/l3-preflight.sh and scripts/worktree-preflight.sh."""
    errs = []
    for block in _FENCE_RE.findall(body):
        for lineno, raw_line in enumerate(block.splitlines(), start=1):
            # Strip a shell comment first — the same idiom
            # test_plugin.py::test_step0_never_reads_positional_parameters uses —
            # so a comment mentioning one of these shapes does not false-positive.
            # Quote-aware: a `#` inside a quoted string is not a comment.
            code = _strip_comment(raw_line)
            if "$(" in code:
                errs.append(f"inline shape '$(...)' in a bash block — move it into a script (line: {lineno})")
            if _SOURCE_RE.match(code):
                errs.append(f"inline shape 'source' in a bash block — move it into a script (line: {lineno})")
            if _CASE_RE.search(code):
                errs.append(f"inline shape 'case' in a bash block — move it into a script (line: {lineno})")
            if _IF_RE.match(code):
                errs.append(f"inline shape 'if' in a bash block — move it into a script (line: {lineno})")
    return errs


def main(argv):
    # argv was accepted and never read: `validate_l3_command.py commands/drive.md`
    # re-checked the same hardcoded set and printed nothing, which reads as a pass
    # for a file it never opened. Reject arguments rather than appear to honour them.
    if len(argv) > 1:
        print(
            "validate_l3_command.py takes no arguments — it validates the full L3 set "
            f"({', '.join(sorted(L3_CHECKS))}). Got: {argv[1:]}"
        )
        return 2
    cmd_root = _HERE.parent / "commands"
    failed = False
    for fname, rb in L3_CHECKS.items():
        p = cmd_root / fname
        if not p.exists():
            continue  # tolerate pre-cutover state
        body = p.read_text(encoding="utf-8").split("---", 2)[-1]
        errs = check_command(body, require_branch=rb)
        if fname == "implement.md":
            errs += check_delegation_wiring(body)
        if errs:
            failed = True
            for e in errs:
                print(f"FAIL {fname}: {e}")
    for p in sorted(cmd_root.glob("*.md")):
        if p.name in INLINE_SHAPE_EXEMPT:
            continue
        body = p.read_text(encoding="utf-8")
        for e in check_inline_shapes(body):
            failed = True
            print(f"FAIL {p.name}: {e}")
    return 1 if failed else 0

if __name__ == "__main__":
    import sys; raise SystemExit(main(sys.argv))
