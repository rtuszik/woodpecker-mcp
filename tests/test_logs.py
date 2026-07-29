import base64
import json

import httpx2
from fastmcp import Client

from woodpecker_mcp.server import Settings, create_server


def log_entry(line: int, text: str) -> dict:
    return {
        "id": line,
        "step_id": 7,
        "line": line,
        "time": line,
        "type": 0,
        "data": base64.b64encode(text.encode()).decode(),
    }


def server_returning(entries: list[dict] | None, captured: list[httpx2.Request]):
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        # httpx2 treats json=None as "no body"; the real API sends a literal null.
        return httpx2.Response(
            200,
            content=json.dumps(entries),
            headers={"content-type": "application/json"},
        )

    settings = Settings(server_url="https://ci.example.com", token="env-token")
    return create_server(settings, transport=httpx2.MockTransport(handler))


async def test_get_step_logs_returns_decoded_plain_text():
    captured: list[httpx2.Request] = []
    entries = [log_entry(1, "cloning repo"), log_entry(2, "build failed: exit 1")]
    server = server_returning(entries, captured)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
        )

    assert result.data == "cloning repo\nbuild failed: exit 1"
    (request,) = captured
    assert str(request.url) == "https://ci.example.com/api/repos/3/logs/42/7"
    assert request.headers["Authorization"] == "Bearer env-token"


async def test_get_step_logs_tails_long_output_with_a_notice():
    entries = [log_entry(i, f"line {i}") for i in range(1, 501)]
    server = server_returning(entries, [])

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs",
            {"repo_id": 3, "pipeline_number": 42, "step_id": 7, "tail_lines": 3},
        )

    lines = result.data.splitlines()
    assert lines[0] == "[truncated: showing last 3 of 500 lines]"
    assert lines[1:] == ["line 498", "line 499", "line 500"]


async def test_get_step_logs_reports_empty_output():
    server = server_returning([], [])

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
        )

    assert result.data == "(no log output)"


async def test_get_step_logs_skips_purged_null_data_lines():
    entries = [log_entry(1, "still here"), {**log_entry(2, ""), "data": None}]
    server = server_returning(entries, [])

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
        )

    assert result.data == "still here"


async def test_get_step_logs_handles_null_body():
    server = server_returning(None, [])

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
        )

    assert result.data == "(no log output)"
