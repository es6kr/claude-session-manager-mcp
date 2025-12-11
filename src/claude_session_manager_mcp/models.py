"""Data models for Claude Code conversation history."""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    """Individual message."""
    uuid: str
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime
    model: Optional[str] = None
    parent_uuid: Optional[str] = None
    tool_use: Optional[dict] = None


@dataclass
class Session:
    """Conversation session."""
    session_id: str
    project_path: str
    messages: list[Message] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cwd: Optional[str] = None
    git_branch: Optional[str] = None
    version: Optional[str] = None

    @property
    def title(self) -> str:
        """Extract title from first user message (first line only)."""
        import re
        for msg in self.messages:
            if msg.role == 'user' and msg.content:
                content = msg.content.strip()
                # Remove IDE tags (<ide_opened_file>, <ide_selection>, etc.)
                content = re.sub(r'<ide_[^>]*>.*?</ide_[^>]*>', '', content, flags=re.DOTALL)
                content = content.strip()
                if not content:
                    continue
                # Use only content before \n\n or \n as title
                if '\n\n' in content:
                    title = content.split('\n\n')[0]
                elif '\n' in content:
                    title = content.split('\n')[0]
                else:
                    title = content
                # Limit to 100 characters
                if len(title) > 100:
                    title = title[:100] + "..."
                return title
        return f"Session {self.session_id[:8]}"

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass
class Project:
    """Project (folder)."""
    name: str
    path: str
    sessions: list[Session] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Display name (extracted from path)."""
        # -Users-young-works-willkomo-com -> ~/works/willkomo.com
        name = self.name
        if name.startswith('-'):
            name = name[1:]
        # Consecutive -- means hidden folder (e.g., --vscode -> /.vscode)
        name = name.replace('--', '/.')
        # Single - in last segment becomes . (e.g., willkomo-com -> willkomo.com)
        parts = name.split('-')
        if len(parts) > 1:
            # If last part looks like an extension, join with .
            last = parts[-1]
            if last in ('com', 'org', 'net', 'io', 'dev', 'md', 'txt', 'py', 'js', 'ts'):
                parts[-2] = parts[-2] + '.' + last
                parts = parts[:-1]
        name = '/' + '/'.join(parts)
        if name.startswith('/Users/young'):
            name = '~' + name[len('/Users/young'):]
        return name

    @property
    def session_count(self) -> int:
        return len(self.sessions)


class ClaudeHistoryParser:
    """Claude Code conversation history parser."""

    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = os.path.expanduser("~/.claude/projects")
        self.base_path = Path(base_path)

    def get_projects(self) -> list[Project]:
        """Return all projects list."""
        projects = []

        if not self.base_path.exists():
            return projects

        for project_dir in self.base_path.iterdir():
            if project_dir.is_dir() and not project_dir.name.startswith('.'):
                project = Project(
                    name=project_dir.name,
                    path=str(project_dir)
                )
                projects.append(project)

        return sorted(projects, key=lambda p: p.name)

    def get_sessions(self, project_name: str) -> list[Session]:
        """Return all sessions for a project."""
        project_path = self.base_path / project_name
        sessions = []

        if not project_path.exists():
            return sessions

        for jsonl_file in project_path.glob("*.jsonl"):
            # Exclude agent- files (subagent logs)
            if jsonl_file.name.startswith("agent-"):
                continue

            session = self._parse_session_file(jsonl_file, project_name)
            if session and session.messages:
                sessions.append(session)

        # Sort by newest first
        return sorted(sessions, key=lambda s: s.updated_at or datetime.min, reverse=True)

    def get_session(self, project_name: str, session_id: str) -> Optional[Session]:
        """Return specific session details."""
        project_path = self.base_path / project_name
        jsonl_file = project_path / f"{session_id}.jsonl"

        if not jsonl_file.exists():
            return None

        return self._parse_session_file(jsonl_file, project_name)

    def _parse_session_file(self, file_path: Path, project_name: str) -> Optional[Session]:
        """Parse JSONL file."""
        session_id = file_path.stem
        session = Session(
            session_id=session_id,
            project_path=project_name
        )

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        self._process_entry(entry, session)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None

        return session

    def _process_entry(self, entry: dict, session: Session):
        """Process JSONL entry."""
        entry_type = entry.get('type')

        if entry_type in ('user', 'assistant'):
            message = entry.get('message', {})
            content_list = message.get('content', [])

            # Extract content
            text_content = ""
            tool_use = None

            for item in content_list:
                if isinstance(item, dict):
                    if item.get('type') == 'text':
                        text_content += item.get('text', '')
                    elif item.get('type') == 'tool_use':
                        tool_use = {
                            'name': item.get('name'),
                            'input': item.get('input', {})
                        }
                elif isinstance(item, str):
                    text_content += item

            # Parse timestamp
            timestamp_str = entry.get('timestamp', '')
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()

            msg = Message(
                uuid=entry.get('uuid', ''),
                role=entry_type,
                content=text_content,
                timestamp=timestamp,
                model=message.get('model'),
                parent_uuid=entry.get('parentUuid'),
                tool_use=tool_use
            )

            session.messages.append(msg)

            # Update session metadata
            if session.created_at is None or timestamp < session.created_at:
                session.created_at = timestamp
            if session.updated_at is None or timestamp > session.updated_at:
                session.updated_at = timestamp

            if not session.cwd:
                session.cwd = entry.get('cwd')
            if not session.version:
                session.version = entry.get('version')
            if not session.git_branch:
                session.git_branch = entry.get('gitBranch')

    def search_sessions(self, query: str, project_name: str = None) -> list[Session]:
        """Search sessions."""
        results = []
        query_lower = query.lower()

        if project_name:
            projects = [Project(name=project_name, path=str(self.base_path / project_name))]
        else:
            projects = self.get_projects()

        for project in projects:
            sessions = self.get_sessions(project.name)
            for session in sessions:
                # Search in message content
                for msg in session.messages:
                    if query_lower in msg.content.lower():
                        results.append(session)
                        break

        return results

    def delete_session(self, project_name: str, session_id: str) -> bool:
        """Delete session (move file to .bak folder, or delete if empty)."""
        project_path = self.base_path / project_name
        jsonl_file = project_path / f"{session_id}.jsonl"

        if not jsonl_file.exists():
            return False

        # If file is empty (0 bytes), just delete it without backing up
        if jsonl_file.stat().st_size == 0:
            jsonl_file.unlink()
            return True

        # Move to .bak folder (format: project_name_session_id.jsonl)
        backup_dir = self.base_path / ".bak"
        backup_dir.mkdir(exist_ok=True)
        backup_file = backup_dir / f"{project_name}_{session_id}.jsonl"
        jsonl_file.rename(backup_file)
        return True

    def rename_session(self, project_name: str, session_id: str, new_title: str) -> bool:
        """Rename session (get original message from enqueue operation and add title)."""
        project_path = self.base_path / project_name
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

                            # Find original message from queue-operation (enqueue), skip <ide_ tags
                            if entry_type == 'queue-operation' and original_message is None:
                                if entry.get('operation') == 'enqueue':
                                    content_arr = entry.get('content', [])
                                    for item in content_arr:
                                        if isinstance(item, dict) and item.get('type') == 'text':
                                            txt = item.get('text', '')
                                            # Skip messages starting with <ide_
                                            if txt and not txt.strip().startswith('<ide_'):
                                                original_message = txt
                                                break

                            # Find first user message index
                            if entry_type == 'user' and first_user_idx == -1:
                                first_user_idx = i

                        except json.JSONDecodeError:
                            pass

            if first_user_idx == -1:
                return False

            # Modify first user message
            entry = json.loads(lines[first_user_idx].strip())
            message = entry.get('message', {})
            content_list = message.get('content', [])

            if original_message is not None:
                # Use original message from queue-operation
                # Skip content starting with <ide_, find first regular text
                text_idx = -1
                for idx, item in enumerate(content_list):
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text_content = item.get('text', '')
                        # Skip if starts with <ide_ tag
                        if text_content.strip().startswith('<ide_'):
                            continue
                        text_idx = idx
                        break

                if text_idx >= 0:
                    content_list[text_idx]['text'] = f"{new_title}\n\n{original_message}"
                else:
                    # If no regular text, insert after <ide_ tags
                    insert_pos = 0
                    for idx, item in enumerate(content_list):
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text_content = item.get('text', '')
                            if text_content.strip().startswith('<ide_'):
                                insert_pos = idx + 1
                    content_list.insert(insert_pos, {'type': 'text', 'text': f"{new_title}\n\n{original_message}"})
            else:
                # If no original message, use existing method: replace title only
                import re
                for item in content_list:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        old_text = item.get('text', '')
                        # Remove existing title pattern (first line ending with \n\n)
                        old_text = re.sub(r'^[^\n]+\n\n', '', old_text)
                        item['text'] = f"{new_title}\n\n{old_text}"
                        break

            entry['message']['content'] = content_list
            lines[first_user_idx] = json.dumps(entry, ensure_ascii=False) + '\n'

            # Write file back
            with open(jsonl_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return True

        except Exception as e:
            print(f"Error renaming session: {e}")
            return False

    def move_session(self, source_project: str, session_id: str, target_project: str) -> bool:
        """Move session to another project."""
        source_path = self.base_path / source_project
        target_path = self.base_path / target_project

        source_file = source_path / f"{session_id}.jsonl"
        target_file = target_path / f"{session_id}.jsonl"

        if not source_file.exists():
            print(f"Error moving session: Source file does not exist: {source_file}", flush=True)
            return False

        # Create target directory if it doesn't exist
        target_path.mkdir(parents=True, exist_ok=True)

        # If target file already exists, fail
        if target_file.exists():
            print(f"Error moving session: Target file already exists: {target_file}", flush=True)
            return False

        try:
            # Move file
            source_file.rename(target_file)
            print(f"Successfully moved session from {source_project} to {target_project}", flush=True)
            return True
        except Exception as e:
            print(f"Error moving session: {e}", flush=True)
            return False

    def _check_session_status(self, file_path: Path) -> dict:
        """Check session file status (empty session, Invalid API key, etc.)."""
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

                        # Check Invalid API key in summary type
                        if entry_type == 'summary':
                            summary = entry.get('summary', '')
                            if 'Invalid API key' in summary:
                                status['has_invalid_api_key'] = True
                            else:
                                # Summary가 있다는 것은 요약된 메시지가 있다는 의미
                                status['is_empty'] = False
                                status['has_messages'] = True

                        # If user/assistant message exists, not empty session
                        if entry_type in ('user', 'assistant'):
                            status['is_empty'] = False
                            status['has_messages'] = True

                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return status

    def find_cleanable_sessions(self, project_name: str = None) -> dict:
        """Find sessions that can be cleaned."""
        result = {
            'empty_sessions': [],
            'invalid_api_key_sessions': [],
            'total_count': 0
        }

        if project_name:
            projects = [Project(name=project_name, path=str(self.base_path / project_name))]
        else:
            projects = self.get_projects()

        for project in projects:
            project_path = self.base_path / project.name

            if not project_path.exists():
                continue

            for jsonl_file in project_path.glob("*.jsonl"):
                # Exclude agent- files and .bak files
                if jsonl_file.name.startswith("agent-"):
                    continue

                session_id = jsonl_file.stem
                status = self._check_session_status(jsonl_file)

                session_info = {
                    'project_name': project.name,
                    'session_id': session_id,
                    'file_size': status['file_size']
                }

                # Prioritize Invalid API key sessions (no messages, only API error)
                if status['has_invalid_api_key'] and not status['has_messages']:
                    result['invalid_api_key_sessions'].append(session_info)
                elif status['is_empty'] or status['file_size'] == 0:
                    result['empty_sessions'].append(session_info)

        result['total_count'] = len(result['empty_sessions']) + len(result['invalid_api_key_sessions'])
        return result

    def delete_message(self, project_name: str, session_id: str, message_uuid: str) -> bool:
        """Delete a message from session and repair parentUuid chain."""
        project_path = self.base_path / project_name
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

        except Exception as e:
            print(f"Error deleting message: {e}")
            return False

    def clear_sessions(self, project_name: str = None, clear_empty: bool = True, clear_invalid_api_key: bool = True) -> dict:
        """Clear sessions (delete empty and Invalid API key sessions)."""
        cleanable = self.find_cleanable_sessions(project_name)
        deleted = {
            'empty_sessions': [],
            'invalid_api_key_sessions': [],
            'total_deleted': 0,
            'errors': []
        }

        sessions_to_delete = []

        if clear_empty:
            sessions_to_delete.extend([(s, 'empty') for s in cleanable['empty_sessions']])

        if clear_invalid_api_key:
            sessions_to_delete.extend([(s, 'invalid_api_key') for s in cleanable['invalid_api_key_sessions']])

        for session_info, reason in sessions_to_delete:
            try:
                success = self.delete_session(session_info['project_name'], session_info['session_id'])
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
