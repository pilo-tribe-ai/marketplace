# UI Judge

Opens a web application in a browser, moves through it like a person, and rules
whether it does what its own documentation says.

It reports. It never repairs.

## Why

Tools that write browser tests are common. Tools that *rule* are not.

The Playwright healer, for example, exists to make a failing test pass. Point
it at a real fault and it repairs the test until the fault looks fine. It
cannot tell "the application broke" from "the application changed on purpose".

UI Judge answers that question, and only that question.

## How it works

Three layers. Only the middle one decides a verdict.

1. **Sources** — your documents, your code, and you.
2. **Missions** — plain-English files that say what the application must do.
   These are the ground truth. They live in your repository and you review them
   like any other file.
3. **Running** — a driver agent walks a mission by clicking. A separate judge
   agent reads only the mission and the record, and rules. The judge cannot
   open a browser.

## Commands

| Command | What it does |
| --- | --- |
| `/ui-judge:setup` | Ask about the application and where the secrets live. Write the config. |
| `/ui-judge:missions` | Read your documents, ask you to confirm, and write missions. |
| `/ui-judge:judge` | Run missions in the browser and rule on each one. |
| `/ui-judge:explore` | Look around with no mission. Report faults and propose missions. |
| `/ui-judge:compile` | Turn a mission that passed into a Playwright test. |

## A mission

```gherkin
# grounded-in: docs/user-guide.md#buying-an-item
# grounded-in-hash: 8f3c2a91...
# status: approved
@shopper
Feature: Checkout

  Scenario: A shopper buys one item
    Given I am signed in as a shopper
    When I find where the site lists things for sale
    And I add any item to my basket
    Then the basket shows one item
    When I go to the basket and begin checkout
    Then I see a total price

  Rule: never
    - an error in the browser console
    - a total of zero, blank, or "NaN"
```

No web address. No selector. A mission says what a person wants, never where to
click, so renaming a page never makes it report a fault that is not there.

The scenario is the unit of judgement. Each scenario gets its own verdict, and
a mission passes only when every scenario in it passes.

## The four verdicts

| Verdict | Meaning |
| --- | --- |
| `pass` | The application did what the mission says. |
| `app-broken` | The mission is well grounded. The application fails it. |
| `spec-stale` | The application worked, but differently. Your document is out of date. |
| `unclear` | The judge cannot tell. A person must look. |

`unclear` matters. Without it a judge that is unsure will guess.

## Getting started

```
/ui-judge:setup
/ui-judge:missions
/ui-judge:judge
```

## What you need

- Playwright MCP (`@playwright/mcp`), started with `--caps=testing,storage`.
  Both groups are off by default. Without `testing`, the driver has no
  `browser_verify_*` tool and cannot check a `Then` line. Without `storage`, it
  cannot save or restore a browser session. `/ui-judge:setup` shows the entry.
- Playwright 1.56 or newer, for `/ui-judge:compile` only.
- Python 3.12, for the three helper scripts.

## Secrets

UI Judge never stores a secret. Setup asks where each one lives — a secret
manager command, an environment variable, or a question at run time — and
records only the place. The value is held in memory, handed to the driver
agent, and taken out of every screenshot, log, and verdict.

## When a document changes

Each mission records the file it came from and a hash of that file. When the
file changes, the next run marks the mission `needs review` and says which
document moved. The mission is still judged, so the change cannot hide, but a
person must read it again, record the new hash, and set the status back to
`approved`.

## What it will not do

- It never edits your application code.
- It never edits a mission on its own, except to mark a drifted one
  `needs review`. A judge that may rewrite its own contract will rewrite it to
  pass.
- It never repairs a broken test. That is the Playwright healer's job.
