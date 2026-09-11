---
name: compiling-missions
description: Turns a mission that passed into a deterministic Playwright test by handing a generated plan to the Playwright generator agent. Backs /ui-judge:compile.
user-invocable: false
---

# Compiling missions

Turn a mission that passed into a real Playwright test.

**Announce at start:** "I'm using the compiling-missions skill to turn this
mission into a Playwright test."

## What this does not do

It does not write test code itself. The Playwright generator agent does that.
That agent drives the application, checks every locator live, and builds the
code from the same generator behind `playwright codegen`. Code it produces is
machine-written, not guessed.

It does not repair a test that later breaks. The Playwright healer does that.
Keep the two apart: the healer exists to make a failing test pass, which is the
opposite of judging.

## Step 1 — Refuse a mission that is not steady

Read `passes_needed_to_compile` from `.uijudge/config.yaml`. The default is 3.

A mission may be compiled only when it ruled `pass` that many times in a row.
To count, list the run folders under `.uijudge/runs/` and sort them by their
`<stamp>` name, newest last. The judge writes each stamp as
`YYYY-MM-DDTHHMMSSZ`, with every field padded, so sorting the names sorts the
runs. Stop and say so if a folder name does not have that shape: the sort then
says nothing about which run is newest, and this step would count the passes of
the wrong runs. In each run, read this mission's `mission.json`
verdict. Count back from the newest run: the count holds only while each run in
turn reads `pass`, and stops at the first run that does not, or at the first run
that did not include this mission. The passes must be the most recent runs and
must touch no other verdict between them.

A mission that passes two times out of three is not describing steady
behaviour. Compiling it makes a test that fails at random, and a test that
fails at random gets switched off. Report it as unsteady and stop.

## Step 2 — Check the Playwright version

```bash
npx playwright --version
```

Version 1.56 or newer is needed. The agents arrived in that release. If it is
older, stop and say so. The rest of the plugin still works.

## Step 3 — Set up the Playwright agents

If `.claude/agents/playwright-test-generator.md` is missing, run:

```bash
npx playwright init-agents --loop=claude
```

This writes the three agent files, a `specs/` folder, and
`tests/seed.spec.ts`.

## Step 4 — Turn the mission into a plan

```bash
mkdir -p specs
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mission_to_plan.py" \
  .uijudge/missions/<name>.feature > specs/<name>.md.part \
  && mv specs/<name>.md.part specs/<name>.md \
  || { rm -f specs/<name>.md.part; echo "the transform failed" >&2; exit 1; }
```

Write to `<name>.md.part` first, and move it only when the script exits 0. A
plain `> specs/<name>.md` makes the file before the script runs, so a script
that exits 2 leaves an empty plan behind, and Step 5 then hands that empty plan
to the generator, which writes a test that checks nothing.

The `exit 1` at the end matters. Without it the last command of the failure
branch is an `echo`, which succeeds, so the whole line exits 0 and reports the
failed transform as a good step.

If the transform failed, stop. Do not go on to Step 5.

This is a mechanical transform. `Feature:` becomes the title, `Scenario:`
becomes a numbered section, `Given` and `When` become numbered steps, each
`Then` becomes an `expect:` line under the step above it, and `Rule: never`
becomes failure criteria. No model takes part, so the translation is the same
every time.

The plan keeps the order of the mission. A mission checks the basket after it
adds an item, and checks it again after it pays. The two checks are true at
different moments. A plan that lists all the steps and then all the checks
loses that. It then asks for a basket that shows one item and is empty at the
same time, and the generator writes a test that checks everything at the end.

## Step 5 — Hand it to the generator

Dispatch the Playwright generator agent with `specs/<name>.md`.

It drives the application, works out the locators, and writes the test.

## Step 6 — Run the test, and keep it only if it passes

```bash
npx playwright test <the new file>
```

If it passes, keep it. If it fails, delete it and report why. Never commit a
test that does not pass.

## Step 7 — Report

Say which test file was written, which mission it came from, and how many runs
in a row that mission passed.

Say plainly that the mission is still the contract. The test is a faster copy
of it. When they disagree, the mission wins, and something needs a person.
