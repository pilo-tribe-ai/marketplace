# Changelog

## 0.1.3

- All three scripts exit 2 on a file that is not valid UTF-8, and say so in one
  line. `UnicodeDecodeError` is not an `OSError`, so it escaped every guard and
  ended the process with code 1 and a traceback. Code 1 says "a source drifted"
  or "a mission names implementation detail", so a mission saved in the wrong
  encoding was marked `needs review` against a document that never changed.
- `mission_to_plan.py` opens the never block on any `Rule: never` line, not only
  on that exact line. `Rule: never happens` matched nothing, and every bullet
  under it was dropped in silence, so the plan lost its failure criteria.
- The judge writes each run stamp as `YYYY-MM-DDTHHMMSSZ`, with every field
  padded, and `/ui-judge:compile` says so where it sorts the run folders by
  name. No shape was stated, and an unpadded stamp sorts `2026-8-9` after
  `2026-8-11`, so the compile step counted the passes of the wrong runs.
- The driver records `page_changed` for each action. The judge's `movement`
  check read a field nobody wrote, so the check passed on every run.
- `storage_state` is read relative to `.uijudge/`, as `missions_dir` is. Only
  `.uijudge/auth/` is kept out of the repository, so a path read from the
  repository root put a live sign-in where git tracks it.
- `/ui-judge:setup` looks for an MCP entry whose key is exactly
  `plugin_playwright_playwright`, and says to rename any other key. The driver's
  tools are named from that key, so an entry called `playwright` passed setup
  and left the driver with no browser at all.
- `/ui-judge:setup` puts the address in `allowed_origins` as well as `base_url`.
  `/ui-judge:explore` reads `allowed_origins` before it follows a link, so the
  template value stopped exploration at the application's own front door.
- On drift, the judge prints the new hash and names both lines a person must
  edit. Setting `# status:` back to `approved` without recording the new hash
  brought the same `needs review` mark back on the next run, forever.

## 0.1.2

- `/ui-judge:setup` warns about a real site before it writes the config, not
  after. The config that names a site is what lets a later run click buttons on
  it, so the warning was worth nothing where it stood.
- The failure branch of the compile transform ends with `exit 1`. It ended with
  an `echo`, which succeeds, so a failed transform reported a good step.
- The judge reads only the console messages and the network requests that this
  scenario caused. The browser keeps running between scenarios, and a hard
  failure cannot be lifted, so one console error at the start of a run ruled
  every later scenario `app-broken`. A request to another host is reported, but
  it is no longer a hard failure.
- The judge skips the reset when the project has no `reset_command`. Setup
  allows "there is none", and reading an empty command as a failed one stopped
  every scenario.
- The judge reads `missions_dir` from the config and looks for `.feature` files
  there and nowhere else. A search over the whole repository picked up the
  plugin's own template.
- `source_hash.py` reports a source that is there and will not open as
  `unreadable` drift, with exit code 1. It raised, and the caller reads exit
  code 2 as "the mission itself could not be read".

## 0.1.1

- `mission_to_plan.py` keeps the order of a mission in the plan. Each `Then`
  becomes an `expect:` line under the step above it. Before this, the plan held
  one list of steps and one list of expected results. A mission that checks the
  basket after it adds an item, and again after it pays, then asked for a
  basket that shows one item and is empty at the same time. The generator wrote
  a test that checks everything at the end, which fails against a working
  application, or dropped a check without saying so.
- A check that comes before the first step keeps the same `expect:` mark as
  every other check, below a heading that says when it holds. One mark for all
  of them, so a reader who looks for `expect:` finds each check.

## 0.1.0

First release.

- `/ui-judge:setup` writes `.uijudge/config.yaml` and `.uijudge/credentials.md`,
  and records where secrets live without ever storing a value.
- `/ui-judge:missions` derives missions from the project documents and the
  code, asks the person to confirm, and writes high-level Gherkin.
- `/ui-judge:judge` runs missions one after another and rules `pass`,
  `app-broken`, `spec-stale`, or `unclear`, with evidence. The scenario is the
  unit of judgement, and a mission passes only when every scenario passes.
- `/ui-judge:explore` moves through the application with no mission, reports
  faults, and proposes missions.
- `/ui-judge:compile` turns a mission that passed three runs in a row into a
  Playwright test, through the Playwright generator agent.
- The judge agent has no browser tool. A test proves it.
- `mission_lint.py` rejects a mission that names a web address, a selector, a
  test id, or an `aria` ref.
- `source_hash.py` finds document drift before a browser opens. A drifted
  mission is marked `needs review`, and is still judged, so the change cannot
  pass unnoticed.
- `mission_to_plan.py` turns a mission into a Playwright plan with no model.
- A file named on the command line that cannot be read exits 2, not 1, and
  prints a plain message instead of a stack trace. Exit 1 keeps its one
  meaning, so a job cannot read a typo in a filename as a mission that failed
  the gate. This holds for all three scripts, and the skills that call them
  read the code rather than testing it for non-zero.
- `source_hash.py` exits 1 on a mission that names no source at all. A silent 0
  would read as a clean pass, and the mission would be judged as if a person
  had grounded and approved it.
- `mission_to_plan.py` prints nothing on standard output when it fails, so a
  shell redirect cannot leave an empty plan for the generator to build a test
  from.
- Setup shows a Playwright MCP entry with `--caps=testing,storage`. Both
  capability groups are off by default, and without them the driver has no
  check tool and no way to save a browser session.
