"""Upstream authentication for the Woodpecker API.

Uses the configured PAT by default; an MCP client may act as a different
Woodpecker user by sending an X-Woodpecker-Token header with its request.
"""

from collections.abc import Generator

import httpx
from fastmcp.server.dependencies import get_http_headers

OVERRIDE_HEADER = "x-woodpecker-token"


class WoodpeckerAuth(httpx.Auth):
    def __init__(self, default_token: str) -> None:
        self._default_token = default_token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response]:
        token = get_http_headers().get(OVERRIDE_HEADER) or self._default_token
        request.headers["Authorization"] = f"Bearer {token}"
        yield request
