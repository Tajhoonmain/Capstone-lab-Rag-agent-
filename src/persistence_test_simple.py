"""
ClaimGuardian Lab 5: Task 1 — Simplified Persistent Memory (Checkpointing)

A lightweight test to verify SqliteSaver functionality without complex tool calls.
"""

import os
from pathlib import Path
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_google_genai import ChatGoogleGenerativeAI

class SimpleState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def chat_node(state: SimpleState):
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def run_simple_persistence():
    print("\n" + "="*60)
    print(" Simplified Persistence Test: SqliteSaver ")
    print("="*60 + "\n")

    workflow = StateGraph(SimpleState)
    workflow.add_node("chat", chat_node)
    workflow.add_edge(START, "chat")
    workflow.add_edge("chat", END)

    db_path = "simple_checkpoint.sqlite"
    with SqliteSaver.from_conn_string(db_path) as memory:
        graph = workflow.compile(checkpointer=memory)
        thread_id = "simple-thread-1"
        config = {"configurable": {"thread_id": thread_id}}

        # Session 1
        print("--- Session 1 ---")
        msg1 = HumanMessage(content="My secret code is 'ABRACADABRA'. Remember it.")
        print(f"User: {msg1.content}")
        for event in graph.stream({"messages": [msg1]}, config, stream_mode="values"):
            pass
        print(f"Agent: {event['messages'][-1].content}\n")

        # Session 2
        print("--- Session 2 ---")
        msg2 = HumanMessage(content="What is my secret code?")
        print(f"User: {msg2.content}")
        for event in graph.stream({"messages": [msg2]}, config, stream_mode="values"):
            pass
        print(f"Agent Response: {event['messages'][-1].content}")

        if "ABRACADABRA" in event['messages'][-1].content:
            print("\nSUCCESS: Persistence verified.")
        else:
            print("\nFAILURE: Context lost.")

if __name__ == "__main__":
    os.environ["CHROMA_TELEMETRY"] = "false"
    run_simple_persistence()
