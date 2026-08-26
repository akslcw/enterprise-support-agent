from langgraph.checkpoint.memory import InMemorySaver

from app.agent import create_graph


def test_graph_contains_ticket_approval_nodes_and_edges() -> None:
    graph = create_graph(
        mcp_tools=[],
        checkpointer=InMemorySaver(),
    )

    graph_view = graph.get_graph()
    node_names = set(graph_view.nodes)
    edges = {
        (edge.source, edge.target)
        for edge in graph_view.edges
    }

    assert "capture_ticket_draft" in node_names
    assert "request_ticket_approval" in node_names
    assert ("tools", "capture_ticket_draft") in edges
    assert ("tools", "agent") not in edges