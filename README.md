# woodpecker-mcp

An MCP server for [Woodpecker CI](https://woodpecker-ci.org/), generated from
the Woodpecker OpenAPI spec with [fastmcp](https://gofastmcp.com/). Both
streamable HTTP (default) and stdio are supported.

The server supports stateless MCP (spec `2026-07-28`),
so any number of replicas can run behind a plain load balancer without
session affinity.

Only a subset of the Woodpecker API is exposed: read access to repos,
pipelines, logs, orgs, and agents, plus five pipeline write operations
(trigger, restart, cancel, approve, decline). Management of repos, secrets,
crons, and agents is not exposed, and neither is forge or system
administration.

## Tools

| Area                                 | Tools                                                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Repos                                | `list_repos`, `lookup_repo`, `get_repo`, `get_repo_permissions`, `list_branches`, `list_pull_requests` |
| Pipelines                            | `list_pipelines`, `get_pipeline`, `get_pipeline_config`, `get_pipeline_metadata`                       |
| Pipeline ops (write)                 | `trigger_pipeline`, `restart_pipeline`, `cancel_pipeline`, `approve_pipeline`, `decline_pipeline`      |
| Logs                                 | `get_step_logs`                                                                                        |
| Orgs                                 | `lookup_org`, `get_org`, `get_org_permissions`                                                         |
| Queue & agents                       | `get_queue_info`, `list_agents`, `get_agent`, `list_agent_tasks`                                       |
| Secrets & registries (metadata only) | `list_repo_secrets`, `list_org_secrets`, `list_repo_registries`, `list_org_registries`                 |

`get_step_logs` returns plain text and defaults to the last 200 lines.

## Configuration

| Variable                   | Required   | Description                                                                |
| -------------------------- | ---------- | -------------------------------------------------------------------------- |
| `WOODPECKER_SERVER`        | yes        | Woodpecker server URL, e.g. `https://ci.example.com` (`/api` is appended). |
| `WOODPECKER_TOKEN`         | stdio only | Personal access token. Optional with streamable HTTP, see below.           |
| `WOODPECKER_MCP_READ_ONLY` | no         | `true`, `1`, `yes`, or `on` removes the five write tools.                  |
| `WOODPECKER_MCP_TRANSPORT` | no         | `http` (default) or `stdio`.                                               |
| `HOST`                     | no         | Bind address for streamable HTTP. Default `0.0.0.0`.                       |
| `PORT`                     | no         | Bind port for streamable HTTP. Default `8000`.                             |

## Authentication

With streamable HTTP, each client sends its own Woodpecker personal access
token as a bearer header:

```text
Authorization: Bearer <woodpecker-token>
```

The token is forwarded to Woodpecker for that request only, so clients never
share credentials. Requests without a token fall back to `WOODPECKER_TOKEN` if
set and are rejected otherwise.

With stdio there are no request headers, so `WOODPECKER_TOKEN` is required.

The server does not authenticate clients itself, so run it on a trusted network
or behind TLS. `token` fields in Woodpecker responses, such as agent
registration tokens, are redacted before they reach the client.

## Running

### Docker (streamable HTTP)

```sh
docker run -p 8000:8000 \
  -e WOODPECKER_SERVER=https://ci.example.com \
  ghcr.io/rtuszik/woodpecker-mcp:latest
```

Clients send their own tokens, so `WOODPECKER_TOKEN` is optional here. Set it
to provide a fallback for clients without one.

The streamable HTTP endpoint is `http://<host>:8000/mcp`.

Clients on protocol versions older than `2026-07-28` are served in stateless
mode, without an `Mcp-Session-Id` or a standalone SSE stream.

### Connecting a client (streamable HTTP)

Claude Code:

```sh
claude mcp add --transport http woodpecker https://your-mcp-host/mcp \
  --header "Authorization: Bearer <your-woodpecker-token>"
```

Generic MCP client config:

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

Replace `your-mcp-host` with your server's address. Some clients may refuse to send
an `Authorization` header over plain `http://`, so terminate TLS at a reverse
proxy for anything beyond localhost.

### uvx (stdio)

The package is published on PyPI as
[`woodpecker-ci-mcp`](https://pypi.org/project/woodpecker-ci-mcp/). With
`WOODPECKER_MCP_TRANSPORT=stdio`, a client can start the server directly.

Claude Code:

```sh
claude mcp add woodpecker \
  --env WOODPECKER_SERVER=https://ci.example.com \
  --env WOODPECKER_TOKEN=... \
  --env WOODPECKER_MCP_TRANSPORT=stdio \
  -- uvx woodpecker-ci-mcp
```

Generic MCP client config:

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

## Development

```sh
mise install
uv sync            # install
uv run pytest      # tests
mise run check     # format, lint, typecheck, tests
```

The OpenAPI spec is in `src/woodpecker_mcp/openapi.yaml` and the tool allowlist
is in `src/woodpecker_mcp/spec.py`.
