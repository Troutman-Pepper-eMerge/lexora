"""Appointments router."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_roles
from ..database import get_db
from ..models import Appointment, Notification

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class ScheduleBody(BaseModel):
    case_id: int
    title: str
    appointment_type: str = "Meeting"
    scheduled_at: str
    duration_minutes: int = 60
    location: str = ""
    attendees: list[str] = []


class RescheduleBody(BaseModel):
    new_datetime: str
    reason: str = ""


@router.get("")
def list_appointments(days: int = 30, case_id: Optional[int] = None,
                      db: Session = Depends(get_db),
                      _: Principal = Depends(current_principal)):
    q = db.query(Appointment).filter(
        Appointment.scheduled_at >= datetime.utcnow() - timedelta(days=7),
        Appointment.scheduled_at <= datetime.utcnow() + timedelta(days=days),
    )
    if case_id:
        q = q.filter(Appointment.case_id == case_id)
    rows = q.order_by(Appointment.scheduled_at.asc()).all()
    return {"count": len(rows), "appointments": [{
        "id": a.id, "case_id": a.case_id, "title": a.title,
        "type": a.appointment_type, "when": a.scheduled_at.isoformat(),
        "duration_minutes": a.duration_minutes, "location": a.location,
        "attendees": a.attendees, "status": a.status, "notes": a.notes,
    } for a in rows]}


@router.post("")
def create_appointment(body: ScheduleBody, db: Session = Depends(get_db),
                       principal: Principal = Depends(require_roles("Partner","Associate","Paralegal"))):
    try:
        when = datetime.fromisoformat(body.scheduled_at.replace("Z", ""))
    except ValueError:
        raise HTTPException(400, "scheduled_at must be ISO-8601")
    a = Appointment(case_id=body.case_id, title=body.title,
                    appointment_type=body.appointment_type,
                    scheduled_at=when, duration_minutes=body.duration_minutes,
                    location=body.location, attendees=body.attendees,
                    status="scheduled")
    db.add(a); db.commit(); db.refresh(a)
    audit(principal, "create_appointment", target=f"appt:{a.id}")
    return {"id": a.id, "when": a.scheduled_at.isoformat()}


@router.post("/{appt_id}/reschedule")
def reschedule(appt_id: int, body: RescheduleBody,
               db: Session = Depends(get_db),
               principal: Principal = Depends(require_roles("Partner","Associate","Paralegal"))):
    a = db.get(Appointment, appt_id)
    if not a:
        raise HTTPException(404, "Not found")
    try:
        new_dt = datetime.fromisoformat(body.new_datetime.replace("Z", ""))
    except ValueError:
        raise HTTPException(400, "new_datetime must be ISO-8601")
    prev = a.scheduled_at.isoformat()
    a.scheduled_at = new_dt
    a.status = "rescheduled"
    if body.reason:
        a.notes = (a.notes or "") + f"\n[reschedule] {body.reason}"
    for email in (a.attendees or []):
        db.add(Notification(
            case_id=a.case_id, recipient_email=email, channel="email",
            subject=f"Rescheduled: {a.title}",
            body=f"Moved from {prev} -> {new_dt.isoformat()}. {body.reason}",
            status="queued",
        ))
    db.commit()
    audit(principal, "reschedule_appointment",
          target=f"appt:{appt_id}", detail={"prev": prev, "new": new_dt.isoformat()})
    return {"id": appt_id, "previous": prev, "new": new_dt.isoformat()}
