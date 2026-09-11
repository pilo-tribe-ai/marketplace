#!/usr/bin/env python3
"""doc_reference_scan.py — mechanical stale-doc-reference detector (relay).

Stdlib-only. Emits a single JSON findings object to stdout (design §4).
Degrades gracefully: non-git dir / no base ref -> one advisory finding +
verdict CLEAN rather than crashing (design §6).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def parse_args(argv):
    p = argparse.ArgumentParser(prog="doc_reference_scan.py")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--base-ref", default=None)
    p.add_argument("--pr-ref", default=None)
    p.add_argument("--diff-source", choices=["auto", "pr", "local"], default="auto")
    p.add_argument("--diff-file", default=None)
    p.add_argument("--run-gate", action="store_true", default=False)
    return p.parse_args(argv)


def _git(repo_root, *args):
    """Run git; return (returncode, stdout). Never raises."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout
    except (OSError, ValueError):
        return 127, ""


def is_git_repo(repo_root):
    rc, out = _git(repo_root, "rev-parse", "--is-inside-work-tree")
    return rc == 0 and out.strip() == "true"


def resolve_base_ref(repo_root, explicit):
    if explicit:
        return explicit
    rc, out = _git(repo_root, "merge-base", "origin/main", "HEAD")
    if rc == 0 and out.strip():
        return out.strip()
    # fallback: root commit (first parentless commit)
    rc, out = _git(repo_root, "rev-list", "--max-parents=0", "HEAD")
    if rc == 0 and out.strip():
        return out.strip().splitlines()[0]
    return ""


def name_status(repo_root, base_ref):
    """Return list of (status_code, old_path, new_path) from local git name-status."""
    rc, out = _git(repo_root, "diff", "--no-ext-diff", "--name-status", f"{base_ref}...HEAD")
    if rc != 0:
        return []
    entries = []
    for line in out.splitlines():
        parts = line.split("\t")
        code = parts[0]
        if code.startswith("R") and len(parts) >= 3:
            entries.append((code, parts[1], parts[2]))
        elif len(parts) >= 2:
            entries.append((code, parts[1], parts[1]))
    return entries


def added_lines_by_file(repo_root, base_ref, diff_source, diff_file, pr_ref):
    """Return {path: [(lineno, text), ...]} for lines INTRODUCED in the diff."""
    patch = _acquire_patch(repo_root, base_ref, diff_source, diff_file, pr_ref)
    out, cur, new_lineno = {}, None, 0
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            out.setdefault(cur, [])
        elif line.startswith("@@"):
            # @@ -a,b +c,d @@
            try:
                new_lineno = int(line.split("+", 1)[1].split(",", 1)[0].split(" ", 1)[0])
            except (IndexError, ValueError):
                new_lineno = 0
        elif line.startswith("+") and not line.startswith("+++"):
            if cur is not None:
                out[cur].append((new_lineno, line[1:]))
            new_lineno += 1
        elif not line.startswith("-"):
            new_lineno += 1
    return out


def _acquire_patch(repo_root, base_ref, diff_source, diff_file, pr_ref):
    if diff_source == "pr" or (diff_source == "auto" and pr_ref and _gh_available()):
        rc, out = _gh_pr_diff(pr_ref)
        if rc == 0:
            return out
    if diff_file:
        try:
            with open(diff_file) as fh:
                return fh.read()
        except OSError:
            pass
    rc, out = _git(repo_root, "diff", "--no-ext-diff", f"{base_ref}...HEAD")
    return out if rc == 0 else ""


def _gh_available():
    import shutil
    return shutil.which("gh") is not None


