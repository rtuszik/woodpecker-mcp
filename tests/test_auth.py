import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from woodpecker_mcp.server import Settings, create_server


def capture_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": 1})

    return httpx.MockTransport(handler)


def settings(*, token: str | None = "env-token") -> Settings:
    return Settings(server_url="https://ci.example.com", token=token)


def send_headers(monkeypatch, headers: dict[str, str]) -> None:
    monkeypatch.setattr(
        "woodpecker_mcp.auth.get_http_headers",
        lambda **_kwargs: headers,
    )


async def test_tool_calls_fall_back_to_the_env_token():
    captured: list[httpx.Request] = []
    server = create_server(settings(), transport=capture_transport(captured))

    async with Client(server) as client:
        await client.call_tool("get_repo", {"repo_id": 1})

    (request,) = captured
    assert str(request.url) == "https://ci.example.com/api/repos/1"
    assert request.headers["Authorization"] == "Bearer env-token"


async def test_incoming_bearer_token_overrides_the_env_token(monkeypatch):
    send_headers(monkeypatch, {"authorization": "Bearer caller-token"})
    captured: list[httpx.Request] = []
    server = create_server(settings(), transport=capture_transport(captured))

    async with Client(server) as client:
        await client.call_tool("get_repo", {"repo_id": 1})

    (request,) = captured
    assert request.headers["Authorization"] == "Bearer caller-token"


async def test_bearer_scheme_is_case_insensitive(monkeypatch):
    send_headers(monkeypatch, {"authorization": "bearer caller-token"})
    captured: list[httpx.Request] = []
    server = create_server(settings(token=None), transport=capture_transport(captured))

    async with Client(server) as client:
        await client.call_tool("get_repo", {"repo_id": 1})

    (request,) = captured
    assert request.headers["Authorization"] == "Bearer caller-token"


async def test_request_without_a_token_is_rejected(monkeypatch):
    send_headers(monkeypatch, {})
    captured: list[httpx.Request] = []
    server = create_server(settings(token=None), transport=capture_transport(captured))

    async with Client(server) as client:
        with pytest.raises(ToolError, match="Authorization: Bearer"):
            await client.call_tool("get_repo", {"repo_id": 1})

    assert captured == []


async def test_non_bearer_authorization_is_ignored(monkeypatch):
    send_headers(monkeypatch, {"authorization": "Basic Zm9vOmJhcg=="})
    captured: list[httpx.Request] = []
    server = create_server(settings(), transport=capture_transport(captured))

    async with Client(server) as client:
        await client.call_tool("get_repo", {"repo_id": 1})

    (request,) = captured
    assert request.headers["Authorization"] == "Bearer env-token"
