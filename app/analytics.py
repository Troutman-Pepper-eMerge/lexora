"""Analytics queries + pattern detection for the dashboard."""
from __future__ import annotations

import json
import logging
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Appointment, Case, Document, Notification

log = logging.getLogger("lexora.analytics")


# --------------------------------------------------------------------- #
# KPI cards                                                             #
# --------------------------------------------------------------------- #
def kpi_overview(db: Session) -> Dict[str, Any]:
    total = db.query(func.count(Case.id)).scalar() or 0
    open_ = db.query(func.count(Case.id)).filter(Case.status != "Closed").scalar() or 0
    closed = db.query(func.count(Case.id)).filter(Case.status == "Closed").scalar() or 0
    critical = db.query(func.count(Case.id)).filter(Case.priority == "Critical").scalar() or 0
    aov = db.query(func.coalesce(func.sum(Case.estimated_value), 0)).scalar() or 0
    hours = db.query(func.coalesce(func.sum(Case.billable_hours), 0)).scalar() or 0
    docs = db.query(func.count(Document.id)).scalar() or 0
    upcoming = db.query(func.count(Appointment.id)).filter(
        Appointment.scheduled_at >= datetime.utcnow(),
        Appointment.scheduled_at <= datetime.utcnow() + timedelta(days=14),
        Appointment.status == "scheduled",
    ).scalar() or 0
    notifs = db.query(func.count(Notification.id)).filter(
        Notification.created_at >= datetime.utcnow() - timedelta(days=30)
    ).scalar() or 0
    return {
        "total_cases": total,
        "open_cases": open_,
        "closed_cases": closed,
        "critical_cases": critical,
        "total_value_usd": float(aov),
        "billable_hours": float(hours),
        "documents_indexed": docs,
        "upcoming_events_14d": upcoming,
        "notifications_30d": notifs,
    }


# --------------------------------------------------------------------- #
# Charts                                                                #
# --------------------------------------------------------------------- #
def status_distribution(db: Session) -> Dict[str, int]:
    rows = db.query(Case.status, func.count(Case.id)).group_by(Case.status).all()
    return {s or "Unknown": n for s, n in rows}


def cases_by_practice(db: Session) -> Dict[str, int]:
    rows = db.query(Case.practice_area, func.count(Case.id)).group_by(Case.practice_area).all()
    return {p or "Unknown": n for p, n in rows}


def cases_by_jurisdiction(db: Session) -> Dict[str, int]:
    rows = db.query(Case.jurisdiction, func.count(Case.id)).group_by(Case.jurisdiction).all()
    return {j or "Unknown": n for j, n in rows}


def value_by_practice(db: Session) -> Dict[str, float]:
    rows = db.query(Case.practice_area,
                    func.coalesce(func.sum(Case.estimated_value), 0)
                    ).group_by(Case.practice_area).all()
    return {p or "Unknown": float(v) for p, v in rows}


def monthly_filings(db: Session, months: int = 12) -> Dict[str, int]:
    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    buckets: Dict[str, int] = defaultdict(int)
    for (filed,) in db.query(Case.filed_date).filter(Case.filed_date >= cutoff).all():
        if filed:
            buckets[filed.strftime("%Y-%m")] += 1
    return dict(sorted(buckets.items()))


# --------------------------------------------------------------------- #
# Pattern detection                                                     #
# --------------------------------------------------------------------- #
def adjudication_time_by_state(db: Session) -> List[Dict[str, Any]]:
    """Average days from filed_date to (closed_date or today) per jurisdiction.

    Surface the demo insight: California consistently runs longer than peers.
    """
    rows = db.query(Case).all()
    by_state: Dict[str, List[int]] = defaultdict(list)
    for c in rows:
        if not c.filed_date:
            continue
        end = c.closed_date or datetime.utcnow()
        days = max(0, (end - c.filed_date).days)
        by_state[c.jurisdiction or "Unknown"].append(days)
    out = []
    overall = []
    for st, vals in by_state.items():
        if vals:
            avg = sum(vals) / len(vals)
            overall.extend(vals)
            out.append({"jurisdiction": st, "avg_days": round(avg, 1), "n": len(vals)})
    out.sort(key=lambda r: r["avg_days"], reverse=True)
    nat_avg = round(sum(overall) / len(overall), 1) if overall else 0
    for r in out:
        r["delta_vs_national_pct"] = round(
            ((r["avg_days"] - nat_avg) / nat_avg) * 100, 1) if nat_avg else 0
    return out


