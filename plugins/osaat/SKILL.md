---
name: osaat:going-one-step-at-a-time
description: Execute any series of steps one at a time with explicit confirmation between each step. Use when the user mentions "one at a time", "one by one", "step-by-step", or wants to review and approve each step individually before proceeding.
---

# OSAAT (One Step At A Time)

Execute any series of steps one at a time with explicit confirmation between each step.

## When to Use

Invoke when:
- The user wants explicit control over each step of a multi-step process
- Critical operations require oversight before each execution
- The user says "one at a time", "step by step", "review each step", or similar

## How to Invoke

```
/osaat:going-one-step-at-a-time
```

## What It Does

Breaks a task into discrete atomic steps, presents each step to the user, waits for confirmation, executes, shows the result, and repeats until complete. The user can stop, modify, or skip any step.
