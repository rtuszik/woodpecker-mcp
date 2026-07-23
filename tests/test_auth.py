import httpx
from fastmcp import Client

from woodpecker_mcp.server import Settings, create_server


def capture_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": 1})

    return httpx.MockTransport(handler)


def settings() -> Settings:
    return Settings(server_url="https://ci.example.com", token="env-token")


async def test_tool_calls_hit_the_api_with_the_env_token():
    captured: list[httpx.Request] = []
    server = create_server(settings(), transport=capture_transport(captured))

    async with Client(server) as client:
        await client.call_tool("get_repo", {"repo_id": 1})

    (request,) = captured
    assert str(request.url) == "https://ci.example.com/api/repos/1"
    assert request.headers["Authorization"] == "Bearer env-token"


async def test_incoming_x_woodpecker_token_overrides_the_env_token(monkeypatch):
    monkeypatch.setattr(
        "woodpecker_mcp.auth.get_http_headers",
        lambda: {"x-woodpecker-token": "caller-token"},
    )
    captured: list[httpx.Request] = []
    server = create_server(settings(), transport=capture_transport(captured))

    async with Client(server) as client:
        await client.call_tool("get_repo", {"repo_id": 1})

    (request,) = captured
    assert request.headers["Authorization"] == "Bearer caller-token"
