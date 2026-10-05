"""Notification Rules router - event-driven notification subscriptions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_roles
from ..database import get_db
from ..models import NotificationRule

router = APIRouter(prefix="/api/notification-rules", tags=["notification-rules"])


class RuleCreate(BaseModel):
    rule_name: str
    trigger_type: str  # matter_assigned, status_changed, calendar_event, analytics_threshold, document_uploaded
    trigger_conditions: dict  # {"matter_ids": [1,2], "scope": "all_my_matters", "status": "Trial", etc.}
    channel: str  # email, sms, inapp
    message_type: str = "auto_summary"  # custom_message, report_link, auto_summary
    message_template: Optional[str] = None
    report_path: Optional[str] = None
    # Advanced options
    time_constraints: Optional[dict] = None  # {"business_hours_only": true, "weekdays_only": true}
    frequency_limit: Optional[dict] = None  # {"max_per_day": 5, "digest_mode": "daily"}
    condition_logic: str = "AND"  # AND / OR for combining conditions


class RuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    trigger_conditions: Optional[dict] = None
    channel: Optional[str] = None
    message_type: Optional[str] = None
    message_template: Optional[str] = None
    report_path: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("")
def list_rules(db: Session = Depends(get_db),
               principal: Principal = Depends(current_principal)):
    """List all notification rules for the current user."""
    rules = (db.query(NotificationRule)
             .filter(NotificationRule.user_email == principal.email)
             .order_by(NotificationRule.created_at.desc())
             .all())

    return {"count": len(rules), "rules": [{
        "id": r.id,
        "rule_name": r.rule_name,
        "trigger_type": r.trigger_type,
        "trigger_conditions": r.trigger_conditions,
        "channel": r.channel,
        "message_type": r.message_type,
        "message_template": r.message_template,
        "report_path": r.report_path,
        "enabled": r.enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rules]}


@router.post("")
def create_rule(body: RuleCreate, db: Session = Depends(get_db),
                principal: Principal = Depends(current_principal)):
    """Create a new notification rule with advanced conditions."""
    rule = NotificationRule(
        user_email=principal.email,
        rule_name=body.rule_name,
        trigger_type=body.trigger_type,
        trigger_conditions=body.trigger_conditions,
        channel=body.channel,
        message_type=body.message_type,
        message_template=body.message_template,
        report_path=body.report_path,
        time_constraints=body.time_constraints,
        frequency_limit=body.frequency_limit,
        condition_logic=body.condition_logic,
        enabled=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    audit(principal, "create_notification_rule", target=f"rule:{rule.id}",
          detail={"trigger": body.trigger_type, "channel": body.channel})

    return {"id": rule.id, "rule_name": rule.rule_name}


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, db: Session = Depends(get_db),
                principal: Principal = Depends(current_principal)):
    """Update an existing notification rule."""
    rule = db.get(NotificationRule, rule_id)
    if not rule or rule.user_email != principal.email:
        raise HTTPException(404, "Rule not found")

    if body.rule_name is not None:
        rule.rule_name = body.rule_name
    if body.trigger_conditions is not None:
        rule.trigger_conditions = body.trigger_conditions
    if body.channel is not None:
        rule.channel = body.channel
    if body.message_type is not None:
        rule.message_type = body.message_type
    if body.message_template is not None:
        rule.message_template = body.message_template
    if body.report_path is not None:
        rule.report_path = body.report_path
    if body.enabled is not None:
        rule.enabled = body.enabled

    db.commit()
    audit(principal, "update_notification_rule", target=f"rule:{rule_id}")

    return {"id": rule_id, "rule_name": rule.rule_name}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db),
                principal: Principal = Depends(current_principal)):
    """Delete a notification rule."""
    rule = db.get(NotificationRule, rule_id)
    if not rule or rule.user_email != principal.email:
        raise HTTPException(404, "Rule not found")

    db.delete(rule)
    db.commit()
    audit(principal, "delete_notification_rule", target=f"rule:{rule_id}")

    return {"status": "deleted"}
