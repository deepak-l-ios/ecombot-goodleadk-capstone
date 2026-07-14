"""
retriever.py — eComBot RAG Retriever
======================================
Retrieves the most relevant knowledge chunks for a user query using
cosine similarity over the ChromaDB collection built by embed_catalog.py.

Public API:
    retrieve(query, n_results=3) → list[dict]

Each returned dict:
    {
        "id":       str,
        "text":     str,
        "metadata": dict,
        "score":    float,  # cosine similarity in [0, 1]
    }

Hallucination guard:
    If all results fall below SIMILARITY_THRESHOLD, `retrieve()` returns
    an empty list so the agent applies the fallback rule.
"""

import logging
from typing import Any

from rag.embed_catalog import embed, get_collection

log = logging.getLogger(__name__)

# Similarity threshold — chunks below this are too weak to ground an answer on.
SIMILARITY_THRESHOLD: float = 0.30

# Minimum chunks above threshold required to proceed; fewer triggers fallback.
MIN_USEFUL_CHUNKS: int = 1

def retrieve(query: str, n_results: int = 3) -> list[dict[str, Any]]:
    """
    Retrieve the top `n_results` chunks most relevant to `query`.

    Returns an empty list when:
    - The query is blank or whitespace.
    - The collection is empty.
    - No chunk clears SIMILARITY_THRESHOLD (hallucination guard).
    - Any retrieval error occurs (never raises to caller).

    Each result dict: {"id", "text", "metadata", "score"}.
    """
    if not query or not query.strip():
        return []

    try:
        collection = get_collection()
        if collection.count() == 0:
            log.warning("ChromaDB collection is empty — no retrieval possible.")
            return []

        query_embedding = embed([query.strip()])[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        chunks = []
        for cid, doc, meta, dist in zip(ids, documents, metadatas, distances):
            # ChromaDB cosine distance is in [0, 2]; convert to similarity in [0, 1].
            similarity = max(0.0, 1.0 - dist / 2.0)
            if similarity < SIMILARITY_THRESHOLD:
                continue
            chunks.append({
                "id": cid,
                "text": doc,
                "metadata": meta or {},
                "score": round(similarity, 4),
            })

        if len(chunks) < MIN_USEFUL_CHUNKS:
            log.info(
                "Retrieval: %d chunk(s) passed threshold %.2f for query '%s…' — fallback.",
                len(chunks), SIMILARITY_THRESHOLD, query[:60],
            )
            return []

        log.debug(
            "Retrieval: %d chunk(s) returned for query '%s…'",
            len(chunks), query[:60],
        )
        return chunks

    except Exception as exc:
        log.error("Retrieval error for query '%s…': %s", query[:60], exc)
        return []
