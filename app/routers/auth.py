"""Auth router - demo login + Entra ID OAuth2 flow."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth import (COOKIE_NAME, Principal, audit, current_principal,
                    issue_session_cookie, upsert_user_from_principal)
from ..config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEMO_PROFILES = [
    {"email": "hpatel@troutman-demo.com",  "name": "Harini Patel",    "role": "Partner",   "department": "Litigation"},
    {"email": "ssharma@troutman-demo.com", "name": "Sasha Sharma",    "role": "Associate", "department": "Litigation"},
    {"email": "rkapoor@troutman-demo.com", "name": "Riya Kapoor",     "role": "Paralegal", "department": "Litigation"},
    {"email": "admin@troutman-demo.com",   "name": "Alex Morgan",     "role": "Admin",     "department": "IT"},
]


class LoginRequest(BaseModel):
    email: str


@router.get("/login")
def login_redirect():
    s = get_settings()
    if s.demo_mode:
        return RedirectResponse("/login", status_code=302)
    from ..entra import build_auth_url
    return RedirectResponse(build_auth_url(secrets.token_urlsafe(16)), status_code=302)


@router.get("/callback")
def oauth_callback(request: Request, code: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"Entra ID error: {error}")
    if not code:
        raise HTTPException(400, "Missing authorization code")
    from ..entra import exchange_code
    result = exchange_code(code)
    if "error" in result:
        raise HTTPException(400, result.get("error_description", result["error"]))

    claims = result.get("id_token_claims", {})
    s = get_settings()
    if claims.get("tid") != s.azure_tenant_id:
        raise HTTPException(403, "Tenant not authorized")

    from ..auth import _strip_app_role
    roles = claims.get("roles") or []
    principal = Principal(
        email=claims.get("preferred_username") or claims.get("upn") or "",
        display_name=claims.get("name", ""),
        role=_strip_app_role(roles[0]) if roles else "Client",
    )
    upsert_user_from_principal(principal)
    cookie = issue_session_cookie(principal)
    audit(principal, "login", target=principal.email)

    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(COOKIE_NAME, cookie, httponly=True, samesite="lax", max_age=60 * 60 * 8)
    return resp


@router.get("/profiles")
def list_demo_profiles():
    if not get_settings().demo_mode:
        raise HTTPException(404, "Demo mode disabled")
    return {"profiles": DEMO_PROFILES}


@router.post("/login")
def demo_login(body: LoginRequest, response: Response):
    if not get_settings().demo_mode:
        raise HTTPException(404, "Demo mode disabled - use Entra ID bearer token")
    profile = next((p for p in DEMO_PROFILES if p["email"] == body.email), None)
    if not profile:
        raise HTTPException(404, "Unknown demo profile")
    principal = Principal(email=profile["email"], display_name=profile["name"],
                          role=profile["role"], department=profile["department"])
    upsert_user_from_principal(principal)
    cookie = issue_session_cookie(principal)
    response.set_cookie(COOKIE_NAME, cookie, httponly=True, samesite="lax",
                        max_age=60 * 60 * 8)
    audit(principal, "login", target=principal.email)
    return {"principal": principal.__dict__}


@router.post("/logout")
def logout(response: Response, principal: Principal = Depends(current_principal)):
    audit(principal, "logout", target=principal.email)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(principal: Principal = Depends(current_principal)):
    return {"principal": principal.__dict__}
