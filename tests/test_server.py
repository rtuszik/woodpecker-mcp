import httpx
import pytest
from fastmcp import Client

from woodpecker_mcp.server import Settings, create_server
from woodpecker_mcp.spec import TOOLS


def settings(*, read_only: bool = False) -> Settings:
    return Settings(
        server_url="https://ci.example.com", token="test-token", read_only=read_only
    )


async def test_server_exposes_exactly_the_curated_tool_names():
    server = create_server(settings())

    async with Client(server) as client:
        tools = await client.list_tools()

    expected = {tool.name for tool in TOOLS.values()} | {"get_step_logs"}
    assert {t.name for t in tools} == expected


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("WOODPECKER_SERVER", "https://ci.example.com")
    monkeypatch.setenv("WOODPECKER_TOKEN", "secret")
    monkeypatch.setenv("WOODPECKER_MCP_READ_ONLY", "true")
    monkeypatch.setenv("PORT", "9000")

    loaded = Settings.from_env()

    assert loaded == Settings(
        server_url="https://ci.example.com",
        token="secret",
        read_only=True,
        port=9000,
    )


def test_settings_read_stdio_transport_from_environment(monkeypatch):
    monkeypatch.setenv("WOODPECKER_SERVER", "https://ci.example.com")
    monkeypatch.setenv("WOODPECKER_TOKEN", "secret")
    monkeypatch.setenv("WOODPECKER_MCP_TRANSPORT", "STDIO")

    assert Settings.from_env().transport == "stdio"


def test_settings_reject_unknown_transport(monkeypatch):
    monkeypatch.setenv("WOODPECKER_SERVER", "https://ci.example.com")
    monkeypatch.setenv("WOODPECKER_TOKEN", "secret")
    monkeypatch.setenv("WOODPECKER_MCP_TRANSPORT", "carrier-pigeon")

    with pytest.raises(ValueError, match="WOODPECKER_MCP_TRANSPORT"):
        Settings.from_env()


def test_settings_default_to_writable(monkeypatch):
    monkeypatch.setenv("WOODPECKER_SERVER", "https://ci.example.com")
    monkeypatch.setenv("WOODPECKER_TOKEN", "secret")
    monkeypatch.delenv("WOODPECKER_MCP_READ_ONLY", raising=False)

    assert Settings.from_env().read_only is False


async def test_generated_tools_tolerate_responses_the_spec_misdescribes():
    """Woodpecker sends null for nil slices and objects where the spec says
    array; neither may fail output validation."""
    responses = {
        "/api/agents/5/tasks": None,
        "/api/orgs/2": {"id": 2, "name": "placetel", "is_user": True},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses[request.url.path])

    server = create_server(settings(), transport=httpx.MockTransport(handler))

    async with Client(server) as client:
        await client.call_tool("list_agent_tasks", {"agent_id": 5})
        result = await client.call_tool("get_org", {"org_id": "2"})

    assert result.data == {"id": 2, "name": "placetel", "is_user": True}


async def test_read_only_server_has_no_write_tools():
    server = create_server(settings(read_only=True))

    async with Client(server) as client:
        tools = await client.list_tools()

    expected = {tool.name for tool in TOOLS.values() if not tool.write} | {
        "get_step_logs"
    }
    assert {t.name for t in tools} == expected