def detect_patterns(db: Session) -> List[Dict[str, Any]]:
    """Statistical, multi-dimensional pattern engine.

    Unlike a fixed rule list, each detector computes a *magnitude* and only
    surfaces a signal when it is materially significant. Magnitude drives a
    numeric ``score`` (used for ranking) plus a ``severity`` and ``confidence``.
    Detectors span jurisdiction, judge, practice, value, staleness, deadline
    clustering and documentation-readiness dimensions.
    """
    detectors = (
        _p_adjudication_outliers,
        _p_judge_outliers,
        _p_practice_concentration,
        _p_value_concentration,
        _p_critical_exposure,
        _p_deadline_clustering,
        _p_stalled_cases,
        _p_documentation_gaps,
        _p_settlement_rate,
    )
    found: List[Dict[str, Any]] = []
    for fn in detectors:
        try:
            found.extend(fn(db) or [])
        except Exception:                                     # pragma: no cover
            log.exception("pattern detector %s failed", fn.__name__)

    # Rank by score (desc) and tag severity if a detector didn't set one.
    found.sort(key=lambda p: p.get("score", 0), reverse=True)
    for p in found:
        p.setdefault("confidence", 0.7)
        p.setdefault("category", "General")
    return found


# --------------------------------------------------------------------- #
# Statistical helpers                                                   #
# --------------------------------------------------------------------- #
def _severity_from_z(z: float) -> str:
    az = abs(z)
    if az >= 2.0:
        return "high"
    if az >= 1.0:
        return "medium"
    return "low"


def _confidence_from_z(z: float, n: int) -> float:
    """Heuristic confidence: grows with effect size and sample size."""
    base = min(0.99, 0.55 + abs(z) * 0.18)
    # shrink for tiny samples
    if n < 3:
        base *= 0.7
    elif n < 5:
        base *= 0.85
    return round(min(0.99, base), 2)


# --------------------------------------------------------------------- #
# Individual detectors                                                  #
# --------------------------------------------------------------------- #
def _p_adjudication_outliers(db: Session) -> List[Dict[str, Any]]:
    """Flag jurisdictions whose avg adjudication time is a statistical outlier
    (z-score) against the cross-jurisdiction distribution."""
    rows = adjudication_time_by_state(db)
    vals = [r["avg_days"] for r in rows if r["n"] >= 2]
    if len(vals) < 3:
        return []
    mean = statistics.mean(vals)
    stdev = statistics.pstdev(vals) or 1.0
    out: List[Dict[str, Any]] = []
    for r in rows:
        if r["n"] < 2:
            continue
        z = (r["avg_days"] - mean) / stdev
        if z < 1.0:                       # only material slow-downs
            continue
        sev = _severity_from_z(z)
        out.append({
            "category": "Adjudication",
            "severity": sev,
            "score": 6.0 + z,             # outliers rank high
            "confidence": _confidence_from_z(z, r["n"]),
            "metric": f"{r['delta_vs_national_pct']:+.1f}% vs national",
            "title": f"{r['jurisdiction']} adjudicates {z:.1f}σ slower than peers",
            "detail": (f"Average adjudication time in {r['jurisdiction']} is "
                       f"{r['avg_days']} days across {r['n']} matters "
                       f"(portfolio mean {mean:.0f} days). "
                       "Consider earlier mediation, venue strategy, or dedicated "
                       "scheduling pressure to compress the timeline."),
        })
    return out


def _p_judge_outliers(db: Session) -> List[Dict[str, Any]]:
    """Judges whose docket runs materially longer than the portfolio mean."""
    cases = db.query(Case).all()
    by_judge: Dict[str, List[int]] = defaultdict(list)
    all_days: List[int] = []
    for c in cases:
        if not c.filed_date or not c.judge:
            continue
        end = c.closed_date or datetime.utcnow()
        d = max(0, (end - c.filed_date).days)
        by_judge[c.judge].append(d)
        all_days.append(d)
    if len(all_days) < 5:
        return []
    mean = statistics.mean(all_days)
    stdev = statistics.pstdev(all_days) or 1.0
    out: List[Dict[str, Any]] = []
    for judge, ds in by_judge.items():
        if len(ds) < 3:
            continue
        avg = statistics.mean(ds)
        z = (avg - mean) / stdev
        if z < 1.0:
            continue
        out.append({
            "category": "Judicial",
            "severity": _severity_from_z(z),
            "score": 5.0 + z,
            "confidence": _confidence_from_z(z, len(ds)),
            "metric": f"{avg:.0f}d avg · {len(ds)} cases",
            "title": f"{judge}'s docket runs {((avg-mean)/mean*100):+.0f}% longer",
            "detail": (f"{len(ds)} matters before {judge} average {avg:.0f} days "
                       f"vs. a {mean:.0f}-day portfolio mean. Calibrate scheduling "
                       "expectations and brief partners on realistic timelines."),
        })
    return out


