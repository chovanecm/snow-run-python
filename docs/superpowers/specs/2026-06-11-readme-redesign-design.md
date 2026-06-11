---
name: readme-redesign
description: README redesign and GitHub repo rename to snow-cli — two-hero layout targeting ServiceNow developers, admins, and AI/LLM users
metadata:
  type: project
---

# README Redesign & Repo Rename: snow-cli

## Context

The project is a cross-platform ServiceNow CLI + MCP server. The current README has solid technical depth but does not market to new users effectively: the hero buries the two key differentiators (AI integration and CLI scripting breadth), several sections are aimed at project history (Bash migration), and a TODO list signals incompleteness. The goal is to attract three target personas: ServiceNow developers, admins/platform engineers, and AI/LLM users.

## Decisions

- **Approach**: "Two Heroes" — co-equal hero blocks for AI integration and CLI scripting/querying
- **Lead hook**: MCP/AI integration + full CLI toolkit (both highlighted)
- **Repo rename**: `snow-cli` → `snow-cli` (matches the pyproject.toml name and `snow` command; no trademark risk)
- **Credibility**: Real-world use cases + rich terminal output examples
- **Removals**: TODO section, "Advantages over Bash", "Migration from Bash", "Next Generation" history section

## README Structure

### 1. Title, badges, tagline

Title: `snow-cli`

Badges: Python version, platform.

Tagline: A cross-platform CLI and MCP server for ServiceNow — run background scripts, query tables, inspect schemas, and connect AI assistants to your instances.

### 2. Two-hero section

**Hero A — AI assistant integration**

Pitch: Add `snow mcp` to Claude Desktop or GitHub Copilot and your AI assistant can query incidents, count records, run scripts, and inspect table schemas — with human-confirmation prompts for destructive operations.

Show: Claude Desktop config JSON + prose example of what you can ask.

**Hero B — Terminal scripting & querying**

Pitch: Run background scripts from file or stdin, query any table, aggregate data — on macOS, Linux, and Windows, no Bash required.

Show: `snow run` with output, `snow record search` with formatted table output.

### 3. Use Cases (new section)

Four scenario blocks, one per persona, each with a terminal example:

- **Developer**: `cat deploy.js | snow run --auto-login`
- **Admin/Platform Engineer**: `snow table fields incident -F excel -O incident_fields.xlsx`
- **AI user**: Ask Claude to group incidents by priority; it calls `snow_record_aggregate`
- **Multi-instance**: `snow add --default dev1234 && snow use test5678 && snow list`

### 4. Quickstart (reordered)

Lead with `uv tool install` (fastest path). Other install methods (pipx, pip, dev clone) in a `<details>` block.

Warning admonition here (shortened): `> ⚠️ Do not run this against a production instance.`

### 5. MCP Server Mode (promoted before Record Queries)

Keep existing content. Move above the Record Queries sections.

### 6. Commands reference

Keep existing content. Reorder: MCP tools table first, then other commands.

### 7. Record Queries, Table Schema, Configuration, Multi-Instance, Troubleshooting, Development

Keep existing content, minor reordering only.

### Removed sections

- `## TODO` — signals incompleteness
- `## Next Generation` — project history irrelevant to new users
- `## Advantages over Bash version` — irrelevant to new users
- `## Migration from Bash` — irrelevant to new users
- `## Warning` (current verbose version) — replaced by one-line admonition

## Repo Rename Steps

1. Rename GitHub repo from `snow-cli` to `snow-cli` in GitHub repository settings
2. Update all `chovanecm/snow-cli` URLs in README.md to `chovanecm/snow-cli`
3. Update any references in docs/ and examples/ that point to the old repo URL

## Verification

- Read the final README as each of the three target personas — does each have an immediate "this is for me" moment in the first screen?
- Confirm all install URLs point to the renamed repo after the rename
- Confirm terminal output examples are realistic and accurately reflect command output format
