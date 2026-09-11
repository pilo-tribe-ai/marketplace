#!/usr/bin/env python3
"""Count the instructions in a prompt, and flag the shapes current models handle badly.

The number that matters is the instruction count, not the token count. Rule
following collapses geometrically: at a per-rule compliance of 0.98, the chance
that all 40 rules hold at once is about 45%. Reference material degrades gently
with size, so this tool counts rules and reference lines separately.

Exit codes:
  0  every file was read, and no file has a finding
  1  at least one finding
  2  a file could not be read, or no file was given anything to read

Rule identifiers (P1-P9, L1-L8, U1-U2) name entries in reference/principles.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Every identifier this tool prints. reference/principles.md holds one entry per
# identifier, and tests/test_reference_ids.py fails when the two lists drift.
RULES = {
    "P1": "Describe the outcome, not the procedure",
    "P2": "Keep rules few, and keep reference material separate",
    "P3": "Use concrete thresholds, not judgment words",
    "P4": "Put a small, stable corpus in the prompt and cache it",
    "P5": "Order the prompt for caching and attention",
    "P6": "Use one formatting scheme",
    "P7": "Frame instructions positively, and give a reason for each prohibition",
    "P8": "Enforce outside the prompt",
    "P9": "Version prompts, and test again on every model change",
    "L1": "Leave behind: capitals and emphasis words",
    "L2": "Leave behind: repairing behaviour by adding an instruction",
    "L3": "Leave behind: expert personas",
    "L4": "Leave behind: politeness, tips, and threats",
    "L5": "Leave behind: anti-laziness scaffolding",
    "L6": "Leave behind: a bigger window as room for more rules",
    "L7": "Leave behind: prescribing the reasoning steps",
    "L8": "Leave behind: XML tags treated as a Claude-only thing",
    "U1": "Unsettled: few-shot examples",
    "U2": "Unsettled: minimalism is a frontier-model luxury",
}

# The per-rule compliance the estimate assumes. The guide that this tool comes
# from quotes 0.98, and calls the figure directional. --per-rule changes it.
PER_RULE_DEFAULT = 0.98

# An instruction count is healthy when the estimate that all of its rules hold
# at once stays at or above 0.80, and at risk below 0.60. At 0.98 per rule that
# is 11 instructions and 26 instructions.
BAND_HEALTHY = 0.80
BAND_WATCH = 0.60

COSTS = ("delete", "rewrite", "move")

# Every check this tool can raise, and the rule it cites. reference/principles.md
# names its check under each rule, and tests/test_reference_ids.py fails when
# the two lists drift. A rule that is absent here is judgement only: a reader
# applies it, and no check can.
CHECKS = {
    "emphasis": "L1",
    "hedge": "P3",
    "bare-prohibition": "P7",
    "persona": "L3",
    "pressure": "L4",
    "anti-laziness": "L5",
    "prescribed-reasoning": "L7",
    "hard-rule-in-prose": "P8",
    "mixed-format": "P6",
    "instructions-before-reference": "P5",
}

# ---------------------------------------------------------------------------
# Text segmentation
# ---------------------------------------------------------------------------

ZONE_FRONTMATTER = "frontmatter"
ZONE_CODE = "code"
ZONE_REFERENCE = "reference"
ZONE_RULE = "rule"

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")
REFERENCE_TITLE = re.compile(
    r"^(reference|references|example|examples|appendix|corpus|background|"
    r"glossary|prior art|source|sources|data|input|inputs|document|documents|"
    r"transcript|sample|samples|template|templates)\b",
    re.I,
)
REFERENCE_OPEN = re.compile(
    r"^\s*<(reference|references|context|document|documents|example|examples|"
    r"data|corpus|transcript|input)>\s*$",
    re.I,
)
REFERENCE_CLOSE = re.compile(
    r"^\s*</(reference|references|context|document|documents|example|examples|"
    r"data|corpus|transcript|input)>\s*$",
    re.I,
)


class Line:
    """One source line, with the zone it sits in."""

    __slots__ = ("no", "text", "zone")

    def __init__(self, no: int, text: str, zone: str):
        self.no = no
        self.text = text
        self.zone = zone

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Line({self.no}, {self.zone}, {self.text[:40]!r})"


def segment(text: str) -> list[Line]:
    """Split a document into lines tagged with a zone.

    Frontmatter and fenced code hold no instructions. A section under a heading
    named Reference, Examples, Appendix and the like is reference material, and
    so is anything between a <reference> pair. Everything else is a rule zone,
    and only the rule zone is counted and flagged.
    """
    raw = text.split("\n")
    lines: list[Line] = []

    in_frontmatter = raw and raw[0].strip() == "---"
    in_code = False
    fence_mark = ""
    reference_depth = 0
    reference_level = 0  # heading level that opened a reference section, 0 = none

    for index, item in enumerate(raw):
        no = index + 1

        if in_frontmatter:
            lines.append(Line(no, item, ZONE_FRONTMATTER))
            if index > 0 and item.strip() == "---":
                in_frontmatter = False
            continue

        fence = FENCE.match(item)
        if fence and not in_code:
            in_code = True
            fence_mark = fence.group(1)
            lines.append(Line(no, item, ZONE_CODE))
            continue
        if in_code:
            lines.append(Line(no, item, ZONE_CODE))
            if item.strip().startswith(fence_mark):
                in_code = False
            continue

        if REFERENCE_OPEN.match(item):
            reference_depth += 1
            lines.append(Line(no, item, ZONE_REFERENCE))
            continue
        if REFERENCE_CLOSE.match(item):
            reference_depth = max(0, reference_depth - 1)
            lines.append(Line(no, item, ZONE_REFERENCE))
            continue

        heading = HEADING.match(item)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if REFERENCE_TITLE.match(title):
                reference_level = level
            elif reference_level and level <= reference_level:
                reference_level = 0

        zone = ZONE_REFERENCE if (reference_depth or reference_level) else ZONE_RULE
        lines.append(Line(no, item, zone))

    return lines


# ---------------------------------------------------------------------------
# Sentences and instructions
# ---------------------------------------------------------------------------

INLINE_CODE = re.compile(r"`[^`]*`")
QUOTED = re.compile(r'"[^"\n]{0,200}"')
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
CHECKBOX = re.compile(r"^\s*\[[ xX]\]\s*")
BLOCKQUOTE = re.compile(r"^\s*>\s?")
EMPHASIS_MARK = re.compile(r"\*\*|__|\*|_")
ABBREV_TAIL = re.compile(r"\b(e\.g|i\.e|etc|vs|cf|approx|fig|eq|no|al)\.$", re.I)

MODAL = re.compile(
    r"\b(must|should|shall|needs? to|have to|has to|required to|is required|"
    r"never|always|do not|don't|dont|cannot|can't|may not|ensure|make sure|"
    r"be sure to|avoid|refrain from|under no circumstances|at all times|"
    r"only ever|mandatory|forbidden|prohibited)\b",
    re.I,
)

IMPERATIVE = {
    "accept", "add", "announce", "answer", "apply", "ask", "assume", "attach",
    "begin", "build", "call", "cap", "capture", "check", "choose", "cite",
    "close", "collect", "commit", "complete", "confirm", "continue", "convert",
    "copy", "count", "cover", "create", "declare", "delete", "deploy",
    "describe", "do", "document", "drop", "emit", "end", "exclude", "explain",
    "extract", "filter", "find", "finish", "fix", "flag", "follow", "format",
    "gather", "generate", "give", "group", "highlight", "identify", "ignore",
    "include", "install", "invoke", "keep", "limit", "link", "list", "load",
    "log", "make", "mark", "merge", "move", "name", "note", "open", "output",
    "parse", "pick", "prefer", "prioritize", "print", "produce", "provide",
    "push", "put", "quote", "raise", "rank", "read", "record", "reject",
    "remove", "rename", "repeat", "replace", "report", "respond", "restate",
    "return", "retry", "review", "rewrite", "run", "save", "say", "scale",
    "search", "select", "send", "set", "show", "skip", "sort", "split",
    "start", "state", "stop", "structure", "summarise", "summarize", "tell",
    "test", "trace", "translate", "treat", "update", "use", "validate",
    "verify", "wait", "write",
}

# A softener in front of an imperative hides the imperative from a first-word
# test. "Please think step by step" is an instruction, and so is "First, run
# the tests". The softener is removed before the test, and L4 still flags the
# politeness itself.
SOFTENER = re.compile(
    r"^(please|kindly|now|then|next|first|second|third|finally|lastly|also|"
    r"additionally|instead|always|never|remember to|be sure to|make sure to|"
    r"you should|you must|you will|you can|you may)[,:]?\s+",
    re.I,
)


def strip_markup(text: str) -> str:
    """Remove the markup that is not part of the sentence.

    Inline code spans and double-quoted spans go first. A phrase inside
    backticks or quotation marks is a phrase being named, not a phrase being
    used, so a document is free to write about the words this tool flags as
    long as it quotes them.
    """
    out = INLINE_CODE.sub(" ", text)
    out = QUOTED.sub(" ", out)
    out = LINK.sub(r"\1", out)
    out = BLOCKQUOTE.sub("", out)
    out = LIST_MARKER.sub("", out)
    out = CHECKBOX.sub("", out)
    out = EMPHASIS_MARK.sub("", out)
    return out.strip()


def sentences(text: str) -> list[str]:
    """Split a line into sentences, holding common abbreviations together."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    buffer = ""
    for part in parts:
        buffer = f"{buffer} {part}".strip() if buffer else part
        if ABBREV_TAIL.search(buffer):
            continue
        if buffer:
            out.append(buffer)
        buffer = ""
    if buffer:
        out.append(buffer)
    return out