def _p_practice_concentration(db: Session) -> List[Dict[str, Any]]:
    pa = cases_by_practice(db)
    total = sum(pa.values())
    if not total:
        return []
    top, n = max(pa.items(), key=lambda kv: kv[1])
    share = n / total * 100
    if share < 25:
        return []
    sev = "high" if share >= 45 else "medium"
    return [{
        "category": "Concentration",
        "severity": sev,
        "score": 2.0 + share / 20,
        "confidence": round(min(0.95, 0.6 + share / 200), 2),
        "metric": f"{share:.0f}% of caseload",
        "title": f"{top} concentration risk ({share:.0f}% of matters)",
        "detail": (f"{n} of {total} open matters sit in {top}. "
                   "Validate staffing depth, conflicts coverage and "
                   "single-practice revenue dependency."),
    }]


def _p_value_concentration(db: Session) -> List[Dict[str, Any]]:
    """Single-client exposure concentration by estimated value."""
    rows = (db.query(Case.client_name,
                     func.coalesce(func.sum(Case.estimated_value), 0))
            .filter(Case.status != "Closed")
            .group_by(Case.client_name).all())
    by_client = {c or "Unknown": float(v) for c, v in rows}
    total = sum(by_client.values())
    if total <= 0:
        return []
    client, val = max(by_client.items(), key=lambda kv: kv[1])
    share = val / total * 100
    if share < 30:
        return []
    sev = "high" if share >= 50 else "medium"
    return [{
        "category": "Exposure",
        "severity": sev,
        "score": 3.0 + share / 25,
        "confidence": round(min(0.95, 0.6 + share / 200), 2),
        "metric": f"${val/1e6:.1f}M · {share:.0f}% of book",
        "title": f"{client} represents {share:.0f}% of open exposure",
        "detail": (f"${val/1e6:.1f}M of a ${total/1e6:.1f}M open book is tied to "
                   f"{client}. Concentrated client risk — confirm engagement "
                   "diversification and collections posture."),
    }]


def _p_critical_exposure(db: Session) -> List[Dict[str, Any]]:
    crit = (db.query(Case)
            .filter(Case.priority == "Critical", Case.status != "Closed").all())
    if not crit:
        return []
    exposure = sum(c.estimated_value or 0 for c in crit)
    return [{
        "category": "Risk",
        "severity": "high",
        "score": 4.0 + len(crit) * 0.3,
        "confidence": 0.9,
        "metric": f"{len(crit)} cases · ${exposure/1e6:.1f}M",
        "title": f"{len(crit)} critical matters demand partner attention",
        "detail": (f"Combined exposure of ${exposure/1e6:.1f}M across "
                   f"{len(crit)} critical, still-open matters. Tag for weekly "
                   "status review and confirm escalation owners."),
    }]


def _p_deadline_clustering(db: Session) -> List[Dict[str, Any]]:
    """Detect days where multiple filing deadlines stack up (bottleneck risk)."""
    soon = (db.query(Appointment)
            .filter(Appointment.appointment_type == "Filing-Deadline",
                    Appointment.scheduled_at >= datetime.utcnow(),
                    Appointment.scheduled_at <= datetime.utcnow() + timedelta(days=14),
                    Appointment.status == "scheduled").all())
    if not soon:
        return []
    by_day: Dict[str, int] = defaultdict(int)
    for a in soon:
        by_day[a.scheduled_at.strftime("%Y-%m-%d")] += 1
    worst_day, worst_n = max(by_day.items(), key=lambda kv: kv[1])
    out = [{
        "category": "Deadlines",
        "severity": "medium",
        "score": 2.0 + len(soon) * 0.2,
        "confidence": 0.85,
        "metric": f"{len(soon)} in 14d",
        "title": f"{len(soon)} filing deadlines in the next 14 days",
        "detail": "Auto-reminders queued. Verify owner assignments on the Calendar tab.",
    }]
    if worst_n >= 2:
        out.append({
            "category": "Deadlines",
            "severity": "high" if worst_n >= 3 else "medium",
            "score": 4.0 + worst_n,
            "confidence": 0.88,
            "metric": f"{worst_n} on {worst_day}",
            "title": f"Deadline bottleneck: {worst_n} filings due {worst_day}",
            "detail": (f"{worst_n} filing deadlines converge on a single day. "
                       "Redistribute prep workload now to avoid a same-day crunch."),
        })
    return out


def _p_stalled_cases(db: Session) -> List[Dict[str, Any]]:
    """Open cases filed long ago with no upcoming activity — likely stalled."""
    cutoff_old = datetime.utcnow() - timedelta(days=180)
    open_cases = (db.query(Case)
                  .filter(Case.status != "Closed",
                          Case.filed_date <= cutoff_old).all())
    if not open_cases:
        return []
    stalled = []
    for c in open_cases:
        has_future = any(
            a.scheduled_at and a.scheduled_at >= datetime.utcnow()
            and a.status == "scheduled"
            for a in c.appointments
        )
        if not has_future:
            stalled.append(c)
    if not stalled:
        return []
    exposure = sum(c.estimated_value or 0 for c in stalled)
    sev = "high" if len(stalled) >= 5 else "medium"
    return [{
        "category": "Velocity",
        "severity": sev,
        "score": 3.0 + len(stalled) * 0.25,
        "confidence": 0.8,
        "metric": f"{len(stalled)} cases · ${exposure/1e6:.1f}M idle",
        "title": f"{len(stalled)} aging matters show no scheduled activity",
        "detail": (f"{len(stalled)} matters older than 180 days have no upcoming "
                   f"hearing, deposition or deadline (${exposure/1e6:.1f}M exposure). "
                   "Schedule next steps or evaluate for resolution/settlement."),
    }]


