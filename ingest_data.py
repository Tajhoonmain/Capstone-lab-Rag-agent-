"""
ClaimGuardian RAG Pipeline: Ingestion, Cleaning, Chunking, and Vector Indexing.

Lab 2: Source Memory — Ingest project-specific data into a vector database
for retrieval-augmented generation (RAG). Embeddings: Gemini (GEMINI_API_KEY),
OpenAI (OPENAI_API_KEY), or local sentence-transformers.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import Iterator

# Optional: use dotenv for API key
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

os.environ["CHROMA_TELEMETRY"] = "false"
import chromadb
from chromadb.config import Settings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
PROJECT_DOCS_DIR = Path(__file__).parent  # PRD, SYSTEM_DESIGN, LANGGRAPH in project root
CHROMA_PERSIST_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "claimguardian_knowledge"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_MIN_CHARS = 200
CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP = 100

# Files to ingest from project root (project docs)
PROJECT_DOC_FILES = ["PRD.md", "SYSTEM_DESIGN.md", "LANGGRAPH_ARCHITECTURE.md"]


# ---------------------------------------------------------------------------
# Task 1: Cleaning & Metadata Enrichment
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces/newlines and strip leading/trailing whitespace."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_domain_noise(text: str, file_path: Path) -> str:
    """
    Strip domain-specific noise: markdown frontmatter, horizontal rules,
    boilerplate footers (e.g. 'Last updated', 'Document owner'), and
    excessive punctuation.
    """
    # Remove YAML-style frontmatter (--- ... ---)
    text = re.sub(r"^---\s*\n[\s\S]*?\n---\s*\n", "", text, count=1)
    # Remove standalone horizontal rules (--- or ***)
    text = re.sub(r"\n\s*[-*_]{3,}\s*\n", "\n\n", text)
    # Remove common footer lines (case-insensitive)
    footer_patterns = [
        r"\n\s*Last updated:.*$",
        r"\n\s*Document owner:.*$",
        r"\n\s*\*?\s*Last updated:.*$",
        r"\n\s*—+\s*$",
        r"\n\s*Version:.*\|\s*Date:.*\|\s*Status:.*$",
    ]
    for pat in footer_patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE | re.MULTILINE)
    # Remove line-only headers that are metadata (e.g. "**Version:** 1.0")
    text = re.sub(r"\n\s*\*\*Version:\*\*.*\n", "\n", text)
    text = re.sub(r"\n\s*\*\*Date:\*\*.*\n", "\n", text)
    text = re.sub(r"\n\s*\*\*Status:\*\*.*\n", "\n", text)
    return normalize_whitespace(strip_html(text))


def infer_metadata(file_path: Path, source_label: str) -> dict:
    """
    Attach at least 3 searchable metadata tags per chunk.
    Returns: doc_type, department, priority_level, last_updated.
    """
    path_str = str(file_path).lower()
    name = file_path.stem.lower()

    # doc_type: policy, reference, prd, system_design, architecture
    if "policy" in path_str or "policies" in path_str:
        doc_type = "policy"
    elif "benchmark" in name or "reference" in name:
        doc_type = "reference"
    elif "prd" in name:
        doc_type = "prd"
    elif "system_design" in name or "system_design" in path_str:
        doc_type = "system_design"
    elif "langgraph" in name or "architecture" in name:
        doc_type = "architecture"
    else:
        doc_type = "documentation"

    # department: claims, underwriting, product, engineering
    if doc_type in ("policy", "reference"):
        department = "claims"
    elif doc_type == "policy":
        department = "underwriting"
    elif doc_type in ("prd",):
        department = "product"
    elif doc_type in ("system_design", "architecture"):
        department = "engineering"
    else:
        department = "general"

    # priority_level: high (policy/claims), medium (design/architecture), low (reference)
    if doc_type == "policy":
        priority_level = "high"
    elif doc_type in ("prd", "system_design", "architecture"):
        priority_level = "medium"
    else:
        priority_level = "low"

    # last_updated: use file mtime or default to today
    try:
        mtime = os.path.getmtime(file_path)
        last_updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except OSError:
        last_updated = datetime.now().strftime("%Y-%m-%d")

    return {
        "doc_type": doc_type,
        "department": department,
        "priority_level": priority_level,
        "last_updated": last_updated,
        "source_file": source_label,
    }


# ---------------------------------------------------------------------------
# Task 2: Semantic Chunking
# ---------------------------------------------------------------------------

def chunk_by_sections(
    text: str,
    min_chars: int = CHUNK_MIN_CHARS,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text by markdown headers (## or ###) to keep full sections/clauses
    together. If a section exceeds max_chars, split by paragraph then by sentence.
    """
    # Split by ## or ### (at line start, optional leading whitespace)
    section_pattern = r"(?m)^(#{2,3}\s+.+)$"
    parts = re.split(section_pattern, text)
    chunks = []
    current = []
    current_len = 0

    i = 0
    while i < len(parts):
        block = parts[i]
        block_stripped = block.strip()
        if not block_stripped:
            i += 1
            continue
        # If it's a header line (starts with ##)
        if re.match(r"^#{2,3}\s+", block_stripped):
            if current and current_len >= min_chars:
                chunk_text = "\n\n".join(current)
                chunks.append(chunk_text)
                # Overlap: keep last paragraph/sentence
                if overlap and current:
                    overlap_text = current[-1]
                    if len(overlap_text) > overlap:
                        overlap_text = overlap_text[-overlap:]
                    current = [overlap_text]
                    current_len = len(overlap_text)
                else:
                    current = []
                    current_len = 0
            current = [block_stripped]
            current_len = len(block_stripped)
            i += 1
            continue
        # Content block
        if current_len + len(block_stripped) + 2 <= max_chars:
            current.append(block_stripped)
            current_len += len(block_stripped) + 2
            i += 1
        else:
            # Block too big: split by paragraph
            paras = [p.strip() for p in block_stripped.split("\n\n") if p.strip()]
            for p in paras:
                if current_len + len(p) + 2 <= max_chars:
                    current.append(p)
                    current_len += len(p) + 2
                else:
                    if current:
                        chunks.append("\n\n".join(current))
                        current = []
                        current_len = 0
                    if len(p) > max_chars:
                        # Split by sentence
                        sentences = re.split(r"(?<=[.!?])\s+", p)
                        for s in sentences:
                            if current_len + len(s) + 1 <= max_chars:
                                current.append(s)
                                current_len += len(s) + 1
                            else:
                                if current:
                                    chunks.append(" ".join(current))
                                current = [s]
                                current_len = len(s) + 1
                    else:
                        current = [p]
                        current_len = len(p) + 2
            i += 1

    if current and current_len >= min_chars:
        chunks.append("\n\n".join(current))
    elif current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if c.strip()]


