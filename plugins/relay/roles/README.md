# Relay Roles

**22 roles** dispatched through `relay:leaf-worker` (writers) or `relay:leaf-reader` (readers).

## The 22 roles

| slug | role-class | consuming skills |
|------|-----------|-----------------|
| doc-reference-reviewer | reader | refining-prs |
| fix-coder | writer | refining-prs, refining |
| fix-planner | writer | refining |
| implementer | writer | dispatching-acpx-agents |
| navigator | writer | refining-ui |
| panel-member | writer | panel |
| panel-moderator | writer | panel |
| panel-synthesizer | writer | panel |
| plan-fixer | writer | refining-plans |
| plan-simulator | reader | refining-plans |
| plan-writer | writer | dispatching-acpx-agents |
| scenario-writer | writer | refining |
| server-runner | reader | running-web-apps, refining-prs |
| spec-fixer | writer | refining-specs |
| spec-reviewer | reader | refining-specs |
| spec-simulator | reader | refining-specs |
| test-writer | writer | dispatching-acpx-agents |
| ui-accessibility-evaluator | reader | refining-ui |
| ui-code-evaluator | reader | refining-ui |
| ui-generator | writer | refining-ui |
| ui-ux-evaluator | reader | refining-ui |
| ui-visual-evaluator | reader | refining-ui |

## Binding parameters

`one_shot`, `max_turns`, `model`, `verify_artifact` (where applicable) live in
`bindings/presets.yaml` for each role. Dispatch parameters (`mechanism`, `modalities`,
`delegate_eligible`) also live there.

## Role resolution order (§5)

`RELAY_ROLE_PATH` override → `roles/<slug>.md` → `agents/<slug>.md` (kept agents only);
typed error `ROLE_FILE_MISSING` otherwise.

## agentType derivation

| role-class | agentType |
|-----------|-----------|
| `writer` | `relay:leaf-worker` |
| `reader` | `relay:leaf-reader` |
| `registered` (binding field) | use explicit `agentType` from binding |

## Role file format

Role files use `role-version`, `description`, `role-class`, `input-slots`,
`output-tokens`, `terminal_token`, and `requires` frontmatter keys. They must NOT
contain `name:`, `tools:`, or `model:` (those are agent/binding concerns, not role concerns).

The `verify_artifact` key is present only on the four roles that declare it:
`implementer`, `test-writer`, `fix-coder`, `plan-writer`.
