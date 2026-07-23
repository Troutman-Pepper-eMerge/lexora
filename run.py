"""LEXORA launcher - spins up both the FastAPI app and the FastMCP server.

Usage:
    python run.py          # API on :8000, MCP on :8765
    python run.py --no-mcp # API only
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import sys
import warnings

import uvicorn

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
except Exception:  # pragma: no cover
    LangChainPendingDeprecationWarning = Warning

from app.config import get_settings

# Suppress a known third-party pending deprecation warning from langgraph/checkpoint
# while staying on the current LangChain/LangGraph compatibility band.
warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change in a future version.*",
    category=LangChainPendingDeprecationWarning,
)


def _run_api(host: str, port: int, log_level: str) -> None:
    uvicorn.run("app.main:app", host=host, port=port,
                log_level=log_level.lower(), reload=False)


def _run_mcp() -> None:
    from app.mcp.server import main as mcp_main
    mcp_main([])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mcp", action="store_true",
                        help="Skip starting the FastMCP server")
    args = parser.parse_args()

    s = get_settings()
    logging.basicConfig(level=s.log_level,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    log = logging.getLogger("lexora.launcher")

    mcp_proc = None
    if not args.no_mcp:
        mcp_proc = mp.Process(target=_run_mcp, name="lexora-mcp", daemon=True)
        mcp_proc.start()
        log.info("FastMCP server started (pid=%s) on %s:%s",
                 mcp_proc.pid, s.mcp_host, s.mcp_port)

    log.info("LEXORA API at http://%s:%s", s.app_host, s.app_port)
    try:
        _run_api(s.app_host, s.app_port, s.log_level)
    finally:
        if mcp_proc and mcp_proc.is_alive():
            mcp_proc.terminate()
            mcp_proc.join(timeout=3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
