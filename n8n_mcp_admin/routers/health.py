"""Health dashboard router for n8n MCP Admin.

Returns data in the format the Dashboard frontend expects.

Endpoints:
    GET /api/health - Dashboard health data
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter

from mcp_admin_core.config import get_config_store
from mcp_admin_core.process import get_process_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


async def _check_n8n(api_url: str, api_key: str) -> dict[str, Any]:
    """Check n8n health via GET /rest/settings."""
    if not api_url:
        return {"healthy": False, "url": "", "error": "Not configured"}
    url = f"{api_url.rstrip('/')}/rest/settings"
    headers: dict[str, str] = {}
    if api_key:
        headers["X-N8N-API-KEY"] = api_key
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return {"healthy": True, "url": api_url, "status_code": resp.status_code}
    except httpx.ConnectError:
        return {"healthy": False, "url": api_url, "error": "Connection refused"}
    except httpx.TimeoutException:
        return {"healthy": False, "url": api_url, "error": "Timed out"}
    except httpx.HTTPStatusError as exc:
        return {"healthy": False, "url": api_url, "error": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"healthy": False, "url": api_url, "error": str(exc)}


async def _get_n8n_info(api_url: str, api_key: str) -> dict[str, Any]:
    """Get n8n version and workflow count."""
    info: dict[str, Any] = {"version": None, "db_name": "n8n", "item_count": None}
    if not api_url:
        return info
    headers: dict[str, str] = {}
    if api_key:
        headers["X-N8N-API-KEY"] = api_key
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get version — /rest/settings returns versionCli only with session auth.
            # Try public settings first, then fall back to n8n-mcp /health endpoint.
            resp = await client.get(f"{api_url.rstrip('/')}/rest/settings", headers=headers)
            if resp.status_code == 200:
                body = resp.json()
                settings = body.get("data", body) if isinstance(body, dict) else {}
                ver = settings.get("versionCli")
                if ver:
                    info["version"] = ver

            # Fallback: check n8n-mcp server /health which reports n8n version
            if not info["version"]:
                store = get_config_store()
                mcp_cfg = await store.get("mcp_server", {})
                mcp_port = mcp_cfg.get("port", 3000)
                try:
                    mcp_health = await client.get(f"http://127.0.0.1:{mcp_port}/health", timeout=3)
                    if mcp_health.status_code == 200:
                        mh = mcp_health.json()
                        info["version"] = mh.get("version", mh.get("n8nVersion"))
                except Exception:
                    pass

            # Get workflow count via API
            try:
                resp2 = await client.get(f"{api_url.rstrip('/')}/api/v1/workflows", headers=headers)
                if resp2.status_code == 200:
                    data = resp2.json()
                    if isinstance(data, dict) and "data" in data:
                        info["item_count"] = len(data["data"])
                    elif isinstance(data, list):
                        info["item_count"] = len(data)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Failed to get n8n info: %s", exc)
    return info


@router.get("")
async def get_health() -> dict[str, Any]:
    """Return health data in the format the Dashboard frontend expects."""
    store = get_config_store()
    pm = get_process_manager()

    conn = await store.get("connection", {})
    api_url = conn.get("n8n_api_url", "")
    api_key = conn.get("n8n_api_key", "")
    pm_status = await pm.status()

    # MCP server status
    mcp_running = pm_status.get("running", False)
    mcp_server = {
        "healthy": mcp_running,
        "pod_name": f"pid={pm_status.get('pid')}" if mcp_running else "stopped",
        "restart_count": pm_status.get("restart_count", 0),
    }

    # n8n health
    target_app = await _check_n8n(api_url, api_key)

    # MCP proxy (built-in)
    proxy = {"healthy": True, "pod_name": "built-in reverse proxy"}

    # Extra info
    n8n_info = await _get_n8n_info(api_url, api_key)

    all_healthy = mcp_running and target_app.get("healthy", False)

    return {
        "app_type": "n8n",
        "overall_status": "ok" if all_healthy else "degraded" if mcp_running or target_app.get("healthy") else "error",
        "mcp_server": mcp_server,
        "target_app": target_app,
        "proxy": proxy,
        "version": n8n_info.get("version"),
        "db_name": n8n_info.get("db_name"),
        "item_count": n8n_info.get("item_count"),
        "namespace": "podman",
    }
