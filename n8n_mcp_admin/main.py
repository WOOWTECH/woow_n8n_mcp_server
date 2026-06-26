"""FastAPI application entry point for n8n MCP Admin."""

from __future__ import annotations

from mcp_admin_core.app import create_app

from .routers import config, health, logs, tokens, tools

app = create_app(
    title="n8n MCP Admin",
    extra_routers=[
        config.router,
        tools.router,
        tokens.router,
        health.router,
        logs.router,
    ],
)
