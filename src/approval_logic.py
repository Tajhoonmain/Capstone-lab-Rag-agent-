"""
ClaimGuardian Lab 5: Task 2 & 3 — Human-in-the-Loop (HITL)

Demonstrates how to interrupt a graph before a high-risk action, 
allowing a human to review and edit the state before proceeding.
"""

import os
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

# Import from local project modules
from src.multi_agent_graph import MultiAgentState, researcher_node, analyst_node, tool_node, route_researcher, route_analyst, route_tools
from src.agent_tools import send_decision_notification

# ---------------------------------------------------------------------------
# High-Risk Action Node
# ---------------------------------------------------------------------------

def notification_node(state: MultiAgentState):
    """
    High-risk Node: Sends the actual notification.
    This node will be interrupted before execution.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # Normally, the LLM would have called the tool. 
    # Here we just acknowledge the tool execution.
    print("\n[SYSTEM] Executing High-Risk Action: send_decision_notification")
    return state

# ---------------------------------------------------------------------------
# Graph Compilation with HITL
# ---------------------------------------------------------------------------

def create_hitl_graph():
    workflow = StateGraph(MultiAgentState)

    workflow.add_node("researcher", researcher_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("notification_node", notification_node)

    workflow.add_edge(START, "researcher")

    workflow.add_conditional_edges(
        "researcher", 
        route_researcher, 
        {"tools": "tools", "analyst": "analyst"}
    )

    workflow.add_conditional_edges(
        "analyst",
        route_analyst,
        {"tools": "tools", END: END}
    )

    # Note: For this demo, we can modify route_analyst or add a manual transition
    # to the notification_node to trigger the HITL pause.
    
    workflow.add_conditional_edges(
        "tools",
        route_tools,
        {"researcher": "researcher", "analyst": "analyst"}
    )

    # Use a persistent checkpointer
    memory = SqliteSaver.from_conn_string("checkpoint_db.sqlite")
    
    # CRITICAL: interrupt_before=["notification_node"]
    return workflow.compile(checkpointer=memory, interrupt_before=["notification_node"])

# ---------------------------------------------------------------------------
# HITL Execution Demo
# ---------------------------------------------------------------------------

def run_hitl_demo():
    print("\n" + "="*60)
    print(" ClaimGuardian HITL Test: Safety Pauses & State Editing ")
    print("="*60 + "\n")

    graph = create_hitl_graph()
    thread_id = "hitl-thread-789"
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Start the process
    query = "User Alex (USER-67890) on POL-12345 has a low risk score. Propose a decision notification email."
    print(f"Query: {query}\n")
    
    initial_input = {"messages": [HumanMessage(content=query)]}
    
    # We need to manually route to notification_node for the demo if the LLM doesn't.
    # For simplicity in this lab, let's assume the Analyst calls the tool.
    
    print("--- Running until interrupt ---")
    for event in graph.stream(initial_input, config, stream_mode="values"):
         pass
    
    # Check if we are at an interrupt
    state = graph.get_state(config)
    if state.next:
        print(f"\n[HITL] PAUSED! Next scheduled node: {state.next}")
        print("-" * 30)
        print("PROPOSED STATE REVIEW:")
        last_msg = state.values["messages"][-1]
        print(f"Agent wants to call: {last_msg.tool_calls[0]['name'] if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls else 'None'}")
        
        # Task 3: State Editing
        print("\n[HITL] HUMAN INTERVENTION: Editing the email body...")
        # We find the tool call and edit its arguments
        edited_messages = state.values["messages"]
        if hasattr(edited_messages[-1], "tool_calls") and edited_messages[-1].tool_calls:
            edited_messages[-1].tool_calls[0]["args"]["body"] = "EDITED BY HUMAN: Your claim for the burst pipe is approved with a waiver on the deductible."
            print(f"New Body: {edited_messages[-1].tool_calls[0]['args']['body']}")
        
        # Update the state with the edited message
        graph.update_state(config, {"messages": edited_messages})
        
        print("\n[HITL] HUMAN COMMAND: Proceeding with edited state.")
        # Resume the graph (passing None to continue from the checkpoint)
        for event in graph.stream(None, config, stream_mode="values"):
            pass
        
        print("\n--- Process Complete ---")
        final_msg = event["messages"][-1]
        print(f"Final Outcome: {final_msg.content[:100]}...")
    else:
        print("\n[ERROR] Graph did not interrupt as expected.")

if __name__ == "__main__":
    os.environ["CHROMA_TELEMETRY"] = "false"
    run_hitl_demo()
