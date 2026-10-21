"""Scrub credentials from upstream responses.

Woodpecker returns agent registration tokens in cleartext on the agent
endpoints (for admin PATs); nothing an MCP client receives should contain
them. Redaction happens at the HTTP transport so every tool is covered.
"""

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from typing import Any, cast

import httpx2

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {"token"}
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_CONTENT_ENCODINGS = 5


def _check_response_size(size: int, request: httpx2.Request) -> None:
    if size > MAX_RESPONSE_BYTES:
        msg = f"Upstream response exceeds the {MAX_RESPONSE_BYTES}-byte limit"
        raise httpx2.ReadError(msg, request=request)


class _LimitedStream(httpx2.AsyncByteStream):
    """Bound wire bytes and each decoded representation of the response."""

    def __init__(
        self, inner: httpx2.AsyncByteStream | httpx2.Response, request: httpx2.Request
    ):
        self._inner = inner
        self._request = request

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        chunks = (
            self._inner.aiter_bytes()
            if isinstance(self._inner, httpx2.Response)
            else self._inner.__aiter__()
        )
        try:
            async for chunk in chunks:
                size += len(chunk)
                _check_response_size(size, self._request)
                yield chunk
        finally:
            if isinstance(chunks, AsyncGenerator):
                await chunks.aclose()

    async def aclose(self) -> None:
        await self._inner.aclose()


def _limit_response_stream(response: httpx2.Response, request: httpx2.Request) -> None:
    response.stream = _LimitedStream(
        cast(httpx2.AsyncByteStream, response.stream), request
    )
    encodings = response.headers.get_list("content-encoding", split_commas=True)
    if len(encodings) > _MAX_CONTENT_ENCODINGS:
        msg = f"Upstream response exceeds {_MAX_CONTENT_ENCODINGS} content encodings"
        raise httpx2.DecodingError(msg, request=request)
    # Decode one layer at a time so intermediate expansion is bounded too.
    for encoding in reversed(encodings):
        layer = httpx2.Response(
            response.status_code,
            headers={"content-encoding": encoding},
            stream=response.stream,
            request=request,
        )
        response.stream = _LimitedStream(layer, request)
    response.headers.pop("content-encoding", None)


def redact(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: REDACTED
            if key in _SENSITIVE_KEYS and isinstance(value, str)
            else redact(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact(item) for item in data]
    return data


class RedactingTransport(httpx2.AsyncBaseTransport):
    def __init__(self, inner: httpx2.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        buffer = bytearray()
        try:
            _limit_response_stream(response, request)
            # Apply the budget before either JSON parsing or the client's own
            # full-body read, regardless of Content-Type or Content-Length.
            async with aclosing(response.aiter_bytes()) as chunks:
                async for chunk in chunks:
                    _check_response_size(len(buffer) + len(chunk), request)
                    buffer.extend(chunk)
        finally:
            await response.aclose()
        body = bytes(buffer)
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                data = json.loads(body)
            except ValueError:
                pass
            else:
                redacted = redact(data)
                if redacted != data:
                    body = json.dumps(redacted).encode()
                    _check_response_size(len(body), request)
        headers = response.headers.copy()
        # The body is now decoded and may have been redacted. Preserve the
        # other upstream headers and let Response recalculate its length.
        for name in ("content-encoding", "content-length", "transfer-encoding"):
            headers.pop(name, None)
        return httpx2.Response(
            response.status_code,
            headers=headers,
            content=body,
            request=request,
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
