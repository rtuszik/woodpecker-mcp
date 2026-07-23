from woodpecker_mcp.__main__ import main


def test_main_runs_http_server_from_env(monkeypatch):
    monkeypatch.setenv("WOODPECKER_SERVER", "https://ci.example.com")
    monkeypatch.setenv("WOODPECKER_TOKEN", "secret")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")
    runs: list[dict] = []
    monkeypatch.setattr(
        "fastmcp.FastMCP.run", lambda self, **kwargs: runs.append(kwargs)
    )

    main()

    assert runs == [{"transport": "http", "host": "127.0.0.1", "port": 9000}]


def test_main_runs_stdio_server_from_env(monkeypatch):
    monkeypatch.setenv("WOODPECKER_SERVER", "https://ci.example.com")
    monkeypatch.setenv("WOODPECKER_TOKEN", "secret")
    monkeypatch.setenv("WOODPECKER_MCP_TRANSPORT", "stdio")
    runs: list[dict] = []
    monkeypatch.setattr(
        "fastmcp.FastMCP.run", lambda self, **kwargs: runs.append(kwargs)
    )

    main()

    assert runs == [{"transport": "stdio"}]
