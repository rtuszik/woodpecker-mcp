import base64
import json

import httpx2
import pytest
from fastmcp import Client

from woodpecker_mcp.server import Settings, create_server

ARGS = {"repo_id": 3, "pipeline_number": 42}


def config_file(name: str, text: str) -> dict:
    return {
        "hash": f"hash-{name}",
        "name": name,
        "data": base64.b64encode(text.encode()).decode(),
    }


def server_returning(files: list[dict] | None, captured: list[httpx2.Request]):
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(
            200,
            content=json.dumps(files),
            headers={"content-type": "application/json"},
        )

    settings = Settings(server_url="https://ci.example.com", token="env-token")
    return create_server(settings, transport=httpx2.MockTransport(handler))


async def test_get_pipeline_config_returns_decoded_yaml_per_file():
    captured: list[httpx2.Request] = []
    files = [
        config_file("build", "steps:\n  - name: test\n    image: alpine\n"),
        config_file("deploy", "depends_on: [build]\n"),
    ]
    server = server_returning(files, captured)

    async with Client(server) as client:
        result = await client.call_tool("get_pipeline_config", ARGS)

    assert result.data == (
        "==> build <==\nsteps:\n  - name: test\n    image: alpine\n\n"
        "==> deploy <==\ndepends_on: [build]"
    )
    (request,) = captured
    assert str(request.url) == "https://ci.example.com/api/repos/3/pipelines/42/config"
    assert request.headers["Authorization"] == "Bearer env-token"


async def test_get_pipeline_config_keeps_the_header_for_a_null_data_file():
    files = [{**config_file("empty", ""), "data": None}]
    server = server_returning(files, [])

    async with Client(server) as client:
        result = await client.call_tool("get_pipeline_config", ARGS)

    assert result.data == "==> empty <==\n"


@pytest.mark.parametrize("files", [None, []])
async def test_get_pipeline_config_reports_no_files(files):
    server = server_returning(files, [])

    async with Client(server) as client:
        result = await client.call_tool("get_pipeline_config", ARGS)

    assert result.data == "(no config files)"
