"""Connection configuration router for n8n MCP Admin.

Manages n8n MCP connection settings stored in the config store.

Endpoints:
  GET  /api/config             - current n8n connection settings (masked)
  PUT  /api/config/connection   - update connection settings
  POST /api/config/test         - test n8n REST API connectivity
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from mcp_admin_core.config import get_config_store
from mcp_admin_core.process import get_process_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ConnectionConfig(BaseModel):
    """Current n8n connection configuration (read-only view)."""

    n8n_api_url: str = ""
    n8n_api_key_masked: str = ""
    mcp_session_timeout: int = 3600
    mcp_max_sessions: int = 10


class ConnectionUpdate(BaseModel):
    """Payload for updating n8n connection settings."""

    n8n_api_url: str = Field(..., description="Full n8n REST API URL (e.g. http://n8n:5678)")
    n8n_api_key: str = Field(..., description="n8n API key for REST authentication")
    mcp_session_timeout: int = Field(3600, ge=60, le=86400, description="MCP session timeout in seconds")
    mcp_max_sessions: int = Field(10, ge=1, le=100, description="Maximum concurrent MCP sessions")
    restart: bool = Field(default=True, description="Restart MCP server after update")


class ConnectionTestResult(BaseModel):
    """Result of an n8n connectivity test."""

    success: bool
    message: str
    n8n_version: str | None = None
    details: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask_key(key: str) -> str:
    """Mask an API key showing only first 4 and last 4 characters."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=ConnectionConfig)
async def get_config() -> ConnectionConfig:
    """Return current n8n MCP connection settings with masked secrets."""
    store = get_config_store()
    conn = await store.get("connection", {})

    api_key = conn.get("n8n_api_key", "")
    return ConnectionConfig(
        n8n_api_url=conn.get("n8n_api_url", ""),
        n8n_api_key_masked=_mask_key(api_key) if api_key else "(not set)",
        mcp_session_timeout=int(conn.get("mcp_session_timeout", 3600)),
        mcp_max_sessions=int(conn.get("mcp_max_sessions", 10)),
    )


@router.put("/connection", response_model=dict[str, str])
async def update_connection(payload: ConnectionUpdate) -> dict[str, str]:
    """Update n8n connection settings and optionally restart MCP server."""
    store = get_config_store()
    await store.patch("connection", {
        "n8n_api_url": payload.n8n_api_url,
        "n8n_api_key": payload.n8n_api_key,
        "mcp_session_timeout": str(payload.mcp_session_timeout),
        "mcp_max_sessions": str(payload.mcp_max_sessions),
    })
    logger.info("Updated n8n connection config")

    restarted = False
    if payload.restart:
        pm = get_process_manager()
        if pm.is_running:
            await pm.restart()
            restarted = True

    msg = "Connection updated and n8n-mcp restarted" if restarted else "Connection updated"
    return {"status": "ok", "message": msg}


@router.post("/test", response_model=ConnectionTestResult)
async def test_connection() -> ConnectionTestResult:
    """Test connectivity to the n8n REST API by calling GET /rest/settings."""
    store = get_config_store()
    conn = await store.get("connection", {})

    api_url = conn.get("n8n_api_url", "")
    api_key = conn.get("n8n_api_key", "")

    if not api_url:
        return ConnectionTestResult(
            success=False,
            message="n8n_api_url is not configured",
        )

    url = f"{api_url.rstrip('/')}/rest/settings"
    headers: dict[str, str] = {}
    if api_key:
        headers["X-N8N-API-KEY"] = api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.ConnectError as exc:
        return ConnectionTestResult(
            success=False,
            message=f"Connection refused: {exc}",
        )
    except httpx.TimeoutException:
        return ConnectionTestResult(
            success=False,
            message=f"Connection timed out after 10 s to {url}",
        )
    except httpx.HTTPStatusError as exc:
        return ConnectionTestResult(
            success=False,
            message=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
    except Exception as exc:
        return ConnectionTestResult(
            success=False,
            message=f"Unexpected error: {exc}",
        )

    # Extract version from settings response
    n8n_version = None
    if isinstance(body, dict):
        n8n_version = body.get("data", {}).get("versionCli") or body.get("versionCli")

    return ConnectionTestResult(
        success=True,
        message="n8n REST API is reachable",
        n8n_version=n8n_version,
        details={
            "url": url,
            "status_code": resp.status_code,
        },
    )
