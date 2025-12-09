# claude-session-manager-mcp

MCP server for managing Claude Code conversation sessions with GUI support.

Manage your Claude Code conversation history (`~/.claude/projects`) through MCP tools or a web-based GUI interface.

## Features

- 📋 **Session Management**: List, rename, and delete conversation sessions
- 🗑️ **Smart Cleanup**: Automatically identify and clean empty or invalid sessions
- 🌐 **Web GUI**: Beautiful web interface for browsing conversation history
- 🔧 **MCP Integration**: Full MCP protocol support for Claude Code
- 🚀 **Easy Install**: One-line installation with `uvx`

## Install

```bash
# Using uvx (recommended)
uvx claude-session-manager-mcp

# Or install globally
uv tool install claude-session-manager-mcp

# Web GUI
uvx --from claude-session-manager-mcp claude-session-manager-web
```

## Usage

### Claude Code MCP Integration

Add to Claude Code:

```bash
claude mcp add claude-session-manager -- uvx claude-session-manager-mcp
```

Or manually edit `~/.claude.json`:

```json
{
  "mcpServers": {
    "claude-session-manager": {
      "command": "uvx",
      "args": ["claude-session-manager-mcp"]
    }
  }
}
```

### Web GUI

Launch the web interface:

```bash
# Direct launch
uvx --from claude-session-manager-mcp claude-session-manager-web

# Or via MCP tool (from Claude Code)
> Use the start_gui tool to launch web interface
```

The GUI will open at `http://localhost:5050` with features:
- Browse all projects and sessions
- Search conversations
- View full conversation history
- Rename sessions with inline editing
- Delete unwanted sessions
- Bulk cleanup of empty sessions

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List all Claude Code projects with session counts |
| `list_sessions` | List all sessions in a specific project |
| `rename_session` | Add descriptive title prefix to session |
| `delete_session` | Delete session (safely backed up to .bak) |
| `preview_cleanup` | Preview sessions that can be cleaned |
| `clear_sessions` | Delete empty and invalid API key sessions |
| `start_gui` | Launch web GUI and open in browser |
| `stop_gui` | Stop the web GUI server |

## Examples

### Via Claude Code

```
List all projects:
> @claude-session-manager list_projects

List sessions in a project:
> @claude-session-manager list_sessions project_name="-Users-young-works-myproject"

Rename a session:
> @claude-session-manager rename_session project_name="..." session_id="abc123" new_title="Fix authentication bug"

Launch web GUI:
> @claude-session-manager start_gui
```

### Via CLI

```bash
# Run MCP server (stdio mode)
uvx claude-session-manager-mcp

# Launch web GUI
uvx --from claude-session-manager-mcp claude-session-manager-web
```

## Project Structure

```
~/.claude/projects/
├── -Users-young-works-project1/
│   ├── session1.jsonl
│   ├── session2.jsonl
│   └── agent-xxx.jsonl
├── -Users-young-works-project2/
└── .bak/                    # Deleted sessions backup
    └── project_session.jsonl
```

## Development

```bash
# Clone repository
git clone https://github.com/es6kr/claude-session-manager-mcp.git
cd claude-session-manager-mcp

# Install dependencies
uv sync

# Run MCP server locally
uv run claude-session-manager-mcp

# Run web GUI locally
uv run claude-session-manager-web

# Run from project directory (development mode)
uv run --directory /path/to/claude-session-manager-mcp claude-session-manager-mcp
```

## How It Works

1. **Session Detection**: Scans `~/.claude/projects/` for `.jsonl` files
2. **Smart Parsing**: Extracts titles from first user message, removing IDE context tags
3. **Safe Deletion**: Moves deleted sessions to `.bak` folder for recovery
4. **Cleanup Logic**: Identifies empty sessions and invalid API key errors
5. **Web Server**: Flask-based GUI with RESTful API

## Requirements

- Python 3.10+
- Claude Code (for MCP integration)
- Modern web browser (for GUI)

## Contributing

Issues and pull requests are welcome at [github.com/es6kr/claude-session-manager-mcp](https://github.com/es6kr/claude-session-manager-mcp)

## License

MIT
