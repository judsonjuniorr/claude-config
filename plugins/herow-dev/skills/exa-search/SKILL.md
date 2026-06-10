---
name: exa-search
description: (herow) Reference for the Exa MCP tools (web_search_exa, web_fetch_exa) — parameters and query patterns. Use for quick web/code lookups via Exa. For multi-source cited reports, use the deep-research skill.
---

# Exa Search

> **Drift-prone skill.** Exa MCP tool names, parameters, and account limits can
> change. Confirm the exposed tool surface and current Exa docs before relying
> on a specific search mode, category, or livecrawl behavior.

Neural search for web content, code, companies, and people via the Exa MCP server.

## When to Activate

- User needs current web information or news
- Searching for code examples, API docs, or technical references
- Researching companies, competitors, or market players
- Finding professional profiles or people in a domain
- Running background research for any development task
- User says "search for", "look up", "find", or "what's the latest on"

## MCP Requirement

Exa MCP server must be configured. Add to `~/.claude.json`:

```json
"exa-web-search": {
  "command": "npx",
  "args": ["-y", "exa-mcp-server"],
  "env": { "EXA_API_KEY": "YOUR_EXA_API_KEY_HERE" }
}
```

Get an API key at [exa.ai](https://exa.ai).
This repo's current Exa setup documents the tool surface exposed here: `web_search_exa` and `web_fetch_exa`.
If your Exa server exposes additional tools (e.g. `get_code_context_exa`), verify their exact names before depending on them in docs or prompts.

## Core Tools

### web_search_exa
General web search for current information, news, or facts.

```
web_search_exa(query: "latest AI developments 2026", numResults: 5)
```

**Parameters:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `query` | string | required | Search query |
| `numResults` | number | 8 | Number of results |
| `type` | string | `auto` | Search mode |
| `livecrawl` | string | `fallback` | Prefer live crawling when needed |
| `category` | string | none | Optional focus such as `company` or `research paper` |

### web_fetch_exa
Read a URL's full content as clean markdown — use after `web_search_exa` when highlights
aren't enough, including GitHub, Stack Overflow, and docs pages for code and API detail.

```
web_fetch_exa(urls: ["https://docs.python.org/3/library/asyncio.html"], maxCharacters: 3000)
```

**Parameters:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `urls` | string[] | required | URLs to read; batch multiple in one call |
| `maxCharacters` | number | 3000 | Max characters extracted per page |

## Usage Patterns

### Quick Lookup
```
web_search_exa(query: "Node.js 22 new features", numResults: 3)
```

### Code Research
```
web_search_exa(query: "Rust error handling patterns with the Result type", numResults: 5)
web_fetch_exa(urls: ["<best result URL>"], maxCharacters: 3000)
```

### Company or People Research
```
web_search_exa(query: "Vercel funding valuation 2026", numResults: 3, category: "company")
web_search_exa(query: "site:linkedin.com/in AI safety researchers Anthropic", numResults: 5)
```

### Technical Deep Dive
```
web_search_exa(query: "WebAssembly component model status and adoption", numResults: 5)
web_fetch_exa(urls: ["<best result URL>"], maxCharacters: 4000)
```

## Tips

- Use `web_search_exa` for current information, company lookups, and broad discovery
- Use search operators like `site:`, quoted phrases, and `intitle:` to narrow results
- Lower `maxCharacters` (1000-2000) for focused snippets, higher (5000+) for comprehensive context
- Use `web_fetch_exa` on the best result URLs when you need full page content — API usage, code examples, or docs — rather than search highlights

## Related Skills

- `deep-research` — Full multi-source research workflow with cited reports (uses these Exa tools)
