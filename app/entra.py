"""MSAL / Entra ID helpers: auth URL, code exchange, JWKS-backed JWT verification."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .config import get_settings

_SCOPES = []  # MSAL adds openid/profile automatically for confidential clients


@lru_cache
def _msal_app():
    import msal
    s = get_settings()
    return msal.ConfidentialClientApplication(
        client_id=s.azure_client_id,
        client_credential=s.azure_client_secret,
        authority=f"https://login.microsoftonline.com/{s.azure_tenant_id}",
    )


def build_auth_url(state: str) -> str:
    return _msal_app().get_authorization_request_url(
        scopes=_SCOPES,
        redirect_uri=get_settings().azure_redirect_uri,
        state=state,
    )


def exchange_code(code: str) -> dict:
    return _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=_SCOPES,
        redirect_uri=get_settings().azure_redirect_uri,
    )


@lru_cache
def _jwks_client():
    import jwt as _jwt
    s = get_settings()
    return _jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{s.azure_tenant_id}/discovery/v2.0/keys"
    )


def verify_bearer(token: str) -> Optional[dict]:
    """Verify an Entra ID access token. Falls back to unverified decode when
    AZURE_CLIENT_ID / AZURE_TENANT_ID are not configured (local dev only)."""
    import jwt
    s = get_settings()
    if not s.azure_client_id or not s.azure_tenant_id:
        try:
            return jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
            )
        except jwt.PyJWTError:
            return None
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], audience=s.azure_client_id
        )
    except jwt.PyJWTError:
        return None
    if claims.get("tid") != s.azure_tenant_id:
        return None
    return claims
