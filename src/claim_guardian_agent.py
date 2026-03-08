"""
ClaimGuardian RAG Pipeline: ReAct Loop Graph

Lab 3: Autonomous Reasoning — Moving from static retrieval to autonomous reasoning.
Implements a ReAct (Reason + Act) loop using the LangGraph framework.
"""

import os
import json
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from agent_tools import claim_guardian_tools

# Load environment variables if needed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Suppress ChromaDB telemetry warnings
os.environ["CHROMA_TELEMETRY"] = "false"

# ---------------------------------------------------------------------------
# Task 2: Defining the Graph State & Nodes
# ---------------------------------------------------------------------------

# Define the State: stores the message history of thoughts and actions
class GraphState(TypedDict):
    # The `add_messages` reducer appends new messages to the existing list
    messages: Annotated[list[BaseMessage], add_messages]


# Initialize the LLM (Gemini)
def _get_llm():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent / ".env")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment or .env file")
        
    from langchain_google_genai import ChatGoogleGenerativeAI
    print("Initializing graph with Gemini 3 Flash model (Reasoning optimized).")
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview", 
        temperature=1.0,
        google_api_key=gemini_key
    )

# Instantiate LLM and bind our project-specific tools to it
llm = _get_llm()
bound_llm = llm.bind_tools(claim_guardian_tools)


def agent_node(state: GraphState):
    """
    The Agent Node: Takes the current state, calls the LLM with the injected tools,
    and returns the updated state containing the new message.
    """
    if not bound_llm:
         raise RuntimeError("LLM not initialized successfully.")
    
    recent_messages = state["messages"]
    print("Agent is reasoning...")
    response = bound_llm.invoke(recent_messages)
    # Wrap response in a dict containing the "messages" key to append to state
    return {"messages": [response]}


# Custom Tool Node implementation
def tool_node(state: GraphState):
    messages = state["messages"]
    last_message = messages[-1]
    
    # We will output new tool messages for every tool call
    tool_outputs = []
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            # Find the matching tool
            matched_tool = next((t for t in claim_guardian_tools if t.name == tool_name), None)
            
            if matched_tool:
                try:
                    result = matched_tool.invoke(tool_args)
                    tool_msg = ToolMessage(content=str(result), name=tool_name, tool_call_id=tool_call_id)
                except Exception as e:
                    tool_msg = ToolMessage(content=f"Error executing tool: {e}", name=tool_name, tool_call_id=tool_call_id)
            else:
                tool_msg = ToolMessage(content=f"Error: Tool '{tool_name}' not found.", name=tool_name, tool_call_id=tool_call_id)
                
            tool_outputs.append(tool_msg)
            
    return {"messages": tool_outputs}


# ---------------------------------------------------------------------------
# Task 3: The Conditional Router
# ---------------------------------------------------------------------------

def route_tools(state: GraphState):
    """
    The Conditional Router function. Checks the LLM's last message.
    If it generated 'tool_calls', route to the Tool Node.
    If it generated a 'Final Answer' without tool_calls, route to END.
    """
    last_message = state["messages"][-1]
    
    # Check if the LLM returned any tool calls to be executed
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        print(f"Agent decided to make {len(last_message.tool_calls)} Tool Call(s):")
        for tc in last_message.tool_calls:
             print(f" -> Invoking: {tc['name']} with args: {tc['args']}")
        return "tools"
    
    # Otherwise, it generated a final answer text, so finish the graph.
    print("Agent finished reasoning.")
    return END


# Compile the LangGraph components into an orchestratable loop
graph_builder = StateGraph(GraphState)

# Add our two main nodes
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)

# Add sequential entry edge
graph_builder.add_edge(START, "agent")

# Add conditional exit edge from agent
# If `route_tools` returns "tools", go to tools node. If it returns END, finish.
graph_builder.add_conditional_edges("agent", route_tools, ["tools", END])

# Add sequential edge returning back to agent for the next step of the loop after a tool executes
graph_builder.add_edge("tools", "agent")

# Compile the graph
claim_guardian_graph = graph_builder.compile()


if __name__ == "__main__":
    print("\n============================================================")
    print("ClaimGuardian LangGraph ReAct Agent")
    print("============================================================\n")
    
    # Example test query
    query = "User USER-67890 submitted a water damage claim for $3500 on policy POL-12345. First, verify the policy status and limits. Second, check if the policy documents cover burst pipe incidents. Finally, give me a risk assessment score based on their history. Summarize the decision."
    
    print(f"Target Query: '{query}'\n")
    
    # Invoke the graph with the initial state
    initial_state = {"messages": [HumanMessage(content=query)]}
    
    try:
        final_state = claim_guardian_graph.invoke(initial_state)
        print("\n\n=== Final Agent Response ===")
        print(final_state["messages"][-1].content)
    except Exception as e:
        print(f"\nExecution failed: {e}")