def iter_documents() -> Iterator[tuple[str, Path, str]]:
    """
    Yield (content_cleaned, file_path, source_label) for all files to ingest.
    """
    # Data directory (policies, references)
    if DATA_DIR.exists():
        for ext in ("*.md", "*.txt"):
            for path in DATA_DIR.rglob(ext):
                if path.is_file():
                    try:
                        raw = path.read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        print(f"Skip {path}: {e}")
                        continue
                    cleaned = strip_domain_noise(raw, path)
                    if not cleaned.strip():
                        continue
                    label = path.relative_to(Path(__file__).parent)
                    yield cleaned, path, str(label)

    # Project docs (PRD, SYSTEM_DESIGN, LANGGRAPH)
    for name in PROJECT_DOC_FILES:
        path = PROJECT_DOCS_DIR / name
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"Skip {path}: {e}")
            continue
        cleaned = strip_domain_noise(raw, path)
        if not cleaned.strip():
            continue
        yield cleaned, path, name


# ---------------------------------------------------------------------------
# Embedding: Gemini (GEMINI_API_KEY) > OpenAI (OPENAI_API_KEY) > local
# ---------------------------------------------------------------------------

LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_embeddings_gemini(texts: list[str], model: str = GEMINI_EMBEDDING_MODEL) -> list[list[float]]:
    """Batch embed texts using Google Gemini API (GEMINI_API_KEY)."""
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    batch = [t if t.strip() else " " for t in texts]
    out = []
    batch_size = 100
    for i in range(0, len(batch), batch_size):
        chunk = batch[i : i + batch_size]
        result = client.models.embed_content(model=model, contents=chunk)
        embs = result.embeddings if isinstance(result.embeddings, list) else [result.embeddings]
        for e in embs:
            vals = getattr(e, "values", e)
            out.append(list(vals) if not isinstance(vals, list) else vals)
    return out


