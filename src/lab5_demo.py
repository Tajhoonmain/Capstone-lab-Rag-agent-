"""
ClaimGuardian Lab 5: Task 1, 2, & 3 — Persistence & HITL (Final Demo)

Demonstrates LangGraph's checkpointer and interrupt capabilities 
using a persistent SQLite backend and simulated nodes.
"""

import os
import sqlite3
from pathlib import Path
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

# ---------------------------------------------------------------------------
# State & Nodes
# ---------------------------------------------------------------------------

class DemoState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def researcher_node(state: DemoState):
    print("\n[Researcher] Simulated research complete.")
    return {"messages": [AIMessage(content="Research shows POL-12345 covers water damage.")] }

def analyst_node(state: DemoState):
    print("\n[Analyst] Simulated analysis complete. Proposing Decision Email.")
    tool_call = {
        "name": "send_decision_notification",
        "args": {
            "recipient_email": "alex@example.com",
            "subject": "Claim Decision: Approved",
            "body": "Your claim for water damage has been approved."
        },
        "id": "call_123"
    }
    return {"messages": [AIMessage(content="", tool_calls=[tool_call])]}

def notification_node(state: DemoState):
    print("\n[SYSTEM] Executing High-Risk Action: send_decision_notification")
    last_message = state["messages"][-1]
    tool_args = last_message.tool_calls[0]["args"]
    
    print(f" -> SENDING EMAIL TO: {tool_args['recipient_email']}")
    print(f" -> CONTENT: {tool_args['body']}")
    
    return {"messages": [ToolMessage(content="Email sent successfully.", tool_call_id=last_message.tool_calls[0]["id"])]}

# ---------------------------------------------------------------------------
# Execution Logic
# ---------------------------------------------------------------------------

def run_lab5_demo():
    print("\n" + "="*60)
    print(" ClaimGuardian Lab 5 FINAL VERIFICATION ")
    print("="*60 + "\n")

    workflow = StateGraph(DemoState)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("notification_node", notification_node)

    workflow.add_edge(START, "researcher")
    workflow.add_edge("researcher", "analyst")
    workflow.add_edge("notification_node", END)

    # Persistence Setup
    # Using a connection string or connection object
    db_path = "checkpoint_db.sqlite"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)
    
    # CRITICAL: Safety Breakpoint
    graph = workflow.compile(checkpointer=memory, interrupt_before=["notification_node"])

    thread_id = "lab5-thread-final"
    config = {"configurable": {"thread_id": thread_id}}

    # 1. INITIAL RUN (Session 1)
    print("--- Session 1: Running until Safety Breakpoint ---")
    query = "Process claim for Alex on POL-12345."
    print(f"User: {query}")
    
    for event in graph.stream({"messages": [HumanMessage(content=query)]}, config, stream_mode="values"):
        pass

    # 2. VERIFY INTERRUPT & PERSISTENCE
    state = graph.get_state(config)
    if state.next:
        print(f"\n[HITL] PAUSED before node: {state.next}")
        
        # 3. STATE EDITING (Task 3)
        print("\n[HITL] HUMAN INTERVIEW: Editing the decision content...")
        msgs = list(state.values["messages"])
        # The last message is the Analyst's proposal
        if hasattr(msgs[-1], "tool_calls") and msgs[-1].tool_calls:
            msgs[-1].tool_calls[0]["args"]["body"] = "MODIFIED BY HUMAN: Your claim is approved. We will issue payment for $3500 immediately."
            print(f"New Body: {msgs[-1].tool_calls[0]['args']['body']}")
        
        # Update state persistently
        graph.update_state(config, {"messages": msgs})
        print("Checkpoint updated in SQL database.")

        # 4. RESUME (Session 2 - Persistence Proof)
        print("\n--- Session 2: Resuming with Human Approval ---")
        for event in graph.stream(None, config, stream_mode="values"):
            pass
        
        print("\n[DONE] Workflow finished successfully.")
        final_msg = event["messages"][-1]
        print(f"Final Agent Status: {final_msg.content}")

if __name__ == "__main__":
    run_lab5_demo()
