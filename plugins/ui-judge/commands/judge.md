---
description: "Run missions against the running web application and rule on each one. Reports app-broken, spec-stale, or unclear with evidence. It does not repair anything."
argument-hint: "[mission-name|--tag <tag>|--all]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task, AskUserQuestion, Skill
---

# /ui-judge:judge

Run missions against the running web application, and rule on each one.

## Usage

```
/ui-judge:judge                 every mission that is approved or needs review
/ui-judge:judge checkout        one mission by name
/ui-judge:judge --tag shopper   every such mission with that tag
/ui-judge:judge --all           every mission, including drafts
```

A mission is marked `needs review` when the document behind it changed. It is
still run. If it were skipped, the change that made it drift would never be
judged, and nobody would see it.

## What it does

It runs each mission one after another, and each scenario inside a mission one
after another. For each scenario:

1. It gets the sign-in details from the place `credentials.md` names.
2. It puts the data back to a known state.
3. A driver agent walks the scenario by clicking, like a person.
4. Checks that need no model run first.
5. A separate judge agent rules on the record. That judge cannot open a
   browser.
6. It writes the verdict and the evidence.

The scenario is the unit of judgement. A mission passes only when every
scenario in it passes.

## What it does not do

It does not repair anything. It does not change the application. It does not
edit a mission, except to mark one that drifted as `needs review`. When it
finds a fault, it says what is wrong and shows the evidence. What to do about
it is your decision.

## Before you run it

`/ui-judge:setup` must have run. If `.uijudge/config.yaml` is missing, this
command stops and tells you.

## Process

Invoke `Skill('ui-judge:judging-missions')` with the parsed argument.

## Output

A table of scenarios and verdicts, and a rolled-up line per mission:

```
mission     scenario                    verdict      what decided it
checkout    a shopper buys one item     app-broken   the total read "NaN"
checkout    a shopper empties the cart  pass         the basket showed 0 items
checkout    MISSION                     app-broken   one scenario failed
signing-in  a shopper signs in          pass         the header showed the name
settings    a shopper renames itself    unclear      the record does not show
                                                     whether the name saved
```

Full evidence sits in `.uijudge/runs/<stamp>/`.
