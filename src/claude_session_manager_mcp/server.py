"""MCP server for Claude Code session management."""
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

# Global variable to track web server process
_web_server_process: subprocess.Popen | None = None

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
    """Delete a session (move to .bak folder, or delete if empty)."""
    base_path = get_base_path()
    project_path = base_path / project_name
    jsonl_file = project_path / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        return False

    # If file is empty (0 bytes), just delete it without backing up
    if jsonl_file.stat().st_size == 0:
        jsonl_file.unlink()
        return True

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


def delete_message(project_name: str, session_id: str, message_uuid: str) -> bool:
    """Delete a message from session and repair parentUuid chain."""
    base_path = get_base_path()
    project_path = base_path / project_name
    jsonl_file = project_path / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        return False

    lines = []
    deleted_uuid = None
    parent_of_deleted = None

    try:
        # Read all lines and find the message to delete
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped:
                    lines.append(line)
                    continue

                try:
                    entry = json.loads(line_stripped)
                    entry_uuid = entry.get('uuid')

                    # Found the message to delete
                    if entry_uuid == message_uuid:
                        deleted_uuid = entry_uuid
                        parent_of_deleted = entry.get('parentUuid')
                        # Skip this line (don't add to lines)
                        continue

                    lines.append(line)
                except json.JSONDecodeError:
                    lines.append(line)

        if deleted_uuid is None:
            return False

        # Repair parentUuid chain: find child of deleted message and update its parentUuid
        repaired_lines = []
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                repaired_lines.append(line)
                continue

            try:
                entry = json.loads(line_stripped)

                # If this message's parent is the deleted message, update to deleted's parent
                if entry.get('parentUuid') == deleted_uuid:
                    entry['parentUuid'] = parent_of_deleted
                    repaired_lines.append(json.dumps(entry, ensure_ascii=False) + '\n')
                else:
                    repaired_lines.append(line)
            except json.JSONDecodeError:
                repaired_lines.append(line)

        # Write back to file
        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.writelines(repaired_lines)

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
                        else:
                            # Summary가 있다는 것은 요약된 메시지가 있다는 의미
                            status['is_empty'] = False
                            status['has_messages'] = True

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


def start_web_gui(port: int = 5050, open_browser: bool = True) -> dict:
    """Start the web GUI server."""
    global _web_server_process

    # Check if already running
    if _web_server_process is not None and _web_server_process.poll() is None:
        url = f"http://localhost:{port}"
        if open_browser:
            webbrowser.open(url)
        return {
            "success": True,
            "message": "Web GUI is already running",
            "url": url,
            "pid": _web_server_process.pid
        }

    try:
        # Get the package directory
        package_dir = Path(__file__).parent.parent.parent

        # Start Flask server as subprocess
        _web_server_process = subprocess.Popen(
            [sys.executable, "-m", "claude_session_manager_mcp.web"],
            cwd=str(package_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )

        # Wait briefly to check if it started successfully
        import time
        time.sleep(1)

        if _web_server_process.poll() is not None:
            # Process ended, get error
            _, stderr = _web_server_process.communicate()
            return {
                "success": False,
                "message": f"Failed to start web GUI: {stderr.decode()}"
            }

        url = f"http://localhost:{port}"
        if open_browser:
            webbrowser.open(url)

        return {
            "success": True,
            "message": "Web GUI started successfully",
            "url": url,
            "pid": _web_server_process.pid
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to start web GUI: {str(e)}"
        }


def stop_web_gui() -> dict:
    """Stop the web GUI server."""
    global _web_server_process

    if _web_server_process is None or _web_server_process.poll() is not None:
        _web_server_process = None
        return {
            "success": True,
            "message": "Web GUI is not running"
        }

    try:
        _web_server_process.terminate()
        _web_server_process.wait(timeout=5)
        _web_server_process = None
        return {
            "success": True,
            "message": "Web GUI stopped successfully"
        }
    except subprocess.TimeoutExpired:
        _web_server_process.kill()
        _web_server_process = None
        return {
            "success": True,
            "message": "Web GUI forcefully stopped"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to stop web GUI: {str(e)}"
        }


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
            name="delete_message",
            description="Delete a message from a session and repair the parentUuid chain",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project folder name"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "message_uuid": {
                        "type": "string",
                        "description": "UUID of the message to delete"
                    }
                },
                "required": ["project_name", "session_id", "message_uuid"]
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
        ),
        Tool(
            name="start_gui",
            description="Start the web GUI for session management and open it in browser",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {
                        "type": "integer",
                        "description": "Port to run the web server on (default: 5050)"
                    },
                    "open_browser": {
                        "type": "boolean",
                        "description": "Whether to open browser automatically (default: true)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="stop_gui",
            description="Stop the web GUI server",
            inputSchema={
                "type": "object",
                "properties": {},
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

    elif name == "delete_message":
        project_name = arguments.get("project_name", "")
        session_id = arguments.get("session_id", "")
        message_uuid = arguments.get("message_uuid", "")
        success = delete_message(project_name, session_id, message_uuid)
        result = {"success": success, "message": "Message deleted and chain repaired" if success else "Failed to delete message"}

    elif name == "preview_cleanup":
        project_name = arguments.get("project_name")
        result = find_cleanable_sessions(project_name)

    elif name == "clear_sessions":
        project_name = arguments.get("project_name")
        clear_empty = arguments.get("clear_empty", True)
        clear_invalid = arguments.get("clear_invalid", True)
        result = clear_sessions(project_name, clear_empty, clear_invalid)

    elif name == "start_gui":
        port = arguments.get("port", 5050)
        open_browser = arguments.get("open_browser", True)
        result = start_web_gui(port, open_browser)

    elif name == "stop_gui":
        result = stop_web_gui()

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
