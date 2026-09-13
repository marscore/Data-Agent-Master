"""LangGraph state for the agent graph.

Plain-dict messages only (never langgraph add_messages) — the tool loop stashes
`_anthropic_content` (raw Bedrock blocks with thinking/tool_use signatures) on
assistant messages and must replay them verbatim next turn; add_messages would
coerce to AIMessage/ToolMessage and drop that key. The ReAct loop runs entirely
inside one node, so `messages` never has to cross a superstep.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RootState(TypedDict, total=False):
    # conversation
    user_message: str
    history: List[Dict[str, str]]
    lang: str

    # prepared context
    tool_names: List[str]           # federated tool flat-names available this turn
    retrieved_docs: List[Dict[str, Any]]
    rag_context: str

    # routing
    route: str                      # agent | rag | direct | clarify

    # tool loop observability (summaries only, no raw args/PII downstream)
    tool_calls: List[Dict[str, Any]]

    # terminal
    final_text: str
