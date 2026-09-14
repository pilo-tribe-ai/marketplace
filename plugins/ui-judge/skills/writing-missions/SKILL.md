---
name: writing-missions
description: Derives missions from the project documents, the code, and the person, then writes them as high-level Gherkin with no implementation detail. Backs /ui-judge:missions.
user-invocable: false
---

# Writing missions

Turn what the project says it does into missions a judge can rule on.

**Announce at start:** "I'm using the writing-missions skill to write missions
from your documents."

## What a mission is

A mission says what a person wants. It never says where to click.

It is the ground truth. The judge rules against it, and against nothing else.
So it must be right, and a person must agree it is right before it counts.

## Step 1 — Read the sources

Read, in this order:

1. The documents a user would read: `README`, `docs/`, a user guide, a PRD.
2. The code, to find behaviour the documents forgot.
3. Anything the person named when they ran the command.

When the command was run with `--from <path>`, read that document only. Do not
read the rest. The person asked for one document, and a mission grounded in a
document they did not name is a mission they cannot check.

For each behaviour you find, note where you found it. You will record that.

## Step 2 — Group the behaviour into areas

An area is a part of the application a person would name: signing in, the
basket, checkout, settings. One area becomes one mission file.

Do not make an area per page. A page is implementation. An area is what a
person is trying to do.

## Step 3 — Propose, and wait

Show the person the areas you found and the scenarios you would write. Use
`AskUserQuestion`. Ask about one area at a time.

For each area, ask:
- Is this right?
- Is anything missing?
- What must never happen here?

Do not write a file before the person answers. The mission is the contract.
A contract nobody read is not a contract.

## Step 4 — Write the mission

Follow `${CLAUDE_PLUGIN_ROOT}/templates/mission.feature`.

Rules you must not break:

- Write what a person wants. Never write where to click.
- Never write a web address, a path, a CSS selector, a test id, or an `aria`
  ref. The lint rejects all of these.
- Every `Then` must be something a person can see on the screen.
- Say "find where the site lists things for sale", not "open the products
  page".
- Set `# status: draft`. Only a person changes it to `approved`.

Record where the behaviour came from:

```
# grounded-in: docs/user-guide.md#buying-an-item
# grounded-in-hash: <the hash>
```

Get the hash with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/source_hash.py" hash docs/user-guide.md
```

## Step 5 — Lint, before you tell anyone the mission is written

Write the file, then run the gate on it at once.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mission_lint.py" .uijudge/missions/<name>.feature
```

Read the exit code. The three codes mean three different things.

| Exit code | Meaning | Do this |
| --- | --- | --- |
| 0 | the mission is clean | carry on |
| 1 | the mission names implementation detail | rewrite every line the gate printed, then run it again |
| 2 | the gate did not check the file: the path is wrong, or the file could not be read | fix the path and run it again. It named no lines, so there is nothing to rewrite. |

Do not turn off the check. Do not leave a mission in place that fails it: on
exit code 1, either rewrite it until the gate is clean, or delete the file.

The lint exists because a mission that names a URL breaks the moment somebody
renames a page, and then the judge reports a fault that is not there.

## Step 6 — Report

Say which missions you wrote, which sources each came from, and that they are
drafts. Tell the person to read them and change `# status:` to `approved` for
the ones they agree with.

Say plainly: nothing is judged until a person approves it.
