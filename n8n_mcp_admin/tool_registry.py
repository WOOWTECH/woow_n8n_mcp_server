"""n8n MCP tool registry with all 24 tools grouped into 4 categories."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ToolCategory(str, Enum):
    """Categories for n8n MCP tools."""

    CORE_REFERENCE = "Core Reference"
    INSTANCE_MANAGEMENT = "Instance Management"
    ADVANCED = "Advanced"


class ToolDefinition(BaseModel):
    """Definition of a single n8n MCP tool."""

    name: str
    category: ToolCategory
    description: str
    operations: list[str] = []
    dangerous: bool = False


# ---------------------------------------------------------------------------
# Tool Registry: 24 tools in 3 categories (7 + 13 + 4)
# Based on ghcr.io/czlonkowski/n8n-mcp v2.59+
# ---------------------------------------------------------------------------

TOOL_REGISTRY: list[ToolDefinition] = [
    # -----------------------------------------------------------------------
    # Core Reference (7 tools) - read-only documentation and node lookup
    # -----------------------------------------------------------------------
    ToolDefinition(
        name="tools_documentation",
        category=ToolCategory.CORE_REFERENCE,
        description="Get documentation for all available n8n MCP tools",
    ),
    ToolDefinition(
        name="search_nodes",
        category=ToolCategory.CORE_REFERENCE,
        description="Search for n8n nodes by name, description, or category",
    ),
    ToolDefinition(
        name="get_node",
        category=ToolCategory.CORE_REFERENCE,
        description="Get detailed information about a specific n8n node type",
    ),
    ToolDefinition(
        name="validate_node",
        category=ToolCategory.CORE_REFERENCE,
        description="Validate a node configuration against its schema",
    ),
    ToolDefinition(
        name="validate_workflow",
        category=ToolCategory.CORE_REFERENCE,
        description="Validate workflow JSON structure without creating it",
    ),
    ToolDefinition(
        name="search_templates",
        category=ToolCategory.CORE_REFERENCE,
        description="Search n8n community workflow templates by keyword",
    ),
    ToolDefinition(
        name="get_template",
        category=ToolCategory.CORE_REFERENCE,
        description="Get a specific workflow template by ID with full details",
    ),

    # -----------------------------------------------------------------------
    # Instance Management (13 tools) - CRUD workflows, executions, health
    # -----------------------------------------------------------------------
    ToolDefinition(
        name="n8n_create_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Create a new workflow on the n8n instance",
        operations=["create"],
        dangerous=True,
    ),
    ToolDefinition(
        name="n8n_get_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Get a workflow by ID with full node and connection details",
        operations=["read"],
    ),
    ToolDefinition(
        name="n8n_update_full_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Fully replace a workflow's definition (nodes, connections, settings)",
        operations=["update"],
        dangerous=True,
    ),
    ToolDefinition(
        name="n8n_update_partial_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Partially update a workflow (name, active status, settings only)",
        operations=["update"],
    ),
    ToolDefinition(
        name="n8n_delete_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Delete a workflow by ID permanently",
        operations=["delete"],
        dangerous=True,
    ),
    ToolDefinition(
        name="n8n_list_workflows",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="List all workflows on the n8n instance with filtering options",
        operations=["read"],
    ),
    ToolDefinition(
        name="n8n_validate_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Validate a workflow against the live n8n instance schema",
        operations=["read"],
    ),
    ToolDefinition(
        name="n8n_autofix_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Automatically fix common workflow issues and return corrected JSON",
        operations=["update"],
    ),
    ToolDefinition(
        name="n8n_test_workflow",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Execute a workflow in test mode and return results",
        operations=["execute"],
        dangerous=True,
    ),
    ToolDefinition(
        name="n8n_executions",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="List, get, or delete workflow execution history",
        operations=["read", "delete"],
    ),
    ToolDefinition(
        name="n8n_health_check",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Check n8n instance health, version, and connectivity",
        operations=["read"],
    ),
    ToolDefinition(
        name="n8n_workflow_versions",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="List version history of a workflow and restore previous versions",
        operations=["read", "update"],
    ),
    ToolDefinition(
        name="n8n_deploy_template",
        category=ToolCategory.INSTANCE_MANAGEMENT,
        description="Deploy a community template as a new workflow on the instance",
        operations=["create"],
        dangerous=True,
    ),

    # -----------------------------------------------------------------------
    # Advanced (4 tools) - data tables, credentials, generation, audit
    # -----------------------------------------------------------------------
    ToolDefinition(
        name="n8n_manage_datatable",
        category=ToolCategory.ADVANCED,
        description="Create, read, update, and delete n8n data table entries",
        operations=["create", "read", "update", "delete"],
        dangerous=True,
    ),
    ToolDefinition(
        name="n8n_manage_credentials",
        category=ToolCategory.ADVANCED,
        description="List, create, update, and delete n8n credentials",
        operations=["create", "read", "update", "delete"],
        dangerous=True,
    ),
    ToolDefinition(
        name="n8n_generate_workflow",
        category=ToolCategory.ADVANCED,
        description="Generate a workflow from natural language description using AI",
        operations=["create"],
    ),
    ToolDefinition(
        name="n8n_audit_instance",
        category=ToolCategory.ADVANCED,
        description="Run a comprehensive audit of the n8n instance configuration",
        operations=["read"],
    ),
]


def get_tool_by_name(name: str) -> ToolDefinition | None:
    """Look up a tool by its name."""
    for tool in TOOL_REGISTRY:
        if tool.name == name:
            return tool
    return None


def get_tools_by_category(category: ToolCategory) -> list[ToolDefinition]:
    """Return all tools in a given category."""
    return [t for t in TOOL_REGISTRY if t.category == category]


def get_all_tool_names() -> list[str]:
    """Return a flat list of all tool names."""
    return [t.name for t in TOOL_REGISTRY]


def get_categorized_tools() -> dict[str, list[dict[str, Any]]]:
    """Return tools grouped by category as serialisable dicts."""
    result: dict[str, list[dict[str, Any]]] = {}
    for cat in ToolCategory:
        result[cat.value] = [
            t.model_dump() for t in TOOL_REGISTRY if t.category == cat
        ]
    return result
