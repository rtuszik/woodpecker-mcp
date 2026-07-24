import os
from dataclasses import dataclass

import httpx
from fastmcp import FastMCP

from woodpecker_mcp.auth import WoodpeckerAuth
from woodpecker_mcp.logs import register_log_tool
from woodpecker_mcp.redact import RedactingTransport
from woodpecker_mcp.spec import load_spec, prepare_spec

_TRUTHY = {"1", "true", "yes", "on"}
_TRANSPORTS = {"http", "stdio"}


@dataclass(frozen=True)
class Settings:
    server_url: str
    # Optional under http, where each client sends its own bearer token; used
    # as a shared fallback. Required under stdio, which has no request headers.
    token: str | None = None
    read_only: bool = False
    transport: str = "http"
    host: str = "0.0.0.0"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "Settings":
        transport = os.environ.get("WOODPECKER_MCP_TRANSPORT", cls.transport).lower()
        if transport not in _TRANSPORTS:
            msg = (
                "WOODPECKER_MCP_TRANSPORT must be one of "
                f"{sorted(_TRANSPORTS)}, got {transport!r}"
            )
            raise ValueError(msg)
        token = os.environ.get("WOODPECKER_TOKEN")
        if transport == "stdio" and not token:
            msg = "WOODPECKER_TOKEN is required for the stdio transport"
            raise ValueError(msg)
        return cls(
            server_url=os.environ["WOODPECKER_SERVER"],
            token=token,
            read_only=os.environ.get("WOODPECKER_MCP_READ_ONLY", "").lower() in _TRUTHY,
            transport=transport,
            host=os.environ.get("HOST", cls.host),
            port=int(os.environ.get("PORT", cls.port)),
        )


def create_server(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> FastMCP:
    client = httpx.AsyncClient(
        base_url=settings.server_url.rstrip("/") + "/api",
        auth=WoodpeckerAuth(settings.token),
        transport=RedactingTransport(transport or httpx.AsyncHTTPTransport()),
    )
    spec = prepare_spec(load_spec(), read_only=settings.read_only)
    mcp = FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="Woodpecker CI",
    )
    register_log_tool(mcp, client)
    return mcp