def table_cells(text: str) -> list[str]:
    """Return the cells of a markdown table row, or an empty list."""
    stripped = text.strip()
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return []
    if re.fullmatch(r"\|[\s:|-]+\|", stripped):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]


class Block:
    """One paragraph, list item, table row or heading, with its first line number.

    Markdown wraps a sentence over several lines. Counted line by line, one
    sentence becomes several fragments: the count goes up, and a reason that
    sits on the next line is read as missing. Joining the wrapped lines first
    keeps a sentence whole.
    """

    __slots__ = ("no", "text", "zone")

    def __init__(self, no: int, text: str, zone: str):
        self.no = no
        self.text = text
        self.zone = zone

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Block({self.no}, {self.zone}, {self.text[:40]!r})"


def build_blocks(lines: list[Line]) -> list[Block]:
    """Join wrapped lines into blocks. Frontmatter and code hold no blocks."""
    out: list[Block] = []
    open_block: Block | None = None

    for line in lines:
        if line.zone in (ZONE_FRONTMATTER, ZONE_CODE) or not line.text.strip():
            open_block = None
            continue

        text = line.text
        standalone = (
            HEADING.match(text)
            or STRUCTURAL_TAG.match(text)
            or table_cells(text)
        )
        if standalone:
            out.append(Block(line.no, text.strip(), line.zone))
            open_block = None
            continue

        starts_new = (
            open_block is None
            or open_block.zone != line.zone
            or LIST_MARKER.match(text)
            or CHECKBOX.match(text)
        )
        if starts_new:
            open_block = Block(line.no, text.strip(), line.zone)
            out.append(open_block)
            continue

        open_block.text = f"{open_block.text} {text.strip()}"

    return out


