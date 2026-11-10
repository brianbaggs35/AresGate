# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""The only place LangGraph is called, so the rest of the agents can be strictly typed.

LangGraph ships no type information that pyright can read, so what it gives back is unknown to it.
What is wrapped here is what the agents use of it: a graph of nodes with one conditional edge,
run to the end while it says what each node starts and what the whole state is after each step,
and what the graph looks like, for a page that draws it.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

Node = Callable[[Any], dict[str, object] | Awaitable[dict[str, object]]]


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    # Whether the graph chooses it at run time (after ``think``: look again, or report).
    conditional: bool


def compile_graph(state: type, nodes: Mapping[str, Node], route: Callable[[Any], str]) -> Any:
    """The graph of a run: ``plan``, ``act`` and ``think`` in turn, and then, as ``route`` says,
    ``act`` again or ``report``."""
    graph = StateGraph(state)
    for name, node in nodes.items():
        graph.add_node(name, cast("Any", node))
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "think")
    graph.add_conditional_edges("think", route, {"act": "act", "report": "report"})
    graph.add_edge("report", END)
    return graph.compile()


def edges_of(compiled: Any) -> list[Edge]:
    """The edges between the nodes of a graph, as LangGraph reports them."""
    found = compiled.get_graph()
    return [
        Edge(edge.source, edge.target, bool(edge.conditional))
        for edge in found.edges
        if not edge.source.startswith("__") and not edge.target.startswith("__")
    ]


async def stream(compiled: Any, state: object) -> AsyncGenerator[tuple[str, Any]]:
    """What a run does, as it does it: ``("tasks", ...)`` when a node starts and when it finishes,
    and ``("values", ...)`` with the whole state after each step."""
    async for mode, payload in compiled.astream(state, stream_mode=["tasks", "values"]):
        yield mode, payload
