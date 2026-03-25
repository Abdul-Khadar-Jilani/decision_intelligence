from __future__ import annotations

from dataclasses import dataclass, field

from graph.nodes.critic import CritiqueReport


@dataclass(slots=True)
class ResearchGraph:
    """Simple directed graph representation for research orchestration."""

    edges: dict[str, list[str]] = field(default_factory=dict)

    def add_edge(self, source: str, target: str) -> None:
        self.edges.setdefault(source, []).append(target)

    def next_nodes(self, node: str) -> tuple[str, ...]:
        return tuple(self.edges.get(node, []))


def build_research_graph() -> ResearchGraph:
    graph = ResearchGraph()
    graph.add_edge("planner", "research")
    graph.add_edge("research", "critic")

    # Loop: critic can request targeted re-research before synthesis.
    graph.add_edge("critic", "targeted_research")
    graph.add_edge("targeted_research", "critic")

    # Exit path once quality gates pass.
    graph.add_edge("critic", "synthesis")
    return graph


def choose_post_critic_node(report: CritiqueReport) -> str:
    """Route back to targeted research when critique flags severe issues."""
    return "targeted_research" if report.should_reresearch else "synthesis"
