"""
embed_catalog.py — eComBot Knowledge Base Indexer
==================================================
Embeds JSON product catalog, FAQ, and PDF documents from data/ into ChromaDB.

Pipeline:
    1. Load data/products.json and data/faq.json.
    2. Load any *.pdf files in data/.
    3. Split PDF content into overlapping chunks.
    4. Embed every chunk using the configured embedding model via LiteLLM.
    5. Upsert all chunks into a persistent ChromaDB collection.

Usage (rebuild the index):
    python src/rag/embed_catalog.py

VECTOR_BACKEND env var (default: disk):
    disk    → ChromaDB PersistentClient (data/chroma_db/ on disk)
    memory  → ChromaDB EphemeralClient (in-process, lost on exit)
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
import litellm
from dotenv import load_dotenv

# Allow running as a standalone script from the project root.
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.settings import settings  # noqa: E402 — after sys.path fix

load_dotenv()
litellm.suppress_debug_info = True

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Embedding
def embed(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts using the configured embedding model via LiteLLM.

    Uses OPENROUTER_API_KEY automatically (same key as the chat model).
    Falls back gracefully — raises RuntimeError with a clear message if
    the embedding call fails.
    """
    if not texts:
        return []
    try:
        response = litellm.embedding(
            model=settings.embedding_model,
            input=texts,
        )
        return [item["embedding"] for item in response.data]
    except Exception as exc:
        raise RuntimeError(
            f"Embedding failed for model '{settings.embedding_model}': {exc}"
        ) from exc

# JSON loaders
def _load_json_chunks(path: Path) -> list[dict[str, Any]]:
    """Load a JSON file and return a list of knowledge chunks.

    Expected format: list of objects, each with at minimum:
        {"id": str, "text": str, "metadata": dict}
    """
    if not path.exists():
        log.warning("Knowledge file not found: %s", path)
        return []
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    chunks = []
    for item in data:
        if not item.get("text"):
            continue
        chunks.append({
            "id": item["id"],
            "text": item["text"].strip(),
            "metadata": {
                **item.get("metadata", {}),
                "source_file": path.name,
            },
        })
    return chunks

# PDF loader
def _load_pdf_chunks(
    docs_dir: Path = _DATA_DIR,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> list[dict[str, Any]]:
    """
    Read every *.pdf in docs_dir and split pages into overlapping text chunks.

    Chunking strategy:
    - Extract text page by page using pypdf.
    - Concatenate all page text, then slide a window of `chunk_size` characters
      with `chunk_overlap` overlap so context is not lost at page breaks.
    - Attach metadata: source_file, document_title, page (approx), doc_type.

    Returns a list of {"id", "text", "metadata"} dicts.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning(
            "pypdf not installed — PDF ingestion skipped. "
            "Run: pip install pypdf"
        )
        return []

    chunks = []
    for pdf_path in sorted(docs_dir.glob("*.pdf")):
        reader = PdfReader(str(pdf_path))
        # Build full-document text with page markers so we can trace position.
        page_texts: list[tuple[int, str]] = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                page_texts.append((page_num, text))

        full_text = "\n\n".join(t for _, t in page_texts)
        if not full_text:
            continue

        # Build a rough page-number index so metadata reflects the approximate page.
        page_starts: list[tuple[int, int]] = []
        cursor = 0
        for page_num, text in page_texts:
            page_starts.append((cursor, page_num))
            cursor += len(text) + 2  # +2 for the \n\n separator

        def _approx_page(char_pos: int) -> int:
            """Return the approximate page number for a character position."""
            page = 1
            for start, pnum in page_starts:
                if char_pos >= start:
                    page = pnum
                else:
                    break
            return page

        # Slide a window over the full text.
        start = 0
        chunk_index = 0
        while start < len(full_text):
            end = start + chunk_size
            chunk_text = full_text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "id": f"{pdf_path.stem}-c{chunk_index}",
                    "text": chunk_text,
                    "metadata": {
                        "source_file": pdf_path.name,
                        "document_title": pdf_path.stem.replace("_", " ").replace("-", " ").title(),
                        "section": "PDF Content",
                        "page": _approx_page(start),
                        "doc_type": "pdf",
                    },
                })
                chunk_index += 1
            start += chunk_size - chunk_overlap
            if start >= len(full_text):
                break

    return chunks

# ChromaDB client
def _get_client() -> chromadb.Client:
    """Return a ChromaDB client based on VECTOR_BACKEND env var."""
    backend = os.getenv("VECTOR_BACKEND", "disk").strip().lower()
    if backend == "memory":
        return chromadb.EphemeralClient()
    persist_dir = str(settings.chroma_persist_dir)
    return chromadb.PersistentClient(path=persist_dir)

_chroma_client = None

def get_collection(reset: bool = False) -> chromadb.Collection:
    """
    Return the ChromaDB collection, creating and indexing it on first call.

    If `reset=True`, the existing collection is deleted and rebuilt from
    scratch — useful after updating the knowledge files.

    The client is cached at module level so repeated calls within the same
    process skip re-indexing.
    """
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = _get_client()

    if reset:
        try:
            _chroma_client.delete_collection(settings.chroma_collection)
        except Exception:
            pass  # Collection may not exist yet.

    collection = _chroma_client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )

    # Only index if the collection is empty (or reset was requested).
    if collection.count() == 0:
        _rebuild_collection(collection)

    return collection

def _rebuild_collection(collection: chromadb.Collection) -> None:
    """Load all knowledge sources and upsert them into the collection."""
    chunks: list[dict[str, Any]] = []

    # JSON sources
    chunks.extend(_load_json_chunks(_DATA_DIR / "products.json"))
    chunks.extend(_load_json_chunks(_DATA_DIR / "faq.json"))

    # PDF sources
    chunks.extend(_load_pdf_chunks(_DATA_DIR))

    if not chunks:
        log.warning("No knowledge chunks found — collection will be empty.")
        return

    log.info("Embedding %d chunks into ChromaDB collection '%s'…",
             len(chunks), settings.chroma_collection)

    # Embed in batches of 50 to stay within API limits.
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]
        embeddings = embed(texts)
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=texts,
            embeddings=embeddings,
            metadatas=[c["metadata"] for c in batch],
        )
        log.info("  Upserted batch %d/%d", i // batch_size + 1,
                 (len(chunks) + batch_size - 1) // batch_size)

    log.info("Indexing complete. Collection contains %d documents.",
             collection.count())

# CLI entry point
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Rebuild the eComBot knowledge base.")
    parser.add_argument("--reset", action="store_true",
                        help="Delete and fully rebuild the existing collection.")
    args = parser.parse_args()

    col = get_collection(reset=args.reset)
    print(f"Collection '{settings.chroma_collection}' contains {col.count()} document(s).")
