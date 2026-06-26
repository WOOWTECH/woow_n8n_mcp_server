# n8n MCP Admin Bundle — Admin GUI + MCP Proxy + n8n-mcp server in one container
#
# Usage:
#   podman run -p 8080:8080 -v ./data:/data n8n-mcp-admin-bundle
#   docker run -p 8080:8080 -v ./data:/data n8n-mcp-admin-bundle

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/
RUN cd frontend && npm install --production=false
COPY frontend/ frontend/
RUN cd frontend && npm run build

# Stage 2: Python + Node.js runtime
FROM python:3.12-slim
WORKDIR /app

# Install Node.js 20 for n8n-mcp
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install n8n-mcp server globally
RUN npm install -g n8n-mcp

# Install core library
COPY pyproject.toml /tmp/mcp-admin-core/pyproject.toml
COPY mcp_admin_core/ /tmp/mcp-admin-core/mcp_admin_core/
RUN pip install --no-cache-dir /tmp/mcp-admin-core/ && rm -rf /tmp/mcp-admin-core/

# Install n8n admin package
COPY n8n_pyproject.toml /tmp/n8n-mcp-admin/pyproject.toml
COPY n8n_mcp_admin/ /tmp/n8n-mcp-admin/n8n_mcp_admin/
RUN pip install --no-cache-dir /tmp/n8n-mcp-admin/ && rm -rf /tmp/n8n-mcp-admin/

# Copy frontend build
COPY --from=frontend-builder /build/frontend/dist /app/static

# Config volume
RUN mkdir -p /data
VOLUME /data

# Single port — admin GUI + MCP proxy
EXPOSE 8080

ENV MCP_ADMIN_CONFIG=/data/config.json

CMD ["uvicorn", "n8n_mcp_admin.main:app", "--host", "0.0.0.0", "--port", "8080"]