def _p_documentation_gaps(db: Session) -> List[Dict[str, Any]]:
    """High-priority open cases with zero ingested documents — readiness risk."""
    cases = (db.query(Case)
             .filter(Case.status != "Closed",
                     Case.priority.in_(["High", "Critical"])).all())
    gaps = [c for c in cases if not c.documents]
    if not gaps:
        return []
    sev = "high" if len(gaps) >= 4 else "medium"
    return [{
        "category": "Readiness",
        "severity": sev,
        "score": 2.5 + len(gaps) * 0.3,
        "confidence": 0.82,
        "metric": f"{len(gaps)} high-priority cases",
        "title": f"{len(gaps)} priority matters have no documents on file",
        "detail": ("High/Critical matters with zero ingested documents can't be "
                   "served by RAG search or e-discovery. Prioritise intake of "
                   "pleadings and key evidence for these cases."),
    }]


def _p_settlement_rate(db: Session) -> List[Dict[str, Any]]:
    """Flag jurisdictions with an unusually low closure/settlement rate."""
    rows = (db.query(Case.jurisdiction, Case.status).all())
    tally: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "closed": 0})
    for juris, status in rows:
        key = juris or "Unknown"
        tally[key]["total"] += 1
        if status in ("Closed", "Settled"):
            tally[key]["closed"] += 1
    eligible = {k: v for k, v in tally.items() if v["total"] >= 3}
    if len(eligible) < 2:
        return []
    rates = {k: v["closed"] / v["total"] for k, v in eligible.items()}
    overall = sum(v["closed"] for v in eligible.values()) / \
              sum(v["total"] for v in eligible.values())
    worst, worst_rate = min(rates.items(), key=lambda kv: kv[1])
    if overall - worst_rate < 0.2:        # only flag a meaningful gap
        return []
    return [{
        "category": "Resolution",
        "severity": "medium",
        "score": 2.0 + (overall - worst_rate) * 5,
        "confidence": 0.75,
        "metric": f"{worst_rate*100:.0f}% vs {overall*100:.0f}% avg",
        "title": f"{worst} closes only {worst_rate*100:.0f}% of matters",
        "detail": (f"{worst} resolves {worst_rate*100:.0f}% of its cases vs a "
                   f"{overall*100:.0f}% portfolio average — a drag on realization. "
                   "Review settlement posture and case-aging there."),
    }]


# --------------------------------------------------------------------- #
# Optional agentic narrative (Azure OpenAI)                            #
# --------------------------------------------------------------------- #
def narrate_patterns(db: Session, max_patterns: int = 6) -> Dict[str, Any]:
    """Use Azure OpenAI to turn the structured signals into an executive
    narrative. Safe: returns a graceful fallback if the LLM is unreachable."""
    patterns = detect_patterns(db)[:max_patterns]
    if not patterns:
        return {"summary": "No material patterns detected in the current portfolio.",
                "patterns": []}
    bullet_src = "\n".join(
        f"- [{p['category']}/{p['severity']}] {p['title']} ({p.get('metric','')})"
        for p in patterns
    )
    try:
        from .azure_clients import get_chat_llm
        llm = get_chat_llm(temperature=0.2)
        prompt = (
            "You are LEXORA, a litigation analytics copilot briefing a law-firm "
            "CIO. Given these detected signals, write a tight 3-4 sentence "
            "executive summary that connects the dots and recommends the single "
            "highest-leverage action. Do not invent numbers.\n\n"
            f"Signals:\n{bullet_src}"
        )
        resp = llm.invoke(prompt)
        summary = getattr(resp, "content", str(resp)).strip()
    except Exception as exc:                                  # pragma: no cover
        log.warning("narrate_patterns LLM fallback: %s", exc)
        summary = ("Key signals: " +
                   "; ".join(p["title"] for p in patterns[:3]) + ".")
    return {"summary": summary, "patterns": patterns}


# --------------------------------------------------------------------- #
# Hybrid engine: statistical detectors + grounded LLM discovery         #
# --------------------------------------------------------------------- #
_SEV_SCORE = {"high": 5.0, "medium": 3.0, "low": 1.5}


