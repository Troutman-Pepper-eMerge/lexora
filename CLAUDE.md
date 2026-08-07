# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run locally (API on :8000, MCP on :8765)
python run.py

# API only — used in production container
python run.py --no-mcp

# Seed the database (only needed if data/lexora.db is absent)
python -m app.seed
python -m app.seed --force   # wipe and re-seed

# Docker / ACA deployment (tag = short git commit hash)
make build    # docker buildx build --platform linux/amd64
make push     # az acr login + docker push
make update   # az containerapp update
make deploy   # all three
```

There are no tests in this codebase. No linting or formatting tooling is configured (no ruff, flake8, mypy, or pre-commit hooks).

## Architecture

LEXORA is an Azure-native litigation management SPA: FastAPI backend + vanilla JS frontend, with a LangGraph agentic layer and a FastMCP tool server running as a separate subprocess.

```
Browser (vanilla JS — /frontend/, no bundler)
  → FastAPI routers (/api/*)
      → auth.py          — session cookie (demo) or Entra ID bearer token (prod)
      → entra.py         — MSAL ConfidentialClientApplication + JWKS token verify
      → agent/graph.py   — LangGraph react agent (START→agent→tools loop)
      → analytics.py     — KPIs, pattern detection, outcome predictor
      → timeline.py      — case milestone events (auto-inserted on case creation)
      → document_processor.py / vector_store.py  [see stubs section below]
      → database.py      — SQLAlchemy sessions
  → app/mcp/server.py    — FastMCP (separate process, :8765)
```

### Non-obvious patterns

**Single TOOL_REGISTRY** — `app/agent/tools.py` defines every tool exactly once as `TOOL_REGISTRY = {"name": (fn, description)}`. The LangGraph agent (`agent/graph.py`) wraps these as `StructuredTool` instances; `mcp/server.py` registers the same callables with FastMCP. Never add a tool to one without the other — always go through the registry.

**Lazy cached singletons** — `get_settings()`, all Azure clients (`get_credential`, `get_chat_llm`, `get_embeddings`), and the compiled LangGraph graph (`_compiled_graph()`) are all `@lru_cache`. They initialize on first call and are effectively module-level globals. Mutating settings or clients at runtime won't work. `get_chat_llm()` is cached *per temperature value* — `analytics.py` and `cases.py` (0.0/0.2) get different singletons from `agent/graph.py` (0.1).

**Vector store — FAISS is dead code** — `app/vector_store.py` contains a full `_LocalFaiss` class but `add_chunks()` and `semantic_search()` short-circuit to empty/0 unless `AZURE_SEARCH_ENDPOINT` is set, in which case Azure AI Search is used. `faiss-cpu` is not in `requirements.txt`. The `_LocalFaiss` class is unreachable in current routing.

**Document processing is disabled** — `_process_uploaded_document` in `app/routers/documents.py` runs as a FastAPI `BackgroundTask` but is effectively a no-op: the extract/summarize/embed lines are commented out. The `/documents/{doc_id}/analyze` endpoint also does nothing. Uploads create a DB record only.

**Dual-mode auth** — `DEMO_MODE=true` (default): POST email to `/api/auth/login`, get a signed `itsdangerous` cookie. `DEMO_MODE=false`: client supplies an Entra ID bearer token. The JWT validation in `auth.py::_from_bearer()` currently skips signature verification — this must be hardened before real production use. Role hierarchy: `Admin ⊇ Partner ⊇ Associate ⊇ Paralegal`, `Client` is isolated.

**Analytics has two pattern engines** — `detect_patterns()` is pure statistical (9 threshold detectors). `hybrid_patterns()` adds an LLM discovery layer that builds a grounded evidence pack and asks the model for cross-signal patterns; falls back to statistical-only if Azure OpenAI is unreachable. `predict_case_outcome()` uses explicit per-feature coefficient tables plus LLM narration.

**DB session patterns** — two coexist: `session_scope()` (context manager, used in tool/service layer) and `get_db()` (FastAPI dependency). Don't mix them in the same call chain. `audit()` uses `session_scope()` and commits synchronously inside every request handler; errors are silently swallowed.

**Timeline auto-insert** — `app/timeline.py::ensure_case_events()` is called on every `POST /api/cases`. It idempotently inserts a randomized-but-date-capped milestone sequence (`CaseEvent` rows: intake → filing → answer → discovery → hearing → motion → optional settlement/closed). `GET /api/cases/{id}` merges these with `Appointment` rows into a unified chronological timeline.

**Schema management** — there is no Alembic. `init_db()` calls `Base.metadata.create_all()` on startup. Adding or changing columns on an existing database requires manual intervention or dropping/recreating the SQLite file.

**Known open bug** — `CaseNote.author_id` is hardcoded to `None` in `app/routers/cases.py`. Notes are created without an author.

**Seed demo skew** — `app/seed.py` intentionally applies a `1.55x` adjudication-time multiplier to California cases to surface the headline analytics insight ("CA cases take 55% longer"). Use `--force` to reseed.

**Unused dependency** — `pandas==2.2.3` is in `requirements.txt` but not imported anywhere in the app code. `numpy` is used only in `vector_store.py` for FAISS (currently dead code).

### Frontend (vanilla JS, no build step)

`/frontend/` is served as `/static/`. Two HTML entry points: `index.html` (SPA) and `login.html`. CDN dependencies only (chart.js 4.4.6, gsap, Google Fonts) — no npm, no bundler.

`/frontend/js/app.js` exposes `window.LEXORA` IIFE with: `api()`, `toast()`, formatting helpers, `switchTo()`. All API calls use `credentials: "include"` to send the httponly `lexora_session` cookie. `api()` auto-redirects to `/api/auth/login` on 401.

Tab lifecycle: every tab switch fires a `lexora:view` CustomEvent; each JS module lazy-loads its data on that event. Theme toggle fires `lexora:rerender`; chart modules destroy and recreate Chart.js instances in response. `lexora:ready` fires once after auth succeeds.

Document uploads and case extract calls bypass `LEXORA.api()` and use raw `fetch()` with `FormData` (to avoid the `Content-Type: application/json` header that `api()` forces).

## Environment

| Variable | Default | Notes |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | `""` | Required |
| `AZURE_OPENAI_API_KEY` | `""` | Optional — omit to use RBAC/Managed Identity |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | `gpt-4o` | |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` | |
| `DATABASE_URL` | `sqlite:///./data/lexora.db` | PostgreSQL supported — `database.py` auto-detects by URL prefix |
| `APP_SECRET` | `lexora-dev-secret` | Must override in any real deployment — signs session cookies |
| `DEMO_MODE` | `true` | Set `false` to require real Entra ID tokens |
| `AZURE_TENANT_ID` | `""` | Required when `DEMO_MODE=false` |
| `AZURE_CLIENT_ID` | `""` | App registration client ID |
| `AZURE_SEARCH_ENDPOINT` | `""` | Optional — enables Azure AI Search (vector store is inert without this) |

In production (ACA), `.env` is excluded from the image — all values must be set as ACA environment variables. Locally, copy `.env.example` to `.env`.

## Deployment notes

- ACA ingress target port: **8000**
- Liveness + readiness probes: HTTP GET `/api/health`, port 8000, `initialDelaySeconds: 10`
- Extended health: `GET /api/health/services` — checks DB (`SELECT 1`), and config-presence of Azure OpenAI, Search, vector store, and MCP
- MCP subprocess is disabled in the container (`--no-mcp`). Port 8765 is not reachable via ACA ingress.
- PostgreSQL firewall must allow Azure services. `DATABASE_URL` must be the full connection string value only — no `KEY=` prefix.
- `init_db()` runs `create_all()` on startup — schema is created automatically on first boot against a new database.
- Makefile ACA coordinates (registry, image name, container app name, resource group) are hardcoded — update the Makefile if deploying to a different environment.
