"""Compile the agent StateGraph (singleton) with the configured checkpointer.

START -> prepare -> supervisor -> {agent|rag|direct|clarify} -> finalize -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents import nodes, supervisor
from app.agents.state import RootState
from app.memory.checkpointer import get_checkpointer

_graph = None


def _route(state: RootState) -> str:
    return state.get("route") or "direct"


def build_graph() -> StateGraph:
    b = StateGraph(RootState)
    b.add_node("prepare", nodes.prepare_node)
    b.add_node("supervisor", supervisor.supervisor_node)
    b.add_node("agent", nodes.agent_node)
    b.add_node("rag", nodes.rag_node)
    b.add_node("direct", nodes.direct_node)
    b.add_node("clarify", nodes.clarify_node)
    b.add_node("finalize", nodes.finalize_node)

    b.add_edge(START, "prepare")
    b.add_edge("prepare", "supervisor")
    b.add_conditional_edges(
        "supervisor", _route,
        {"agent": "agent", "rag": "rag", "direct": "direct", "clarify": "clarify"},
    )
    for n in ("agent", "rag", "direct", "clarify"):
        b.add_edge(n, "finalize")
    b.add_edge("finalize", END)
    return b


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph().compile(checkpointer=get_checkpointer())
    return _graph
