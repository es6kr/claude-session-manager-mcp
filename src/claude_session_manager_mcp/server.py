"""MCP server for Claude Code session management."""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

mcp = Server("claude-session-manager")


def get_base_path() -> Path:
    """Get base path for Claude projects."""
    return Path(os.path.expanduser("~/.claude/projects"))


def get_projects() -> list[dict]:
    """Get all projects."""
    base_path = get_base_path()
    projects = []

    if not base_path.exists():
        return projects

    for project_dir in base_path.iterdir():
        if project_dir.is_dir() and not project_dir.name.startswith('.'):
            # Count sessions
            session_count = len(list(project_dir.glob("*.jsonl")))
            projects.append({
                "name": project_dir.name,
                "display_name": format_project_name(project_dir.name),
                "session_count": session_count
            })

    return sorted(projects, key=lambda p: p["name"])


def format_project_name(name: str) -> str:
    """Format project name for display."""
    if name.startswith('-'):
        name = name[1:]
    name = name.replace('--', '/.')
    parts = name.split('-')
    if len(parts) > 1:
        last = parts[-1]
        if last in ('com', 'org', 'net', 'io', 'dev', 'md', 'txt', 'py', 'js', 'ts'):
            parts[-2] = parts[-2] + '.' + last
            parts = parts[:-1]
    name = '/' + '/'.join(parts)
    if name.startswith('/Users/young'):
        name = '~' + name[len('/Users/young'):]
    return name


def get_sessions(project_name: str) -> list[dict]:
    """Get all sessions for a project."""
    base_path = get_base_path()
    project_path = base_path / project_name
    sessions = []

    if not project_path.exists():
        return sessions

    for jsonl_file in project_path.glob("*.jsonl"):
        if jsonl_file.name.startswith("agent-"):
            continue

        session_info = parse_session_summary(jsonl_file)
        if session_info:
            sessions.append(session_info)

    return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)


def parse_session_summary(file_path: Path) -> dict | None:
    """Parse session file for summary info."""
    session_id = file_path.stem
    info = {
        "session_id": session_id,
        "title": f"Session {session_id[:8]}",
        "message_count": 0,
        "created_at": None,
        "updated_at": None,
    }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_user_content = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_type = entry.get('type')

                    if entry_type in ('user', 'assistant'):
                        info["message_count"] += 1
                        timestamp = entry.get('timestamp', '')
                        if timestamp:
                            if not info["created_at"] or timestamp < info["created_at"]:
                                info["created_at"] = timestamp
                            if not info["updated_at"] or timestamp > info["updated_at"]:
                                info["updated_at"] = timestamp

                        if entry_type == 'user' and first_user_content is None:
                            message = entry.get('message', {})
                            content_list = message.get('content', [])
                            for item in content_list:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    text = item.get('text', '').strip()
                                    text = re.sub(r'<ide_[^>]*>.*?</ide_[^>]*>', '', text, flags=re.DOTALL).strip()
                                    if text:
                                        first_user_content = text
                                        break
                except json.JSONDecodeError:
                    continue

            if first_user_content:
                if '\n\n' in first_user_content:
                    info["title"] = first_user_content.split('\n\n')[0][:100]
                elif '\n' in first_user_content:
                    info["title"] = first_user_content.split('\n')[0][:100]
                else:
                    info["title"] = first_user_content[:100]

    except Exception:
        return None

    return info if info["message_count"] > 0 else None


def delete_session(project_name: str, session_id: str) -> bool:
    """Delete a session (move to .bak folder)."""
    base_path = get_base_path()
    project_path = base_path / project_name
    jsonl_file = project_path / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        return False

    backup_dir = base_path / ".bak"
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f"{project_name}_{session_id}.jsonl"
    jsonl_file.rename(backup_file)
    return True


def rename_session(project_name: str, session_id: str, new_title: str) -> bool:
    """Rename a session by adding title prefix to first message."""
    base_path = get_base_path()
    project_path = base_path / project_name
    jsonl_file = project_path / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        return False

    lines = []
    first_user_idx = -1
    original_message = None

    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                lines.append(line)
                line_stripped = line.strip()
                if line_stripped:
                    try:
                        entry = json.loads(line_stripped)
                        entry_type = entry.get('type')

                        if entry_type == 'queue-operation' and original_message is None:
                            if entry.get('operation') == 'enqueue':
                                content_arr = entry.get('content', [])
                                for item in content_arr:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        txt = item.get('text', '')
                                        if txt and not txt.strip().startswith('<ide_'):
                                            original_message = txt
                                            break

                        if entry_type == 'user' and first_user_idx == -1:
                            first_user_idx = i

                    except json.JSONDecodeError:
                        pass

        if first_user_idx == -1:
            return False

        entry = json.loads(lines[first_user_idx].strip())
        message = entry.get('message', {})
        content_list = message.get('content', [])

        if original_message is not None:
            text_idx = -1
            for idx, item in enumerate(content_list):
                if isinstance(item, dict) and item.get('type') == 'text':
                    text_content = item.get('text', '')
                    if text_content.strip().startswith('<ide_'):
                        continue
                    text_idx = idx
                    break

            if text_idx >= 0:
                content_list[text_idx]['text'] = f"{new_title}\n\n{original_message}"
            else:
                insert_pos = 0
                for idx, item in enumerate(content_list):
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text_content = item.get('text', '')
                        if text_content.strip().startswith('<ide_'):
                            insert_pos = idx + 1
                content_list.insert(insert_pos, {'type': 'text', 'text': f"{new_title}\n\n{original_message}"})
        else:
            for item in content_list:
                if isinstance(item, dict) and item.get('type') == 'text':
                    old_text = item.get('text', '')
                    old_text = re.sub(r'^[^\n]+\n\n', '', old_text)
                    item['text'] = f"{new_title}\n\n{old_text}"
                    break

        entry['message']['content'] = content_list
        lines[first_user_idx] = json.dumps(entry, ensure_ascii=False) + '\n'

        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return True

    except Exception:
        return False