def units(block: Block) -> list[str]:
    """Return the sentence-sized units of one block, for counting and flagging."""
    if block.zone != ZONE_RULE:
        return []
    if HEADING.match(block.text):
        return []
    cells = table_cells(block.text)
    if cells:
        return [strip_markup(cell) for cell in cells if strip_markup(cell)]
    body = strip_markup(block.text)
    if not body:
        return []
    return sentences(body)


def is_instruction(sentence: str) -> bool:
    """Answer whether one sentence tells the reader to do or not do something."""
    body = sentence.strip()
    if not body or body.endswith("?"):
        return False
    if MODAL.search(body):
        return True
    body = SOFTENER.sub("", body, count=1)
    words = re.findall(r"[A-Za-z']+", body)
    if not words:
        return False
    return words[0].lower() in IMPERATIVE


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

EMPHASIS_WORDS = {
    "ABSOLUTELY", "ALL", "ALWAYS", "ATTENTION", "CAUTION", "CRITICAL", "DO",
    "DONT", "EVERY", "EXTREMELY", "FORBIDDEN", "IMMEDIATELY", "IMPORTANT",
    "MANDATORY", "MUST", "NEVER", "NOT", "NOTE", "ONLY", "REMEMBER",
    "REQUIRED", "STOP", "URGENT", "WARNING",
}
CAPS_TOKEN = re.compile(r"[A-Z']{2,}")
BANG = re.compile(r"!!")