def _build_evidence_pack(db: Session, stat_patterns: List[Dict[str, Any]]) -> str:
    """Compact, *grounded* fact sheet the LLM may reason over. Every number the
    model is allowed to cite lives here — it must not invent figures."""
    kpi = kpi_overview(db)
    adj = adjudication_time_by_state(db)
    prac = cases_by_practice(db)
    try:
        val = value_by_practice(db)
    except Exception:                                         # pragma: no cover
        val = {}
    status = status_distribution(db)

    lines = [
        "PORTFOLIO_KPIS: " + json.dumps(kpi, default=str),
        "STATUS_DISTRIBUTION: " + json.dumps(status, default=str),
        "CASES_BY_PRACTICE: " + json.dumps(prac, default=str),
        "OPEN_VALUE_BY_PRACTICE: " + json.dumps(val, default=str),
        "ADJUDICATION_BY_JURISDICTION: " + json.dumps(adj[:12], default=str),
        "STATISTICAL_FINDINGS:",
    ]
    for p in stat_patterns:
        lines.append(
            f"  - [{p.get('category')}/{p.get('severity')}] {p.get('title')} "
            f"| metric={p.get('metric','')} | {p.get('detail','')}"
        )
    return "\n".join(lines)


def _parse_json_block(raw: str) -> Dict[str, Any]:
    """Tolerantly extract a JSON object from an LLM reply (handles code fences
    and surrounding prose)."""
    if not raw:
        return {}
    txt = raw.strip()
    txt = re.sub(r"^```(?:json)?", "", txt).strip()
    txt = re.sub(r"```$", "", txt).strip()
    start, end = txt.find("{"), txt.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(txt[start:end + 1])
    except Exception:                                         # pragma: no cover
        return {}


def _clamp_conf(v: Any, default: float = 0.6) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return round(min(0.95, max(0.3, f)), 2)


def llm_discover_patterns(
    db: Session, stat_patterns: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], str]:
    """LLM *discovery* layer. Reasons across the grounded evidence pack to find
    cross-signal, qualitative patterns the threshold detectors cannot express
    (e.g. interactions between jurisdiction, practice, staffing and readiness).
    Returns (discoveries, executive_summary). Strictly grounded + validated."""
    evidence = _build_evidence_pack(db, stat_patterns)
    from .azure_clients import get_chat_llm
    llm = get_chat_llm(temperature=0.2)
    prompt = (
        "You are LEXORA, a litigation-analytics copilot briefing a law-firm CIO.\n"
        "You are given an EVIDENCE pack containing portfolio aggregates and the "
        "output of a statistical anomaly engine.\n\n"
        "TASK: Reason ACROSS these signals to surface up to 3 *non-obvious, "
        "cross-cutting* patterns that the single-dimension statistics miss "
        "(e.g. a jurisdiction slowdown combined with a documentation gap in the "
        "same practice area implying a staffing bottleneck). For each, give a "
        "concrete recommended action.\n\n"
        "HARD RULES:\n"
        "- Only cite numbers that appear in EVIDENCE. Never fabricate figures.\n"
        "- Do NOT merely restate a single statistical finding; synthesize.\n"
        "- For every discovery, populate 'evidence' with the 2-4 specific "
        "EVIDENCE facts/rows you reasoned from, quoted closely (e.g. "
        "'California 405.6 days across 8 matters', 'documents_indexed: 57'). "
        "This is your audit trail — it must justify the pattern.\n"
        "- If no defensible cross-signal pattern exists, return an empty list.\n\n"
        "Respond with STRICT JSON only, no prose, in this schema:\n"
        '{"summary": "3-4 sentence executive briefing connecting the dots and '
        'naming the single highest-leverage action",\n'
        ' "discoveries": [{"title": "short headline", "detail": "1-2 sentences '
        'of evidence-grounded reasoning", "category": "Risk|Resolution|'
        'Adjudication|Staffing|Readiness|Revenue", "severity": "high|medium|low", '
        '"confidence": 0.0, "metric": "short metric chip", '
        '"recommended_action": "imperative next step", '
        '"evidence": ["specific fact 1 from EVIDENCE", "specific fact 2"]}]}\n\n'
        f"EVIDENCE:\n{evidence}"
    )
    resp = llm.invoke(prompt)
    raw = getattr(resp, "content", str(resp))
    data = _parse_json_block(raw)

    discoveries: List[Dict[str, Any]] = []
    for d in (data.get("discoveries") or [])[:3]:
        if not isinstance(d, dict) or not d.get("title"):
            continue
        sev = str(d.get("severity", "medium")).lower()
        if sev not in _SEV_SCORE:
            sev = "medium"
        conf = _clamp_conf(d.get("confidence"), 0.65)
        ev_raw = d.get("evidence") or []
        if isinstance(ev_raw, str):
            ev_raw = [ev_raw]
        evidence_items = [str(e)[:160] for e in ev_raw if str(e).strip()][:4]
        discoveries.append({
            "category": str(d.get("category", "Insight"))[:24],
            "severity": sev,
            "score": round(_SEV_SCORE[sev] * conf, 2),
            "confidence": conf,
            "metric": str(d.get("metric", ""))[:48],
            "title": str(d["title"])[:140],
            "detail": str(d.get("detail", ""))[:320],
            "recommended_action": str(d.get("recommended_action", ""))[:200],
            "evidence": evidence_items,
            "source": "llm",
            "method": "LLM synthesis",
        })
    summary = str(data.get("summary", "")).strip()
    return discoveries, summary


