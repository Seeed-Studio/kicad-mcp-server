"""Main entry point for KiCad MCP Server."""



def main() -> None:
    """Entry point for running the MCP server."""
    from .server import mcp

    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()
