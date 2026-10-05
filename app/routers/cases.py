"""Cases router."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     UploadFile)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_roles
from ..config import get_settings
from ..database import get_db
from ..document_processor import EXTRACTORS, extract_chunks, full_text
from ..models import Case, CaseNote
from ..timeline import build_timeline, ensure_case_events

router = APIRouter(prefix="/api/cases", tags=["cases"])
log = logging.getLogger("lexora.cases")


# Controlled vocabularies surfaced to the intake UI (kept aligned with seed).
PRACTICE_AREAS = ["Commercial Litigation", "Intellectual Property", "M&A",
                  "Employment", "Antitrust", "Securities", "Real Estate",
                  "Bankruptcy", "Tax", "Regulatory"]
CASE_TYPES = ["Contract Dispute", "Patent Infringement", "Class Action",
              "Wrongful Termination", "Breach of Fiduciary Duty",
              "Trade Secret", "Shareholder Derivative", "Merger Review",
              "Regulatory Investigation", "Other"]
STATUSES = ["Open", "Discovery", "Motion Practice", "Trial Prep",
            "Trial", "Settlement Talks", "Closed"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
JURISDICTIONS = ["California", "New York", "Texas", "Illinois", "Florida",
                 "Virginia", "Washington", "Massachusetts", "Delaware",
                 "New Jersey", "Georgia", "Pennsylvania"]


class CaseCreate(BaseModel):
    title: str
    client_name: Optional[str] = None
    practice_area: Optional[str] = None
    case_type: Optional[str] = None
    status: str = "Open"
    priority: str = "Medium"
    jurisdiction: Optional[str] = None
    court: Optional[str] = None
    judge: Optional[str] = None
    opposing_counsel: Optional[str] = None
    filed_date: Optional[str] = None
    estimated_value: Optional[float] = None
    summary: Optional[str] = None


class CaseUpdate(BaseModel):
    title: str
    client_name: Optional[str] = None
    practice_area: Optional[str] = None
    case_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    jurisdiction: Optional[str] = None
    court: Optional[str] = None
    judge: Optional[str] = None
    opposing_counsel: Optional[str] = None
    filed_date: Optional[str] = None
    estimated_value: Optional[float] = None
    summary: Optional[str] = None


@router.get("/intake-options")
def intake_options(_: Principal = Depends(current_principal)):
    """Vocabularies for the New Case form dropdowns."""
    return {
        "practice_areas": PRACTICE_AREAS, "case_types": CASE_TYPES,
        "statuses": STATUSES, "priorities": PRIORITIES,
        "jurisdictions": JURISDICTIONS,
    }


@router.get("")
def list_cases(
    q: Optional[str] = None,
    status: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Principal = Depends(current_principal),
):
    query = db.query(Case)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Case.title.ilike(like)) | (Case.client_name.ilike(like))
            | (Case.case_number.ilike(like))
        )
    if status:        query = query.filter(Case.status == status)
    if jurisdiction:  query = query.filter(Case.jurisdiction == jurisdiction)
    if priority:      query = query.filter(Case.priority == priority)
    rows = query.order_by(Case.filed_date.desc()).limit(limit).all()
    return {"count": len(rows), "cases": [_serialize(c) for c in rows]}


@router.get("/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db),
             _: Principal = Depends(current_principal)):
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    data = _serialize(c)
    data["documents"] = [{
        "id": d.id, "filename": d.filename, "category": d.doc_category,
        "indexed": d.indexed, "size_bytes": d.size_bytes,
        "pages": d.page_count, "summary": d.summary,
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
    } for d in c.documents]
    data["appointments"] = [{
        "id": a.id, "title": a.title, "type": a.appointment_type,
        "when": a.scheduled_at.isoformat(), "status": a.status,
        "location": a.location, "duration_minutes": a.duration_minutes,
        "attendees": a.attendees,
    } for a in c.appointments]
    data["notes"] = [{"id": n.id, "body": n.body,
                      "created_at": n.created_at.isoformat()}
                     for n in c.notes]
    data["timeline"] = build_timeline(c)
    return data


@router.post("/{case_id}/notes")
def add_note(case_id: int, body: dict,
             db: Session = Depends(get_db),
             principal: Principal = Depends(require_roles("Partner", "Associate", "Paralegal"))):
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    note = CaseNote(case_id=case_id, body=body.get("body", ""),
                    author_id=None)
    db.add(note); db.commit(); db.refresh(note)
    audit(principal, "add_note", target=f"case:{case_id}")
    return {"id": note.id, "body": note.body,
            "created_at": note.created_at.isoformat()}


# --------------------------------------------------------------------- #
# Case intake: create + AI-assisted extraction                          #
# --------------------------------------------------------------------- #
def _next_case_number(db: Session) -> str:
    """Generate the next sequential LEX-YYYY-NNNN identifier."""
    year = datetime.utcnow().year
    prefix = f"LEX-{year}-"
    rows = db.query(Case.case_number).filter(
        Case.case_number.like(f"{prefix}%")).all()
    max_seq = 1000
    for (num,) in rows:
        m = re.search(r"-(\d+)$", num or "")
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    # Also consider legacy numbers to avoid collisions on the unique index.
    return f"{prefix}{max_seq + 1}"


@router.post("")
def create_case(body: CaseCreate, db: Session = Depends(get_db),
                principal: Principal = Depends(
                    require_roles("Partner", "Associate", "Paralegal", "Admin"))):
    """Create a new case. Case number is auto-generated server-side."""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "title is required")

    filed = _parse_filed_date(body.filed_date) or datetime.utcnow()

    case_number = _next_case_number(db)
    c = Case(
        case_number=case_number, title=title,
        client_name=(body.client_name or "").strip() or None,
        practice_area=body.practice_area or None,
        case_type=body.case_type or None,
        status=body.status or "Open",
        priority=body.priority or "Medium",
        jurisdiction=body.jurisdiction or None,
        court=(body.court or "").strip() or None,
        judge=(body.judge or "").strip() or None,
        opposing_counsel=(body.opposing_counsel or "").strip() or None,
        filed_date=filed,
        estimated_value=body.estimated_value,
        billable_hours=0.0,
        summary=(body.summary or "").strip() or None,
    )
    db.add(c); db.commit(); db.refresh(c)
    ensure_case_events(db, c)
    db.commit()
    audit(principal, "create_case", target=f"case:{c.id}",
          detail={"case_number": case_number, "title": title})
    return _serialize(c)


@router.put("/{case_id}")
def update_case(
    case_id: int, body: CaseUpdate, db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles("Partner", "Associate", "Paralegal", "Admin")),
):
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "Case not found")

    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "title is required")

    c.title = title
    c.client_name = (body.client_name or "").strip() or None
    c.practice_area = body.practice_area or None
    c.case_type = body.case_type or None
    c.status = body.status or "Open"
    c.priority = body.priority or "Medium"
    c.jurisdiction = body.jurisdiction or None
    c.court = (body.court or "").strip() or None
    c.judge = (body.judge or "").strip() or None
    c.opposing_counsel = (body.opposing_counsel or "").strip() or None
    c.summary = (body.summary or "").strip() or None
    c.estimated_value = body.estimated_value
    c.filed_date = _parse_filed_date(body.filed_date)

    db.commit()
    db.refresh(c)
    ensure_case_events(db, c)
    db.commit()
    audit(principal, "update_case", target=f"case:{c.id}",
          detail={"case_number": c.case_number, "title": c.title})
    return _serialize(c)


def _parse_filed_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "")[:19])
    except ValueError:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _coerce_value(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    digits = re.sub(r"[^0-9.]", "", str(raw))
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _pick(value: Any, allowed: list[str]) -> Optional[str]:
    """Snap a free-text value to the closest allowed vocabulary entry."""
    if not value:
        return None
    v = str(value).strip().lower()
    for a in allowed:
        if a.lower() == v:
            return a
    for a in allowed:
        if v in a.lower() or a.lower() in v:
            return a
    return None


def _llm_extract_fields(source_text: str) -> Dict[str, Any]:
    """Use Azure OpenAI to pull structured case fields from raw text.
    Returns a dict of suggested fields (never raises; safe fallback = {})."""
    snippet = (source_text or "")[:12000]
    if not snippet.strip():
        return {}
    try:
        from ..azure_clients import get_chat_llm
        llm = get_chat_llm(temperature=0.0)
        prompt = (
            "You are LEXORA's case-intake assistant. Extract litigation case "
            "fields from the SOURCE document text below. Respond with STRICT "
            "JSON only, no prose, using this schema (use null when unknown; "
            "never invent facts):\n"
            '{"title": str, "client_name": str, "practice_area": str, '
            '"case_type": str, "jurisdiction": str, "court": str, '
            '"judge": str, "opposing_counsel": str, '
            '"estimated_value": number, "filed_date": "YYYY-MM-DD", '
            '"priority": "Low|Medium|High|Critical", '
            '"summary": "2-3 sentence neutral synopsis"}\n\n'
            f"SOURCE:\n{snippet}"
        )
        resp = llm.invoke(prompt)
        raw = getattr(resp, "content", str(resp))
        txt = raw.strip()
        txt = re.sub(r"^```(?:json)?", "", txt).strip()
        txt = re.sub(r"```$", "", txt).strip()
        s, e = txt.find("{"), txt.rfind("}")
        data = json.loads(txt[s:e + 1]) if s != -1 and e > s else {}
    except Exception as exc:                                  # pragma: no cover
        log.warning("case extract LLM failed: %s", exc)
        return {}

    # Normalize / snap to controlled vocab where applicable.
    out: Dict[str, Any] = {}
    for k in ("title", "client_name", "court", "judge",
              "opposing_counsel", "summary", "filed_date"):
        val = data.get(k)
        if val:
            out[k] = str(val).strip()
    out["practice_area"] = _pick(data.get("practice_area"), PRACTICE_AREAS)
    out["case_type"] = _pick(data.get("case_type"), CASE_TYPES)
    out["jurisdiction"] = _pick(data.get("jurisdiction"), JURISDICTIONS)
    out["priority"] = _pick(data.get("priority"), PRIORITIES) or "Medium"
    out["estimated_value"] = _coerce_value(data.get("estimated_value"))
    return {k: v for k, v in out.items() if v is not None}


@router.post("/extract")
async def extract_case_fields(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    principal: Principal = Depends(
        require_roles("Partner", "Associate", "Paralegal", "Admin")),
):
    """AI-assisted intake: accept an uploaded file, pasted text, or a URL and
    return *suggested* case fields. Nothing is persisted here."""
    raw_text = ""
    origin = "text"

    if file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in EXTRACTORS:
            raise HTTPException(
                400, f"Unsupported file type {suffix}. "
                     f"Allowed: {sorted(EXTRACTORS)}")
        s = get_settings()
        tmp_dir = Path(s.docs_dir) / "intake_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tmp_dir / f"{int(datetime.utcnow().timestamp()*1000)}_{Path(file.filename).name}"
        data = await file.read()
        tmp.write_bytes(data)
        try:
            raw_text = full_text(extract_chunks(tmp))
        except Exception as exc:
            raise HTTPException(422, f"Could not parse file: {exc}")
        finally:
            try: tmp.unlink()
            except OSError: pass
        origin = f"file:{file.filename}"

    elif source_url:
        if not re.match(r"^https?://", source_url, re.I):
            raise HTTPException(400, "source_url must be http(s)")
        try:
            import httpx
            with httpx.Client(timeout=15, follow_redirects=True) as cx:
                r = cx.get(source_url)
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                raw_text = json.dumps(r.json(), indent=2) \
                    if "json" in ct else r.text
        except Exception as exc:
            raise HTTPException(422, f"Could not fetch URL: {exc}")
        origin = f"url:{source_url}"

    elif text:
        raw_text = text
    else:
        raise HTTPException(400, "Provide a file, text, or source_url")

    fields = _llm_extract_fields(raw_text)
    audit(principal, "case_extract", target=origin,
          detail={"chars": len(raw_text), "fields": list(fields)})
    return {"source": origin, "fields": fields,
            "extracted_chars": len(raw_text)}


def _serialize(c: Case) -> dict:
    return {
        "id": c.id, "case_number": c.case_number, "title": c.title,
        "client_name": c.client_name, "practice_area": c.practice_area,
        "case_type": c.case_type, "status": c.status, "priority": c.priority,
        "jurisdiction": c.jurisdiction, "court": c.court, "judge": c.judge,
        "opposing_counsel": c.opposing_counsel,
        "filed_date": c.filed_date.isoformat() if c.filed_date else None,
        "closed_date": c.closed_date.isoformat() if c.closed_date else None,
        "estimated_value": c.estimated_value,
        "billable_hours": c.billable_hours,
        "summary": c.summary,
    }
