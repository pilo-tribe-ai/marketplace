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

   Writing a skill? Run `/writing-skills` first — this repo's
   [authoring guide](./.claude/skills/writing-skills/SKILL.md) covers the quality bar
   and repo conventions.

2. Add an entry to the `plugins` array in `.claude-plugin/marketplace.json`:

   ```json
   {
     "name": "<plugin-name>",
     "source": "./plugins/<plugin-name>"
   }
   ```

   Only `name` and `source` are required here. `plugin.json` is the authority for
   `description` and `version` — don't duplicate them in this entry, since a stale
   copy loses silently.

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
