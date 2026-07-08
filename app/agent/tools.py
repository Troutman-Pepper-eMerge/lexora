"""Agent tools - real, live operations against the LEXORA database & RAG.

Each tool is defined ONCE here and reused in two places:
  * `app.mcp.server`  - exposed over the FastMCP transport (HTTP/stdio)
  * `app.agent.graph` - wrapped as a LangChain Tool for the LangGraph agent

Nothing here is hard-coded: every call hits SQLite / FAISS / Azure OpenAI
in real time.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from ..database import session_scope
from ..models import Appointment, Case, Document, Notification
from ..vector_store import semantic_search


# --------------------------------------------------------------------- #
# Helpers                                                               #
# --------------------------------------------------------------------- #
def _case_to_dict(c: Case) -> Dict[str, Any]:
    return {
        "id": c.id,
        "case_number": c.case_number,
        "title": c.title,
        "client": c.client_name,
        "practice_area": c.practice_area,
        "case_type": c.case_type,
        "status": c.status,
        "priority": c.priority,
        "jurisdiction": c.jurisdiction,
        "court": c.court,
        "judge": c.judge,
        "filed_date": c.filed_date.isoformat() if c.filed_date else None,
        "estimated_value": c.estimated_value,
        "billable_hours": c.billable_hours,
        "summary": c.summary,
    }


# --------------------------------------------------------------------- #
# Case search & retrieval                                               #
# --------------------------------------------------------------------- #
def search_cases(query: str = "", status: Optional[str] = None,
                 jurisdiction: Optional[str] = None,
                 priority: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Search cases by free text (matches title, client, case_number, summary)
    with optional filters."""
    with session_scope() as db:
        q = db.query(Case)
        if query:
            like = f"%{query}%"
            q = q.filter(or_(Case.title.ilike(like),
                             Case.client_name.ilike(like),
                             Case.case_number.ilike(like),
                             Case.summary.ilike(like)))
        if status:        q = q.filter(Case.status == status)
        if jurisdiction:  q = q.filter(Case.jurisdiction == jurisdiction)
        if priority:      q = q.filter(Case.priority == priority)
        rows = q.order_by(Case.priority.desc(), Case.filed_date.desc()).limit(limit).all()
        return {"count": len(rows), "cases": [_case_to_dict(c) for c in rows]}


def get_case_detail(case_id: int) -> Dict[str, Any]:
    """Return full case detail including documents, appointments, notes."""
    with session_scope() as db:
        c = db.get(Case, case_id)
        if not c:
            return {"error": f"Case {case_id} not found"}
        data = _case_to_dict(c)
        data["documents"] = [{
            "id": d.id, "filename": d.filename, "category": d.doc_category,
            "indexed": d.indexed, "pages": d.page_count, "summary": d.summary,
        } for d in c.documents]
        data["appointments"] = [{
            "id": a.id, "title": a.title, "type": a.appointment_type,
            "when": a.scheduled_at.isoformat(), "status": a.status,
            "location": a.location, "attendees": a.attendees,
        } for a in c.appointments]
        data["notes"] = [{"id": n.id, "body": n.body,
                          "created_at": n.created_at.isoformat()}
                         for n in c.notes]
        return data


# --------------------------------------------------------------------- #
# Document Q&A (RAG)                                                    #
# --------------------------------------------------------------------- #
def query_documents(question: str, case_id: Optional[int] = None,
                    top_k: int = 6) -> Dict[str, Any]:
    """Semantic search across ingested documents. Returns ranked passages
    with citations - the agent will synthesize the final answer."""
    hits = semantic_search(question, k=top_k, case_id=case_id)
    return {
        "question": question,
        "case_id": case_id,
        "results": [{
            "filename": h["filename"],
            "page": h["page"],
            "section": h["section"],
            "score": round(h["score"], 4),
            "snippet": (h["text"] or "")[:600],
            "doc_id": h.get("doc_id"),
            "case_id": h.get("case_id"),
        } for h in hits],
    }


# --------------------------------------------------------------------- #
# Appointments                                                          #
# --------------------------------------------------------------------- #
def list_upcoming_appointments(days: int = 30, case_id: Optional[int] = None) -> Dict[str, Any]:
    from datetime import timedelta
    with session_scope() as db:
        q = db.query(Appointment).filter(
            Appointment.scheduled_at >= datetime.utcnow(),
            Appointment.scheduled_at <= datetime.utcnow() + timedelta(days=days),
            Appointment.status == "scheduled",
        )
        if case_id:
            q = q.filter(Appointment.case_id == case_id)
        rows = q.order_by(Appointment.scheduled_at.asc()).all()
        return {"count": len(rows), "appointments": [{
            "id": a.id, "case_id": a.case_id, "title": a.title,
            "type": a.appointment_type, "when": a.scheduled_at.isoformat(),
            "duration_minutes": a.duration_minutes,
            "location": a.location, "attendees": a.attendees, "status": a.status,
        } for a in rows]}


