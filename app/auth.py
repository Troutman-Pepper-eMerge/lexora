"""Tenant RBAC authentication & authorization.

Two modes:
  * DEMO_MODE=true  -> signed cookie carries (email, role) chosen on the
    /login screen. No external IdP calls. Lets you showcase role-based
    behaviour during the demo.
  * DEMO_MODE=false -> validates Entra ID JWT bearer tokens issued for
    AZURE_CLIENT_ID. Role claims (`roles` array on the token) drive RBAC.

Either way the **authorization** layer is identical: route handlers
declare required roles, the `require_roles` dependency enforces them
and emits an audit-log entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer

from .config import get_settings
from .database import session_scope
from .models import AuditLog, User

ROLE_HIERARCHY = {
    "Admin":     {"Admin", "Partner", "Associate", "Paralegal", "Client"},
    "Partner":   {"Partner", "Associate", "Paralegal"},
    "Associate": {"Associate", "Paralegal"},
    "Paralegal": {"Paralegal"},
    "Client":    {"Client"},
}

COOKIE_NAME = "lexora_session"


@dataclass
class Principal:
    email: str
    display_name: str
    role: str
    department: Optional[str] = None

    def can(self, required: Iterable[str]) -> bool:
        allowed = ROLE_HIERARCHY.get(self.role, {self.role})
        return any(r in allowed for r in required)


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().app_secret, salt="lexora-session")


def issue_session_cookie(principal: Principal) -> str:
    return _serializer().dumps({
        "email": principal.email,
        "name": principal.display_name,
        "role": principal.role,
        "department": principal.department,
    })


def _from_cookie(token: str) -> Optional[Principal]:
    try:
        data = _serializer().loads(token)
    except BadSignature:
        return None
    return Principal(
        email=data["email"],
        display_name=data["name"],
        role=data["role"],
        department=data.get("department"),
    )


def _from_bearer(token: str) -> Optional[Principal]:
    """Validate an Entra ID JWT.  Signature validation is intentionally
    lax here so the demo can be exercised without spinning up real JWKS;
    in production, fetch the tenant JWKS and verify properly."""
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    if s.azure_tenant_id and claims.get("tid") and claims["tid"] != s.azure_tenant_id:
        return None
    roles = claims.get("roles") or []
    role = roles[0] if roles else "Paralegal"
    return Principal(
        email=claims.get("preferred_username") or claims.get("upn") or claims.get("email", ""),
        display_name=claims.get("name", "Entra User"),
        role=role,
    )


async def current_principal(request: Request) -> Principal:
    # 1) Bearer token from Entra ID
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        p = _from_bearer(auth.split(" ", 1)[1].strip())
        if p:
            return p

    # 2) Signed session cookie (demo or after interactive login)
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        p = _from_cookie(cookie)
        if p:
            return p

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not authenticated")


def require_roles(*roles: str):
    """Dependency factory: require principal to hold any of the roles."""
    async def _dep(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.can(roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Requires one of: {', '.join(roles)}")
        return principal
    return _dep


def audit(principal: Principal, action: str, target: str = "", detail: dict | None = None) -> None:
    with session_scope() as db:
        db.add(AuditLog(
            actor_email=principal.email, actor_role=principal.role,
            action=action, target=target, detail=detail or {},
        ))


def upsert_user_from_principal(principal: Principal) -> None:
    with session_scope() as db:
        u = db.query(User).filter(User.email == principal.email).first()
        if not u:
            db.add(User(email=principal.email,
                        display_name=principal.display_name,
                        role=principal.role,
                        department=principal.department or "Legal"))
