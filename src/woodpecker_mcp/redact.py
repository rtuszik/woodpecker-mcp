"""Scrub credentials from upstream responses.

Woodpecker returns agent registration tokens in cleartext on the agent
endpoints (for admin PATs); nothing an MCP client receives should contain
them. Redaction happens at the HTTP transport so every tool is covered.
"""

import json
from typing import Any

import httpx2

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {"token"}


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
        if not response.headers.get("content-type", "").startswith("application/json"):
            return response
        body = await response.aread()
        try:
            data = json.loads(body)
        except ValueError:
            return response
        redacted = redact(data)
        if redacted == data:
            return response
        return httpx2.Response(
            response.status_code,
            headers={"content-type": "application/json"},
            content=json.dumps(redacted).encode(),
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
