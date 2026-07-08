"""High-performance document ingestion for PDF / DOCX / PPTX / JSON / TXT.

Design choices for performance with document-heavy workloads:
  * Streaming readers per file type (no full-file loads when avoidable).
  * Token-aware chunking (tiktoken cl100k) -> stable embedding cost.
  * Async upload endpoint streams to ./docs/uploads and dispatches the
    heavy parse+embed work to a worker thread so the HTTP request
    returns immediately.
  * Embeddings are batched (max 64 chunks per request).
  * Each chunk carries metadata: case_id, doc_id, page, category.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import tiktoken
from pypdf import PdfReader
from docx import Document as DocxDocument
from pptx import Presentation

log = logging.getLogger("lexora.docs")

_ENC = tiktoken.get_encoding("cl100k_base")
MAX_TOKENS_PER_CHUNK = 600
CHUNK_OVERLAP_TOKENS = 80


@dataclass
class Chunk:
    text: str
    page: int
    section: str
    token_count: int


# --------------------------------------------------------------------- #
# Extractors                                                            #
# --------------------------------------------------------------------- #
def _extract_pdf(path: Path) -> List[Chunk]:
    out: List[Chunk] = []
    reader = PdfReader(str(path))
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:                             # pragma: no cover
            log.warning("pdf page %s parse error: %s", i, exc)
            continue
        if text:
            out.extend(_chunk_text(text, page=i, section=f"Page {i}"))
    return out


def _extract_docx(path: Path) -> List[Chunk]:
    doc = DocxDocument(str(path))
    buf: list[str] = []
    out: List[Chunk] = []
    section = "Body"
    for para in doc.paragraphs:
        t = (para.text or "").strip()
        if not t:
            continue
        style = (para.style.name if para.style else "") or ""
        if style.startswith("Heading"):
            if buf:
                out.extend(_chunk_text("\n".join(buf), page=1, section=section))
                buf.clear()
            section = t[:120]
        else:
            buf.append(t)
    if buf:
        out.extend(_chunk_text("\n".join(buf), page=1, section=section))
    return out


def _extract_pptx(path: Path) -> List[Chunk]:
    prs = Presentation(str(path))
    out: List[Chunk] = []
    for i, slide in enumerate(prs.slides, start=1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.text:
                            parts.append(run.text)
        text = "\n".join(parts).strip()
        if text:
            out.extend(_chunk_text(text, page=i, section=f"Slide {i}"))
    return out


def _extract_json(path: Path) -> List[Chunk]:
    data = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(data, indent=2, ensure_ascii=False)
    return _chunk_text(text, page=1, section="JSON")


def _extract_xlsx(path: Path) -> List[Chunk]:
    """Flatten spreadsheet rows into readable text (one block per sheet)."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:                               # pragma: no cover
        raise ValueError("Excel support requires openpyxl") from exc
    wb = load_workbook(str(path), read_only=True, data_only=True)
    out: List[Chunk] = []
    for i, ws in enumerate(wb.worksheets, start=1):
        lines: list[str] = [f"Sheet: {ws.title}"]
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(" | ".join(cells))
        text = "\n".join(lines).strip()
        if text:
            out.extend(_chunk_text(text, page=i, section=ws.title[:120]))
    wb.close()
    return out


def _extract_text(path: Path) -> List[Chunk]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return _chunk_text(text, page=1, section="Body")


EXTRACTORS = {
    ".pdf":  _extract_pdf,
    ".docx": _extract_docx,
    ".pptx": _extract_pptx,
    ".json": _extract_json,
    ".xlsx": _extract_xlsx,
    ".txt":  _extract_text,
    ".md":   _extract_text,
}


# --------------------------------------------------------------------- #
# Chunking                                                              #
# --------------------------------------------------------------------- #
def _chunk_text(text: str, *, page: int, section: str) -> List[Chunk]:
    text = re.sub(r"\s+\n", "\n", text).strip()
    if not text:
        return []
    tokens = _ENC.encode(text)
    out: List[Chunk] = []
    step = MAX_TOKENS_PER_CHUNK - CHUNK_OVERLAP_TOKENS
    for start in range(0, len(tokens), step):
        window = tokens[start:start + MAX_TOKENS_PER_CHUNK]
        if not window:
            break
        out.append(Chunk(
            text=_ENC.decode(window),
            page=page,
            section=section,
            token_count=len(window),
        ))
    return out


# --------------------------------------------------------------------- #
# Public API                                                            #
# --------------------------------------------------------------------- #
def extract_chunks(path: Path) -> List[Chunk]:
    ext = path.suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if not extractor:
        raise ValueError(f"Unsupported file type: {ext}")
    return extractor(path)


def full_text(chunks: Iterable[Chunk], cap: int = 20_000) -> str:
    body = "\n\n".join(c.text for c in chunks)
    return body[:cap]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for blk in iter(lambda: fp.read(1 << 16), b""):
            h.update(blk)
    return h.hexdigest()


def classify_document(filename: str, text: str) -> str:
    """Light heuristic classification (also augmented by LLM later)."""
    f = filename.lower()
    t = (text or "")[:2000].lower()
    if any(k in f or k in t for k in ("complaint", "petition", "motion", "pleading")):
        return "Pleading"
    if any(k in f or k in t for k in ("interrogator", "deposition", "subpoena", "discovery")):
        return "Discovery"
    if any(k in f or k in t for k in ("contract", "agreement", "nda", "mou")):
        return "Contract"
    if any(k in f or k in t for k in ("brief", "memorandum", "memo")):
        return "Brief"
    if any(k in f or k in t for k in ("order", "judgment", "ruling")):
        return "Court Order"
    return "General"


def summarize_with_llm(text: str, filename: str) -> str:
    """LLM-powered summary (Azure OpenAI via RBAC)."""
    from .azure_clients import get_aoai_client
    from .config import get_settings
    if not text.strip():
        return ""
    client = get_aoai_client()
    s = get_settings()
    prompt = (
        "You are a senior litigation associate. In 4-6 bullet points, "
        "summarize the document's purpose, parties, key facts, and any "
        "deadlines or relief sought. Be precise; cite page numbers when "
        "given. End with a single-line 'Risk:' rating (Low/Medium/High).")
    rsp = client.chat.completions.create(
        model=s.azure_openai_chat_deployment,
        temperature=0.2,
        max_tokens=400,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Filename: {filename}\n\n{text[:12000]}"},
        ],
    )
    return rsp.choices[0].message.content or ""
