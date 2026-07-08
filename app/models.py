"""SQLAlchemy ORM models for LEXORA case management."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (Column, Integer, String, Text, DateTime, Float,
                        ForeignKey, Boolean, JSON)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # Admin | Partner | Associate | Paralegal | Client
    department = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True)
    case_number = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    client_name = Column(String(255))
    practice_area = Column(String(100), index=True)        # IP, M&A, Litigation, etc.
    case_type = Column(String(100))                         # Civil, Criminal, Contract...
    status = Column(String(50), index=True)                 # Open / Discovery / Trial / Settled / Closed
    priority = Column(String(20))                           # Low / Medium / High / Critical
    jurisdiction = Column(String(100), index=True)          # State (e.g., California)
    court = Column(String(255))
    judge = Column(String(255))
    opposing_counsel = Column(String(255))
    filed_date = Column(DateTime)
    closed_date = Column(DateTime)
    estimated_value = Column(Float)                         # USD
    billable_hours = Column(Float, default=0.0)
    lead_attorney_id = Column(Integer, ForeignKey("users.id"))
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead_attorney = relationship("User", foreign_keys=[lead_attorney_id])
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="case", cascade="all, delete-orphan")
    notes = relationship("CaseNote", back_populates="case", cascade="all, delete-orphan")
    events = relationship("CaseEvent", back_populates="case", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), index=True)
    filename = Column(String(512), nullable=False)
    file_type = Column(String(20))                          # pdf, docx, pptx, json, txt
    file_path = Column(String(1024))                        # local path under DOCS_DIR
    size_bytes = Column(Integer)
    page_count = Column(Integer)
    doc_category = Column(String(100))                      # Pleading / Discovery / Contract / Brief
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    indexed = Column(Boolean, default=False)
    summary = Column(Text)
    extracted_text = Column(Text)
    doc_metadata = Column(JSON)

    case = relationship("Case", back_populates="documents")


class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), index=True)
    title = Column(String(255), nullable=False)
    appointment_type = Column(String(50))   # Hearing / Deposition / Meeting / Filing-Deadline
    location = Column(String(255))
    scheduled_at = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, default=60)
    attendees = Column(JSON)                # list of user emails
    status = Column(String(30), default="scheduled")  # scheduled / completed / cancelled / rescheduled
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="appointments")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    recipient_email = Column(String(255), index=True)
    channel = Column(String(20))             # email / sms / inapp
    subject = Column(String(255))
    body = Column(Text)
    status = Column(String(20), default="queued")   # queued / sent / failed
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class CaseNote(Base):
    __tablename__ = "case_notes"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), index=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="notes")


class CaseEvent(Base):
    """A milestone on a case's history timeline (received, filed, hearings…)."""
    __tablename__ = "case_events"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), index=True)
    category = Column(String(30), index=True)   # intake / filing / discovery / hearing / motion / settlement / closed / other
    title = Column(String(255), nullable=False)
    description = Column(Text)
    event_date = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="events")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    actor_email = Column(String(255), index=True)
    actor_role = Column(String(50))
    action = Column(String(100))
    target = Column(String(255))
    detail = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
