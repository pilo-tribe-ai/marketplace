---
description: "Turn a mission that passed three runs in a row into a deterministic Playwright test, by handing a generated plan to the Playwright generator agent. Needs Playwright 1.56 or newer."
argument-hint: "<mission-name>"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task, Skill
---

# /ui-judge:compile

Turn a mission that passed into a real Playwright test.

## Usage

```
/ui-judge:compile checkout
```

## What it does

1. It checks the mission passed three runs in a row. A mission that passes only
   sometimes makes a test that fails at random.
2. It turns the mission into a Playwright markdown plan. This is a mechanical
   transform with no model in it.
3. It hands the plan to the Playwright generator agent, which drives the
   application, checks every locator live, and writes the test.
4. It runs the test, and keeps it only if it passes.

## What you need

Playwright 1.56 or newer. The agents arrived in that release. Everything else
in this plugin works without it.

## Process

Invoke `Skill('ui-judge:compiling-missions')` with the mission name.
