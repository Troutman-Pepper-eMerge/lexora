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

# Docker / ACA deployment (tag = short git commit hash)
make build    # docker buildx build --platform linux/amd64
make push     # az acr login + docker push
make update   # az containerapp update
make deploy   # all three
```

There are no tests in this codebase.

## Architecture

LEXORA is an Azure-native litigation management SPA: FastAPI backend + vanilla JS frontend, with a LangGraph agentic layer and a FastMCP tool server running as a separate subprocess.

```
Browser (vanilla JS)
  → FastAPI routers (/api/*)
      → auth.py          — session cookie or Entra ID bearer token
      → agent/graph.py   — LangGraph react agent (START→agent→tools loop)
      → analytics.py     — KPIs, pattern detection, outcome predictor
      → document_processor.py / vector_store.py  [currently stubbed]
      → database.py      — SQLAlchemy sessions
  → app/mcp/server.py    — FastMCP (separate process, :8765)
```

### Non-obvious patterns

**Single TOOL_REGISTRY** — `app/agent/tools.py` defines every tool exactly once as `TOOL_REGISTRY = {"name": (fn, description)}`. The LangGraph agent (`agent/graph.py`) wraps these as `StructuredTool` instances; `mcp/server.py` registers the same callables with FastMCP. Never add a tool to one without the other — always go through the registry.

**Lazy cached singletons** — `get_settings()`, all Azure clients (`get_credential`, `get_chat_llm`, `get_embeddings`), and the compiled LangGraph graph (`_compiled_graph()`) are all `@lru_cache`. They initialize on first call and are effectively module-level globals. Mutating settings or clients at runtime won't work.

**Vector store is stubbed** — `app/vector_store.py` contains a full `_LocalFaiss` implementation and Azure AI Search backend, but all public functions (`semantic_search`, `add_chunks`, `embed_texts`, `embed_query`, `index_stats`) return empty values. `faiss-cpu` is not in `requirements.txt`. The `query_documents` tool will always return no results until this is wired up.

**Document processing is disabled** — `_process_uploaded_document` in `app/routers/documents.py` is commented out. Uploads create a DB record but no extraction, classification, summarization, or embedding runs. The `/documents/{doc_id}/analyze` endpoint is also a no-op.

**Dual-mode auth** — `DEMO_MODE=true` (default): POST email to `/api/auth/login`, get a signed `itsdangerous` cookie. `DEMO_MODE=false`: client supplies an Entra ID bearer token. The JWT validation in `auth.py::_from_bearer()` currently skips signature verification — this must be hardened before real production use. Role hierarchy: `Admin ⊇ Partner ⊇ Associate ⊇ Paralegal`, `Client` is isolated.

**Analytics has two pattern engines** — `detect_patterns()` is pure statistical (9 threshold detectors). `hybrid_patterns()` adds an LLM discovery layer that builds a grounded evidence pack and asks the model for cross-signal patterns; falls back to statistical-only if Azure OpenAI is unreachable. `predict_case_outcome()` uses explicit per-feature coefficients plus LLM narration.

**DB session patterns** — two coexist: `session_scope()` (context manager, used in tool/service layer) and `get_db()` (FastAPI dependency). Don't mix them in the same call chain.

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
| `AZURE_SEARCH_ENDPOINT` | `""` | Optional — enables Azure AI Search instead of local FAISS |

In production (ACA), `.env` is excluded from the image — all values must be set as ACA environment variables. Locally, copy `.env.example` to `.env`.

## Deployment notes

- ACA ingress target port: **8000**
- Liveness + readiness probes: HTTP GET `/api/health`, port 8000, `initialDelaySeconds: 10`
- MCP subprocess is disabled in the container (`--no-mcp`). Port 8765 is not reachable via ACA ingress.
- PostgreSQL firewall must allow Azure services. `DATABASE_URL` must be the full connection string value only — no `KEY=` prefix.
- `init_db()` runs `create_all()` on startup — schema is created automatically on first boot against a new database.