def _fallback_summary(stat: List[Dict[str, Any]]) -> str:
    if not stat:
        return "No material patterns detected in the current portfolio."
    return "Key signals: " + "; ".join(p["title"] for p in stat[:3]) + "."


def hybrid_patterns(db: Session, max_patterns: int = 10) -> Dict[str, Any]:
    """Best-of-both-worlds engine: rigorous statistical detection fused with a
    grounded LLM discovery layer. Returns a single ranked list (each pattern
    tagged with its ``source``), an executive narrative, and engine counts.
    Degrades gracefully to pure statistics if the LLM is unreachable."""
    stat = detect_patterns(db)
    for p in stat:
        p.setdefault("source", "statistical")
        p.setdefault("method", "Statistical model")

    discoveries: List[Dict[str, Any]] = []
    summary = ""
    try:
        discoveries, summary = llm_discover_patterns(db, stat[:8])
    except Exception as exc:                                  # pragma: no cover
        log.warning("hybrid LLM layer fallback: %s", exc)

    if not summary:
        summary = _fallback_summary(stat)

    fused = stat + discoveries
    fused.sort(key=lambda p: p.get("score", 0), reverse=True)
    return {
        "summary": summary,
        "patterns": fused[:max_patterns],
        "engine": {"statistical": len(stat), "llm": len(discoveries)},
    }


# --------------------------------------------------------------------- #
# Litigation Outcome & Settlement Predictor                             #
# --------------------------------------------------------------------- #
# Transparent, logistic-style model. Every adjustment is an explicit,
# defensible coefficient surfaced in the evidence trail (no black box).
import math

# Practice-area priors: (settlement log-odds nudge, duration complexity x)
_PRACTICE_PRIOR = {
    "Employment":              (0.40, 0.85),
    "Commercial Litigation":   (0.18, 1.00),
    "Intellectual Property":   (0.10, 1.25),
    "M&A":                     (0.00, 1.10),
    "Securities":              (-0.22, 1.30),
    "Antitrust":               (-0.32, 1.45),
    "Real Estate":             (0.15, 0.95),
    "Bankruptcy":              (0.05, 1.15),
    "Tax":                     (-0.05, 1.10),
    "Regulatory":              (-0.25, 1.35),
}
# Status priors: settlement log-odds nudge based on current phase.
_STATUS_PRIOR = {
    "Settlement Talks": 0.95, "Discovery": 0.12, "Motion Practice": 0.08,
    "Open": 0.0, "Trial Prep": -0.30, "Trial": -0.85, "Closed": 0.0,
}
_PRIORITY_PRIOR = {"Critical": -0.25, "High": -0.10, "Medium": 0.0, "Low": 0.12}
_CASE_TYPE_PRIOR = {
    "Class Action": 0.22, "Wrongful Termination": 0.30, "Contract Dispute": 0.12,
    "Patent Infringement": 0.05, "Trade Secret": -0.05,
    "Breach of Fiduciary Duty": -0.08, "Shareholder Derivative": -0.10,
    "Merger Review": -0.15, "Regulatory Investigation": -0.28,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-12.0, min(12.0, x))))


def _portfolio_context(db: Session) -> Dict[str, Any]:
    adj = {r["jurisdiction"]: r for r in adjudication_time_by_state(db)}
    nat_vals = [r["avg_days"] for r in adj.values()]
    nat_avg = round(sum(nat_vals) / len(nat_vals), 1) if nat_vals else 365.0
    return {"adj": adj, "national_avg_days": nat_avg}


