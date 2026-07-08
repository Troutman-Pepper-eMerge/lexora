"""Azure clients constructed with RBAC (DefaultAzureCredential).

KEY-BASED AUTHENTICATION IS DISABLED ON THE TENANT.
All Azure resources are accessed via Entra ID identities.
The runtime principal (developer az-cli login, Managed Identity, or
service principal) must hold these role assignments:

  * Azure OpenAI resource  -> "Cognitive Services OpenAI User"
  * Azure AI Search (opt.) -> "Search Index Data Contributor"
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from .config import get_settings

_AOAI_SCOPE = "https://cognitiveservices.azure.com/.default"


@lru_cache
def get_credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


@lru_cache
def get_token_provider():
    return get_bearer_token_provider(get_credential(), _AOAI_SCOPE)


@lru_cache
def get_aoai_client() -> AzureOpenAI:
    s = get_settings()
    return AzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_version=s.azure_openai_api_version,
        azure_ad_token_provider=get_token_provider(),
    )


@lru_cache
def get_chat_llm(temperature: float = 0.1) -> AzureChatOpenAI:
    s = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_version=s.azure_openai_api_version,
        azure_deployment=s.azure_openai_chat_deployment,
        azure_ad_token_provider=get_token_provider(),
        temperature=temperature,
        streaming=False,
    )


@lru_cache
def get_embeddings() -> AzureOpenAIEmbeddings:
    s = get_settings()
    return AzureOpenAIEmbeddings(
        azure_endpoint=s.azure_openai_endpoint,
        api_version=s.azure_openai_api_version,
        azure_deployment=s.azure_openai_embedding_deployment,
        azure_ad_token_provider=get_token_provider(),
    )


def get_search_client() -> Optional[object]:
    """Returns an Azure AI Search client when configured, else None."""
    s = get_settings()
    if not s.azure_search_endpoint:
        return None
    from azure.search.documents import SearchClient
    return SearchClient(
        endpoint=s.azure_search_endpoint,
        index_name=s.azure_search_index_name,
        credential=get_credential(),
    )
