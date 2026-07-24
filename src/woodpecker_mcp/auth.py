"""Upstream authentication for the Woodpecker API.

Each MCP client authenticates as its own Woodpecker user by sending an
`Authorization: Bearer <token>` header with every request; that token is
forwarded upstream. A shared `WOODPECKER_TOKEN`, if configured, is used only
as a fallback when a request carries no token of its own (and is the only
token available under the stdio transport, which has no per-request headers).
"""

from collections.abc import Generator

import httpx
from fastmcp.server.dependencies import get_http_headers

# fastmcp strips `authorization` from get_http_headers() by default; opt back
# in so we can read the caller's bearer token and forward it upstream.
_AUTH_HEADER = "authorization"
_BEARER_PREFIX = "bearer "


class MissingTokenError(RuntimeError):
    """Raised when a request has neither its own token nor a shared fallback."""

    def __init__(self) -> None:
        super().__init__(
            "No Woodpecker API token: send an 'Authorization: Bearer <token>' "
            "header, or configure WOODPECKER_TOKEN as a shared fallback."
        )


class WoodpeckerAuth(httpx.Auth):
    def __init__(self, default_token: str | None = None) -> None:
        self._default_token = default_token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response]:
        token = _caller_token() or self._default_token
        if not token:
            raise MissingTokenError
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def _caller_token() -> str | None:
    header = get_http_headers(include={_AUTH_HEADER}).get(_AUTH_HEADER, "")
    if header.lower().startswith(_BEARER_PREFIX):
        return header[len(_BEARER_PREFIX) :].strip() or None
    return None
