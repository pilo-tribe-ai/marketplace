---
description: "Move through the running web application with no mission, like a curious tester. Reports the areas found, behaviour that looks wrong, and missions worth writing."
argument-hint: "[--budget <steps>]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task, Skill, mcp__plugin_playwright_playwright
---

# /ui-judge:explore

Look around the application with no mission, and report what you find.

## Usage

```
/ui-judge:explore
/ui-judge:explore --budget 100
```

## What it does

It starts at the front door and clicks its way around, like a person who was
never told what the pages are. It never types an address.

It reports three things:

1. The areas it found, named the way a person would name them.
2. Behaviour that looks wrong, with a screenshot for each.
3. Missions worth writing, saved to `.uijudge/findings/`.

It also reports the controls that have no test id and no accessible name.
Those are the ones that make a compiled test fragile.

## What it does not do

It never writes into `.uijudge/missions/`. A mission is a contract, and only
you may add one. Run `/ui-judge:missions` to turn a proposal into a mission.

It never repairs anything.

## Process

Invoke `Skill('ui-judge:exploring-web-apps')` with the parsed argument.
