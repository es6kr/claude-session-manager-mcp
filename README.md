# claude-session-manager-mcp

MCP server for managing Claude Code (`~/.claude/projects`) conversation sessions.

## Install

```bash
# Using uv (recommended)
uvx claude-session-manager-mcp

# Or install globally
uv tool install claude-session-manager-mcp
```

## Usage

### Claude Code

```bash
claude mcp add claude-session-manager-mcp -- uvx claude-session-manager-mcp
```

### Manual MCP config

```json
{
  "mcpServers": {
    "claude-session-manager-mcp": {
      "command": "uvx",
      "args": ["claude-session-manager-mcp"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List all Claude Code projects |
| `list_sessions` | List sessions in a project |
| `rename_session` | Add title prefix to session |
| `delete_session` | Delete session (backup to .bak) |
| `preview_cleanup` | Preview cleanable sessions |
| `clear_sessions` | Delete empty/invalid sessions |

## Examples

```
[list_projects]
> Shows all projects with session counts

[list_sessions] project_name="-Users-young-works-myproject"
> Lists all sessions in the project

[rename_session] project_name="..." session_id="abc123" new_title="Fix auth bug"
> Adds "Fix auth bug\n\n" prefix to first message

[delete_session] project_name="..." session_id="abc123"
> Moves session to ~/.claude/projects/.bak/

[preview_cleanup]
> Shows empty sessions and invalid API key sessions

[clear_sessions]
> Deletes all empty and invalid sessions
```

## Development

```bash
git clone https://github.com/user/claude-session-manager-mcp
cd claude-session-manager-mcp

# Install with uv
uv sync

# Run locally
uv run claude-session-manager-mcp
```

## License

MIT
