"""Web UI for Claude Session Manager."""
import os


def main():
    """Run the Flask web server."""
    from .app import app
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=True)


__all__ = ["main"]
