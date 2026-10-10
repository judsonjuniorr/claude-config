## Model choice for new components

When asked to create a new command, skill or agent in `~/.claude/` or a project's `.claude/` (not a
herow plugin dir), suggest a `model:` before writing the file: `haiku` for mechanical/lookup work,
`sonnet` for scoped implementation or review, `opus` for architecture or high-stakes reasoning. Ask
via `AskUserQuestion` with the suggestion as "(Recommended)" plus "Leave empty (inherit session model)".
For a command or skill, say in the recommended option's description that `model:` switches the main
conversation's model for that turn, so the session's prompt cache likely won't carry over.

Empty means omit the `model:` key entirely — never `model: ""`. Editing an existing component doesn't
trigger this unless the user asks.
