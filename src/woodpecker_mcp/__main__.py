from woodpecker_mcp.server import Settings, create_server


def main() -> None:
    settings = Settings.from_env()
    server = create_server(settings)
    if settings.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