def get_embeddings_openai(texts: list[str], model: str = OPENAI_EMBEDDING_MODEL) -> list[list[float]]:
    """Batch embed texts using OpenAI API."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    out = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        b = texts[i : i + batch_size]
        b = [t if t.strip() else " " for t in b]
        resp = client.embeddings.create(input=b, model=model)
        for e in resp.data:
            out.append(e.embedding)
    return out


def get_embeddings_local(texts: list[str]) -> list[list[float]]:
    """Batch embed texts using local sentence-transformers (no API key)."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
    batch = [t if t.strip() else " " for t in texts]
    vectors = model.encode(batch, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# Task 3: Vector Indexing (ChromaDB)
# ---------------------------------------------------------------------------

def main():
    print("ClaimGuardian RAG — Ingestion pipeline")
    print("=" * 50)

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if gemini_key:
        embedding_backend = "gemini"
        print("Using Gemini for embeddings (GEMINI_API_KEY set).")
    elif openai_key:
        embedding_backend = "openai"
        print("Using OpenAI for embeddings (OPENAI_API_KEY set).")
    else:
        embedding_backend = "local"
        print("No API key set — using local embeddings (sentence-transformers).")

    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)

    chroma_client = chromadb.PersistentClient(
        path=str(CHROMA_PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "ClaimGuardian knowledge base: policies, docs, benchmarks"},
    )

    ids = []
    documents = []
    metadatas = []

    doc_count = 0
    chunk_count = 0

    for content, file_path, source_label in iter_documents():
        doc_count += 1
        base_meta = infer_metadata(file_path, source_label)
        chunks = chunk_by_sections(content, CHUNK_MIN_CHARS, CHUNK_MAX_CHARS, CHUNK_OVERLAP)
        for j, chunk in enumerate(chunks):
            chunk_id = f"{source_label}:{j}".replace(" ", "_").replace(os.sep, "_")
            ids.append(chunk_id[:200])
            documents.append(chunk)
            metadatas.append({**base_meta})
            chunk_count += 1

    if not documents:
        print("No documents to ingest. Add files under data/ or ensure project docs exist.")
        return

    print(f"Documents: {doc_count}, Chunks: {chunk_count}")
    print("Generating embeddings...")
    if embedding_backend == "gemini":
        embeddings = get_embeddings_gemini(documents)
    elif embedding_backend == "openai":
        embeddings = get_embeddings_openai(documents)
    else:
        embeddings = get_embeddings_local(documents)

    # ChromaDB expects metadata values to be str, int, float, or bool
    for m in metadatas:
        for k, v in m.items():
            if not isinstance(v, (str, int, float, bool)):
                m[k] = str(v)

    # Upsert in batches (ChromaDB limit)
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            documents=documents[i : i + batch_size],
            embeddings=embeddings[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )
        print(f"  Indexed chunks {i + 1}–{min(i + batch_size, len(documents))}/{len(documents)}")

    print(f"\nDone. Collection '{COLLECTION_NAME}' has {collection.count()} chunks.")
    print(f"Persisted to: {CHROMA_PERSIST_DIR}")


if __name__ == "__main__":
    main()