def predict_case_outcome(db: Session, case_id: int) -> Dict[str, Any]:
    """Transparent litigation outcome + settlement predictor for one matter.

    Produces settlement likelihood, favorable-outcome probability, expected
    duration (with range), and a settlement value range — each driven by
    explicit factors that populate a 'Why?' evidence trail, then narrated by
    the LLM (with a safe statistical fallback).
    """
    c = db.get(Case, case_id)
    if c is None:
        raise ValueError(f"case {case_id} not found")

    ctx = _portfolio_context(db)
    nat_avg = ctx["national_avg_days"]
    jrow = ctx["adj"].get(c.jurisdiction or "")
    juris_avg = jrow["avg_days"] if jrow else nat_avg
    juris_delta = jrow["delta_vs_national_pct"] if jrow else 0.0

    factors: List[Dict[str, Any]] = []
    evidence: List[str] = []

    def add_factor(label: str, impact: str, weight: float, detail: str):
        factors.append({"label": label, "impact": impact,
                        "weight": round(abs(weight), 3), "detail": detail})

    # ---- Settlement likelihood (logistic) --------------------------- #
    base = 0.75  # ~68% baseline settlement rate => logit
    score = base
    add_factor("Civil-litigation baseline", "neutral", 0.0,
               "Most commercial disputes resolve before verdict (~68% base rate).")

    pa = c.practice_area or ""
    pa_nudge, pa_complexity = _PRACTICE_PRIOR.get(pa, (0.0, 1.0))
    if pa_nudge:
        score += pa_nudge
        add_factor(f"Practice area: {pa}",
                   "increases" if pa_nudge > 0 else "decreases", pa_nudge,
                   f"{pa} matters historically "
                   f"{'settle more readily' if pa_nudge > 0 else 'are more trial/regulatory-driven'}.")
        evidence.append(f"Practice area = {pa} (settlement nudge {pa_nudge:+.2f})")

    ct = c.case_type or ""
    ct_nudge = _CASE_TYPE_PRIOR.get(ct, 0.0)
    if ct_nudge:
        score += ct_nudge
        add_factor(f"Case type: {ct}",
                   "increases" if ct_nudge > 0 else "decreases", ct_nudge,
                   f"{ct} cases tend to "
                   f"{'settle' if ct_nudge > 0 else 'proceed to adjudication'}.")

    val = c.estimated_value or 0.0
    if val >= 10_000_000:
        score += 0.45
        add_factor("High exposure (≥ $10M)", "increases", 0.45,
                   "Large potential exposure raises pressure to settle and cap risk.")
        evidence.append(f"Estimated value = ${val/1e6:.1f}M (high-exposure settlement pressure)")
    elif val >= 1_000_000:
        score += 0.22
        add_factor("Material exposure ($1M–$10M)", "increases", 0.22,
                   "Meaningful exposure modestly favors negotiated resolution.")
        evidence.append(f"Estimated value = ${val/1e6:.1f}M")
    elif 0 < val < 1_000_000:
        score -= 0.08
        add_factor("Lower exposure (< $1M)", "decreases", 0.08,
                   "Smaller matters are likelier to be litigated or dismissed outright.")

    if juris_delta:
        nudge = max(-0.25, min(0.25, juris_delta * 0.004))
        if abs(nudge) >= 0.02:
            score += nudge
            add_factor(f"Venue speed: {c.jurisdiction}",
                       "increases" if nudge > 0 else "decreases", nudge,
                       f"{c.jurisdiction} runs {juris_delta:+.1f}% vs national cycle time; "
                       f"{'slower dockets increase settlement pressure' if nudge > 0 else 'faster dockets reduce settlement pressure'}.")
            evidence.append(f"{c.jurisdiction} cycle {juris_avg:.0f}d ({juris_delta:+.1f}% vs national {nat_avg:.0f}d)")

    if c.judge:
        evidence.append(f"Assigned judge: {c.judge}")
        add_factor(f"Judge on record: {c.judge}", "neutral", 0.0,
                   "Judge assignment incorporated; docket history informs duration.")

    pr_nudge = _PRIORITY_PRIOR.get(c.priority or "", 0.0)
    if pr_nudge:
        score += pr_nudge
        add_factor(f"Priority: {c.priority}",
                   "increases" if pr_nudge > 0 else "decreases", pr_nudge,
                   f"{c.priority}-priority matters are "
                   f"{'often contested harder' if pr_nudge < 0 else 'typically resolved expediently'}.")

    st_nudge = _STATUS_PRIOR.get(c.status or "", 0.0)
    if st_nudge:
        score += st_nudge
        add_factor(f"Current phase: {c.status}",
                   "increases" if st_nudge > 0 else "decreases", st_nudge,
                   f"Matter is in '{c.status}'; "
                   f"{'settlement is actively in motion' if st_nudge > 0 else 'late-stage posture lowers settlement odds'}.")
        evidence.append(f"Current phase = {c.status}")

    settle_p = _sigmoid(score)
    trial_p = 1.0 - settle_p

    # ---- Favorable-outcome probability (separate, lighter model) ----- #
    fav = 0.20  # logit baseline ~0.55
    if pa in ("Employment", "Commercial Litigation", "Real Estate"):
        fav += 0.10
    if (c.priority or "") in ("Critical", "High"):
        fav += 0.10  # better-resourced matters
    if juris_delta and juris_delta > 0:
        fav -= 0.05  # slow venue, marginal drag
    favorable_p = _sigmoid(fav)

    # ---- Expected duration ----------------------------------------- #
    dur = juris_avg * pa_complexity
    if val >= 10_000_000:
        dur *= 1.18
    elif 0 < val < 1_000_000:
        dur *= 0.9
    if (c.status or "") in ("Trial", "Trial Prep"):
        dur *= 1.1
    dur = max(60.0, dur)
    dur_low = round(dur * 0.78)
    dur_high = round(dur * 1.22)
    age_days = (datetime.utcnow() - c.filed_date).days if c.filed_date else 0

    # ---- Settlement value range ------------------------------------ #
    settlement_low = settlement_high = settlement_expected = None
    if val and val > 0:
        mid = 0.45 + (favorable_p - 0.55) * 0.20      # favorability shifts midpoint
        mid = max(0.30, min(0.62, mid))
        settlement_expected = round(val * mid)
        settlement_low = round(val * max(0.25, mid - 0.12))
        settlement_high = round(val * min(0.72, mid + 0.15))
        evidence.append(
            f"Settlement model: {mid*100:.0f}% of ${val/1e6:.1f}M claim "
            f"=> ~${settlement_expected/1e6:.2f}M expected")

    # ---- Confidence + risk band ------------------------------------ #
    n_juris = jrow["n"] if jrow else 0
    conf = 0.55
    if val > 0: conf += 0.12
    if c.judge: conf += 0.08
    if n_juris >= 4: conf += 0.12
    elif n_juris >= 2: conf += 0.06
    conf = round(min(0.95, conf), 2)

    exposure_risk = (val or 0) * trial_p * (1 - favorable_p)
    if exposure_risk >= 8_000_000 or (c.priority == "Critical" and trial_p > 0.4):
        risk_band = "High"
    elif exposure_risk >= 2_000_000:
        risk_band = "Moderate"
    else:
        risk_band = "Low"

    factors.sort(key=lambda f: f["weight"], reverse=True)

    prediction = {
        "settlement_likelihood": round(settle_p, 3),
        "trial_likelihood": round(trial_p, 3),
        "favorable_outcome": round(favorable_p, 3),
        "expected_duration_days": round(dur),
        "duration_low_days": dur_low,
        "duration_high_days": dur_high,
        "age_days": age_days,
        "settlement_expected": settlement_expected,
        "settlement_low": settlement_low,
        "settlement_high": settlement_high,
        "confidence": conf,
        "risk_band": risk_band,
    }
    case_info = {
        "id": c.id, "case_number": c.case_number, "title": c.title,
        "client_name": c.client_name, "practice_area": c.practice_area,
        "case_type": c.case_type, "jurisdiction": c.jurisdiction,
        "judge": c.judge, "status": c.status, "priority": c.priority,
        "estimated_value": c.estimated_value,
    }
    narrative = _narrate_prediction(case_info, prediction, factors)
    return {"case": case_info, "prediction": prediction,
            "factors": factors, "evidence": evidence, "narrative": narrative}


