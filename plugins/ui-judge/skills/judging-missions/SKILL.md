---
name: judging-missions
description: Runs missions against a running web application and rules on each one. A driver agent walks and records. A separate judge agent rules on the record. Backs /ui-judge:judge.
user-invocable: false
---

# Judging missions

Run one or more missions against a running web application, and rule on each.

**Announce at start:** "I'm using the judging-missions skill to rule on these
missions."

## The rule that shapes everything

The agent that walks the application is not the agent that rules. The judge
cannot open a browser. It never sees the application, only the record.

A judge that could go and look would keep looking until it found a reason to
pass. Then the same mission would give two answers on two days, and nobody
could tell why.

## Missions run one after another

Never run two missions at the same time. Two missions can change the same
data, and then a failure does not say which mission caused it.

The scenarios inside a mission also run one after another, and for the same
reason.

## Before anything else

1. Read `.uijudge/config.yaml`. If it is missing, stop and say to run
   `/ui-judge:setup` first.
2. Read `missions_dir` from the config, and read it as a path relative to
   `.uijudge/`. Look for `.feature` files in that folder and nowhere else. A
   search over the whole repository picks up the plugin's own template and any
   other project's fixtures, and then the run judges files nobody wrote as
   missions.
3. Work out which missions to run, from the argument you were given:

   | Argument | Run |
   | --- | --- |
   | none | every `.feature` file whose `# status:` is `approved` or `needs review` |
   | a mission name | that one file, whatever its status |
   | `--tag <tag>` | every `approved` or `needs review` file that carries that tag |
   | `--all` | every `.feature` file, drafts included |

   Say how many you found, and name any you skipped and why. If the set is
   empty, stop and say so. A run that judges nothing must never report success.
4. Start the application with the `start_command`, unless it already answers at
   `base_url`. Wait until it answers. If it never answers, stop and say so.

## For each mission, in turn

### RESOLVE

Check the source for drift first. No browser is open yet.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/source_hash.py" check <mission> --root .
```

Read the exit code. The three codes mean three different things, and you must
not treat them alike.

| Exit code | Meaning | Do this |
| --- | --- | --- |
| 0 | every source still matches | carry on |
| 1 | drift: a source changed, went missing, could not be opened, is ungrounded, or has no recorded hash | the three steps below, then carry on |
| 2 | the mission itself could not be read | stop this mission and report it as an error. It is not drift, and it is not a verdict. |

On exit code 1, do three things, then carry on. Do not stop.

1. Hold `source_changed_since_approval: true` for this run.
2. Rewrite the mission's `# status:` line to `# status: needs review`. A
   mission whose source changed is no longer approved by anyone. Leave the rest
   of the mission alone. This is the one edit this skill is allowed to make,
   and it changes a status line only, never a step.
3. Say plainly which source the tool named, and which of the five states it
   printed: `changed`, `missing`, `unreadable`, `unrecorded`, or `ungrounded`.
   Only `changed` means the document moved on. The other four mean the mission
   names no source you can trust.

A changed source makes a `spec-stale` verdict more likely.

Now get the sign-in details. Read `.uijudge/credentials.md`. For the role the
mission names, follow the "Where to get the details" instructions in order
until one works. Hold the value in memory. Never write it to a file, and never
put it in your reply.

You have no browser tool. The driver holds the only browser tools, so pass the
value to the driver when you dispatch it. Name it `<role user>` and
`<role pass>` in everything you write afterward.

## For each scenario in the mission, in turn

The scenario is the unit of judgement. A mission with three scenarios gets
three verdicts, and one rolled-up mission verdict.

### RESET

Read `reset_command` from the config. Setup allows a project to have none, so
the value may be empty or absent. When it is, skip this step, say once in the
report that no reset ran, and carry on. Do not treat an empty command as a
failed one: that would stop every scenario in a project that needs no reset.

When there is a command, run it. If it fails, stop this scenario and record
why. Do not judge on data you do not understand.

You cannot restore a browser session yourself, because you hold no browser
tool. Instead, read `storage_state` for the role from the config, and give that
path to the driver when you dispatch it. The driver restores the session.

Read that path as relative to `.uijudge/`, as you read `missions_dir`. A saved
session holds a live sign-in. `.uijudge/.gitignore` keeps `auth/` out of the
repository, and it can only do that for `.uijudge/auth/`. A path read from the
repository root puts the same file where git tracks it, and the next commit
carries the sign-in.

