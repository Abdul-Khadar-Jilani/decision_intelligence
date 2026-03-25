"""Workflow graph builder with conditional branching, retries, and HITL pause/resume."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable

from graph.nodes import NodeFn
from graph.state import WorkflowState


ConditionFn = Callable[[WorkflowState], bool]
NextNodeFn = Callable[[WorkflowState], str | None]


@dataclass(slots=True)
class ConditionalEdge:
    """Represents a conditional transition to another node."""

    condition: ConditionFn
    target: str


@dataclass(slots=True)
class RetryRule:
    """Retry metadata for a node."""

    should_retry: ConditionFn
    max_attempts: int = 1


@dataclass(slots=True)
class CheckpointStore:
    """JSON file-based checkpoint persistence for pause/resume."""

    path: Path = field(default_factory=lambda: Path(".checkpoints/workflow_state.json"))

    def save(self, state: WorkflowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def load(self) -> WorkflowState:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def exists(self) -> bool:
        return self.path.exists()


@dataclass
class DecisionGraphBuilder:
    """Builds and executes a stateful node graph."""

    nodes: dict[str, NodeFn] = field(default_factory=dict)
    default_edges: dict[str, str] = field(default_factory=dict)
    conditional_edges: dict[str, list[ConditionalEdge]] = field(default_factory=dict)
    retry_rules: dict[str, RetryRule] = field(default_factory=dict)
    checkpoint_store: CheckpointStore = field(default_factory=CheckpointStore)

    def add_node(self, name: str, handler: NodeFn) -> "DecisionGraphBuilder":
        self.nodes[name] = handler
        return self

    def add_edge(self, source: str, target: str) -> "DecisionGraphBuilder":
        self.default_edges[source] = target
        return self

    def add_conditional_edge(
        self,
        source: str,
        condition: ConditionFn,
        target: str,
    ) -> "DecisionGraphBuilder":
        self.conditional_edges.setdefault(source, []).append(
            ConditionalEdge(condition=condition, target=target)
        )
        return self

    def add_retry_rule(
        self,
        node: str,
        should_retry: ConditionFn,
        max_attempts: int,
    ) -> "DecisionGraphBuilder":
        self.retry_rules[node] = RetryRule(should_retry=should_retry, max_attempts=max_attempts)
        return self

    def run(self, start_node: str, state: WorkflowState) -> WorkflowState:
        current = state.get("current_node", start_node)

        while current is not None:
            state["current_node"] = current
            state = self._run_with_retry(current, state)

            if self._should_pause_for_human(state):
                self.checkpoint_store.save(state)
                return state

            current = self._resolve_next_node(current, state)

        state["current_node"] = "completed"
        return state

    def resume(self) -> WorkflowState:
        if not self.checkpoint_store.exists():
            raise FileNotFoundError("No persisted checkpoint found to resume from.")

        state = self.checkpoint_store.load()
        next_node = self._resolve_next_node(state["current_node"], state)
        if next_node is None:
            state["current_node"] = "completed"
            return state
        return self.run(next_node, state)

    def _run_with_retry(self, node_name: str, state: WorkflowState) -> WorkflowState:
        node = self.nodes[node_name]
        retry_rule = self.retry_rules.get(node_name)

        attempts = 0
        while True:
            attempts += 1
            state = node(state)
            if not retry_rule:
                return state
            if not retry_rule.should_retry(state):
                return state
            if attempts >= retry_rule.max_attempts:
                return state

    def _resolve_next_node(self, node_name: str, state: WorkflowState) -> str | None:
        for edge in self.conditional_edges.get(node_name, []):
            if edge.condition(state):
                return edge.target
        return self.default_edges.get(node_name)

    @staticmethod
    def _should_pause_for_human(state: WorkflowState) -> bool:
        return state.get("approval_status") == "pending" and state.get("current_node") == "human_approval"



def build_default_graph(nodes: dict[str, NodeFn]) -> DecisionGraphBuilder:
    """Create a default decision-intelligence graph with branching, retries, and HITL controls."""

    graph = DecisionGraphBuilder()

    for name, handler in nodes.items():
        graph.add_node(name, handler)

    graph.add_edge("intent_parser", "planner")

    # Branch by planning output.
    graph.add_conditional_edge("planner", lambda s: "market" in s.get("plan", []), "research_market")
    graph.add_conditional_edge("planner", lambda s: "technical" in s.get("plan", []), "research_technical")
    graph.add_conditional_edge("planner", lambda s: "financial" in s.get("plan", []), "research_financial")
    graph.add_conditional_edge("planner", lambda s: "legal" in s.get("plan", []), "research_legal")
    graph.add_conditional_edge("planner", lambda s: "competitor" in s.get("plan", []), "research_competitor")
    graph.add_conditional_edge("planner", lambda s: "sentiment" in s.get("plan", []), "research_sentiment")

    # Research fan-in.
    graph.add_edge("research_market", "critic")
    graph.add_edge("research_technical", "critic")
    graph.add_edge("research_financial", "critic")
    graph.add_edge("research_legal", "critic")
    graph.add_edge("research_competitor", "critic")
    graph.add_edge("research_sentiment", "critic")

    # Retry critical analysis when critique quality is low.
    graph.add_retry_rule("critic", lambda s: s.get("evaluation", {}).get("critique_score", 1) < 0.6, max_attempts=2)
    graph.add_edge("critic", "human_approval")

    # HITL branching.
    graph.add_conditional_edge("human_approval", lambda s: s.get("approval_status") == "rejected", "planner")
    graph.add_conditional_edge("human_approval", lambda s: s.get("approval_status") == "needs_revision", "critic")
    graph.add_conditional_edge("human_approval", lambda s: s.get("approval_status") == "approved", "synthesizer")

    graph.add_edge("synthesizer", "evaluator")

    return graph
