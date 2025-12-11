kill:
	lsof -i :5050 -t | xargs kill 2>/dev/null; true

run-web:
	uvx --from . claude-session-manager-web

web-restart: kill
	uvx --refresh-package claude-session-manager-mcp --from . claude-session-manager-web
