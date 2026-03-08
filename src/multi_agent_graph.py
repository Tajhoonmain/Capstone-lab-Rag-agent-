"""
ClaimGuardian Multi-Agent Graph: The Specialist Team

Lab 4: Team of Specialists — Splitting responsibilities into personas.
Implements a handshake mechanism between Researcher and Analyst nodes.
"""

import os
import json
from typing import Annotated, TypedDict, Literal
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# Import from local project modules
from src.agent_tools import (
    semantic_search_policy, 
    query_policy, 
    calculate_fraud_score,
    claim_guardian_tools
)
from src.agents_config import AGENTS_CONFIG

# Suppress ChromaDB telemetry
os.environ["CHROMA_TELEMETRY"] = "false"

# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------

class MultiAgentState(TypedDict):
    # Standard message history
    messages: Annotated[list[BaseMessage], add_messages]
    # Track which agent is currently active to route tool results back
    active_agent: str


# ---------------------------------------------------------------------------
# LLM Initialization
# ---------------------------------------------------------------------------

def _get_llm():
    from dotenv import load_dotenv
    # Ensure env is loaded from project root if possible
    load_dotenv(Path(__file__).parent.parent / ".env")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY is not set.")
        
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview", 
        temperature=0.0, # Lower temperature for reliability in multi-agent logic
        google_api_key=gemini_key
    )

llm = _get_llm()

# Bind specific toolsets to specific agents
researcher_llm = llm.bind_tools(AGENTS_CONFIG["researcher"]["tools"])
analyst_llm = llm.bind_tools(AGENTS_CONFIG["analyst"]["tools"])


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------

def researcher_node(state: MultiAgentState):
    """Lead Policy Researcher Node."""
    messages = state["messages"]
    
    # Inject system prompt if this is the first researcher message
    if not any(isinstance(m, SystemMessage) and "Policy Researcher" in m.content for m in messages):
        messages = [SystemMessage(content=AGENTS_CONFIG["researcher"]["prompt"])] + messages

    print("\n[Researcher] Investigating claim documents...")
    response = researcher_llm.invoke(messages)
    
    # Prefix response to clearly show in logs who sent it
    if not response.tool_calls:
         print("[Researcher] Research complete. Handing over to Analyst.")
    
    return {
        "messages": [response],
        "active_agent": "researcher"
    }


def analyst_node(state: MultiAgentState):
    """Claims Fraud Analyst Node."""
    messages = state["messages"]
    
    # Inject system prompt if this is the first analyst message
    if not any(isinstance(m, SystemMessage) and "Fraud Analyst" in m.content for m in messages):
        messages = [SystemMessage(content=AGENTS_CONFIG["analyst"]["prompt"])] + messages

    print("\n[Analyst] Assessing risk and synthesizing decision...")
    response = analyst_llm.invoke(messages)
    
    return {
        "messages": [response],
        "active_agent": "analyst"
    }


def tool_node(state: MultiAgentState):
    """Specialized Tool Execution Node."""
    messages = state["messages"]
    last_message = messages[-1]
    active_agent = state.get("active_agent", "researcher")
    
    tool_outputs = []
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            # Find the matching tool from total project tools
            matched_tool = next((t for t in claim_guardian_tools if t.name == tool_name), None)
            
            if matched_tool:
                try:
                    print(f"[{active_agent.capitalize()}] Executing tool: {tool_name}")
                    result = matched_tool.invoke(tool_args)
                    tool_msg = ToolMessage(content=str(result), name=tool_name, tool_call_id=tool_call_id)
                except Exception as e:
                    tool_msg = ToolMessage(content=f"Error: {e}", name=tool_name, tool_call_id=tool_call_id)
            else:
                tool_msg = ToolMessage(content=f"Error: Tool '{tool_name}' unauthorized.", name=tool_name, tool_call_id=tool_call_id)
                
            tool_outputs.append(tool_msg)
            
    return {"messages": tool_outputs}


# ---------------------------------------------------------------------------
# Handover & Routing Logic
# ---------------------------------------------------------------------------

def route_researcher(state: MultiAgentState):
    """Routes from Researcher: Tools or Handover to Analyst."""
    last_message = state["messages"][-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    # If no tool calls, research is done. Hand over to Analyst.
    return "analyst"


def route_analyst(state: MultiAgentState):
    """Routes from Analyst: Tools or Final Answer."""
    last_message = state["messages"][-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    # If no tool calls, the Analyst has provided a final synthesis.
    print("[Analyst] Final assessment delivered.")
    return END


def route_tools(state: MultiAgentState):
    """Routes from Tools back to the agent that called them."""
    return state["active_agent"]


# ---------------------------------------------------------------------------
# Graph Compilation
# ---------------------------------------------------------------------------

workflow = StateGraph(MultiAgentState)

# Add Nodes
workflow.add_node("researcher", researcher_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("tools", tool_node)

# Add Entry Edge
workflow.add_edge(START, "researcher")

# Add Conditional Edges
# Researcher Handover logic
workflow.add_conditional_edges(
    "researcher", 
    route_researcher, 
    {
        "tools": "tools",
        "analyst": "analyst"
    }
)

# Analyst Finalization logic
workflow.add_conditional_edges(
    "analyst",
    route_analyst,
    {
        "tools": "tools",
        END: END
    }
)

# Router back from tools to appropriate agent
workflow.add_conditional_edges(
    "tools",
    route_tools,
    {
        "researcher": "researcher",
        "analyst": "analyst"
    }
)

# Compile
multi_agent_graph = workflow.compile()


# ---------------------------------------------------------------------------
# Execution (Test Case)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*60)
    print(" ClaimGuardian Multi-Agent Specialist Team ")
    print("="*60 + "\n")
    
    test_query = (
        "Check policy POL-12345 to see if it's active. Then, search the policy knowledge base "
        "to confirm if 'flood' is an excluded incident for v2.0 policies. "
        "Finally, assess the risk level for user USER-67890 for a $1200 claim."
    )
    
    print(f"Collaboration Start: {test_query}\n")
    
    initial_state = {
        "messages": [HumanMessage(content=test_query)],
        "active_agent": "researcher" 
    }
    
    try:
        final_state = multi_agent_graph.invoke(initial_state)
        print("\n" + "="*60)
        print(" FINAL COLLABORATIVE RESPONSE ")
        print("="*60 + "\n")
        print(final_state["messages"][-1].content)
        
    except Exception as e:
        print(f"\nMulti-agent collaboration failed: {e}")
