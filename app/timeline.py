"""Case history timeline: milestone generation and assembly.

The timeline shown when a case is opened combines two sources:

* ``CaseEvent`` rows  – durable historical milestones (received, filed,
  discovery opened, first hearing, closed …).
* ``Appointment`` rows – scheduled hearings / depositions / deadlines that
  lawyers add over time (rendered as upcoming or past on the same axis).

Every entry carries a ``category`` that the frontend maps to a colour so the
vertical graphic is easy to follow at a glance.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session

from .models import Appointment, Case, CaseEvent

# Category -> human phase label (also used by the UI legend / colours).
CATEGORIES = ("intake", "filing", "discovery", "motion",
              "hearing", "settlement", "closed", "other")

# Map appointment types to a timeline category for consistent colouring.
_APPT_CATEGORY = {
    "Hearing": "hearing",
    "Deposition": "discovery",
    "Meeting": "other",
    "Filing-Deadline": "filing",
}


def build_baseline_events(case: Case, *, now: datetime | None = None) -> List[CaseEvent]:
    """Return a realistic milestone sequence for ``case``.

    Only milestones whose date is on/before ``now`` are emitted, so the list
    reads as genuine history rather than speculation. Always includes at least
    the intake + filing milestones.
    """
    now = now or datetime.utcnow()
    filed = case.filed_date or case.created_at or now
    events: List[CaseEvent] = []

    def add(offset_days: int, category: str, title: str, desc: str,
            anchor: datetime | None = None) -> None:
        when = (anchor or filed) + timedelta(days=offset_days)
        if when <= now:
            events.append(CaseEvent(
                case_id=case.id, category=category, title=title,
                description=desc, event_date=when,
            ))

    # 1) Case received by the firm (a few days before filing).
    add(-random.randint(3, 12), "intake", "Case Received",
        f"Matter intake completed for {case.client_name or 'the client'}.")

    # 2) Complaint filed with the court.
    add(0, "filing", "Complaint Filed",
        f"Complaint filed in {case.court or 'court'}"
        + (f" before {case.judge}." if case.judge else "."))

    # 3) Opposing party's answer / response.
    add(random.randint(21, 40), "filing", "Answer / Response Filed",
        f"{case.opposing_counsel or 'Opposing counsel'} filed their response.")

    # 4) Discovery phase opens.
    add(random.randint(55, 80), "discovery", "Discovery Commenced",
        "Initial disclosures exchanged; discovery requests served.")

    # 5) First substantive hearing.
    add(random.randint(88, 120), "hearing", "First Hearing",
        f"First hearing held{(' before ' + case.judge) if case.judge else ''}.")

    # 6) A dispositive motion round.
    add(random.randint(130, 180), "motion", "Motion Practice",
        "Dispositive motions briefed and argued.")

    # 7) Terminal milestone.
    if case.closed_date:
        events.append(CaseEvent(
            case_id=case.id, category="closed", title="Case Closed",
            description=f"Matter concluded ({case.status or 'Closed'}).",
            event_date=case.closed_date,
        ))
    elif (case.status or "").lower() in ("settlement talks", "settled"):
        add(random.randint(150, 210), "settlement", "Settlement Discussions",
            "Parties entered settlement negotiations.")

    events.sort(key=lambda e: e.event_date)
    return events


def ensure_case_events(db: Session, case: Case) -> None:
    """Idempotently create baseline milestones for a case that has none."""
    existing = db.query(CaseEvent).filter(CaseEvent.case_id == case.id).count()
    if existing:
        return
    for ev in build_baseline_events(case):
        db.add(ev)


def backfill_all(db: Session) -> int:
    """Generate baseline milestones for every case lacking them. Returns count."""
    created = 0
    for case in db.query(Case).all():
        if db.query(CaseEvent).filter(CaseEvent.case_id == case.id).count():
            continue
        evs = build_baseline_events(case)
        for ev in evs:
            db.add(ev)
        created += len(evs)
    if created:
        db.commit()
    return created


def build_timeline(case: Case, *, now: datetime | None = None) -> List[dict]:
    """Assemble the ordered, colour-coded timeline for the case detail view."""
    now = now or datetime.utcnow()
    entries: List[dict] = []

    for ev in case.events:
        entries.append({
            "kind": "milestone",
            "category": ev.category or "other",
            "title": ev.title,
            "description": ev.description or "",
            "date": ev.event_date.isoformat() if ev.event_date else None,
            "when_ts": ev.event_date or now,
            "upcoming": bool(ev.event_date and ev.event_date > now),
        })

    for a in case.appointments:
        cat = _APPT_CATEGORY.get(a.appointment_type or "", "other")
        loc = f" — {a.location}" if a.location else ""
        entries.append({
            "kind": "appointment",
            "category": cat,
            "title": a.title,
            "description": f"{a.appointment_type or 'Event'}{loc}",
            "date": a.scheduled_at.isoformat() if a.scheduled_at else None,
            "when_ts": a.scheduled_at or now,
            "upcoming": bool(a.scheduled_at and a.scheduled_at > now),
            "status": a.status,
        })

    entries.sort(key=lambda e: e["when_ts"])
    for e in entries:
        e.pop("when_ts", None)
    return entries
