# End-to-end check

**Nothing below is proved. Every item reads NOT RUN.**

A person must run this check against a real web application. It needs a browser,
a running application with a sign-in, a list, and a form, and the slash commands
typed in a live Claude Code session. No test in the suite above can stand in for
it: those tests read files and run three scripts. They never open a browser.

Until someone runs this and edits the lines below, the plugin is untested
against a real application.

## The application used

NOT RUN — write down which application you used, and how you started it.

Any small web application in a local checkout with a dev server will do. It
must have a sign-in, a list, and a form. If none is at hand,
`npx create-next-app` with a sample template is enough.

## The steps

| # | Step | Result |
| --- | --- | --- |
| 1 | Choose a target application and write down which one | NOT RUN |
| 2 | Run `/ui-judge:setup`, then check the files it wrote | NOT RUN |
| 3 | Run `/ui-judge:missions`, then lint every mission it wrote | NOT RUN |
| 4 | Prove `pass`, then break the application and prove `app-broken` | NOT RUN |
| 5 | Put the application back, change the source document, prove `spec-stale` | NOT RUN |
| 6 | Prove no secret leaked into `.uijudge/runs/` | NOT RUN |
| 7 | Run `/ui-judge:explore` and prove it finds an uncovered area | NOT RUN |
| 8 | Run a mission three times, then `/ui-judge:compile` it | NOT RUN |
| 9 | Write down what happened, in this file | NOT RUN |

### Step 2 — what to confirm

- `.uijudge/config.yaml` exists and is valid YAML.
- `.uijudge/credentials.md` exists and holds no secret value.
- `.uijudge/.gitignore` holds `runs/` and `auth/`.
- A secret resolves from at least one recorded place.

### Step 3 — what to run

```bash
python3 plugins/ui-judge/scripts/mission_lint.py .uijudge/missions/*.feature
```

Expected: exit 0. No mission names a web address or a selector.

### Step 4 — what to expect

Mark a mission `approved`, then run `/ui-judge:judge`. Expect `pass`, with
evidence.

Now break the application on purpose. Change a label the mission depends on, or
make a total render as `NaN`. Run the judge again. Expect `app-broken`, naming
the step and the evidence. Not `spec-stale`.

Put the application back.

### Step 5 — what to expect

Leave the application alone. Edit the source document so it describes different
behaviour, and edit the mission to match. Run the judge.

Expect `spec-stale`. The verdict must also carry
`source_changed_since_approval: true`, because the hash no longer matches. The
mission's `# status:` line must now read `needs review`.

Put both back.

### Step 6 — what to run

```bash
grep -ri "<the real password>" .uijudge/runs/ || echo "clean"
```

Expected: `clean`.

### Step 7 — what to expect

A findings file that names an area no mission covers, and proposes a mission
for it. Confirm nothing was written into `.uijudge/missions/`.

### Step 8 — what to expect

A Playwright test file that passes. If Playwright is older than 1.56, expect a
clear message and no test, and record that instead.

## The acceptance list

These come from section 12 of `docs/superpowers/specs/2026-08-10-ui-judge-design.md`.

| Acceptance item | Result |
| --- | --- |
| `/ui-judge:setup` writes a valid `config.yaml` and `credentials.md`, and resolves a secret from at least one recorded source | NOT RUN |
| `/ui-judge:missions` writes a mission from a real document, and the mission holds no URL path and no selector | NOT RUN |
| `/ui-judge:judge` returns all four verdicts on a sample application, with evidence for each | NOT RUN |
| The judge rules `app-broken` when the application is broken, and `spec-stale` when the document is out of date | NOT RUN |
| `/ui-judge:explore` finds an area that no mission covers and proposes a mission for it | NOT RUN |
| `/ui-judge:compile` produces a Playwright test that passes | NOT RUN |
| `/ui-judge:compile` refuses a mission that passed only two runs out of three | NOT RUN |
| The judge writes its key points before it reads the record | NOT RUN |
| A ruling with `low` confidence is reported as `unclear` | NOT RUN |
| No secret appears in any file under `.uijudge/runs/` | NOT RUN |

## What was fixed

NOT RUN — when an item fails, say here what was wrong and what changed.
