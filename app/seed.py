"""Mock data seeder for the LEXORA demo.

Populates ~30 cases across multiple US jurisdictions with deliberately
skewed timelines so that the analytics layer can surface the headline
insight: 'California cases take materially longer to adjudicate.'
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .database import session_scope
from .models import (Appointment, Case, CaseNote, Document, Notification, User)

random.seed(42)

USERS = [
    ("admin@troutman-demo.com",    "Alex Morgan",      "Admin",     "IT"),
    ("hpatel@troutman-demo.com",   "Harini Patel",     "Partner",   "Litigation"),
    ("jwilliams@troutman-demo.com","Jordan Williams",  "Partner",   "M&A"),
    ("ssharma@troutman-demo.com",  "Sasha Sharma",     "Associate", "Litigation"),
    ("mlee@troutman-demo.com",     "Marcus Lee",       "Associate", "IP"),
    ("rkapoor@troutman-demo.com",  "Riya Kapoor",      "Paralegal", "Litigation"),
    ("tnguyen@troutman-demo.com",  "Tina Nguyen",      "Paralegal", "M&A"),
    ("client.acme@example.com",    "Acme Corp",        "Client",    "External"),
]

JURISDICTIONS = [
    # (state, courthouse, avg_days_skew)
    ("California",     "Superior Court of California, San Francisco",  1.55),
    ("New York",       "U.S. District Court, S.D.N.Y.",                1.00),
    ("Texas",          "Harris County District Court",                 0.85),
    ("Illinois",       "Cook County Circuit Court",                    0.95),
    ("Florida",        "Miami-Dade Circuit Court",                     0.90),
    ("Virginia",       "U.S. District Court, E.D. Va.",                0.70),  # rocket docket
    ("Washington",     "King County Superior Court",                   1.05),
    ("Massachusetts",  "Suffolk Superior Court",                       1.10),
]

PRACTICE_AREAS = ["Commercial Litigation", "Intellectual Property",
                  "M&A", "Employment", "Antitrust", "Securities"]
CASE_TYPES = ["Contract Dispute", "Patent Infringement", "Class Action",
              "Wrongful Termination", "Breach of Fiduciary Duty",
              "Trade Secret", "Shareholder Derivative"]
STATUSES = ["Open", "Discovery", "Motion Practice", "Trial Prep",
            "Trial", "Settlement Talks", "Closed"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]

JUDGES = ["Hon. Eleanor Vance", "Hon. Marcus Chen", "Hon. Patricia Alvarez",
          "Hon. Robert Okonkwo", "Hon. Lisa Tanaka", "Hon. James Reilly"]

OPPOSING = ["Skadden Arps", "Latham & Watkins", "DLA Piper",
            "Wachtell Lipton", "Kirkland & Ellis", "Sidley Austin"]


def seed(force: bool = False) -> None:
    with session_scope() as db:
        if db.query(User).count() > 0:
            if not force:
                print("Database already contains data. Use --force to reseed.")
                return

    if force:
        with session_scope() as db:
            for model in (Notification, Appointment, CaseNote, Document, Case, User):
                db.query(model).delete(synchronize_session=False)
        print("Existing data cleared.")

    with session_scope() as db:

        # ---- Users ----
        user_map: dict[str, User] = {}
        for email, name, role, dept in USERS:
            u = User(email=email, display_name=name, role=role, department=dept)
            db.add(u); db.flush()
            user_map[email] = u

        lead_emails = ["hpatel@troutman-demo.com", "jwilliams@troutman-demo.com",
                       "ssharma@troutman-demo.com", "mlee@troutman-demo.com"]

        # ---- Cases ----
        cases: list[Case] = []
        for i in range(1, 31):
            state, court, skew = random.choice(JURISDICTIONS)
            practice = random.choice(PRACTICE_AREAS)
            ctype = random.choice(CASE_TYPES)
            status = random.choices(STATUSES, weights=[3,4,4,3,2,3,5])[0]
            priority = random.choices(PRIORITIES, weights=[1,3,4,2])[0]
            base_days = random.randint(120, 420)
            duration = int(base_days * skew)
            filed = datetime.utcnow() - timedelta(days=duration + random.randint(0, 60))
            closed = (filed + timedelta(days=duration)) if status == "Closed" else None
            lead = user_map[random.choice(lead_emails)]
            c = Case(
                case_number=f"LEX-{2024 + (i % 3)}-{1000 + i}",
                title=f"{random.choice(['Acme', 'Globex', 'Initech', 'Umbrella', 'Hooli', 'Stark'])} "
                      f"v. {random.choice(['Wayne', 'Vandelay', 'Pied Piper', 'Soylent', 'Wonka', 'Tyrell'])}",
                client_name=random.choice(["Acme Corp", "Globex Inc.", "Initech LLC",
                                           "Umbrella Holdings", "Hooli Systems", "Stark Industries"]),
                practice_area=practice,
                case_type=ctype,
                status=status,
                priority=priority,
                jurisdiction=state,
                court=court,
                judge=random.choice(JUDGES),
                opposing_counsel=random.choice(OPPOSING),
                filed_date=filed,
                closed_date=closed,
                estimated_value=round(random.uniform(0.25, 50.0), 2) * 1_000_000,
                billable_hours=round(random.uniform(40, 1400), 1),
                lead_attorney_id=lead.id,
                summary=f"{ctype} pending in {state}. Lead counsel: {lead.display_name}. "
                        f"Current phase: {status}.",
            )
            db.add(c); db.flush()
            cases.append(c)

            # Notes
            for _ in range(random.randint(1, 4)):
                db.add(CaseNote(
                    case_id=c.id,
                    author_id=lead.id,
                    body=random.choice([
                        "Client briefing scheduled. Discovery requests under review.",
                        "Met with opposing counsel; settlement posture remains firm.",
                        "Drafted MIL on hearsay evidence. Awaiting partner review.",
                        "Expert witness retained; deposition prep in progress.",
                        "Motion to compel filed. Hearing set for next month.",
                    ]),
                ))

            # Appointments
            for j in range(random.randint(1, 3)):
                when = datetime.utcnow() + timedelta(days=random.randint(-14, 60),
                                                     hours=random.randint(9, 16))
                db.add(Appointment(
                    case_id=c.id,
                    title=random.choice(["Status Hearing", "Deposition", "Client Strategy Call",
                                          "Mediation Session", "Filing Deadline"]),
                    appointment_type=random.choice(["Hearing","Deposition","Meeting","Filing-Deadline"]),
                    location=court if j == 0 else "Conference Room 4B",
                    scheduled_at=when,
                    duration_minutes=random.choice([30, 60, 90, 120]),
                    attendees=[lead.email, "rkapoor@troutman-demo.com"],
                    status="scheduled",
                ))

            # Notifications
            db.add(Notification(
                case_id=c.id,
                recipient_email=lead.email,
                channel="email",
                subject=f"Reminder: upcoming deadline on {c.case_number}",
                body="Please review the attached filing checklist before Friday.",
                status="sent",
                sent_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
            ))

            # Stub documents (no files yet; users upload real ones via UI)
            for _ in range(random.randint(1, 3)):
                db.add(Document(
                    case_id=c.id,
                    filename=f"{c.case_number}-{random.choice(['complaint','answer','motion','brief'])}.pdf",
                    file_type="pdf",
                    file_path="",
                    size_bytes=random.randint(40_000, 2_000_000),
                    page_count=random.randint(2, 60),
                    doc_category=random.choice(["Pleading","Discovery","Brief","Contract"]),
                    uploaded_by=lead.id,
                    indexed=False,
                    summary="Seeded placeholder - upload a real PDF/DOCX via the Documents tab to enable semantic search on this case.",
                ))


if __name__ == "__main__":
    import argparse
    from .database import init_db
    parser = argparse.ArgumentParser(description="Seed the LEXORA demo database.")
    parser.add_argument("--force", action="store_true",
                        help="Truncate existing data and reseed.")
    args = parser.parse_args()
    init_db()
    seed(force=args.force)
    print("LEXORA database seeded.")
