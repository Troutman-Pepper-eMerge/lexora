"""Chat / agent router."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..agent.graph import run_agent
from ..auth import Principal, audit, current_principal
from ..agent.tools import TOOL_REGISTRY

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None


@router.post("")
def chat(req: ChatRequest, principal: Principal = Depends(current_principal)):
    hist = [m.model_dump() for m in (req.history or [])]
    result = run_agent(req.message, history=hist)
    audit(principal, "agent_chat",
          detail={"message": req.message[:200], "trace_n": len(result["trace"])})
    return result


@router.get("/tools")
def list_tools(_: Principal = Depends(current_principal)):
    """Return MCP / agent tool catalog for the UI."""
    return {"tools": [{"name": n, "description": d}
                       for n, (_, d) in TOOL_REGISTRY.items()]}
