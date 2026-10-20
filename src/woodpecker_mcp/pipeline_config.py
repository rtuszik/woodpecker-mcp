"""Hand-written pipeline config tool.

Woodpecker serializes config data ([]byte) as base64; this tool decodes it to YAML text.
"""

import base64

import httpx2
from fastmcp import FastMCP

from woodpecker_mcp.upstream import raise_for_status


def register_config_tool(mcp: FastMCP, client: httpx2.AsyncClient) -> None:
    @mcp.tool
    async def get_pipeline_config(repo_id: int, pipeline_number: int) -> str:
        """Get the configuration files of a pipeline as YAML text.

        Each file is preceded by a `==> name <==` header.
        """
        response = await client.get(
            f"/repos/{repo_id}/pipelines/{pipeline_number}/config"
        )
        raise_for_status(response)
        files = [
            f"==> {entry['name']} <==\n"
            + base64.b64decode(entry.get("data") or "")
            .decode(errors="replace")
            .rstrip("\n")
            for entry in response.json() or []
        ]
        return "\n\n".join(files) or "(no config files)"
