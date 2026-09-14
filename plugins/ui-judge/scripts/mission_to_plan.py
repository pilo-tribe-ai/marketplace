#!/usr/bin/env python3
"""Turn a mission into a Playwright markdown plan.

The Playwright generator agent reads a markdown plan of scenarios, steps, and
expected results. A mission already holds those, in Gherkin shape. This turns
one into the other with no model in the loop, so the translation is the same
every time.

Usage:
    python3 mission_to_plan.py FILE

Exit code 0 means the plan was written to standard output. Exit code 2 means
this run produced no plan: no file was named, or the file could not be read.
"Could not be read" covers a file that is not valid UTF-8 as well as a file that
is not there. Nothing is printed to standard output on a failure, so a shell
redirect never leaves a half-written plan behind.
"""

import re
import sys
from typing import NamedTuple


class Step(NamedTuple):
    kind: str
    text: str


class Scenario(NamedTuple):
    name: str
    steps: list[Step]


class Mission(NamedTuple):
    feature: str
    tags: list[str]
    scenarios: list[Scenario]
    never: list[str]


FEATURE = re.compile(r"^\s*Feature:\s*(.+?)\s*$")
SCENARIO = re.compile(r"^\s*Scenario:\s*(.+?)\s*$")
# `\b`, not `$`. A `Rule: never` line that a writer extended, as in
# `Rule: never happens`, opened no never block, and every bullet under it was
# then dropped without a word. The plan lost its failure criteria, and the
# compiled test asked for less than the mission asked for.
NEVER = re.compile(r"^\s*Rule:\s*never\b", re.IGNORECASE)
BULLET = re.compile(r"^\s*-\s*(.+?)\s*$")
STEP = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+?)\s*$")
TAGS = re.compile(r"^\s*@(\S.*)$")

# Given and When say what a person does. Then says what must be true.
DOES = {"given", "when"}
MUST = {"then"}


def parse(text: str) -> Mission:
    """Read a mission into its parts."""
    feature = ""
    tags: list[str] = []
    scenarios: list[Scenario] = []
    never: list[str] = []

    name = ""
    steps: list[Step] = []
    in_never = False

    def close():
        if name:
            scenarios.append(Scenario(name, steps.copy()))

    for line in text.splitlines():
        if not line.strip():
            continue

        match = TAGS.match(line)
        if match:
            tags.extend(tag.lstrip("@") for tag in match.group(0).split())
            continue

        match = FEATURE.match(line)
        if match:
            feature = match.group(1)
            continue

        if NEVER.match(line):
            close()
            name, in_never = "", True
            continue

        match = SCENARIO.match(line)
        if match:
            close()
            name, in_never = match.group(1), False
            steps = []
            continue

        if in_never:
            match = BULLET.match(line)
            if match:
                never.append(match.group(1))
            continue

        match = STEP.match(line)
        if match:
            word, body = match.group(1).lower(), match.group(2)
            if word in DOES:
                kind = "does"
            elif word in MUST:
                kind = "must"
            else:
                # `And` and `But` continue the step above them. The list holds
                # that step, so nothing else must remember its kind.
                kind = steps[-1].kind if steps else "does"
            # One list, in the order of the mission. Two lists, one of actions
            # and one of checks, lose the moment at which each check holds.
            steps.append(Step(kind, body))

    close()
    return Mission(feature, tags, scenarios, never)


def steps_block(steps: list[Step]) -> list[str]:
    """Write the steps of one scenario, in the order the mission gave them.

    Each check goes under the action it follows. A mission that adds an item,
    checks the basket shows one item, pays, and then checks the basket is
    empty holds both checks at different moments. In two flat lists the plan
    asks for a basket that shows one item and is empty at the same time, and
    the generator either checks everything at the end, which fails against a
    working application, or drops a check without saying so.
    """
    lead: list[str] = []
    lines: list[str] = []
    number = 0
    for step in steps:
        if step.kind == "does":
            number += 1
            lines.append(f"{number}. {step.text}")
        else:
            # A check before the first action has no action to go under. Keep
            # it, and let a heading say when it holds. A dropped check is a
            # test that asks for less than the mission asked for.
            #
            # It keeps the same `expect:` mark as every other check. One mark
            # for all of them: a reader, or a tool, that looks for `expect:`
            # to find the checks must find each one.
            (lines if number else lead).append(f"   - expect: {step.text}")
    if lead:
        lead = ["Before the first step:"] + lead + [""]
    return lead + lines


def to_plan(mission: Mission) -> str:
    """Write the markdown plan the Playwright generator reads."""
    out = [f"# {mission.feature}", ""]
    if mission.tags:
        out.append("Tags: " + ", ".join(mission.tags))
        out.append("")

    for number, scenario in enumerate(mission.scenarios, start=1):
        out.append(f"## {number}. {scenario.name}")
        out.append("")
        out.append("**Steps:**")
        out.append("")
        out.extend(steps_block(scenario.steps))
        out.append("")

    if mission.never:
        out.append("## Failure criteria")
        out.append("")
        out.append("The test fails if any of these happen:")
        for item in mission.never:
            out.append(f"- {item}")
        out.append("")

    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: mission_to_plan.py FILE", file=sys.stderr)
        return 2

    # A file that cannot be read is not a plan with no scenarios in it. Say so
    # plainly and exit 2, as the two scripts beside this one do. A traceback
    # here goes to standard error while the shell redirect still makes an empty
    # plan file, and the next step then hands that empty file to the generator.
    #
    # A file that is not valid UTF-8 raises `UnicodeDecodeError`, which is not an
    # `OSError`. Left uncaught it ends the process with code 1 and a traceback,
    # and code 1 is not one of this script's two answers.
    try:
        with open(argv[1], encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        reason = (
            "the file is not valid UTF-8"
            if isinstance(error, UnicodeDecodeError)
            else error.strerror
        )
        print(
            f"mission_to_plan.py: cannot read {argv[1]}: {reason}",
            file=sys.stderr,
        )
        return 2

    mission = parse(text)
    if not mission.scenarios:
        print(
            f"mission_to_plan.py: {argv[1]} holds no Scenario, so there is no "
            f"plan to write.",
            file=sys.stderr,
        )
        return 2

    print(to_plan(mission))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
