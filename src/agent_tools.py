"""
ClaimGuardian RAG Pipeline: ReAct Loop Tools

Lab 3: Autonomous Reasoning — Defining the project-specific toolset.
Contains tools for policy lookup, fraud scoring, and semantic (vector) search.
All tools are strictly validated using Pydantic and annotated with @tool.
"""

import os
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.tools import tool

import chromadb
from chromadb.config import Settings

# Suppress ChromaDB telemetry warnings
os.environ["CHROMA_TELEMETRY"] = "false"

# ---------------------------------------------------------------------------
# Tool 1: Grounding Tool (Semantic Search)
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR = Path(__file__).parent.parent / "chroma_db"
COLLECTION_NAME = "claimguardian_knowledge"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

def _embed_query(text: str) -> list[float]:
    """Helper to embed the search query using the appropriate model."""
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
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        r = client.embeddings.create(input=[text], model=OPENAI_EMBEDDING_MODEL)
        return r.data[0].embedding
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
    return model.encode([text], convert_to_numpy=True)[0].tolist()


class SemanticSearchInput(BaseModel):
    query: str = Field(description="Natural language query describing the claim or policy question to search for.")
    policy_version: str = Field(default="v2.0", description="Policy version to search. Defaults to 'v2.0'.")
    top_k: int = Field(default=3, description="Number of top results to return. Defaults to 3.")


@tool("semantic_search_policy", args_schema=SemanticSearchInput)
def semantic_search_policy(query: str, policy_version: str = "v2.0", top_k: int = 3) -> list[dict]:
    """
    Performs semantic search on ClaimGuardian policy documents and benchmarks
    to find relevant clauses based on a natural language query.
    Use this tool to read actual policy language, coverage rules, exclusions, and repair cost benchmarks.
    """
    try:
        chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_PERSIST_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        collection = chroma_client.get_collection(COLLECTION_NAME)
    except Exception as e:
        return [{"error": f"Failed to connect to Knowledge Base: {e}"}]

    try:
        q_embed = _embed_query(query)
        results = collection.query(
            query_embeddings=[q_embed],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        clauses = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            ids = results["ids"][0]
            docs = results["documents"][0]
            metadatas = results["metadatas"][0]
            for id_, doc, meta in zip(ids, docs, metadatas):
                clauses.append({
                    "id": id_,
                    "content": doc,
                    "doc_type": meta.get("doc_type", "unknown"),
                    "department": meta.get("department", "unknown")
                })
        return clauses
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]


# ---------------------------------------------------------------------------
# Tool 2: Action Tool (Policy Lookup)
# ---------------------------------------------------------------------------

class QueryPolicyInput(BaseModel):
    policy_id: str = Field(description="Unique identifier for the policy, usually formatted like 'POL-12345'")


@tool("query_policy", args_schema=QueryPolicyInput)
def query_policy(policy_id: str) -> dict:
    """
    Retrieves policyholder information including coverage limits, deductibles, effective dates, and status.
    Use this tool to verify if a policy is active and check specific coverage dollar amounts.
    """
    # Mocked database response for purposes of this lab
    mock_db = {
        "POL-12345": {
            "policy_id": "POL-12345",
            "user_id": "USER-67890",
            "policy_type": "Homeowner",
            "status": "Active",
            "coverage_dwelling": 500000.00,
            "coverage_personal_property": 250000.00,
            "deductible": 1000.00,
            "effective_date": "2024-01-01",
            "expiration_date": "2025-01-01"
        },
        "POL-99999": {
            "policy_id": "POL-99999",
            "user_id": "USER-11111",
            "policy_type": "Renter",
            "status": "Expired",
            "coverage_personal_property": 50000.00,
            "deductible": 500.00,
            "effective_date": "2022-01-01",
            "expiration_date": "2023-01-01"
        }
    }
    
    if policy_id in mock_db:
        return mock_db[policy_id]
    else:
        return {"error": f"PolicyNotFoundError: Policy '{policy_id}' does not exist in system."}


# ---------------------------------------------------------------------------
# Tool 3: Action Tool (Fraud Risk Assessment)
# ---------------------------------------------------------------------------

class FraudScoreInput(BaseModel):
    user_id: str = Field(description="Unique identifier for the policyholder (e.g. 'USER-67890')")
    claim_amount: float = Field(description="The dollar amount claimed for the repair/loss")


@tool("calculate_fraud_score", args_schema=FraudScoreInput)
def calculate_fraud_score(user_id: str, claim_amount: float) -> dict:
    """
    Calculates a fraud risk score (0.0 to 1.0) and retrieves risk indicators for a claim based on user history and claim anomalies.
    Use this tool to assess risk level for a claim before generating a decision rationale.
    """
    # Mocked fraud score and indicators response
    if claim_amount > 50000:
        return {
            "fraud_score": 0.85, 
            "risk_level": "Critical",
            "indicators": ["Amount_Anomaly: Claim amount is significantly outside normal parameters", "High_Severity"]
        }
    elif user_id == "USER-11111": # hardcoded risky user for testing
        return {
            "fraud_score": 0.72,
            "risk_level": "High",
            "indicators": ["Claim_Frequency: User has filed 4 claims in 12 months"]
        }
    else:
        return {
            "fraud_score": 0.15,
            "risk_level": "Low",
            "indicators": ["Amount_Anomaly: Claim amount is well within expected range", "Claim_Frequency: Normal"]
        }


# ---------------------------------------------------------------------------
# Tool 4: High-Risk Action (Notification)
# ---------------------------------------------------------------------------

class NotificationInput(BaseModel):
    recipient_email: str = Field(description="Email address of the policyholder")
    subject: str = Field(description="Subject line for the claim decision")
    body: str = Field(description="Content of the decision notice")

@tool("send_decision_notification", args_schema=NotificationInput)
def send_decision_notification(recipient_email: str, subject: str, body: str) -> str:
    """
    Sends a formal claim decision notification to the user.
    CRITICAL: This tool performs an external operation and requires manual review.
    """
    # Mocking the actual email sending process
    print(f"\n[SYSTEM] MOCK_EMAIL_SEND TO: {recipient_email}")
    print(f"[SYSTEM] SUBJECT: {subject}")
    print(f"[SYSTEM] BODY: {body}")
    return f"SUCCESS: Notification sent to {recipient_email} regarding '{subject}'."

# Combine tools into a list to be easily imported and bound to the LangGraph model
claim_guardian_tools = [semantic_search_policy, query_policy, calculate_fraud_score, send_decision_notification]

if __name__ == "__main__":
    print("Testing Tool Schemas and Invocations...\n")
    print("1. query_policy schema:")
    print(query_policy.args_schema.schema())
    print("\n2. Test invoking query_policy for 'POL-12345':")
    print(query_policy.invoke({"policy_id": "POL-12345"}))
