"""Hand-written log tool.

The transport bounds the upstream body before parsing. This tool retains
only a bounded tail and limits individual blobs and the returned text.
"""

import base64
from collections import deque
from typing import Annotated

import httpx2
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from woodpecker_mcp.upstream import raise_for_status

MAX_TAIL_LINES = 1000
MAX_LOG_ENTRY_BYTES = 64 * 1024
MAX_LOG_OUTPUT_BYTES = 1024 * 1024
_MAX_ENCODED_ENTRY_BYTES = 4 * ((MAX_LOG_ENTRY_BYTES + 2) // 3)


def register_log_tool(mcp: FastMCP, client: httpx2.AsyncClient) -> None:
    @mcp.tool
    async def get_step_logs(
        repo_id: int,
        pipeline_number: int,
        step_id: int,
        tail_lines: Annotated[
            int,
            Field(
                gt=0,
                le=MAX_TAIL_LINES,
                description="Return at most this many trailing lines",
            ),
        ] = 200,
    ) -> str:
        """Get the log output of a pipeline step as plain text.

        Returns the last `tail_lines` lines. Step IDs come from the
        `workflows[].children[]` entries of get_pipeline.
        Rejects logs over 8 MiB upstream, entries over 64 KiB decoded,
        or returned text over 1 MiB. At most 1000 tail lines may be requested.
        """
        response = await client.get(
            f"/repos/{repo_id}/logs/{pipeline_number}/{step_id}"
        )
        raise_for_status(response)
        # Both the body and individual line blobs may be null (purged logs).
        tail: deque[str] = deque(maxlen=tail_lines)
        count = 0
        for entry in response.json() or []:
            data = entry.get("data")
            if not data:
                continue
            # Check the decoded-size upper bound, including padding, without
            # decoding entries that will be discarded by the tail.
            if (
                len(data) > _MAX_ENCODED_ENTRY_BYTES
                or len(data.rstrip("=")) * 3 // 4 > MAX_LOG_ENTRY_BYTES
            ):
                msg = f"Log entry exceeds the {MAX_LOG_ENTRY_BYTES}-byte limit"
                raise ToolError(msg)
            tail.append(data)
            count += 1
        if not tail:
            return "(no log output)"
        lines = []
        if count > tail_lines:
            lines.append(f"[truncated: showing last {tail_lines} of {count} lines]")
        output_size = sum(len(line.encode()) for line in lines)
        for data in tail:
            decoded = base64.b64decode(data)
            if len(decoded) > MAX_LOG_ENTRY_BYTES:
                msg = f"Log entry exceeds the {MAX_LOG_ENTRY_BYTES}-byte limit"
                raise ToolError(msg)
            line = decoded.decode(errors="replace").rstrip("\n")
            output_size += len(line.encode()) + bool(lines)
            if output_size > MAX_LOG_OUTPUT_BYTES:
                msg = f"Log output exceeds the {MAX_LOG_OUTPUT_BYTES}-byte limit"
                raise ToolError(msg)
            lines.append(line)
        return "\n".join(lines)
