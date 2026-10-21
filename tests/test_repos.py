import json

import httpx2
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from woodpecker_mcp.server import Settings, create_server

PIPELINE = {
    "id": 71006,
    "number": 15554,
    "status": "failure",
    "event": "push",
    "branch": "main",
    "created": 1792504991,
    "message": "a long commit message",
    "changed_files": ["app/models/user.rb"],
    "errors": [{"type": "linter", "message": "bad habit"}],
}
REPO = {
    "id": 5,
    "name": "neo",
    "full_name": "Placetel/neo",
    "org_id": 2,
    "default_branch": "main",
    "active": True,
    "clone_url": "https://github.com/Placetel/neo.git",
    "trusted": {"network": True},
    "last_pipeline": PIPELINE,
}


def server_returning(body, captured: list[httpx2.Request], status: int = 200):
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(
            status,
            content=json.dumps(body),
            headers={"content-type": "application/json"},
        )

    settings = Settings(server_url="https://ci.example.com", token="env-token")
    return create_server(settings, transport=httpx2.MockTransport(handler))


async def test_list_repos_returns_summaries_with_a_slim_last_pipeline():
    captured: list[httpx2.Request] = []
    server = server_returning(
        [REPO, {**REPO, "id": 6, "last_pipeline": None}], captured
    )

    async with Client(server) as client:
        result = await client.call_tool("list_repos", {})

    summary = {
        "id": 5,
        "full_name": "Placetel/neo",
        "org_id": 2,
        "default_branch": "main",
        "active": True,
        "last_pipeline": {
            "number": 15554,
            "status": "failure",
            "event": "push",
            "branch": "main",
            "created": 1792504991,
        },
    }
    assert result.data == [summary, {**summary, "id": 6, "last_pipeline": None}]
    (request,) = captured
    assert str(request.url) == "https://ci.example.com/api/user/repos"
    assert request.headers["Authorization"] == "Bearer env-token"


async def test_list_repos_forwards_the_filters():
    captured: list[httpx2.Request] = []
    server = server_returning([], captured)

    async with Client(server) as client:
        await client.call_tool("list_repos", {"include_inactive": True, "name": "neo"})

    (request,) = captured
    assert dict(request.url.params) == {"all": "true", "name": "neo"}


@pytest.mark.parametrize("body", [None, []])
async def test_list_repos_returns_an_empty_list_for_no_repos(body):
    server = server_returning(body, [])

    async with Client(server) as client:
        result = await client.call_tool("list_repos", {})

    assert result.data == []


async def test_list_repos_errors_like_the_generated_tools():
    server = server_returning("bad token", [], status=401)

    async with Client(server) as client:
        with pytest.raises(ToolError) as error:
            await client.call_tool("list_repos", {})

    assert str(error.value) == (
        "Error calling tool 'list_repos': HTTP error 401: Unauthorized - \"bad token\""
    )


def forge_only(name: str) -> dict:
    """A forge repo that `all` adds but Woodpecker has not activated: no id."""
    repo = {
        key: value for key, value in REPO.items() if key not in {"id", "last_pipeline"}
    }
    return {**repo, "name": name, "full_name": f"Placetel/{name}", "active": False}


async def test_list_repos_summarizes_forge_repos_without_an_id():
    server = server_returning([forge_only("aspgpt")], [])

    async with Client(server) as client:
        result = await client.call_tool("list_repos", {"include_inactive": True})

    (summary,) = result.data
    assert summary["id"] is None
    assert summary["full_name"] == "Placetel/aspgpt"
    assert summary["active"] is False
    assert summary["last_pipeline"] is None


async def test_list_repos_applies_the_name_filter_to_forge_repos_too():
    upstream = [REPO, {**REPO, "id": 1, "name": "accounts"}, forge_only("aspgpt")]
    server = server_returning(upstream, [])

    async with Client(server) as client:
        result = await client.call_tool(
            "list_repos", {"include_inactive": True, "name": "neo"}
        )

    assert [repo["full_name"] for repo in result.data] == ["Placetel/neo"]
