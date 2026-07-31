# experimental-plugins

A [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) for Tribe AI.

## Plugins

| Plugin | Description |
|---|---|
| [`ai-fluency`](./plugins/ai-fluency) | Skills operationalizing the AI Fluency framework (Delegation, Description, Discernment, Diligence) |

## Using this marketplace

```
/plugin marketplace add pilo-tribe-ai/marketplace
/plugin install <plugin-name>@experimental-plugins
```

## Adding a plugin

1. Create the plugin under `plugins/<plugin-name>/`, with a `.claude-plugin/plugin.json` manifest and any `skills/`, `agents/`, `commands/`, or `hooks/` it needs.

   Writing a skill? Run `/writing-skills` (or just ask Claude) — this repo ships a
   [`writing-skills`](./.claude/skills/writing-skills/SKILL.md) skill distilling Anthropic's
   official authoring guidance: frontmatter schema, how to write a `description` that
   actually triggers, progressive disclosure, and a pre-ship checklist.

2. Add an entry to the `plugins` array in `.claude-plugin/marketplace.json`:

   ```json
   {
     "name": "<plugin-name>",
     "source": "./plugins/<plugin-name>",
     "description": "..."
   }
   ```

3. Validate before pushing:

   ```
   claude plugin validate .
   ```

4. Test locally:

   ```
   /plugin marketplace add ./
   /plugin install <plugin-name>@experimental-plugins
   /reload-plugins
   ```

See the [plugin marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces) and [plugin docs](https://code.claude.com/docs/en/plugins) for full schema details.