def _gh_pr_diff(pr_ref):
    try:
        proc = subprocess.run(["gh", "pr", "diff", str(pr_ref), "--patch"],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout
    except OSError:
        return 127, ""


def effective_diff_source(diff_source, diff_file, pr_ref):
    if diff_source == "pr" or (diff_source == "auto" and pr_ref and _gh_available()):
        return "pr"
    if diff_file:
        return "diff-file"
    return "local"


DOC_BASENAMES = {"README", "CLAUDE.md", "AGENTS.md", "README.md"}
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# [inferred] §5 name kinds + bare relative paths cited in prose/tables.
BARE_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|py|sh|ya?ml|json|txt))`")
COMMAND_NAME = re.compile(r"(?<![\w/])/([a-z][\w-]*):([a-z][\w-]*)")     # /plugin:command
SKILL_NAME = re.compile(r"(?<![\w/-])relay:([a-z][\w-]*)")               # relay:<skill> (not /relay:<cmd>)
AGENT_SLUG = re.compile(r"(?<![\w/-])agents/([a-z][\w-]*)\b")           # agents/<slug> (not part of a longer slug like dispatching-acpx-agents/)


def is_doc_file(path):
    base = os.path.basename(path)
    return path.endswith(".md") or base in DOC_BASENAMES or base == "README"


def file_exists_at_head(repo_root, rel_path):
    rc, _ = _git(repo_root, "cat-file", "-e", f"HEAD:{rel_path}")
    return rc == 0


def candidate_roots_for(doc_path, repo_root):
    """Resolution roots, plugin-first then repo-root.

    Walks doc_path upward looking for a `.claude-plugin/plugin.json` marker
    (the canonical plugin root).  Returns a list of Path objects; the repo root
    is always the last entry so non-plugin docs still resolve correctly.
    """
    roots = []
    repo = Path(repo_root).resolve()
    cur = Path(doc_path).resolve().parent
    while True:
        if (cur / ".claude-plugin" / "plugin.json").is_file():
            roots.append(cur)
            break
        if cur == repo or cur.parent == cur:
            break
        cur = cur.parent
    if repo not in roots:
        roots.append(repo)
    return roots


def file_exists_in_any_root(roots, rel):
    """Return True if `rel` resolves to a tracked file under any of `roots`."""
    repo_root = str(roots[-1])  # last entry is always the repo root
    for root in roots:
        candidate = str(root / rel)
        # Make the candidate relative to repo_root for git cat-file
        try:
            rel_to_repo = str(Path(candidate).relative_to(roots[-1]))
        except ValueError:
            continue
        if file_exists_at_head(repo_root, rel_to_repo):
            return True
    return False


def _strip_anchor(target):
    if "#" in target:
        path, anchor = target.split("#", 1)
        return path, anchor
    return target, None


def _is_external(target):
    return target.startswith(("http://", "https://", "mailto:"))


def _is_template_slot(target):
    return "{{" in target and "}}" in target


def _slugify_heading(text):  # [inferred] GitHub-style slug
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s+", "-", s).strip("-")


def _heading_slugs_at_head(repo_root, rel_path):  # [inferred] AC1(c)
    rc, out = _git(repo_root, "show", f"HEAD:{rel_path}")
    if rc != 0:
        return set()
    return {_slugify_heading(m.group(1))
            for m in re.finditer(r"^#{1,6}\s+(.+)$", out, re.M)}


def _anchor_resolves(repo_root, target_rel_path, anchor):  # [inferred]
    return _slugify_heading(anchor) in _heading_slugs_at_head(repo_root, target_rel_path)


def introduced_findings(repo_root, base_ref, added):
    findings = []
    repo_root_path = Path(repo_root).resolve()
    for path, lines in added.items():
        if not is_doc_file(path):
            continue
        doc_dir = os.path.dirname(path)
        # Resolve the absolute path of the doc for plugin-root detection.
        doc_abs = (repo_root_path / path).resolve()
        roots = candidate_roots_for(doc_abs, repo_root_path)
        for lineno, text in lines:
            def add(reference, why, fix, confidence="high"):
                findings.append({
                    "location": f"{path}:{lineno}", "reference": reference,
                    "kind": "introduced-unresolved", "confidence": confidence,
                    "why": why, "suggested_fix": fix,
                })
            # (a) relative markdown links + (c) anchors on those links
            for m in MD_LINK.finditer(text):
                target = m.group(1).strip()
                if _is_external(target) or _is_template_slot(target) or not target:
                    continue
                ref_path, anchor = _strip_anchor(target)
                if ref_path:
                    norm = os.path.normpath(os.path.join(doc_dir, ref_path))
                    if not file_exists_at_head(repo_root, norm):
                        add(target, f"introduced link target {ref_path} does not resolve at HEAD",
                            "point the link at an existing file or remove it")
                        continue
                    if anchor and not _anchor_resolves(repo_root, norm, anchor):
                        add(target, f"introduced anchor #{anchor} not found in {ref_path}",
                            "point the anchor at an existing heading or remove it")
                elif anchor:  # intra-file anchor
                    if not _anchor_resolves(repo_root, path, anchor):
                        add(target, f"introduced intra-file anchor #{anchor} not found",
                            "point the anchor at an existing heading or remove it")
            # (b) bare relative file paths in prose/tables (inline-code spans)
            for m in BARE_PATH.finditer(text):
                ref_path = m.group(1)
                if _is_template_slot(ref_path):
                    continue
                norm = os.path.normpath(os.path.join(doc_dir, ref_path))
                # Try plugin-aware multi-root resolution, then repo-root-relative.
                if (not file_exists_in_any_root(roots, norm)
                        and not file_exists_in_any_root(roots, ref_path)
                        and not file_exists_at_head(repo_root, norm)
                        and not file_exists_at_head(repo_root, ref_path)):
                    add(ref_path, f"introduced bare path {ref_path} does not resolve at HEAD",
                        "correct the path or remove the citation")
            # (d) §5 name kinds — command / skill / agent
            for m in COMMAND_NAME.finditer(text):
                plugin, cmd = m.group(1), m.group(2)
                # resolve against plugins/<plugin>/commands/<cmd>.md (repo layout)
                cand = f"plugins/{plugin}/commands/{cmd}.md"
                if not file_exists_at_head(repo_root, cand):
                    add(f"/{plugin}:{cmd}", f"introduced command /{plugin}:{cmd} has no commands/ entry at HEAD",
                        "register the command or correct the name")
            for m in SKILL_NAME.finditer(text):
                skill = m.group(1)
                # Plugin-aware: try skills/<skill>/SKILL.md under any candidate root.
                # Also try the canonical relay plugin path for docs sitting outside any plugin root.
                if not (file_exists_in_any_root(roots, f"skills/{skill}/SKILL.md")
                        or file_exists_at_head(str(roots[-1]), f"plugins/relay/skills/{skill}/SKILL.md")):
                    add(f"relay:{skill}", f"introduced skill relay:{skill} has no skills/{skill}/SKILL.md at HEAD",
                        "add the skill or correct the name")
            for m in AGENT_SLUG.finditer(text):
                slug = m.group(1)
                if slug == "README":
                    continue
                # Plugin-aware: try agents/<slug>.md under any candidate root.
                # Also try the canonical relay plugin path for docs sitting outside any plugin root.
                if not (file_exists_in_any_root(roots, f"agents/{slug}.md")
                        or file_exists_at_head(str(roots[-1]), f"plugins/relay/agents/{slug}.md")):
                    add(f"agents/{slug}", f"introduced agent slug agents/{slug} has no agents/{slug}.md at HEAD",
                        "add the agent or correct the slug")
    return findings


DOC_SCRIPT_RE = re.compile(
    r"docs:check|lint:docs|(?:^|:)link(?:[-:]|s$|check(?:er)?|$)|markdownlint|doc.*validate",
    re.I,
)
# (?:^|:)link(?:[-:]|s$|check(?:er)?|$) requires "link" at the start of the script name
# or immediately after a ":" namespace separator, and followed by a separator/terminator
# or known link-checker suffixes (check, checker).
# Pragmatic loss: "markdown-link-check" no longer matches; the typical npm alias for
# that tool is "link-check" (which still matches), so this is acceptable.
# Strict allowlist for gate names/targets: only safe identifier chars, no shell metacharacters.
# This prevents command injection from attacker-controlled package.json script keys or
# Makefile/justfile targets encountered when reviewing untrusted PR content.
GATE_NAME_RE = re.compile(r"[A-Za-z0-9:_.-]+")


def discover_doc_gate(repo_root):
    """Return (found, command) per §8 discovery order. Does NOT run the gate."""
    pkg = os.path.join(repo_root, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg) as fh:
                scripts = json.load(fh).get("scripts", {})
            for name in scripts:
                if DOC_SCRIPT_RE.search(name) and GATE_NAME_RE.fullmatch(name):
                    return True, f"npm run {name}"
        except (OSError, ValueError):
            pass
    for mk in ("Makefile", "justfile"):
        path = os.path.join(repo_root, mk)
        if os.path.isfile(path):
            try:
                text = open(path).read()
            except OSError:
                continue
            # [inferred] Capture the ACTUAL matched target name (e.g. docs-validate,
            # docs-check, doc-lint) rather than hard-coding docs-check, so the emitted
            # command names a target that really exists.
            m = re.search(r"^(docs?[\w-]*):", text, re.M)
            if m:
                target = m.group(1)
                # Validate target against strict allowlist before returning.
                if not GATE_NAME_RE.fullmatch(target):
                    continue
                runner = "make" if mk == "Makefile" else "just"
                return True, f"{runner} {target}"
    return False, None


def _gate_argv(command):
    """Map a discovered gate command string to a safe fixed argv list, or None.

    Accepts ONLY the three canonical forms produced by discover_doc_gate:
      "npm run <name>"  -> ["npm", "run", name]
      "make <target>"   -> ["make", target]
      "just <target>"   -> ["just", target]

    The name/target must fully match GATE_NAME_RE (no shell metacharacters).
    Returns None for any unrecognised or invalid form so the caller can
    safely skip execution — no shell is ever invoked.

    NOTE: PR content (package.json keys, Makefile targets) is UNTRUSTED.
    This validation is the last line of defence against command injection.
    """
    if command is None:
        return None
    parts = command.split(" ", 2)
    if len(parts) == 3 and parts[0] == "npm" and parts[1] == "run":
        name = parts[2]
        if GATE_NAME_RE.fullmatch(name):
            return ["npm", "run", name]
        return None
    if len(parts) == 2 and parts[0] in ("make", "just"):
        target = parts[1]
        if GATE_NAME_RE.fullmatch(target):
            return [parts[0], target]
        return None
    return None


def run_doc_gate(repo_root, command):
    """Map exit code to pass|fail|not-run. 30s timeout, combined stdout+stderr.

    The gate is executed as a fixed argv list — NO shell is invoked. The command
    string is validated by _gate_argv() which accepts only the three safe canonical
    forms ("npm run <name>", "make <target>", "just <target>") with name/target
    fully matched against GATE_NAME_RE (alphanumeric plus :_.- only).

    PR content (package.json script keys, Makefile targets) is NOT assumed trusted.
    Any name containing shell metacharacters is rejected and execution is skipped.
    """
    argv = _gate_argv(command)
    if argv is None:
        return "not-run"
    try:
        proc = subprocess.run(
            argv,
            cwd=repo_root, timeout=30, capture_output=True, text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "not-run"
    return "pass" if proc.returncode == 0 else "fail"


def _grep_at_head(repo_root, needle):
    """Return [(path, lineno, line)] for matches of a literal needle across tracked files."""
    rc, out = _git(repo_root, "grep", "-n", "-F", "--", needle, "HEAD")
    if rc != 0:
        return []
    hits = []
    for line in out.splitlines():
        # format: HEAD:<path>:<lineno>:<text>
        rest = line[len("HEAD:"):] if line.startswith("HEAD:") else line
        parts = rest.split(":", 2)
        if len(parts) == 3:
            path, lineno, text = parts
            hits.append((path, lineno, text))
    return hits


def dangling_findings(repo_root, statuses):
    findings = []
    for code, old_path, new_path in statuses:
        if code == "D":
            kind, label = "dangling-delete", "deleted"
        elif code.startswith("R"):
            kind, label = "dangling-rename", f"renamed to {new_path}"
        else:
            continue
        if not is_doc_file(old_path):
            continue
        basename = os.path.basename(old_path)
        needles = [old_path] if old_path == basename else [old_path, basename]
        for needle in needles:
            hit_count = 0  # [inferred]
            for path, lineno, text in _grep_at_head(repo_root, needle):
                if code.startswith("R") and path == new_path:
                    continue
                hit_count += 1
                findings.append({
                    "location": f"{path}:{lineno}",
                    "reference": needle,
                    "kind": kind,
                    "confidence": "high",
                    "why": f"references {old_path}, which was {label} in this diff",
                    "suggested_fix": (f"update the reference to {new_path}"
                                      if code.startswith("R") else
                                      "remove the reference or restore the target"),
                })
            # [inferred] Only break if the more-specific path-form produced hits;
            # otherwise fall through to the basename needle so a reference citing
            # only the basename of a deleted/renamed NESTED doc is still caught.
            if needle == old_path and hit_count > 0:
                break
    return findings


def advisory(why):
    return {
        "location": "<repo>",
        "reference": "",
        "kind": "advisory",
        "confidence": "low",
        "why": why,
        "suggested_fix": "run inside a git repository with a resolvable base ref",
    }


def emit(obj):
    json.dump(obj, sys.stdout)
    sys.stdout.write("\n")


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    result = {
        "verdict": "CLEAN",
        "diff_source": "local",
        "base_ref": args.base_ref or "",
        "findings": [],
        "doc_gate": {"found": False, "command": None, "result": None},
    }
    if not is_git_repo(args.repo_root):
        result["findings"].append(advisory("not a git repository; nothing scanned"))
        emit(result)
        return 0
    base_ref = resolve_base_ref(args.repo_root, args.base_ref)
    if not base_ref:
        result["findings"].append(advisory("no resolvable base ref; nothing scanned"))
        emit(result)
        return 0
    result["base_ref"] = base_ref
    result["diff_source"] = effective_diff_source(args.diff_source, args.diff_file, args.pr_ref)
    statuses = name_status(args.repo_root, base_ref)
    added = added_lines_by_file(args.repo_root, base_ref, args.diff_source,
                                args.diff_file, args.pr_ref)
    result["findings"].extend(introduced_findings(args.repo_root, base_ref, added))
    result["findings"].extend(dangling_findings(args.repo_root, statuses))
    if result["findings"]:
        result["verdict"] = "FINDINGS"
    found, command = discover_doc_gate(args.repo_root)
    gate = {"found": found, "command": command, "result": None}
    if found:
        gate["result"] = run_doc_gate(args.repo_root, command) if args.run_gate else "not-run"
    result["doc_gate"] = gate
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
