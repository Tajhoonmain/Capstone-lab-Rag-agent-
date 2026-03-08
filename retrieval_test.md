# Retrieval Test — ClaimGuardian Knowledge Base

This document describes **3 test queries** run against the `claimguardian_knowledge` ChromaDB collection after running `ingest_data.py`. At least one test demonstrates **metadata filtering** (query 2).

---

## Prerequisites

1. Run ingestion: `python ingest_data.py` (uses `GEMINI_API_KEY` if set, else `OPENAI_API_KEY`, else local embeddings).
2. Run queries with: `python run_retrieval_tests.py` (same key order: Gemini > OpenAI > local).

---

## Test Query 1: Semantic Search (No Filter)

**Query:**  
*What types of water damage are covered under the homeowner policy?*

**Purpose:**  
Verify that semantic search returns relevant policy clauses about water damage coverage without using metadata.

**Expected behavior:**  
Top results should include chunks from `data/policies/homeowner_policy_standard_v2.md`, specifically content about:
- Sudden and accidental discharge from plumbing (e.g., burst pipes) being covered
- Gradual leakage or seepage (e.g., over 14+ days) not being covered

**Metadata filter:** None (pure semantic retrieval).

---

## Test Query 2: Metadata Filtering (doc_type)

**Query:**  
*Find the repair cost range for water damage, but only from the reference or benchmark documents.*

**Purpose:**  
Demonstrate **metadata filtering**: restrict results to chunks where `doc_type` is `reference` so that only repair benchmark data is returned, not policy or PRD text.

**Expected behavior:**  
Results should come only from `data/policies/repair_benchmarks_reference.md` (or any document tagged `doc_type == "reference"`), showing cost ranges for water damage (e.g., Minor: $1,200–$2,500; Moderate: $2,500–$5,000; Severe: $8,000–$25,000+).

**Metadata filter:**  
`{"doc_type": "reference"}`  
(or `{"doc_type": "reference"}` in ChromaDB `where` clause).

---

## Test Query 3: Semantic + High-Priority Policy

**Query:**  
*What are the main exclusions in the policy?*

**Purpose:**  
Verify retrieval of exclusion clauses and optionally bias toward high-priority policy content.

**Expected behavior:**  
Top results should include Section C (Exclusions) from the homeowner policy: flood exclusion, wear and tear, earth movement, etc.

**Metadata filter (optional):**  
`{"doc_type": "policy"}` to restrict to policy documents only, or no filter to allow any relevant chunk.

---

## Summary

| Test | Query focus                     | Metadata filter        | Validates                    |
|------|----------------------------------|-------------------------|-----------------------------|
| 1    | Water damage coverage           | None                    | Semantic search quality     |
| 2    | Repair costs from benchmarks    | `doc_type == "reference"` | **Metadata filtering**      |
| 3    | Policy exclusions               | Optional: `doc_type == "policy"` | Policy retrieval / filtering |

Running `python run_retrieval_tests.py` executes these three queries and prints the top retrieved chunks and metadata for verification.
