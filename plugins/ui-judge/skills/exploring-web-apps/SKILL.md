---
name: exploring-web-apps
description: Moves through a running web application with no mission, like a curious tester. Reports the areas it found, behaviour that looks wrong, and missions worth writing. Backs /ui-judge:explore.
user-invocable: false
---

# Exploring web apps

Look around an application the way a new tester would on their first day.

**Announce at start:** "I'm using the exploring-web-apps skill to look around
this application."

## How to behave

You are a new tester. Nobody gave you a list of pages. You were given the
front door and told to find out what this thing does.

- Do not guess a web address. Reach a new area by clicking, as a person does.
- Do not type a path into the address bar.
- Start at the front door and work outward.
- Follow the paths a real person would follow first.

## Stay inside the application

The Playwright MCP server is started once, by the entry `/ui-judge:setup`
wrote. You cannot change its arguments in the middle of a run.

So check instead. Read `allowed_origins` from `.uijudge/config.yaml`. Before you
follow any link, compare its origin with that list. Never open an origin the
list does not hold. Report the link and carry on.

If the MCP entry does not hold `--allowed-origins`, say so once and tell the
person to run `/ui-judge:setup` again. The check above still holds.

## Stop before you run out

Read `step_budget` from `.uijudge/config.yaml`. When the command was run with
`--budget <steps>`, use that number instead. Stop when you reach it, and
report what you have. A half-finished report is useful. A run that never ends
is not.

Stop early and say so if:
- you see the same area three times with nothing new
- an action would send an email, take a payment, or delete something a person
  would miss

## Report three things

### 1. The areas you found

Name each area the way a person would. Not the address. Say what a person can
do there, and how you got to it.

### 2. Behaviour that looks wrong

Report anything a careful tester would raise:

- a link that goes nowhere
- an error in the browser console
- a request that failed
- a control that does nothing when clicked
- text that shows `NaN`, `undefined`, `null`, or an empty price
- a form that takes obviously bad input without complaint
- a page that never finishes loading

For each one, say what you did, what happened, and what you expected instead.
Save a screenshot.

### 3. Missions worth writing

Propose missions for the areas you found. Write them in the mission shape, but
write them to `.uijudge/findings/exploration-<date>.md`.

Never write into `.uijudge/missions/`. A mission is a contract, and only a
person may add one. Say plainly that these are proposals, and that
`/ui-judge:missions` turns them into real missions.

## Also report what would make tests stable

Playwright picks a locator by a fixed order. A `data-testid` wins. A role with
an accessible name comes next. Everything after that is fragile.

So report every important control that has neither. Name the area, say what the
control does, and say that adding a `data-testid` or an accessible name would
make a compiled test far more stable.

This is the most useful thing you can tell a developer, and only exploring
finds it.
