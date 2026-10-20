"""Hand-written repo list tool.

Upstream embeds every repo's settings and full last pipeline; this returns summaries.
"""

from typing import Annotated, Any

import httpx2
from fastmcp import FastMCP
from pydantic import Field

from woodpecker_mcp.upstream import raise_for_status

_PIPELINE_FIELDS = ("number", "status", "event", "branch", "created")


def summarize(repo: dict[str, Any]) -> dict[str, Any]:
    last = repo.get("last_pipeline")
    return {
        "id": repo["id"],
        "full_name": repo["full_name"],
        "org_id": repo.get("org_id"),
        "default_branch": repo.get("default_branch"),
        "active": repo.get("active"),
        "last_pipeline": {key: last.get(key) for key in _PIPELINE_FIELDS}
        if last
        else None,
    }


def register_repo_tool(mcp: FastMCP, client: httpx2.AsyncClient) -> None:
    @mcp.tool
    async def list_repos(
        *,
        include_inactive: Annotated[
            bool, Field(description="also return inactive repos")
        ] = False,
        name: Annotated[str | None, Field(description="filter repos by name")] = None,
    ) -> list[dict[str, Any]]:
        """List the current user's repositories as summaries.

        Use get_repo for the full settings of one repository.
        """
        params: dict[str, Any] = {}
        if include_inactive:
            params["all"] = True
        if name:
            params["name"] = name
        response = await client.get("/user/repos", params=params)
        raise_for_status(response)
        return [summarize(repo) for repo in response.json() or []]
