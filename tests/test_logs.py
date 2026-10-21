import base64
import json
from unittest.mock import patch

import httpx2
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from woodpecker_mcp.logs import (
    MAX_LOG_ENTRY_BYTES,
    MAX_LOG_OUTPUT_BYTES,
    MAX_TAIL_LINES,
)
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


async def test_small_tail_rejects_oversized_stream_before_decoding(
    monkeypatch, tracked_stream
):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    stream = tracked_stream([b'[{"data":"', *([b"YWFh" * 16] * 10), b'"}]'])

    def handler(_request):
        return httpx2.Response(
            200, headers={"content-type": "application/json"}, stream=stream
        )

    server = create_server(
        Settings(server_url="https://ci.example.com", token="env-token"),
        transport=httpx2.MockTransport(handler),
    )
    async with Client(server) as client:
        with (
            patch("woodpecker_mcp.logs.base64.b64decode") as decode,
            pytest.raises(ToolError, match="128-byte limit"),
        ):
            await client.call_tool(
                "get_step_logs",
                {"repo_id": 3, "pipeline_number": 42, "step_id": 7, "tail_lines": 1},
            )

    decode.assert_not_called()
    assert stream.chunks_read == 3
    assert stream.closed


async def test_only_the_retained_tail_is_decoded():
    entries = [log_entry(i, f"line {i}") for i in range(500)]
    server = server_returning(entries, [])
    async with Client(server) as client:
        with patch(
            "woodpecker_mcp.logs.base64.b64decode", wraps=base64.b64decode
        ) as decode:
            result = await client.call_tool(
                "get_step_logs",
                {"repo_id": 3, "pipeline_number": 42, "step_id": 7, "tail_lines": 1},
            )

    assert result.data == "[truncated: showing last 1 of 500 lines]\nline 499"
    decode.assert_called_once_with(entries[-1]["data"])


@pytest.mark.parametrize("tail_lines", [0, -1, MAX_TAIL_LINES + 1, 10**9])
async def test_invalid_tail_count_is_rejected_before_request(tail_lines):
    captured: list[httpx2.Request] = []
    server = server_returning([], captured)

    async with Client(server) as client:
        with pytest.raises(ToolError, match="validation error"):
            await client.call_tool(
                "get_step_logs",
                {
                    "repo_id": 3,
                    "pipeline_number": 42,
                    "step_id": 7,
                    "tail_lines": tail_lines,
                },
            )

    assert captured == []


@pytest.mark.parametrize("size", [MAX_LOG_ENTRY_BYTES + 1, MAX_LOG_ENTRY_BYTES + 3])
@pytest.mark.parametrize("position", ["tail", "discarded"])
async def test_oversized_entry_is_rejected(size, position):
    entries = [log_entry(1, "x" * size)]
    if position == "discarded":
        entries.append(log_entry(2, "small tail"))
    server = server_returning(entries, [])

    async with Client(server) as client:
        with pytest.raises(ToolError, match="Log entry exceeds"):
            await client.call_tool(
                "get_step_logs",
                {"repo_id": 3, "pipeline_number": 42, "step_id": 7, "tail_lines": 1},
            )


@pytest.mark.parametrize("data", [b"x", b"\xff"])
async def test_returned_text_has_a_cumulative_byte_limit(data):
    entries = [
        {"data": base64.b64encode(data * MAX_LOG_ENTRY_BYTES).decode()}
        for _ in range(MAX_LOG_OUTPUT_BYTES // MAX_LOG_ENTRY_BYTES + 1)
    ]
    server = server_returning(entries, [])

    async with Client(server) as client:
        with pytest.raises(ToolError, match="Log output exceeds"):
            await client.call_tool(
                "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
            )


async def test_limits_accept_exact_entry_size_and_maximum_tail_count():
    text = "x" * MAX_LOG_ENTRY_BYTES
    server = server_returning([log_entry(1, text)], [])

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs",
            {
                "repo_id": 3,
                "pipeline_number": 42,
                "step_id": 7,
                "tail_lines": MAX_TAIL_LINES,
            },
        )

    assert result.data == text


async def test_default_tail_still_returns_200_entries_and_skips_purged_data():
    entries = [log_entry(i, f"line {i}\n") for i in range(201)]
    entries.extend([{"data": None}, {"data": ""}])
    server = server_returning(entries, [])

    async with Client(server) as client:
        result = await client.call_tool(
            "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
        )

    assert result.data.splitlines() == [
        "[truncated: showing last 200 of 201 lines]",
        *(f"line {i}" for i in range(1, 201)),
    ]


@pytest.mark.parametrize("tail_lines", [1, 2])
async def test_output_budget_includes_separators_and_notice(monkeypatch, tail_lines):
    expected = (
        "[truncated: showing last 1 of 2 lines]\nright"
        if tail_lines == 1
        else "left\nright"
    )
    monkeypatch.setattr("woodpecker_mcp.logs.MAX_LOG_OUTPUT_BYTES", len(expected))
    server = server_returning([log_entry(1, "left"), log_entry(2, "right")], [])
    arguments = {
        "repo_id": 3,
        "pipeline_number": 42,
        "step_id": 7,
        "tail_lines": tail_lines,
    }

    async with Client(server) as client:
        result = await client.call_tool("get_step_logs", arguments)
        assert result.data == expected
        monkeypatch.setattr(
            "woodpecker_mcp.logs.MAX_LOG_OUTPUT_BYTES", len(expected) - 1
        )
        with pytest.raises(ToolError, match="Log output exceeds"):
            await client.call_tool("get_step_logs", arguments)


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


async def test_get_step_logs_errors_like_the_generated_tools():
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404)

    settings = Settings(server_url="https://ci.example.com", token="env-token")
    server = create_server(settings, transport=httpx2.MockTransport(handler))

    async with Client(server) as client:
        with pytest.raises(ToolError) as error:
            await client.call_tool(
                "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 1}
            )

    assert (
        str(error.value)
        == "Error calling tool 'get_step_logs': HTTP error 404: Not Found"
    )