def check_session_status(file_path: Path) -> dict:
    """Check session file status."""
    status = {
        'is_empty': True,
        'has_invalid_api_key': False,
        'has_messages': False,
        'file_size': file_path.stat().st_size if file_path.exists() else 0
    }

    if not file_path.exists() or status['file_size'] == 0:
        return status

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_type = entry.get('type')

                    if entry_type == 'summary':
                        summary = entry.get('summary', '')
                        if 'Invalid API key' in summary:
                            status['has_invalid_api_key'] = True

                    if entry_type in ('user', 'assistant'):
                        status['is_empty'] = False
                        status['has_messages'] = True

                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return status


def find_cleanable_sessions(project_name: str | None = None) -> dict:
    """Find sessions that can be cleaned."""
    base_path = get_base_path()
    result = {
        'empty_sessions': [],
        'invalid_api_key_sessions': [],
        'total_count': 0
    }

    if project_name:
        project_dirs = [base_path / project_name]
    else:
        project_dirs = [d for d in base_path.iterdir() if d.is_dir() and not d.name.startswith('.')]

    for project_path in project_dirs:
        if not project_path.exists():
            continue

        for jsonl_file in project_path.glob("*.jsonl"):
            if jsonl_file.name.startswith("agent-"):
                continue

            session_id = jsonl_file.stem
            status = check_session_status(jsonl_file)

            session_info = {
                'project_name': project_path.name,
                'session_id': session_id,
                'file_size': status['file_size']
            }

            if status['has_invalid_api_key'] and not status['has_messages']:
                result['invalid_api_key_sessions'].append(session_info)
            elif status['is_empty'] or status['file_size'] == 0:
                result['empty_sessions'].append(session_info)

    result['total_count'] = len(result['empty_sessions']) + len(result['invalid_api_key_sessions'])
    return result


def clear_sessions(project_name: str | None = None, clear_empty: bool = True, clear_invalid: bool = True) -> dict:
    """Clear empty and invalid sessions."""
    cleanable = find_cleanable_sessions(project_name)
    deleted = {
        'empty_sessions': [],
        'invalid_api_key_sessions': [],
        'total_deleted': 0,
        'errors': []
    }

    sessions_to_delete = []

    if clear_empty:
        sessions_to_delete.extend([(s, 'empty') for s in cleanable['empty_sessions']])
    if clear_invalid:
        sessions_to_delete.extend([(s, 'invalid_api_key') for s in cleanable['invalid_api_key_sessions']])

    for session_info, reason in sessions_to_delete:
        try:
            success = delete_session(session_info['project_name'], session_info['session_id'])
            if success:
                if reason == 'empty':
                    deleted['empty_sessions'].append(session_info)
                else:
                    deleted['invalid_api_key_sessions'].append(session_info)
                deleted['total_deleted'] += 1
        except Exception as e:
            deleted['errors'].append({
                'session': session_info,
                'error': str(e)
            })

    return deleted


# MCP Tool definitions
@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_projects",
            description="List all Claude Code projects with session counts",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="list_sessions",
            description="List all sessions in a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project folder name (e.g., '-Users-young-works-myproject')"
                    }
                },
                "required": ["project_name"]
            }
        ),
        Tool(
            name="rename_session",
            description="Rename a session by adding a title prefix to the first message",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project folder name"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (filename without .jsonl)"
                    },
                    "new_title": {
                        "type": "string",
                        "description": "New title to add as prefix"
                    }
                },
                "required": ["project_name", "session_id", "new_title"]
            }
        ),
        Tool(
            name="delete_session",
            description="Delete a session (moves to .bak folder for recovery)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project folder name"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to delete"
                    }
                },
                "required": ["project_name", "session_id"]
            }
        ),
        Tool(
            name="preview_cleanup",
            description="Preview sessions that would be cleaned (empty and invalid API key sessions)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Optional: filter by project name"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="clear_sessions",
            description="Delete all empty sessions and invalid API key sessions",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Optional: filter by project name"
                    },
                    "clear_empty": {
                        "type": "boolean",
                        "description": "Clear empty sessions (default: true)"
                    },
                    "clear_invalid": {
                        "type": "boolean",
                        "description": "Clear invalid API key sessions (default: true)"
                    }
                },
                "required": []
            }
        )
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    result: Any = None

    if name == "list_projects":
        result = get_projects()

    elif name == "list_sessions":
        project_name = arguments.get("project_name", "")
        result = get_sessions(project_name)

    elif name == "rename_session":
        project_name = arguments.get("project_name", "")
        session_id = arguments.get("session_id", "")
        new_title = arguments.get("new_title", "")
        success = rename_session(project_name, session_id, new_title)
        result = {"success": success, "message": "Session renamed" if success else "Failed to rename session"}

    elif name == "delete_session":
        project_name = arguments.get("project_name", "")
        session_id = arguments.get("session_id", "")
        success = delete_session(project_name, session_id)
        result = {"success": success, "message": "Session deleted (backed up to .bak)" if success else "Failed to delete session"}

    elif name == "preview_cleanup":
        project_name = arguments.get("project_name")
        result = find_cleanable_sessions(project_name)

    elif name == "clear_sessions":
        project_name = arguments.get("project_name")
        clear_empty = arguments.get("clear_empty", True)
        clear_invalid = arguments.get("clear_invalid", True)
        result = clear_sessions(project_name, clear_empty, clear_invalid)

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def run_server():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


def main():
    """Main entry point."""
    import asyncio
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