### WALK

Dispatch the `mission-driver` agent. Give it:

- the mission file, and the name of the one scenario to walk
- the base address
- the step budget from the config
- the path to write `record.json`
- the path to write screenshots
- the `storage_state` path for the role, when one exists, so the driver can
  restore the saved session
- the sign-in details you resolved in RESOLVE, when the scenario signs in

The driver walks and records. It does not rule.

### CHECK

Run the checks that need no model. Read them from the driver's record:

| Check | Fails when |
| --- | --- |
| console | this scenario's own walk put an error in the console |
| network | a request this scenario's own walk caused, to the application's own origin, failed or answered 4xx or 5xx |
| movement | an action's `page_changed` field reads false |
| budget | the driver ran out of steps |
| blocked | the driver said it could not go on |

Read only the console messages and the network requests that came after the
driver's first step. The driver records what the browser already held, apart
from its own. A message an earlier scenario left behind is not this scenario's
fault, and a hard failure cannot be lifted, so counting it would rule every
later scenario `app-broken` for one fault at the start of the run.

A request to another host, such as a font or an analytics service, is not the
application. Report it in the words of the verdict, but do not make it a hard
failure.

Also read the mission's `Rule: never` list. Every line there is a check.

If a check fails, record it as a hard failure. The model is not asked about it.
A hard failure decides the scenario on its own: the scenario verdict is
`app-broken`, whatever the judge later returns. You still run the judge, for the
evidence and the words, but its verdict cannot lift a hard failure to `pass`.

### RULE

Dispatch the `mission-judge` agent. Give it exactly two things:

- the mission file, and the name of the one scenario it rules on
- the driver's `record.json`, with the evidence folder

Give it nothing else. Never give it the address of the application.

The judge writes its key points first, then chooses its evidence, then rules.
It returns one of `pass`, `app-broken`, `spec-stale`, or `unclear` for each key
point, with a confidence. A `low` confidence becomes `unclear`.

### WRITE

Write the run folder. One folder per scenario:

```
.uijudge/runs/<stamp>/<mission>/
  mission.json
  <scenario-slug>/
    record.json
    verdict.json
    evidence/
```

The stamp is the time the run started, in UTC, written as
`YYYY-MM-DDTHHMMSSZ`, as in `2026-08-11T090512Z`. Every field is padded to its
full width. `/ui-judge:compile` sorts these folder names to find the newest
runs, and a stamp that drops a leading zero sorts `2026-8-9` after `2026-8-11`.
The compile step would then count the passes of the wrong runs.

The scenario slug is the scenario name in lower case, with each run of
characters that are not letters or numbers replaced by one dash.

The judge cannot see the hash check, so it leaves two fields for you. Add them
to `verdict.json` after the judge returns:

- `grounded_in`: the list of sources from the mission's `# grounded-in:` lines.
- `source_changed_since_approval`: true or false, from the drift check you ran
  in RESOLVE.

The scenario verdict written here is the judge's verdict only when no hard
check failed in CHECK. When a hard check failed, write `app-broken` instead.

Write `mission.json` after the last scenario. It holds the mission verdict.
The mission passes only when every scenario passes. Otherwise it takes the most
serious verdict among its scenarios, in this order: `app-broken`, then
`spec-stale`, then `unclear`.

Before you write anything, take out every secret value. Replace it with
`<role user>` or `<role pass>`.

## When every mission is done

Report a table: mission, scenario, verdict, and the one thing that decided it.
Add a line per mission with the rolled-up verdict.

Then say what to do next:

- On `app-broken`, name the step and the evidence. Do not fix it.
- On `spec-stale`, say what the mission would have to say instead. Do not edit
  the mission. Write the suggestion to `.uijudge/findings/`.
- On `unclear`, say what a person needs to look at.
- On any mission you marked `needs review`, say which document changed, and ask
  a person to read the mission again and set it back to `approved`. Tell them
  the two lines to edit, and print the new hash the tool gave you. A person who
  sets `# status:` back to `approved` and leaves `# grounded-in-hash:` at the
  old value gets the same `needs review` mark on the very next run, forever.

Never edit the application. Never edit a mission, except the one `# status:`
line named in RESOLVE. You rule. You do not repair.