def reschedule_appointment(appointment_id: int, new_datetime_iso: str,
                            reason: str = "") -> Dict[str, Any]:
    """Move an appointment to a new ISO-8601 timestamp."""
    try:
        new_dt = datetime.fromisoformat(new_datetime_iso.replace("Z", ""))
    except ValueError:
        return {"error": "new_datetime_iso must be ISO-8601, e.g. 2026-07-15T14:30:00"}
    with session_scope() as db:
        a = db.get(Appointment, appointment_id)
        if not a:
            return {"error": f"Appointment {appointment_id} not found"}
        prev = a.scheduled_at.isoformat() if a.scheduled_at else None
        a.scheduled_at = new_dt
        a.status = "rescheduled"
        if reason:
            a.notes = (a.notes or "") + f"\n[reschedule] {reason}"
        # auto-notify attendees
        for email in (a.attendees or []):
            db.add(Notification(
                case_id=a.case_id, recipient_email=email, channel="email",
                subject=f"Rescheduled: {a.title}",
                body=(f"'{a.title}' has been moved from {prev} to "
                      f"{new_dt.isoformat()}. Reason: {reason or 'n/a'}"),
                status="queued",
            ))
        return {"ok": True, "appointment_id": appointment_id,
                "previous": prev, "new": new_dt.isoformat()}


def schedule_appointment(case_id: int, title: str, appointment_type: str,
                          when_iso: str, attendees: List[str],
                          location: str = "", duration_minutes: int = 60) -> Dict[str, Any]:
    try:
        when = datetime.fromisoformat(when_iso.replace("Z", ""))
    except ValueError:
        return {"error": "when_iso must be ISO-8601"}
    with session_scope() as db:
        c = db.get(Case, case_id)
        if not c:
            return {"error": f"Case {case_id} not found"}
        a = Appointment(case_id=case_id, title=title,
                        appointment_type=appointment_type,
                        scheduled_at=when, duration_minutes=duration_minutes,
                        attendees=attendees, location=location,
                        status="scheduled")
        db.add(a); db.flush()
        return {"ok": True, "appointment_id": a.id,
                "when": when.isoformat(), "attendees": attendees}


# --------------------------------------------------------------------- #
# Notifications                                                         #
# --------------------------------------------------------------------- #
def send_notification(recipient_email: str, subject: str, body: str,
                      case_id: Optional[int] = None,
                      channel: str = "email") -> Dict[str, Any]:
    """Queue a notification. In production this would dispatch via Graph
    API / Twilio etc.; for the demo it persists and marks as sent."""
    with session_scope() as db:
        n = Notification(case_id=case_id, recipient_email=recipient_email,
                          channel=channel, subject=subject, body=body,
                          status="sent", sent_at=datetime.utcnow())
        db.add(n); db.flush()
        return {"ok": True, "notification_id": n.id, "sent_at": n.sent_at.isoformat()}


# --------------------------------------------------------------------- #
# Reports                                                               #
# --------------------------------------------------------------------- #
def generate_case_report(case_id: int) -> Dict[str, Any]:
    """Compile a structured report dict for a case (frontend renders it)."""
    detail = get_case_detail(case_id)
    if "error" in detail:
        return detail
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "case": detail,
        "headline": (f"{detail['case_number']} - {detail['title']} "
                     f"[{detail['status']} / {detail['priority']}]"),
        "doc_count": len(detail.get("documents", [])),
        "appt_count": len(detail.get("appointments", [])),
        "note_count": len(detail.get("notes", [])),
    }


def portfolio_analytics() -> Dict[str, Any]:
    """Return the analytics package used by dashboards / agent answers."""
    from ..analytics import (adjudication_time_by_state, cases_by_jurisdiction,
                              cases_by_practice, detect_patterns, kpi_overview,
                              monthly_filings, status_distribution,
                              value_by_practice)
    with session_scope() as db:
        return {
            "kpis": kpi_overview(db),
            "status_distribution": status_distribution(db),
            "by_practice": cases_by_practice(db),
            "by_jurisdiction": cases_by_jurisdiction(db),
            "value_by_practice": value_by_practice(db),
            "monthly_filings": monthly_filings(db),
            "adjudication_time_by_state": adjudication_time_by_state(db),
            "patterns": detect_patterns(db),
        }


# --------------------------------------------------------------------- #
# Registry                                                              #
# --------------------------------------------------------------------- #
TOOL_REGISTRY = {
    "search_cases": (search_cases,
        "Search cases by text / status / jurisdiction / priority."),
    "get_case_detail": (get_case_detail,
        "Return full detail for a single case by id."),
    "query_documents": (query_documents,
        "Semantic RAG search across ingested case documents."),
    "list_upcoming_appointments": (list_upcoming_appointments,
        "List scheduled appointments in the next N days."),
    "schedule_appointment": (schedule_appointment,
        "Create a new appointment on a case."),
    "reschedule_appointment": (reschedule_appointment,
        "Move an existing appointment and notify attendees."),
    "send_notification": (send_notification,
        "Queue a notification (email/sms/in-app)."),
    "generate_case_report": (generate_case_report,
        "Compile a structured report for a single case."),
    "portfolio_analytics": (portfolio_analytics,
        "Aggregate KPIs, distributions, and detected patterns across the firm."),
}