HEDGE = re.compile(
    r"\b(appropriate|appropriately|as needed|when necessary|if appropriate|"
    r"where possible|if possible|relevant|significant|substantial|important|"
    r"high[- ]severity|low[- ]severity|severe|concise|brief|thorough|"
    r"thoroughly|comprehensive|reasonable|properly|carefully|sufficient|"
    r"adequate|meaningful|non-trivial|major|minor|high[- ]quality|"
    r"best[- ]effort|too many|too long|too short|excessive|efficiently|"
    r"clearly|well[- ]written|robust|scalable|maintainable|good|bad)\b",
    re.I,
)
DIGIT = re.compile(r"\d")

# "cannot" and "can't" state that something is impossible far more often than
# they forbid it, so they are left out. P7 is about a prohibition the writer
# chose to make, which is the kind that needs a reason.
PROHIBITION = re.compile(
    r"\b(never|do not|don't|dont|must not|may not|avoid|refrain from|"
    r"under no circumstances|forbidden|prohibited)\b",
    re.I,
)
REASON = re.compile(
    r"\b(because|otherwise|since|as it|as this|as that|which would|which will|"
    r"that way|for this reason|or else|to keep|to stop|to prevent|to avoid|"
    r"the reason|then the|it would|they would|nobody|no one|and then|"
    r"so (it|this|that|the|they|you|a|an|we|i|nobody|no one)\b|"
    r"or (it|this|the|they|you|nobody|no one)\b)",
    re.I,
)

PERSONA = re.compile(
    r"\b(you are (a|an|the) (world[- ]class|expert|senior|highly skilled|"
    r"experienced|professional|master|10x|best|leading|seasoned|brilliant)|"
    r"act as (a|an)|pretend (you are|to be)|world[- ]class|expert[- ]level|"
    r"you are the world's)\b",
    re.I,
)

PRESSURE = re.compile(
    r"(^please\b|\bthank you\b|\bthanks\b|\bi'?ll tip\b|\bi will tip\b|"
    r"\btip you\b|\$\d+ ?tip|\bmy (job|career|life) depends\b|"
    r"\bvery important to me\b|\byou will be penalized\b|"
    r"\btake a deep breath\b|\bi'?m counting on you\b|\bi am counting on you\b|"
    r"\bdo your best\b|\bif you fail\b|\bthis is urgent\b)",
    re.I,
)

ANTI_LAZY = re.compile(
    r"\b(do not be lazy|don't be lazy|do not stop until|never stop until|"
    r"keep going until|do not give up|complete the entire|do not truncate|"
    r"no placeholders|do not omit|write out the full|do not summarize|"
    r"be exhaustive|do not skip any|finish everything|"
    r"do not leave anything|every single|word[- ]for[- ]word|"
    r"do not abbreviate)\b",
    re.I,
)

PRESCRIBED_REASONING = re.compile(
    r"\b(think step[- ]by[- ]step|let'?s think|think carefully|"
    r"reason step[- ]by[- ]step|chain of thought|walk through your reasoning|"
    r"take a moment to think|plan your approach before|in your head|"
    r"first think|think about how to|reason internally|"
    r"before you answer,? think|before responding,? think)\b",
    re.I,
)

HARD_RULE = re.compile(
    r"\b(never reveal|do not reveal|never disclose|do not disclose|"
    r"never share|ignore (any|all) (previous |prior )?instructions|"
    r"disregard (any|all) (previous |prior )?instructions|"
    r"refuse to (answer|comply|respond)|"
    r"do not output (any )?(pii|passwords|secrets|credentials)|"
    r"redact (all|any|every)|sanitize the input)\b",
    re.I,
)

STRUCTURAL_TAG = re.compile(r"^\s*</?([a-zA-Z][\w-]*)\s*>\s*$")


def finding(rule: str, line: int, kind: str, cost: str, excerpt: str, note: str) -> dict:
    assert rule in RULES, f"{rule} is not a known rule identifier"
    assert cost in COSTS, f"{cost} is not a known cost"
    assert CHECKS.get(kind) == rule, f"check {kind} does not belong to rule {rule}"
    short = excerpt.strip()
    if len(short) > 90:
        short = short[:87] + "..."
    return {
        "rule": rule,
        "line": line,
        "kind": kind,
        "cost": cost,
        "excerpt": short,
        "note": note,
    }


