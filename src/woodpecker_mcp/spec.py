"""Curated tool surface over the bundled Woodpecker OpenAPI spec.

The TOOLS table is the single source of truth for what the MCP server
exposes: routes not listed here are dropped, and each entry provides the
operationId that fastmcp turns into the tool name.
"""

from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import yaml


@dataclass(frozen=True)
class Tool:
    name: str
    write: bool = False


TOOLS: dict[tuple[str, str], Tool] = {
    # repos
    ("GET", "/user/repos"): Tool("list_repos"),
    ("GET", "/repos/lookup/{repo_full_name}"): Tool("lookup_repo"),
    ("GET", "/repos/{repo_id}"): Tool("get_repo"),
    ("GET", "/repos/{repo_id}/permissions"): Tool("get_repo_permissions"),
    ("GET", "/repos/{repo_id}/branches"): Tool("list_branches"),
    ("GET", "/repos/{repo_id}/pull_requests"): Tool("list_pull_requests"),
    # pipelines
    ("GET", "/repos/{repo_id}/pipelines"): Tool("list_pipelines"),
    ("GET", "/repos/{repo_id}/pipelines/{pipeline_number}"): Tool("get_pipeline"),
    ("GET", "/repos/{repo_id}/pipelines/{pipeline_number}/config"): Tool(
        "get_pipeline_config"
    ),
    ("GET", "/repos/{repo_id}/pipelines/{pipeline_number}/metadata"): Tool(
        "get_pipeline_metadata"
    ),
    ("POST", "/repos/{repo_id}/pipelines"): Tool("trigger_pipeline", write=True),
    ("POST", "/repos/{repo_id}/pipelines/{pipeline_number}"): Tool(
        "restart_pipeline", write=True
    ),
    ("POST", "/repos/{repo_id}/pipelines/{pipeline_number}/cancel"): Tool(
        "cancel_pipeline", write=True
    ),
    ("POST", "/repos/{repo_id}/pipelines/{pipeline_number}/approve"): Tool(
        "approve_pipeline", write=True
    ),
    ("POST", "/repos/{repo_id}/pipelines/{pipeline_number}/decline"): Tool(
        "decline_pipeline", write=True
    ),
    # orgs
    ("GET", "/orgs/lookup/{org_full_name}"): Tool("lookup_org"),
    ("GET", "/orgs/{org_id}"): Tool("get_org"),
    ("GET", "/orgs/{org_id}/permissions"): Tool("get_org_permissions"),
    # user
    ("GET", "/user"): Tool("get_current_user"),
    # queue + agents
    ("GET", "/queue/info"): Tool("get_queue_info"),
    ("GET", "/agents"): Tool("list_agents"),
    ("GET", "/agents/{agent_id}"): Tool("get_agent"),
    ("GET", "/agents/{agent_id}/tasks"): Tool("list_agent_tasks"),
    # secrets + registries (metadata reads only; values are never returned)
    ("GET", "/repos/{repo_id}/secrets"): Tool("list_repo_secrets"),
    ("GET", "/orgs/{org_id}/secrets"): Tool("list_org_secrets"),
    ("GET", "/repos/{repo_id}/registries"): Tool("list_repo_registries"),
    ("GET", "/orgs/{org_id}/registries"): Tool("list_org_registries"),
}


def load_spec() -> dict[str, Any]:
    raw = files("woodpecker_mcp").joinpath("openapi.yaml").read_text()
    return yaml.safe_load(raw)


def prepare_spec(spec: dict[str, Any], *, read_only: bool = False) -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    for (method, path), tool in TOOLS.items():
        if read_only and tool.write:
            continue
        operation = dict(spec["paths"][path][method.lower()])
        operation["operationId"] = tool.name
        operation["parameters"] = [
            param
            for param in operation.get("parameters", [])
            if param["name"].lower() != "authorization"
        ]
        # The upstream spec misdescribes responses (nil slices arrive as null,
        # some handlers are annotated {array} but return an object), so drop
        # response schemas entirely rather than let fastmcp validate against them.
        operation["responses"] = {
            status: {k: v for k, v in response.items() if k != "content"}
            for status, response in operation.get("responses", {}).items()
        }
        paths.setdefault(path, {})[method.lower()] = operation
    return {**spec, "paths": paths}
