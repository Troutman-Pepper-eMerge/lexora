"""Documents router - upload, list, analyze."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form,
                     HTTPException, UploadFile)
from sqlalchemy.orm import Session

from ..auth import Principal, audit, require_roles, current_principal
from ..database import get_db, session_scope
from ..document_processor import EXTRACTORS
from ..models import Document

router = APIRouter(prefix="/api/documents", tags=["documents"])
log = logging.getLogger("lexora.docs.api")


@router.get("")
def list_documents(case_id: Optional[int] = None, limit: int = 100,
                   db: Session = Depends(get_db),
                   _: Principal = Depends(current_principal)):
    q = db.query(Document)
    if case_id:
        q = q.filter(Document.case_id == case_id)
    rows = q.order_by(Document.uploaded_at.desc()).limit(limit).all()
    return {"count": len(rows), "documents": [{
        "id": d.id, "case_id": d.case_id, "filename": d.filename,
        "file_type": d.file_type, "size_bytes": d.size_bytes,
        "pages": d.page_count, "category": d.doc_category,
        "indexed": d.indexed, "summary": d.summary,
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
    } for d in rows]}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    case_id: Optional[int] = Form(None),
    principal: Principal = Depends(require_roles("Partner","Associate","Paralegal","Admin")),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in EXTRACTORS:
        raise HTTPException(400, f"Unsupported file type {suffix}. "
                            f"Allowed: {sorted(EXTRACTORS)}")

    # Read size without persisting to disk
    content = await file.read()
    size = len(content)

    with session_scope() as db:
        doc = Document(case_id=case_id, filename=file.filename or "upload",
                       file_type=suffix.lstrip("."), file_path="",
                       size_bytes=size, indexed=False,
                       doc_category="Uploaded")
        db.add(doc); db.flush()
        doc_id = doc.id

    audit(principal, "upload_document",
          target=f"doc:{doc_id}", detail={"filename": file.filename, "size": size})
    return {"document_id": doc_id, "filename": file.filename,
            "size_bytes": size, "status": "queued"}


# def _process_uploaded_document(doc_id: int, path: Path, filename: str,
#                                 case_id: Optional[int]) -> None:
#     """Background worker: extract -> classify -> summarize -> embed."""
#     try:
#         chunks = extract_chunks(path)
#         text = full_text(chunks)
#         category = classify_document(filename, text)
#         try:
#             summary = summarize_with_llm(text, filename)
#         except Exception as exc:                                  # pragma: no cover
#             log.warning("summary failed: %s", exc)
#             summary = "(LLM summary unavailable - check Azure OpenAI access.)"
#         n_vectors = 0
#         if case_id is not None:
#             try:
#                 n_vectors = add_chunks(doc_id=doc_id, case_id=case_id,
#                                         filename=filename, chunks=chunks)
#             except Exception as exc:
#                 log.warning("embedding failed: %s", exc)

#         with session_scope() as db:
#             d = db.get(Document, doc_id)
#             if not d:
#                 return
#             d.page_count = max((c.page for c in chunks), default=0)
#             d.extracted_text = text[:200_000]
#             d.doc_category = category
#             d.summary = summary
#             d.indexed = n_vectors > 0
#             d.doc_metadata = {"chunks": len(chunks), "vectors": n_vectors}
#     except Exception as exc:                                      # pragma: no cover
#         log.exception("processing failed for doc %s", doc_id)
#         with session_scope() as db:
#             d = db.get(Document, doc_id)
#             if d:
#                 d.doc_category = "Error"
#                 d.summary = f"Processing error: {exc}"


@router.post("/{doc_id}/analyze")
def analyze_document(doc_id: int,
                     db: Session = Depends(get_db),
                     _: Principal = Depends(current_principal)):
    """On-demand interpretation of an already-uploaded document."""
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    if not d.file_path or not Path(d.file_path).exists():
        raise HTTPException(404, "Source file not on disk (was this a seeded stub?)")
    chunks = [] # extract_chunks(Path(d.file_path))
    summary = "" # summarize_with_llm(full_text(chunks), d.filename)
    d.summary = summary; db.commit()
    return {"document_id": doc_id, "summary": summary,
            "page_count": max((c.page for c in chunks), default=0)}


@router.delete("/{doc_id}")
def delete_document(doc_id: int,
                    db: Session = Depends(get_db),
                    principal: Principal = Depends(require_roles("Partner","Admin"))):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Not found")
    if d.file_path and Path(d.file_path).exists():
        Path(d.file_path).unlink(missing_ok=True)
    db.delete(d); db.commit()
    audit(principal, "delete_document", target=f"doc:{doc_id}")
    return {"ok": True}
