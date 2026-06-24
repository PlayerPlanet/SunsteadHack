FROM node:24-slim

# Install the Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy MCP config (exposed at /etc/readonly-pg.mcp.json for the claude CLI)
COPY readonly-pg.mcp.json /etc/

# Copy entrypoint script and make it executable
COPY propose-entrypoint.sh /
RUN chmod +x /propose-entrypoint.sh

# Entrypoint: run the researcher
ENTRYPOINT ["/propose-entrypoint.sh"]
