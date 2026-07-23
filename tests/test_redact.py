import httpx
from fastmcp import Client

from woodpecker_mcp.redact import REDACTED, redact
from woodpecker_mcp.server import Settings, create_server

AGENT = {
    "id": 312,
    "name": "test-agent",
    "token": "fake-agent-registration-token",
    "custom_labels": {"env": "test"},
}


def test_redact_scrubs_token_keys_recursively():
    data = {"agents": [AGENT], "nested": {"token": "abc"}, "count": 1}

    redacted = redact(data)

    assert redacted["agents"][0]["token"] == REDACTED
    assert redacted["nested"]["token"] == REDACTED
    assert redacted["agents"][0]["name"] == "test-agent"
    assert redacted["count"] == 1


def test_redact_leaves_non_string_token_values_alone():
    assert redact({"token": 42}) == {"token": 42}


async def test_agent_tools_never_return_the_registration_token():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[AGENT])

    server = create_server(
        Settings(server_url="https://ci.example.com", token="env-token"),
        transport=httpx.MockTransport(handler),
    )

    async with Client(server) as client:
        result = await client.call_tool("list_agents", {})

    (agent,) = result.data["result"]
    assert agent["token"] == REDACTED
    assert agent["name"] == "test-agent"
