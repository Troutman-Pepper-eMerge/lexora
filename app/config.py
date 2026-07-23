"""Centralised settings loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""  # If provided, uses key-based auth instead of RBAC
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    # Azure AI Search (optional)
    azure_search_endpoint: str = ""
    azure_search_index_name: str = "lexora-docs"

    # Entra ID
    azure_tenant_id: str = ""
    azure_client_id: str = ""

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret: str = "lexora-dev-secret"
    log_level: str = "INFO"

    # Database
    database_url: str = ""

    # Storage (reserved for future use)
    data_dir: str = "./data"
    docs_dir: str = "./docs"
    vector_index_path: str = "./data/vector_index"

    # MCP
    mcp_transport: str = "http"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    demo_mode: bool = True

    def ensure_dirs(self) -> None:
        pass


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
