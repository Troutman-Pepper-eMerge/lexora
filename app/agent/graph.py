"""LangGraph agent: ReAct-style tool-using assistant.

The graph is intentionally compact - a single 'agent' node that the LLM
loops through until it stops emitting tool calls. Tools come from the
shared TOOL_REGISTRY so they stay in sync with the MCP server.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

from ..azure_clients import get_chat_llm
from .tools import TOOL_REGISTRY

log = logging.getLogger("lexora.agent")

SYSTEM = """You are LEXORA, an agentic litigation lifecycle copilot for a top-tier US law firm.

Capabilities:
  * Search the firm's case portfolio, retrieve case details, run analytics.
  * Answer questions about ingested case documents using RAG; always cite
    filename + page when you quote evidence.
  * Schedule, reschedule and notify attendees about appointments.
  * Generate structured case reports and portfolio insights.

Operating rules:
  1. Use tools rather than guessing. If a fact would benefit from data,
     call the relevant tool first.
  2. When the user asks an analytic question (e.g. "which state takes
     longest to adjudicate?"), call `portfolio_analytics` and reason
     over the returned `adjudication_time_by_state` array.
  3. For document questions, call `query_documents` with the user's
     question (and case_id when known) and synthesize an answer that
     cites filename + page.
  4. Be concise. Prefer bulleted answers for executives.
  5. Never invent case numbers, judges, or document contents.
"""


# --------------------------------------------------------------------- #
# Wrap registry as LangChain StructuredTools                            #
# --------------------------------------------------------------------- #
def _make_langchain_tools() -> List[StructuredTool]:
    tools: List[StructuredTool] = []
    for name, (fn, desc) in TOOL_REGISTRY.items():
        tools.append(StructuredTool.from_function(
            func=fn, name=name, description=desc, return_direct=False,
        ))
    return tools


# --------------------------------------------------------------------- #
# Graph                                                                 #
# --------------------------------------------------------------------- #
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


@lru_cache
def _compiled_graph():
    tools = _make_langchain_tools()
    llm = get_chat_llm(temperature=0.1).bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    def agent_node(state: AgentState) -> Dict[str, Any]:
        rsp = llm.invoke(state["messages"])
        return {"messages": [rsp]}

    def tools_node(state: AgentState) -> Dict[str, Any]:
        last = state["messages"][-1]
        out: list = []
        for call in getattr(last, "tool_calls", []) or []:
            name = call["name"]; args = call.get("args", {})
            tool = tool_map.get(name)
            if not tool:
                content = json.dumps({"error": f"unknown tool {name}"})
            else:
                try:
                    result = tool.invoke(args)
                    content = json.dumps(result, default=str)
                except Exception as exc:                         # pragma: no cover
                    log.exception("tool %s failed", name)
                    content = json.dumps({"error": str(exc)})
            out.append(ToolMessage(content=content, tool_call_id=call["id"], name=name))
        return {"messages": out}

    def route(state: AgentState):
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile()


def run_agent(user_message: str, history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
    """Single-turn invocation. `history` is a list of {role, content} dicts."""
    msgs: list = [SystemMessage(content=SYSTEM)]
    for m in history or []:
        if m["role"] == "user":
            msgs.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            msgs.append(AIMessage(content=m["content"]))
    msgs.append(HumanMessage(content=user_message))

    graph = _compiled_graph()
    state = graph.invoke({"messages": msgs}, config={"recursion_limit": 18})

    tool_trace = []
    final = ""
    for m in state["messages"]:
        if isinstance(m, ToolMessage):
            tool_trace.append({"tool": m.name, "result": _safe_load(m.content)})
        elif isinstance(m, AIMessage):
            if m.content:
                final = m.content
            for tc in (m.tool_calls or []):
                tool_trace.append({"tool": tc["name"], "args": tc.get("args", {}),
                                   "result": None})

    return {"answer": final, "trace": tool_trace}


def _safe_load(s: str):
    try:
        return json.loads(s)
    except Exception:
        return s
