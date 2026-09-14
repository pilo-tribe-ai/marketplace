---
name: osaat:going-one-step-at-a-time
description: Execute any series of steps one at a time with explicit confirmation between each step. Use when the user mentions "one at a time", "one by one", "step-by-step", "review one by one", or wants to review and approve each step individually before proceeding.
---

# OSAAT (One Step At A Time)

Execute any series of steps one at a time with explicit confirmation between each step.

## Overview

This skill enables Claude to break down complex tasks into individual steps and execute them one at a time, waiting for user confirmation before proceeding to the next step. This approach provides maximum control and visibility over the execution process.

## When to Use

Use this skill when:
- You want explicit control over each step of a multi-step process
- You need to review the outcome of each step before proceeding
- You're performing critical operations that require careful oversight
- You want to learn or understand a process step-by-step
- You need to make decisions between steps based on intermediate results

## How It Works

1. Claude breaks down the task into discrete, atomic steps
2. Presents the first step and asks for confirmation
3. Executes the step after receiving confirmation
4. Shows the result and presents the next step
5. Repeats until all steps are complete

## Examples

Example invocation:
- "Execute these steps one at a time: [task description]"
- "Walk me through this process step-by-step with confirmation"
- "One step at a time: [task description]"

## Features

- **Explicit Confirmation**: Each step requires user approval before execution
- **Visibility**: Clear presentation of what each step will do
- **Control**: Ability to stop, modify, or skip steps
- **Learning**: Understand complex processes by seeing them broken down

## Core Directives

- Always present a summary of the step
- Always use ask user question tool when asking the user
