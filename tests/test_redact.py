import gzip
import zlib
from unittest.mock import patch

import httpx2
import pytest
from fastmcp import Client

from woodpecker_mcp.redact import REDACTED, RedactingTransport, redact
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
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=[AGENT])

    server = create_server(
        Settings(server_url="https://ci.example.com", token="env-token"),
        transport=httpx2.MockTransport(handler),
    )

    async with Client(server) as client:
        result = await client.call_tool("list_agents", {})

    (agent,) = result.data["result"]
    assert agent["token"] == REDACTED
    assert agent["name"] == "test-agent"


@pytest.mark.parametrize(
    "headers",
    [
        {"content-type": "application/json"},
        {"content-type": "application/json", "content-length": "1"},
        {"content-type": "text/plain", "transfer-encoding": "chunked"},
        {},
    ],
)
async def test_response_budget_precedes_parsing_and_ignores_headers(
    monkeypatch, tracked_stream, headers
):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    stream = tracked_stream([b" " * 64] * 10)

    def handler(_request):
        return httpx2.Response(200, headers=headers, stream=stream)

    transport = RedactingTransport(httpx2.MockTransport(handler))
    request = httpx2.Request("GET", "https://ci.example.com/api/agents")
    with (
        patch("woodpecker_mcp.redact.json.loads") as parse,
        pytest.raises(httpx2.ReadError, match="128-byte limit") as error,
    ):
        await transport.handle_async_request(request)

    parse.assert_not_called()
    assert error.value.request is request
    assert stream.chunks_read == 3
    assert stream.closed


async def test_response_budget_counts_decompressed_bytes(monkeypatch, tracked_stream):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    compressed = gzip.compress(b" " * 4096)
    assert len(compressed) < 128
    stream = tracked_stream([compressed])

    def handler(_request):
        return httpx2.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
                "content-length": str(len(compressed)),
            },
            stream=stream,
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        with pytest.raises(httpx2.ReadError, match="128-byte limit"):
            await client.get("https://ci.example.com/api/agents")

    assert stream.closed


async def test_response_budget_also_bounds_wire_bytes(monkeypatch, tracked_stream):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    # A gzip header can carry a large filename before producing any output.
    stream = tracked_stream([b"\x1f\x8b\x08\x08" + b"\x00" * 6, *([b"a" * 64] * 10)])

    def handler(_request):
        return httpx2.Response(200, headers={"content-encoding": "gzip"}, stream=stream)

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        with pytest.raises(httpx2.ReadError, match="128-byte limit"):
            await client.get("https://ci.example.com/api/agents")

    assert stream.chunks_read == 3
    assert stream.closed


@pytest.mark.parametrize("body", [b'{"token":"secret","name":"agent"}', b"not JSON"])
async def test_bounded_compressed_response_preserves_status_headers_and_content(
    monkeypatch, tracked_stream, body
):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    compressed = gzip.compress(body)
    stream = tracked_stream([compressed[:10], compressed[10:]])

    def handler(_request):
        return httpx2.Response(
            201,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
                "content-length": str(len(compressed)),
                "x-upstream": "preserved",
            },
            extensions={"http_version": b"HTTP/1.1"},
            stream=stream,
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        response = await client.get("https://ci.example.com/api/agents")

    assert response.status_code == 201
    assert response.headers["x-upstream"] == "preserved"
    assert "content-encoding" not in response.headers
    assert int(response.headers["content-length"]) == len(response.content)
    assert response.extensions["http_version"] == b"HTTP/1.1"
    assert response.request.url.path == "/api/agents"
    if body == b"not JSON":
        assert response.content == body
    else:
        assert response.json() == {"token": REDACTED, "name": "agent"}
    assert stream.closed


async def test_decoding_error_closes_upstream_stream(tracked_stream):
    stream = tracked_stream([b"invalid gzip"])

    def handler(_request):
        return httpx2.Response(200, headers={"content-encoding": "gzip"}, stream=stream)

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        with pytest.raises(httpx2.DecodingError):
            await client.get("https://ci.example.com/api/agents")

    assert stream.closed


async def test_response_exactly_at_budget_remains_accepted(monkeypatch, tracked_stream):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    stream = tracked_stream([b"a" * 64, b"b" * 64])

    def handler(_request):
        return httpx2.Response(
            200, headers={"content-type": "text/plain"}, stream=stream
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        response = await client.get("https://ci.example.com/api/config")

    assert response.content == b"a" * 64 + b"b" * 64
    assert stream.closed


async def test_redaction_cannot_expand_the_response_past_the_budget(
    monkeypatch, tracked_stream
):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 16)
    stream = tracked_stream([b'{"token":""}'])

    def handler(_request):
        return httpx2.Response(
            200, headers={"content-type": "application/json"}, stream=stream
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        with pytest.raises(httpx2.ReadError, match="16-byte limit"):
            await client.get("https://ci.example.com/api/agents")

    assert stream.closed


async def test_response_budget_bounds_intermediate_compression_layers(
    monkeypatch, tracked_stream
):
    monkeypatch.setattr("woodpecker_mcp.redact.MAX_RESPONSE_BYTES", 128)
    compressed = gzip.compress(b"[]")
    # A filename is discarded by the inner gzip decoder. Its intermediate
    # representation still has to fit the budget, even when the final JSON does.
    intermediate = (
        compressed[:3]
        + b"\x08"
        + compressed[4:10]
        + b"a" * 256
        + b"\0"
        + compressed[10:]
    )
    wire = gzip.compress(intermediate)
    assert len(wire) < 128 < len(intermediate)
    stream = tracked_stream([wire])

    def handler(_request):
        return httpx2.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip, gzip",
            },
            stream=stream,
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        with pytest.raises(httpx2.ReadError, match="128-byte limit"):
            await client.get("https://ci.example.com/api/agents")

    assert stream.closed


@pytest.mark.parametrize("encodings", [("gzip", "gzip"), ("gzip", "deflate")])
async def test_bounded_stacked_compression_still_works(tracked_stream, encodings):
    body = b'{"token":"secret","name":"agent"}'
    for encoding in encodings:
        body = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    stream = tracked_stream([body[:10], body[10:]])

    def handler(_request):
        return httpx2.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-encoding": ", ".join(encodings),
            },
            stream=stream,
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        response = await client.get("https://ci.example.com/api/agents")

    assert response.json() == {"token": REDACTED, "name": "agent"}
    assert stream.closed


async def test_excessive_content_encoding_depth_is_rejected(tracked_stream):
    stream = tracked_stream([b"unused"])

    def handler(_request):
        return httpx2.Response(
            200, headers={"content-encoding": ", ".join(["gzip"] * 6)}, stream=stream
        )

    async with httpx2.AsyncClient(
        transport=RedactingTransport(httpx2.MockTransport(handler))
    ) as client:
        with pytest.raises(httpx2.DecodingError, match="exceeds 5 content encodings"):
            await client.get("https://ci.example.com/api/agents")

    assert stream.chunks_read == 0
    assert stream.closed
