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
| `WOODPECKER_TOKEN`         | yes      | Personal access token used for upstream API calls                                     |
| `WOODPECKER_MCP_READ_ONLY` | no       | `true`/`1`/`yes`/`on` removes the five write tools entirely                           |
| `WOODPECKER_MCP_TRANSPORT` | no       | `http` (default) or `stdio`                                                           |
| `HOST`                     | no       | Bind address (http only), default `0.0.0.0`                                           |
| `PORT`                     | no       | Bind port (http only), default `8000`                                                 |

An MCP client may act as a different Woodpecker user by sending an
`X-Woodpecker-Token` header; it overrides `WOODPECKER_TOKEN` for that request.

The server performs no authentication of its own, deploy it on a trusted
network. `token` fields in upstream responses (e.g. agent registration
tokens, which Woodpecker returns in cleartext to admin PATs) are redacted
before reaching the client.

## Running

### Docker (streamable HTTP)

```sh
docker run -p 8000:8000 \
  -e WOODPECKER_SERVER=https://ci.example.com \
  -e WOODPECKER_TOKEN=... \
  ghcr.io/rtuszik/woodpecker-mcp:latest
```

The MCP endpoint is `http://<host>:8000/mcp` (streamable HTTP).

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

In stdio mode the per-request `X-Woodpecker-Token` override does not apply;
the configured token is always used.

## Development

```sh
uv sync            # install
uv run pytest      # tests
mise run check     # format, lint, typecheck, tests
```

The bundled spec lives at `src/woodpecker_mcp/openapi.yaml`; the allowlist that
defines the tool surface is `src/woodpecker_mcp/spec.py`.
