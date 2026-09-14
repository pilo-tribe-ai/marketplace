---
description: "Read the project documents and the code, ask you to confirm, and write missions as high-level Gherkin. Missions are the ground truth the judge rules against."
argument-hint: "[area-name] [--from <path>]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Skill
---

# /ui-judge:missions

Write the missions that say what this application must do.

## Usage

```
/ui-judge:missions                        every area you can find
/ui-judge:missions checkout               one area
/ui-judge:missions --from docs/guide.md   from one document only
```

## What it does

1. It reads your documents and your code.
2. It groups the behaviour into areas a person would name.
3. It asks you to confirm each area before it writes anything.
4. It writes one `.feature` file per area, in plain English.
5. It records which document each mission came from, and the hash of that
   document.
6. It checks that no mission names a web address or a selector.

Every mission is written as a draft. Nothing is judged until you read it and
mark it `approved`.

## Before you run it

`/ui-judge:setup` must have run.

## Process

Invoke `Skill('ui-judge:writing-missions')` with the parsed argument.

## Output

Mission files in `.uijudge/missions/`, and a list of what was written and
where each part came from.
