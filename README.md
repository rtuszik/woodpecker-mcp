# woodpecker-mcp

An MCP server for [Woodpecker CI](https://woodpecker-ci.org/), generated from the
Woodpecker OpenAPI spec with [fastmcp](https://gofastmcp.com/) and served over
streamable HTTP.

The tool surface is a curated allowlist, not the full API: all the reads an agent
needs to answer "why is my build red / stuck", plus exactly five write
operations (trigger, restart, cancel, approve, decline pipeline). Everything
else, repo/secret/cron/agent CRUD, forge and system administration, is not
exposed.

## Tools

| Area                                 | Tools                                                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Repos                                | `list_repos`, `lookup_repo`, `get_repo`, `get_repo_permissions`, `list_branches`, `list_pull_requests` |
| Pipelines                            | `list_pipelines`, `get_pipeline`, `get_pipeline_config`, `get_pipeline_metadata`                       |
| Pipeline ops (write)                 | `trigger_pipeline`, `restart_pipeline`, `cancel_pipeline`, `approve_pipeline`, `decline_pipeline`      |
| Logs                                 | `get_step_logs`, plain-text step logs, base64-decoded, tailed (default 200 lines)                      |
| Orgs                                 | `lookup_org`, `get_org`, `get_org_permissions`                                                         |
| Queue & agents                       | `get_queue_info`, `list_agents`, `get_agent`, `list_agent_tasks`                                       |
| Secrets & registries (metadata only) | `list_repo_secrets`, `list_org_secrets`, `list_repo_registries`, `list_org_registries`                 |

## Configuration

| Variable                   | Required | Description                                                                           |
| -------------------------- | -------- | ------------------------------------------------------------------------------------- |
| `WOODPECKER_SERVER`        | yes      | Base URL of the Woodpecker server, e.g. `https://ci.example.com` (`/api` is appended) |
| `WOODPECKER_TOKEN`         | see below | Personal access token used as a shared fallback for upstream API calls               |
| `WOODPECKER_MCP_READ_ONLY` | no       | `true`/`1`/`yes`/`on` removes the five write tools entirely                           |
| `WOODPECKER_MCP_TRANSPORT` | no       | `http` (default) or `stdio`                                                           |
| `HOST`                     | no       | Bind address (http only), default `0.0.0.0`                                           |
| `PORT`                     | no       | Bind port (http only), default `8000`                                                 |

### Multi-client authentication (http)

Each client authenticates as its own Woodpecker user by sending its personal
access token as a standard bearer header with every request:

```
Authorization: Bearer <woodpecker-token>
```

The token is forwarded upstream for that request only; a shared
`httpx.AsyncClient` reads the header per request, so clients never see each
other's credentials. `WOODPECKER_TOKEN` is optional under http, if set, it is
used as a fallback for requests that carry no bearer token of their own. A
request with neither its own token nor a configured fallback is rejected.

Under the **stdio** transport there are no per-request headers, so
`WOODPECKER_TOKEN` is required and always used.

The server performs no authentication of its own beyond forwarding the token,
deploy it on a trusted network (e.g. behind TLS). `token` fields in upstream
responses (e.g. agent registration tokens, which Woodpecker returns in
cleartext to admin PATs) are redacted before reaching the client.

## Running

### Docker (streamable HTTP)

Run the server once; each client authenticates per request with its own token,
so no shared `WOODPECKER_TOKEN` is required:

```sh
docker run -p 8000:8000 \
  -e WOODPECKER_SERVER=https://ci.example.com \
  ghcr.io/rtuszik/woodpecker-mcp:latest
```

Add `-e WOODPECKER_TOKEN=...` only if you want a shared fallback token for
clients that connect without one of their own.

The MCP endpoint is `http://<host>:8000/mcp` (streamable HTTP).

### Connecting a client (remote HTTP)

Point the client at wherever the server is deployed and send your own
Woodpecker personal access token as a bearer header. Replace the URL below with
your server's endpoint. In Claude Code:

```sh
claude mcp add --transport http woodpecker https://your-mcp-host/mcp \
  --header "Authorization: Bearer <your-woodpecker-token>"
```

or in a generic MCP client config:

```json
{
  "mcpServers": {
    "woodpecker": {
      "type": "http",
      "url": "https://your-mcp-host/mcp",
      "headers": {
        "Authorization": "Bearer <your-woodpecker-token>"
      }
    }
  }
}
```

Every request carries the header, so the server acts as your Woodpecker user
for that request only. Different clients can hit the same server with different
tokens.

A plain `http://` URL works too (e.g. on a trusted LAN without TLS), though
some clients refuse to send an `Authorization` header over non-HTTPS; prefer
terminating TLS at a reverse proxy for anything exposed beyond localhost.

### uvx (stdio)

The package is published to PyPI as
[`woodpecker-ci-mcp`](https://pypi.org/project/woodpecker-ci-mcp/). With
`WOODPECKER_MCP_TRANSPORT=stdio` the server speaks MCP over stdin/stdout, so a
client can spawn it directly. Register it with e.g. Claude Code:

```sh
claude mcp add woodpecker \
  --env WOODPECKER_SERVER=https://ci.example.com \
  --env WOODPECKER_TOKEN=... \
  --env WOODPECKER_MCP_TRANSPORT=stdio \
  -- uvx woodpecker-ci-mcp
```

or in a generic MCP client config:

```json
{
  "mcpServers": {
    "woodpecker": {
      "command": "uvx",
      "args": ["woodpecker-ci-mcp"],
      "env": {
        "WOODPECKER_SERVER": "https://ci.example.com",
        "WOODPECKER_TOKEN": "...",
        "WOODPECKER_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

In stdio mode there are no per-request headers, so the configured
`WOODPECKER_TOKEN` is always used.

## Development

```sh
uv sync            # install
uv run pytest      # tests
mise run check     # format, lint, typecheck, tests
```

The bundled spec lives at `src/woodpecker_mcp/openapi.yaml`; the allowlist that
defines the tool surface is `src/woodpecker_mcp/spec.py`.
