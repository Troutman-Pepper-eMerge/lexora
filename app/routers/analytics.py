"""Analytics router - serves dashboard data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..analytics import (adjudication_time_by_state, cases_by_jurisdiction,
                          cases_by_practice, detect_patterns, hybrid_patterns,
                          kpi_overview, monthly_filings, narrate_patterns,
                          predict_case_outcome, status_distribution,
                          value_by_practice)
from ..auth import Principal, current_principal
from ..database import get_db
from ..vector_store import index_stats

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             _: Principal = Depends(current_principal)):
    return {
        "kpis": kpi_overview(db),
        "status_distribution": status_distribution(db),
        "by_practice": cases_by_practice(db),
        "by_jurisdiction": cases_by_jurisdiction(db),
        "value_by_practice": value_by_practice(db),
        "monthly_filings": monthly_filings(db),
        "vector_index": index_stats(),
    }


@router.get("/patterns")
def patterns(db: Session = Depends(get_db),
             _: Principal = Depends(current_principal)):
    return {
        "adjudication_time_by_state": adjudication_time_by_state(db),
        "patterns": detect_patterns(db),
    }


@router.get("/insights")
def insights(db: Session = Depends(get_db),
             _: Principal = Depends(current_principal)):
    """Hybrid intelligence: statistical detectors fused with a grounded LLM
    discovery layer, plus an AI-narrated executive summary."""
    return hybrid_patterns(db)


@router.get("/predict/{case_id}")
def predict(case_id: int, db: Session = Depends(get_db),
            _: Principal = Depends(current_principal)):
    """Litigation outcome & settlement prediction for a single matter:
    settlement likelihood, expected duration, settlement range, and an
    explainable factor/evidence trail with LLM strategic narration."""
    try:
        return predict_case_outcome(db, case_id)
    except ValueError:
        raise HTTPException(404, "Case not found")
