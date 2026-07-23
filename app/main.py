"""LEXORA FastAPI entrypoint."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import APP_NAME, APP_TAGLINE, __version__
from .config import get_settings
from .database import init_db
from .routers import analytics as analytics_router
from .routers import appointments as appointments_router
from .routers import auth as auth_router
from .routers import cases as cases_router
from .routers import chat as chat_router
from .routers import documents as documents_router
from .routers import notifications as notifications_router

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

app = FastAPI(title=APP_NAME, version=__version__, description=APP_TAGLINE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.on_event("startup")
def _startup():
    init_db()


# --- API routers ----
for r in (auth_router.router, cases_router.router, documents_router.router,
          chat_router.router, analytics_router.router,
          appointments_router.router, notifications_router.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": __version__,
            "demo_mode": settings.demo_mode}


@app.get("/api/health/services")
def health_services():
    """Lightweight reachability probe for each backing service.

    Returns a coarse "ok | degraded | down" per component without making
    expensive calls. Used by the dashboard footer / status widgets.
    """
    from sqlalchemy import text as _sql_text
    from .database import SessionLocal
    from .vector_store import index_stats

    services: dict[str, dict] = {}

    # --- SQLite ---
    try:
        with SessionLocal() as db:
            db.execute(_sql_text("SELECT 1"))
        services["database"] = {"status": "ok", "kind": "sqlite"}
    except Exception as exc:  # pragma: no cover - demo path
        services["database"] = {"status": "down", "error": str(exc)}

    # --- Azure OpenAI (config-only check, no network call) ---
    aoai_ok = bool(settings.azure_openai_endpoint and settings.azure_openai_chat_deployment)
    services["azure_openai"] = {
        "status": "ok" if aoai_ok else "down",
        "endpoint": settings.azure_openai_endpoint or None,
        "chat_deployment": settings.azure_openai_chat_deployment or None,
        "embedding_deployment": settings.azure_openai_embedding_deployment or None,
        "auth": "rbac",
    }

    # --- Azure AI Search (optional) ---
    if settings.azure_search_endpoint:
        services["azure_search"] = {
            "status": "ok",
            "endpoint": settings.azure_search_endpoint,
            "index": settings.azure_search_index_name,
            "auth": "rbac",
        }
    else:
        services["azure_search"] = {"status": "disabled"}

    # --- Vector store (FAISS local or Azure AI Search) ---
    try:
        stats = index_stats()
        services["vector_store"] = {"status": "ok", **stats}
    except Exception as exc:  # pragma: no cover
        services["vector_store"] = {"status": "degraded", "error": str(exc)}

    # --- MCP server (config only - no probe) ---
    services["mcp"] = {
        "status": "ok",
        "transport": settings.mcp_transport,
        "host": settings.mcp_host,
        "port": settings.mcp_port,
    }

    overall = "ok"
    for s in services.values():
        st = s.get("status")
        if st == "down":
            overall = "down"; break
        if st == "degraded" and overall != "down":
            overall = "degraded"

    return {"status": overall, "services": services}


# --- Static frontend ---
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/login")
    def login_page():
        return FileResponse(str(FRONTEND_DIR / "login.html"))
