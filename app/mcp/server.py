"""FastMCP server exposing LEXORA's real-time tools.

The same tools used by the LangGraph agent are registered here, so any
MCP-aware client (Claude Desktop, IDEs, other agents) can drive LEXORA
remotely. Run with:

    python -m app.mcp.server          # http transport on 127.0.0.1:8765
    python -m app.mcp.server --stdio  # stdio transport

No values are mocked - every tool call executes against the live DB,
vector store and Azure OpenAI deployments.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from fastmcp import FastMCP

from ..agent.tools import TOOL_REGISTRY
from ..config import get_settings

log = logging.getLogger("lexora.mcp")

# Host / port are passed as FastMCP settings (FastMCP 0.4.x doesn't accept
# them as kwargs on .run()).  Transport on the wire is SSE over HTTP.
_settings = get_settings()
mcp = FastMCP("LEXORA", host=_settings.mcp_host, port=_settings.mcp_port)


def _register_all() -> None:
    """Auto-register every tool in the shared registry."""
    for name, (fn, desc) in TOOL_REGISTRY.items():
        # FastMCP introspects the function signature -> generates JSON-schema.
        mcp.tool(name=name, description=desc)(fn)


_register_all()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="LEXORA FastMCP server")
    parser.add_argument("--stdio", action="store_true",
                        help="Use stdio transport instead of HTTP.")
    args = parser.parse_args(argv)

    s = get_settings()
    logging.basicConfig(level=s.log_level)
    if args.stdio:
        log.info("LEXORA MCP server (stdio)")
        mcp.run(transport="stdio")
    else:
        log.info("LEXORA MCP server sse://%s:%s/sse", s.mcp_host, s.mcp_port)
        mcp.run(transport="sse")


if __name__ == "__main__":
    main(sys.argv[1:])
