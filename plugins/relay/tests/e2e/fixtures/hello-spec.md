# Spec: greet(name)

## Goal

Add a single pure function `greet(name)` that returns the string
`Hello, <name>!` for any non-empty string `name`.

## Requirements

- `greet("World")` returns exactly `Hello, World!`.
- `greet(name)` interpolates `name` verbatim into the template `Hello, <name>!`.
- Implement in the project's primary language, in a new module/file appropriate
  to the repo's conventions.

## Tests

- One unit test asserting `greet("World") == "Hello, World!"`.
- The test must run under the project's existing test command and pass.

## Out of scope

- Input validation, localization, formatting options. Keep it minimal.

## Refinement Status

Refinement: not yet refined
