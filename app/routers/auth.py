"""Auth router - demo login + Entra ID metadata."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
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
