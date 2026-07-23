"""Hand-written log tool.

The generated pass-through for the log endpoint would return base64-encoded
line blobs of unbounded size; this tool decodes them to plain text and keeps
only the tail.
"""

import base64
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field


def register_log_tool(mcp: FastMCP, client: httpx.AsyncClient) -> None:
    @mcp.tool
    async def get_step_logs(
        repo_id: int,
        pipeline_number: int,
        step_id: int,
        tail_lines: Annotated[
            int, Field(gt=0, description="Return at most this many trailing lines")
        ] = 200,
    ) -> str:
        """Get the log output of a pipeline step as plain text.

        Returns the last `tail_lines` lines. Step IDs come from the
        `workflows[].children[]` entries of get_pipeline.
        """
        response = await client.get(
            f"/repos/{repo_id}/logs/{pipeline_number}/{step_id}"
        )
        response.raise_for_status()
        # Both the body and individual line blobs may be null (purged logs).
        lines = [
            base64.b64decode(entry["data"]).decode(errors="replace").rstrip("\n")
            for entry in response.json() or []
            if entry.get("data")
        ]
        if not lines:
            return "(no log output)"
        if len(lines) > tail_lines:
            notice = f"[truncated: showing last {tail_lines} of {len(lines)} lines]"
            lines = [notice, *lines[-tail_lines:]]
        return "\n".join(lines)
