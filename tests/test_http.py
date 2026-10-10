import asyncio
import base64
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.exceptions import ToolError
from sse_starlette.sse import AppStatus

from woodpecker_mcp.server import Settings, create_server

MODERN = "2026-07-28"
LEGACY = "2025-11-25"
MODES = pytest.mark.parametrize("mode", ["auto", "legacy"])


def upstream(captured: list[httpx2.Request]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        if "/logs/" in request.url.path:
            data = base64.b64encode(b"build ok").decode()
            return httpx2.Response(200, json=[{"line": 1, "data": data}])
        return httpx2.Response(200, json={"id": 1, "login": "someone"})

    return httpx2.MockTransport(handler)


@asynccontextmanager
async def serve(
    captured: list[httpx2.Request], *, token: str | None = None
) -> AsyncIterator[str]:
    mcp = create_server(
        Settings(server_url="https://ci.example.com", token=token),
        transport=upstream(captured),
    )
    sock = socket.create_server(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mcp.http_app(), log_level="error"))
    # Listening socket queues connections until uvicorn accepts; no startup poll.
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task
        # sse-starlette shutdown flag is process-wide; stale True kills later SSE.
        AppStatus.should_exit = False


def bearer(captured: list[httpx2.Request]) -> list[str]:
    return [request.headers["Authorization"] for request in captured]


@pytest.mark.parametrize(("mode", "protocol"), [("auto", MODERN), ("legacy", LEGACY)])
async def test_each_caller_token_is_forwarded_upstream(mode, protocol):
    captured: list[httpx2.Request] = []

    async with serve(captured, token="env-token") as url:
        for token in ("alice-token", "bob-token"):
            async with Client(url, auth=BearerAuth(token), mode=mode) as client:
                await client.call_tool("get_current_user", {})
                assert client.protocol_version == protocol

    assert bearer(captured) == ["Bearer alice-token", "Bearer bob-token"]


@MODES
async def test_concurrent_callers_never_see_each_others_token(mode):
    captured: list[httpx2.Request] = []
    tokens = [f"token-{i}" for i in range(8)]

    async def call(url: str, token: str) -> None:
        async with Client(url, auth=BearerAuth(token), mode=mode) as client:
            for _ in range(3):
                await client.call_tool("get_current_user", {})

    async with serve(captured) as url:
        await asyncio.gather(*(call(url, token) for token in tokens))

    assert sorted(bearer(captured)) == sorted(
        f"Bearer {token}" for token in tokens for _ in range(3)
    )


@MODES
async def test_caller_without_a_token_falls_back_to_the_env_token(mode):
    captured: list[httpx2.Request] = []

    async with (
        serve(captured, token="env-token") as url,
        Client(url, mode=mode) as client,
    ):
        await client.call_tool("get_current_user", {})

    assert bearer(captured) == ["Bearer env-token"]


@MODES
async def test_caller_without_a_token_and_no_fallback_is_rejected(mode):
    captured: list[httpx2.Request] = []

    async with serve(captured) as url, Client(url, mode=mode) as client:
        with pytest.raises(ToolError, match="Authorization: Bearer"):
            await client.call_tool("get_current_user", {})

    assert captured == []


@MODES
async def test_log_tool_forwards_the_caller_token(mode):
    captured: list[httpx2.Request] = []

    async with (
        serve(captured, token="env-token") as url,
        Client(url, auth=BearerAuth("alice-token"), mode=mode) as client,
    ):
        result = await client.call_tool(
            "get_step_logs", {"repo_id": 3, "pipeline_number": 42, "step_id": 7}
        )

    assert result.data == "build ok"
    assert bearer(captured) == ["Bearer alice-token"]
