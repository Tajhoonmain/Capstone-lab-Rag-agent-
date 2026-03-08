"""
ClaimGuardian Lab 5: Task 1 — Persistent Memory (Checkpointing)

Demonstrates how SqliteSaver allows an agent to remember previous context 
using a persistent thread_id.
"""

import os
from pathlib import Path
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

# Import the existing graph logic
# We'll use a slightly modified simple version or the multi-agent one
from src.multi_agent_graph import multi_agent_graph

# Setup persistence database
DB_PATH = Path("checkpoint_db.sqlite")

def run_persistence_demo():
    print("\n" + "="*60)
    print(" ClaimGuardian Persistence Test: SqliteSaver ")
    print("="*60 + "\n")

    # Initialize the checkpointer
    with SqliteSaver.from_conn_string(str(DB_PATH)) as memory:
        from src.multi_agent_graph import workflow
        # Use a stable model for persistence check
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
        graph = workflow.compile(checkpointer=memory)

        thread_id = "alex-session-123"
        config = {"configurable": {"thread_id": thread_id}}

        print(f"--- Session 1 (Thread: {thread_id}) ---")
        input_msg_1 = HumanMessage(content="My name is Alex and I'm inquiring about policy POL-12345.")
        print(f"User: {input_msg_1.content}\n")
        
        for event in graph.stream({"messages": [input_msg_1]}, config, stream_mode="values"):
            pass # Process silently for Demo
        
        last_msg = event["messages"][-1].content
        print(f"Agent: {last_msg}\n")

        print("--- Restarting Script (Simulated) ---\n")

        # 2. Second Session: Agent should remember "Alex" and "POL-12345"
        print(f"--- Session 2 (Thread: {thread_id}) ---")
        input_msg_2 = HumanMessage(content="What was the policy number I just mentioned, and what is my name?")
        print(f"User: {input_msg_2.content}\n")
        
        final_response = ""
        for event in graph.stream({"messages": [input_msg_2]}, config, stream_mode="values"):
            final_response = event["messages"][-1].content
        
        print(f"Agent Response: {final_response}")

        if "Alex" in final_response and "POL-12345" in final_response:
            print("\nSUCCESS: Persistence verified. Agent remembered context from Session 1.")
        else:
            print("\nFAILURE: Agent lost context.")

if __name__ == "__main__":
    # Ensure ChromaDB telemetry is off
    os.environ["CHROMA_TELEMETRY"] = "false"
    run_persistence_demo()
