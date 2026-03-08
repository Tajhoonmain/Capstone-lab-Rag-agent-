"""
Run the 3 retrieval tests from retrieval_test.md against the ClaimGuardian ChromaDB collection.
Uses GEMINI_API_KEY if set, else OPENAI_API_KEY, else local sentence-transformers (same order as ingest_data.py).
Requires: ingest_data.py already run.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

os.environ["CHROMA_TELEMETRY"] = "false"
import chromadb
from chromadb.config import Settings

CHROMA_PERSIST_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "claimguardian_knowledge"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 3


def embed_query(text: str) -> list[float]:
    """Embed a single query: Gemini > OpenAI > local (must match ingest_data.py)."""
    if os.environ.get("GEMINI_API_KEY"):
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        result = client.models.embed_content(model=GEMINI_EMBEDDING_MODEL, contents=text)
        e = result.embeddings
        e = e[0] if isinstance(e, list) else e
        vals = getattr(e, "values", e)
        return list(vals) if not isinstance(vals, list) else vals
    if os.environ.get("OPENAI_API_KEY"):
        from openai import OpenAI
        client = OpenAI()
        r = client.embeddings.create(input=[text], model=OPENAI_EMBEDDING_MODEL)
        return r.data[0].embedding
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
    return model.encode([text], convert_to_numpy=True)[0].tolist()


def main():
    if os.environ.get("GEMINI_API_KEY"):
        print("Using Gemini for query embeddings.")
    elif os.environ.get("OPENAI_API_KEY"):
        print("Using OpenAI for query embeddings.")
    else:
        print("Using local embeddings (sentence-transformers).")

    chroma_client = chromadb.PersistentClient(
        path=str(CHROMA_PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        collection = chroma_client.get_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"Collection not found. Run ingest_data.py first. Error: {e}")
        return

    tests = [
        {
            "name": "Test 1: Semantic search (no filter)",
            "query": "What types of water damage are covered under the homeowner policy?",
            "where": None,
        },
        {
            "name": "Test 2: Metadata filtering (reference only)",
            "query": "Find the repair cost range for water damage, but only from the reference or benchmark documents.",
            "where": {"doc_type": "reference"},
        },
        {
            "name": "Test 3: Policy exclusions",
            "query": "What are the main exclusions in the policy?",
            "where": {"doc_type": "policy"},
        },
    ]

    for t in tests:
        print("\n" + "=" * 60)
        print(t["name"])
        print("Query:", t["query"])
        print("Filter:", t["where"])
        print("-" * 60)
        q_embed = embed_query(t["query"])
        kwargs = {
            "query_embeddings": [q_embed],
            "n_results": TOP_K,
            "include": ["documents", "metadatas", "distances"],
        }
        if t["where"] is not None:
            kwargs["where"] = t["where"]
        results = collection.query(**kwargs)
        ids = results["ids"][0]
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]
        for i, (id_, doc, meta, dist) in enumerate(zip(ids, docs, metadatas, distances), 1):
            print(f"\n  Result {i} (id={id_}, distance={dist:.4f})")
            print(f"  doc_type: {meta.get('doc_type')}, department: {meta.get('department')}")
            print(f"  Text: {doc[:300]}..." if len(doc) > 300 else f"  Text: {doc}")
    print("\n" + "=" * 60)
    print("Retrieval tests done.")


if __name__ == "__main__":
    main()