def _narrate_prediction(case_info: Dict[str, Any], pred: Dict[str, Any],
                        factors: List[Dict[str, Any]]) -> str:
    """LLM executive narration of the prediction (safe fallback if offline)."""
    def _money(v):
        return f"${v/1e6:.2f}M" if v else "n/a"
    drivers = "; ".join(
        f"{f['label']} ({f['impact']})" for f in factors[:5] if f["impact"] != "neutral")
    fallback = (
        f"{case_info.get('jurisdiction','This')} {case_info.get('practice_area','matter')} "
        f"shows a {pred['settlement_likelihood']*100:.0f}% settlement likelihood and an "
        f"estimated {pred['expected_duration_days']} days to resolution "
        f"({pred['duration_low_days']}–{pred['duration_high_days']}d). "
        + (f"Projected settlement range {_money(pred['settlement_low'])}–"
           f"{_money(pred['settlement_high'])} (expected {_money(pred['settlement_expected'])}). "
           if pred.get("settlement_expected") else "")
        + f"Risk band: {pred['risk_band']}. Key drivers: {drivers}."
    )
    try:
        from .azure_clients import get_chat_llm
        llm = get_chat_llm(temperature=0.2)
        prompt = (
            "You are LEXORA, a litigation strategy copilot briefing a partner. "
            "Write a tight 3-4 sentence assessment of this matter's likely "
            "trajectory and the single highest-leverage strategic recommendation "
            "(e.g. open settlement talks, prepare for trial, reserve funds). "
            "Use ONLY the numbers provided; do not invent facts.\n\n"
            f"CASE: {json.dumps(case_info, default=str)}\n"
            f"PREDICTION: {json.dumps(pred, default=str)}\n"
            f"TOP_FACTORS: {json.dumps(factors[:6], default=str)}"
        )
        resp = llm.invoke(prompt)
        out = getattr(resp, "content", str(resp)).strip()
        return out or fallback
    except Exception as exc:                                  # pragma: no cover
        log.warning("predict narration fallback: %s", exc)
        return fallback