def check_unit(block: Block, unit: str, following: str) -> list[dict]:
    """Return every finding raised by one sentence-sized unit."""
    line = block
    out: list[dict] = []
    instruction = is_instruction(unit)

    caps = {token for token in CAPS_TOKEN.findall(unit)} & EMPHASIS_WORDS
    if caps or BANG.search(unit):
        out.append(
            finding(
                "L1", line.no, "emphasis", "rewrite", unit,
                "Current models over-trigger on shouting. Plain wording reads the same to a model.",
            )
        )

    if instruction and HEDGE.search(unit) and not DIGIT.search(unit):
        out.append(
            finding(
                "P3", line.no, "hedge", "rewrite", unit,
                "The model will not ask what the word means. State a number or an explicit test.",
            )
        )

    # A unit that ends in a colon introduces the list under it, and the reason
    # usually sits in that list.
    if (
        instruction
        and not unit.rstrip().endswith(":")
        and PROHIBITION.search(unit)
        and not REASON.search(unit + " " + following)
    ):
        out.append(
            finding(
                "P7", line.no, "bare-prohibition", "rewrite", unit,
                "A prohibition with a reason holds far better than a bare one. Add the because.",
            )
        )

    if PERSONA.search(unit):
        out.append(
            finding(
                "L3", line.no, "persona", "delete", unit,
                "A persona changes style, not accuracy.",
            )
        )

    if PRESSURE.search(unit):
        out.append(
            finding(
                "L4", line.no, "pressure", "delete", unit,
                "Politeness, tips and threats have no reliable effect.",
            )
        )

    if ANTI_LAZY.search(unit):
        out.append(
            finding(
                "L5", line.no, "anti-laziness", "delete", unit,
                "Scaffolding against an older model's laziness breaks worst on a model upgrade. Keep it only on a small or unpinned model (U2).",
            )
        )

    if PRESCRIBED_REASONING.search(unit):
        out.append(
            finding(
                "L7", line.no, "prescribed-reasoning", "delete", unit,
                "Reasoning models often do worse when told how to think. Constrain the output instead.",
            )
        )

    if HARD_RULE.search(unit):
        out.append(
            finding(
                "P8", line.no, "hard-rule-in-prose", "move", unit,
                "A prompt steers; it does not enforce. Put this in a classifier or a code hook.",
            )
        )

    return out


def check_document(
    lines: list[Line], blocks: list[Block], reference_lines: int
) -> list[dict]:
    """Return the findings that belong to the file as a whole."""
    out: list[dict] = []

    headings = sum(
        1 for line in lines if line.zone in (ZONE_RULE, ZONE_REFERENCE) and HEADING.match(line.text)
    )
    tags = {
        STRUCTURAL_TAG.match(line.text).group(1).lower()
        for line in lines
        if line.zone in (ZONE_RULE, ZONE_REFERENCE) and STRUCTURAL_TAG.match(line.text)
    }
    if headings >= 3 and len(tags) >= 3:
        out.append(
            finding(
                "P6", 1, "mixed-format", "rewrite",
                f"{headings} markdown headings and {len(tags)} structural tag names",
                "Markdown headings and tags each work alone. Mixing the two schemes hurts.",
            )
        )

    if reference_lines >= 40:
        first_reference = next(
            (line.no for line in lines if line.zone == ZONE_REFERENCE and line.text.strip()), None
        )
        if first_reference is not None:
            before = [
                block.no
                for block in blocks
                if block.no < first_reference
                for unit in units(block)
                if is_instruction(unit)
            ]
            if len(before) >= 5:
                out.append(
                    finding(
                        "P5", before[-1], "instructions-before-reference", "move",
                        f"{len(before)} instructions sit above the reference block at line {first_reference}",
                        "Stable content first, long documents next, task instructions last.",
                    )
                )

    return out


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def band_of(estimate: float) -> str:
    if estimate >= BAND_HEALTHY:
        return "healthy"
    if estimate >= BAND_WATCH:
        return "watch"
    return "at-risk"


