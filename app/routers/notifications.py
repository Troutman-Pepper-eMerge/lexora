"""Notifications router."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_roles
from ..database import get_db
from ..models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotifyBody(BaseModel):
    recipient_email: str
    subject: str
    body: str
    case_id: Optional[int] = None
    channel: str = "email"


@router.get("")
def list_notifications(limit: int = 50, db: Session = Depends(get_db),
                       _: Principal = Depends(current_principal)):
    rows = (db.query(Notification)
            .order_by(Notification.created_at.desc()).limit(limit).all())
    return {"count": len(rows), "notifications": [{
        "id": n.id, "case_id": n.case_id, "recipient": n.recipient_email,
        "channel": n.channel, "subject": n.subject, "body": n.body,
        "status": n.status,
        "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    } for n in rows]}


@router.post("")
def send(body: NotifyBody, db: Session = Depends(get_db),
         principal: Principal = Depends(require_roles("Partner","Associate","Paralegal","Admin"))):
    n = Notification(case_id=body.case_id, recipient_email=body.recipient_email,
                     channel=body.channel, subject=body.subject, body=body.body,
                     status="sent", sent_at=datetime.utcnow())
    db.add(n); db.commit(); db.refresh(n)
    audit(principal, "send_notification", target=body.recipient_email,
          detail={"subject": body.subject})
    return {"id": n.id, "status": n.status,
            "sent_at": n.sent_at.isoformat()}
