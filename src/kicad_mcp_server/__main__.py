"""Main entry point for KiCad MCP Server."""



def main() -> None:
    """Entry point for running the MCP server."""
    from .server import mcp

    # show_banner=False skips log_server_banner(), which performs a *blocking*
    # httpx.get("https://pypi.org/pypi/fastmcp/json") before stdio_server()
    # opens the transport. That delays the initialize handshake and stalls the
    # client entirely when PyPI is slow or unreachable.
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
