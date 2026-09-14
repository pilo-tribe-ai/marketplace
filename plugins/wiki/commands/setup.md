---
description: "Scaffold an OKF v0.2 knowledge wiki into this repository. Detects any prior wiki, infers the subject, repo, actors, and container, confirms once, writes the container skeleton and an empty five-type bundle, then verifies all four gates pass before declaring done."
argument-hint: "[container path]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, AskUserQuestion, Write, Edit
---

# /wiki:setup

This command provisions the wiki, so it must NOT gate on the wiki already existing -- running it
is how the wiki gets created (or adopted, if one already exists in another shape).

## Step 1 -- Invoke the scaffolding coordinator

Invoke the `wiki:scaffolding-okf-wikis` Skill. It runs the full 6-step setup flow:

1. Resolve the repository root; stop if this is not a git repository.
2. Detect any prior `.claude/wiki.json` or wiki-shaped container and offer adopt, re-scaffold,
   or fresh scaffold accordingly.
3. Infer the container, subject, repo name, human actor, agent actor, and today's date, each with
   a stated fallback.
4. Confirm every inferred value and the full file manifest with you, once.
5. Write the container skeleton and the empty five-type bundle.
6. Run `regen_indexes.py`, then all four gates plus a token-leak sweep, and report a receipt.
   Setup is done only when every gate is green.

Pass `$ARGUMENTS` through verbatim as a container-path hint. The skill owns all interaction from
here; this command holds no paths, no manifest, and no gate commands of its own.