def analyse(text: str, path: str = "<text>", per_rule: float = PER_RULE_DEFAULT) -> dict:
    """Return the instruction count, the reference size, and every finding."""
    lines = segment(text)
    blocks = build_blocks(lines)

    instructions = 0
    findings: list[dict] = []
    rule_blocks = [block for block in blocks if block.zone == ZONE_RULE]

    for position, block in enumerate(rule_blocks):
        # A reason often sits in the next block, not the same sentence, so the
        # two blocks that follow count as part of the prohibition's context.
        following = " ".join(item.text for item in rule_blocks[position + 1 : position + 3])
        for unit in units(block):
            if is_instruction(unit):
                instructions += 1
            findings.extend(check_unit(block, unit, following))

    reference_lines = sum(
        1 for line in lines if line.zone == ZONE_REFERENCE and line.text.strip()
    )
    findings.extend(check_document(lines, blocks, reference_lines))
    findings.sort(key=lambda item: (item["line"], item["rule"]))

    estimate = per_rule**instructions
    return {
        "path": path,
        "instructions": instructions,
        "reference_lines": reference_lines,
        "code_lines": sum(1 for line in lines if line.zone == ZONE_CODE),
        "per_rule": per_rule,
        "estimate": round(estimate, 4),
        "band": band_of(estimate),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Reading and reporting
# ---------------------------------------------------------------------------


class ReadError(Exception):
    """A file that cannot be analysed. It is reported, and it sets exit code 2."""


def read_source(name: str) -> str:
    if name == "-":
        data = sys.stdin.buffer.read()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ReadError("standard input is not valid UTF-8")
        if not text.strip():
            raise ReadError("standard input is empty")
        return text

    path = Path(name)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ReadError(f"{name} is not valid UTF-8")
    except IsADirectoryError:
        raise ReadError(f"{name} is a directory; give it the files, or use resolve_target.py")
    except OSError as error:
        raise ReadError(f"{name} cannot be read: {error}")
    if not text.strip():
        raise ReadError(f"{name} is empty")
    return text


def render(reports: list[dict], errors: list[str]) -> str:
    out: list[str] = []
    for report in reports:
        estimate = f"{report['estimate'] * 100:.0f}%"
        out.append(report["path"])
        out.append(
            f"  instructions {report['instructions']}"
            f"   reference lines {report['reference_lines']}"
            f"   all-rules estimate {estimate} ({report['band']})"
        )
        if report["findings"]:
            out.append("  line  rule  kind                        cost     text")
            for item in report["findings"]:
                out.append(
                    f"  {item['line']:>4}  {item['rule']:<4}  {item['kind']:<26}"
                    f"  {item['cost']:<7}  {item['excerpt']}"
                )
        out.append(f"  {len(report['findings'])} findings")
        out.append("")

    if errors:
        out.append("errors")
        for message in errors:
            out.append(f"  {message}")
        out.append("")

    total_findings = sum(len(report["findings"]) for report in reports)
    total_instructions = sum(report["instructions"] for report in reports)
    out.append(
        f"{len(reports)} files read, {total_instructions} instructions, "
        f"{total_findings} findings, {len(errors)} errors"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Count the instructions in a prompt and flag the shapes current models handle badly.",
    )
    parser.add_argument("files", nargs="+", help="files to read, or - for standard input")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument(
        "--per-rule",
        type=float,
        default=PER_RULE_DEFAULT,
        help=f"per-rule compliance the estimate assumes (default {PER_RULE_DEFAULT})",
    )
    args = parser.parse_args(argv)

    if not 0.0 < args.per_rule <= 1.0:
        print("--per-rule takes a number above 0 and at or below 1", file=sys.stderr)
        return 2

    reports: list[dict] = []
    errors: list[str] = []
    for name in args.files:
        try:
            text = read_source(name)
        except ReadError as error:
            errors.append(str(error))
            continue
        reports.append(analyse(text, name, args.per_rule))

    if args.json:
        print(
            json.dumps(
                {
                    "files": reports,
                    "errors": errors,
                    "totals": {
                        "files": len(reports),
                        "instructions": sum(item["instructions"] for item in reports),
                        "findings": sum(len(item["findings"]) for item in reports),
                        "errors": len(errors),
                    },
                },
                indent=2,
            )
        )
    else:
        print(render(reports, errors))

    if errors or not reports:
        if not reports and not errors:
            print("no file was read", file=sys.stderr)
        return 2
    return 1 if any(report["findings"] for report in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
