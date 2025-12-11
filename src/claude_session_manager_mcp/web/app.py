"""Claude Code conversation history viewer web server"""
import os
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from ..models import ClaudeHistoryParser

app = Flask(__name__)
CORS(app)

parser = ClaudeHistoryParser()


def get_version():
    """Get version from package metadata"""
    try:
        from importlib.metadata import version
        return version('claude-session-manager-mcp')
    except:
        # Fallback to pyproject.toml
        try:
            pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
            with open(pyproject_path, 'r') as f:
                for line in f:
                    if line.startswith('version = '):
                        return line.split('=')[1].strip().strip('"').strip("'")
        except:
            pass
    return "unknown"


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/version')
def get_version_info():
    """Get version API"""
    return jsonify({'version': get_version()})


@app.route('/api/projects')
def get_projects():
    """List projects API"""
    projects = parser.get_projects()
    return jsonify([{
        'name': p.name,
        'display_name': p.display_name,
        'path': p.path
    } for p in projects])


@app.route('/api/projects/<path:project_name>/sessions')
def get_sessions(project_name: str):
    """List sessions API"""
    sessions = parser.get_sessions(project_name)
    return jsonify([{
        'session_id': s.session_id,
        'title': s.title,
        'message_count': s.message_count,
        'created_at': s.created_at.isoformat() if s.created_at else None,
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
        'cwd': s.cwd,
        'version': s.version,
        'git_branch': s.git_branch
    } for s in sessions])


@app.route('/api/projects/<path:project_name>/sessions/<session_id>')
def get_session(project_name: str, session_id: str):
    """Get session details API"""
    session = parser.get_session(project_name, session_id)

    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'session_id': session.session_id,
        'title': session.title,
        'cwd': session.cwd,
        'version': session.version,
        'git_branch': session.git_branch,
        'created_at': session.created_at.isoformat() if session.created_at else None,
        'updated_at': session.updated_at.isoformat() if session.updated_at else None,
        'messages': [{
            'uuid': m.uuid,
            'role': m.role,
            'content': m.content,
            'timestamp': m.timestamp.isoformat(),
            'model': m.model,
            'tool_use': m.tool_use
        } for m in session.messages]
    })


@app.route('/api/search')
def search():
    """Search API"""
    query = request.args.get('q', '')
    project_name = request.args.get('project', None)

    if not query:
        return jsonify([])

    sessions = parser.search_sessions(query, project_name)
    return jsonify([{
        'session_id': s.session_id,
        'project_path': s.project_path,
        'title': s.title,
        'message_count': s.message_count,
        'updated_at': s.updated_at.isoformat() if s.updated_at else None
    } for s in sessions[:50]])  # max 50 results


@app.route('/api/projects/<path:project_name>/sessions/<session_id>', methods=['DELETE'])
def delete_session(project_name: str, session_id: str):
    """Delete session API"""
    success = parser.delete_session(project_name, session_id)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Session not found'}), 404


@app.route('/api/projects/<path:project_name>/sessions/<session_id>/rename', methods=['POST'])
def rename_session(project_name: str, session_id: str):
    """Rename session API"""
    data = request.get_json() or {}
    new_title = data.get('title', '').strip()

    if not new_title:
        return jsonify({'error': 'Title is required'}), 400

    success = parser.rename_session(project_name, session_id, new_title)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to rename session'}), 500


@app.route('/api/projects/<path:project_name>/sessions/<session_id>/messages/<message_uuid>', methods=['DELETE'])
def delete_message(project_name: str, session_id: str, message_uuid: str):
    """Delete message API"""
    success = parser.delete_message(project_name, session_id, message_uuid)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to delete message'}), 500


@app.route('/api/clear/preview')
def clear_preview():
    """Preview cleanable sessions API"""
    project_name = request.args.get('project', None)
    result = parser.find_cleanable_sessions(project_name)
    return jsonify(result)


@app.route('/api/clear', methods=['POST'])
def clear_sessions():
    """Clear sessions API"""
    data = request.get_json() or {}
    project_name = data.get('project', None)
    clear_empty = data.get('clear_empty', True)
    clear_invalid_api_key = data.get('clear_invalid_api_key', True)

    result = parser.clear_sessions(project_name, clear_empty, clear_invalid_api_key)
    return jsonify(result)


@app.route('/api/projects/<path:project_name>/sessions/<session_id>/move', methods=['POST'])
def move_session(project_name: str, session_id: str):
    """Move session to another project API"""
    data = request.get_json() or {}
    target_project = data.get('target_project', '').strip()

    if not target_project:
        return jsonify({'error': 'Target project is required'}), 400

    success = parser.move_session(project_name, session_id, target_project)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to move session'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=True)
