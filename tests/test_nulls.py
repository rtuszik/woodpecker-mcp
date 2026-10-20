import httpx2
import pytest
from fastmcp import Client

from woodpecker_mcp.nulls import NullListTransport
from woodpecker_mcp.server import Settings, create_server


def transport_returning(
    content: bytes, content_type: str, status: int = 200
) -> NullListTransport:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, content=content, headers={"content-type": content_type}
        )

    return NullListTransport(httpx2.MockTransport(handler))


async def send(transport: NullListTransport) -> httpx2.Response:
    async with httpx2.AsyncClient(transport=transport) as client:
        return await client.get("https://ci.example.com/api/agents/5/tasks")


async def test_null_json_body_becomes_an_empty_list():
    response = await send(transport_returning(b"null\n", "application/json"))

    assert response.json() == []


@pytest.mark.parametrize(
    ("content", "content_type", "status"),
    [
        (b'{"id": 1}', "application/json", 200),
        (b"null", "text/plain", 200),
        (b"null", "application/json", 500),
    ],
)
async def test_other_bodies_pass_through_unchanged(content, content_type, status):
    response = await send(transport_returning(content, content_type, status))

    assert response.content == content


async def test_generated_list_tools_return_an_empty_list_for_null():
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )

    server = create_server(
        Settings(server_url="https://ci.example.com", token="env-token"),
        transport=httpx2.MockTransport(handler),
    )

    async with Client(server) as client:
        result = await client.call_tool("list_repo_registries", {"repo_id": 5})

    assert result.data == {"result": []}
