FROM node:24-slim

# Install the Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy MCP config (exposed at /etc/readonly-pg.mcp.json for the claude CLI)
COPY readonly-pg.mcp.json /etc/

# Aiven project CA — lets the read-only Postgres MCP server verify Aiven's
# self-signed server cert (DSN uses sslmode=verify-ca&sslrootcert=/etc/aiven-ca.pem).
COPY aiven-ca.pem /etc/aiven-ca.pem

# Copy entrypoint script, normalize line endings (repo may be checked out with
# CRLF on Windows -> a `#!/bin/bash\r` shebang fails with "no such file or
# directory"), and make it executable.
COPY propose-entrypoint.sh /
RUN sed -i 's/\r$//' /propose-entrypoint.sh && chmod +x /propose-entrypoint.sh

# Entrypoint: run the researcher
ENTRYPOINT ["/propose-entrypoint.sh"]
