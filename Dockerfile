# renovate: datasource=docker depName=ghcr.io/astral-sh/uv versioning=docker
ARG UV_VERSION=0.12.3
# renovate: datasource=docker depName=dhi.io/python versioning=docker
ARG PYTHON_VERSION=3.14

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM dhi.io/python:${PYTHON_VERSION}-alpine3.23-dev AS builder
COPY --from=uv /uv /usr/local/bin/uv

# no managed CPython, venv must link the base image python
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM dhi.io/python:${PYTHON_VERSION}-alpine3.23
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["/app/.venv/bin/python", "-m", "woodpecker_mcp"]
