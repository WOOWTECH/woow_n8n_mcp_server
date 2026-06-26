# Architecture

## System Overview

The n8n MCP Admin Bundle is a single-container solution that packages three components into one deployment unit:

1. **React SPA** (Frontend) -- Admin dashboard for managing n8n MCP server configuration
2. **FastAPI Backend** -- REST API + MCP reverse proxy + process manager
3. **n8n-mcp Server** (Node.js subprocess) -- MCP protocol server that interfaces with the n8n REST API

## Request Flow

```mermaid
flowchart LR
    subgraph Browser
        SPA["React SPA<br/>Dashboard / Config / Tools / Tokens / Logs"]
    end

    subgraph Container["n8n MCP Admin Bundle (:8080)"]
        direction TB
        FastAPI["FastAPI<br/>(uvicorn)"]
        Auth["JWT Auth<br/>Middleware"]
        ConfigStore["ConfigStore<br/>(config.json)"]
        ProcessMgr["Process<br/>Manager"]
        Proxy["MCP Reverse<br/>Proxy"]
        N8nMCP["n8n-mcp<br/>(Node.js subprocess)"]

        FastAPI --> Auth
        Auth --> ConfigStore
        Auth --> ProcessMgr
        Auth --> Proxy
        ProcessMgr --> N8nMCP
        Proxy --> N8nMCP
    end

    subgraph External["n8n Instance"]
        N8nAPI["n8n REST API<br/>(:5678)"]
    end

    SPA -->|Admin API| FastAPI
    SPA -->|MCP SSE/JSON| Proxy
    N8nMCP -->|REST API calls| N8nAPI
```

## Component Details

### Frontend (React 19 + Tailwind CSS)

The frontend is a single-page application built with React 19, Tailwind CSS, and Vite. It provides seven views:

| Page | Description |
|------|-------------|
| Login | JWT-based authentication |
| Dashboard | System health overview (n8n, MCP server, proxy status) |
| Connection Config | n8n API URL and API Key configuration |
| Tool Manager | Enable/disable 24 MCP tools across 3 categories |
| Token Manager | MCP proxy token generation, rotation, and history |
| Log Viewer | Real-time SSE log streaming with search |
| Settings | Full config.json editor with MCP process control |

### Backend (FastAPI + Python 3.12)

The backend is split into two Python packages:

**mcp-admin-core** -- Shared library providing:
- `ConfigStore` -- File-backed JSON configuration persistence
- `McpProcessManager` -- asyncio subprocess lifecycle management
- `MCP Reverse Proxy` -- Token-validated reverse proxy with SSE streaming support
- `AuthMiddleware` -- JWT authentication for API endpoints
- `Settings Router` -- Full configuration CRUD

**n8n-mcp-admin** -- n8n-specific extension providing:
- `Connection Config Router` -- n8n API URL + API Key management with connectivity testing
- `Tool Manager Router` -- 24-tool registry with category-based enable/disable
- `Token Router` -- Proxy token generation, rotation, and history tracking
- `Health Router` -- Dashboard data aggregation (n8n version, workflow count, process status)
- `Log Router` -- In-memory ring buffer + SSE streaming

### n8n-mcp Server (Node.js)

The n8n-mcp server (`n8n-mcp` npm package, v2.60.0) is a Node.js process managed by `McpProcessManager`. It:

- Runs as a subprocess via `node http-server.js`
- Connects to the n8n REST API using the configured API URL and API Key
- Exposes 24 MCP tools for AI assistants (Claude, ChatGPT, etc.)
- Communicates via MCP protocol (SSE + JSON-RPC)

## Data Flow

```mermaid
sequenceDiagram
    participant AI as AI Assistant
    participant Proxy as MCP Proxy
    participant N8nMCP as n8n-mcp (Node.js)
    participant N8n as n8n REST API

    AI->>Proxy: SSE connect /private_{token}/sse
    Proxy->>N8nMCP: Forward to localhost:3000/sse
    N8nMCP-->>Proxy: SSE stream established
    Proxy-->>AI: SSE stream forwarded

    AI->>Proxy: POST /private_{token}/messages
    Proxy->>N8nMCP: Forward JSON-RPC
    N8nMCP->>N8n: GET /api/v1/workflows
    N8n-->>N8nMCP: Workflow data
    N8nMCP-->>Proxy: Tool result
    Proxy-->>AI: JSON-RPC response
```

## Configuration Architecture

All configuration is stored in a single JSON file (`/data/config.json`):

```json
{
  "admin_password": "...",
  "mcp_auth_token": "...",
  "connection": {
    "n8n_api_url": "http://n8n:5678",
    "n8n_api_key": "..."
  },
  "tools": {
    "disabled": [],
    "disabled_operations": {}
  },
  "mcp_server": {
    "command": "n8n-mcp",
    "args": ["--transport", "http", "--port", "3000"],
    "port": 3000,
    "env": {}
  },
  "proxy": {
    "timeout": 86400
  },
  "token_history": []
}
```

## Deployment Options

### Standalone (Podman/Docker)

Single container with a volume mount for persistent configuration:

```
podman run -p 8080:8080 -v ./data:/data ghcr.io/woowtech/n8n-mcp-admin:latest
```

### Docker Compose

Full stack with PostgreSQL + n8n + MCP Admin Bundle:

```
docker compose up -d
```

### Kubernetes

Deploy as a Deployment with RBAC, health probes, and resource limits. See `k8s-deploy.yaml`.

## Security Model

```mermaid
flowchart TB
    subgraph Auth["Authentication Layer"]
        JWT["JWT Token<br/>(HS256, 24h expiry)"]
        AdminPW["Admin Password<br/>(config.json)"]
    end

    subgraph API["API Protection"]
        Middleware["AuthMiddleware<br/>/api/* routes"]
        Public["Public Routes<br/>/api/auth/login<br/>/healthz"]
    end

    subgraph MCP["MCP Proxy Protection"]
        URLToken["URL Path Token<br/>/private_{token}/"]
    end

    AdminPW --> JWT
    JWT --> Middleware
    Middleware --> API
    URLToken --> MCP
```

- **Admin GUI:** Protected by JWT authentication. Login with admin password, receive a 24-hour token.
- **MCP Proxy:** Protected by URL path token. AI assistants use `/private_{token}/` paths to access the MCP server.
- **MCP Server:** Not directly exposed. Only accessible through the authenticated reverse proxy.
