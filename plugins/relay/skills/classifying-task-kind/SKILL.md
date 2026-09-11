---
name: classifying-task-kind
description: Use as the first node of any L3 relay command to classify the user's request into exactly one closed-enum task kind from context.
user-invocable: false
---

# classifying-task-kind

Classify the request into exactly one member of the closed enum, then hand the typed result to the command's policy-selection node.

## Closed enum

The kind is exactly one of: `feature` · `script` · `config-artifact` · `bugfix` · `docs`. There is no open-ended kind; extending the set is a PR against this skill and the language-reference doc, not a runtime inference (DSL design §4.1).

## Steps

1. **Classify from context.** Map the request to exactly one member by its dominant outcome: new behavior ⇒ `feature`; a one-off runnable ⇒ `script`; a generated config/manifest ⇒ `config-artifact`; a defect fix ⇒ `bugfix`; prose/reference ⇒ `docs`. The kind is always inferred — there is no user-facing override flag.
2. **Emit the typed result.** Return a single `typed-output` object `{ kind: "<member>" }` consumed by the policy-selection node.
3. **Surface to the user.** Report the inferred kind before workflow generation proceeds.

Calm imperatives only.
