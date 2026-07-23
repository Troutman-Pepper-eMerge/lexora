"""Local FAISS vector store (used when Azure AI Search is not configured).

Uses Azure OpenAI embeddings (RBAC) under the hood.  Persisted to
DATA_DIR/vector_index.  Thread-safe via a coarse re-entrant lock - the
demo workload is light enough that this is not a bottleneck.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np

from .azure_clients import get_embeddings, get_search_client
from .config import get_settings

log = logging.getLogger("lexora.vector")
_LOCK = threading.RLock()


class _LocalFaiss:
    def __init__(self, dir_path: str) -> None:
        import faiss                          # local import: heavy
        self._faiss = faiss
        self.dir = Path(dir_path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.faiss"
        self.meta_path = self.dir / "meta.json"
        self.dim: Optional[int] = None
        self.index = None
        self.meta: List[dict] = []
        self._load()

    def _load(self) -> None:
        if self.meta_path.exists():
            self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        if self.index_path.exists():
            self.index = self._faiss.read_index(str(self.index_path))
            self.dim = self.index.d

    def _ensure_index(self, dim: int) -> None:
        if self.index is None:
            self.dim = dim
            self.index = self._faiss.IndexFlatIP(dim)

    def _persist(self) -> None:
        if self.index is not None:
            self._faiss.write_index(self.index, str(self.index_path))
        self.meta_path.write_text(json.dumps(self.meta), encoding="utf-8")

    def add(self, vectors: List[List[float]], metadatas: List[dict]) -> None:
        if not vectors:
            return
        arr = np.array(vectors, dtype="float32")
        # cosine via inner product on normalized vectors
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        arr = arr / norms
        self._ensure_index(arr.shape[1])
        self.index.add(arr)
        self.meta.extend(metadatas)
        self._persist()

    def search(self, vector: List[float], k: int = 6,
               filter_case_id: Optional[int] = None) -> List[dict]:
        if self.index is None or self.index.ntotal == 0:
            return []
        v = np.array([vector], dtype="float32")
        v = v / (np.linalg.norm(v) + 1e-12)
        D, I = self.index.search(v, min(k * 4, self.index.ntotal))
        results: List[dict] = []
        for score, idx in zip(D[0].tolist(), I[0].tolist()):
            if idx < 0 or idx >= len(self.meta):
                continue
            m = self.meta[idx]
            if filter_case_id is not None and m.get("case_id") != filter_case_id:
                continue
            results.append({**m, "score": float(score)})
            if len(results) >= k:
                break
        return results

    @property
    def size(self) -> int:
        return 0 if self.index is None else self.index.ntotal


_STORE: Optional[_LocalFaiss] = None


def _store() -> _LocalFaiss:
    global _STORE
    if _STORE is None:
        _STORE = _LocalFaiss(get_settings().vector_index_path)
    return _STORE


def embed_texts(texts: List[str]) -> List[List[float]]:
    return []


def embed_query(text: str) -> List[float]:
    return []


def add_chunks(*, doc_id: int, case_id: int, filename: str,
               chunks: List["Chunk"]) -> int:                # noqa: F821
    return 0


def semantic_search(query: str, *, k: int = 6,
                    case_id: Optional[int] = None) -> List[dict]:
    return []


# --------------------------------------------------------------------- #
# Azure AI Search backend (optional)                                    #
# --------------------------------------------------------------------- #
def _add_to_azure_search(vectors, metas) -> int:
    client = get_search_client()
    if not client:
        return 0
    docs = []
    for i, (v, m) in enumerate(zip(vectors, metas)):
        docs.append({
            "id": f"{m['doc_id']}-{i}",
            "doc_id": str(m["doc_id"]),
            "case_id": str(m["case_id"]),
            "filename": m["filename"],
            "page": m["page"],
            "section": m["section"],
            "text": m["text"],
            "embedding": v,
        })
    client.upload_documents(documents=docs)
    return len(docs)


def _search_azure(query: str, *, k: int, case_id: Optional[int]):
    from azure.search.documents.models import VectorizedQuery
    client = get_search_client()
    if not client:
        return []
    qv = embed_query(query)
    vq = VectorizedQuery(vector=qv, k_nearest_neighbors=k, fields="embedding")
    filt = f"case_id eq '{case_id}'" if case_id is not None else None
    results = client.search(search_text=query, vector_queries=[vq],
                            filter=filt, top=k)
    return [{
        "doc_id": int(r["doc_id"]), "case_id": int(r["case_id"]),
        "filename": r["filename"], "page": r["page"],
        "section": r["section"], "text": r["text"],
        "score": r["@search.score"],
    } for r in results]


def index_stats() -> dict:
    return {"backend": "disabled", "vectors": 0}
