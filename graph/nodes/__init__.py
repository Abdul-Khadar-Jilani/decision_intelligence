"""Node interface signatures for the decision-intelligence workflow."""

from __future__ import annotations

from typing import Protocol

from graph.state import WorkflowState


class NodeFn(Protocol):
    """Protocol implemented by all graph nodes."""

    def __call__(self, state: WorkflowState) -> WorkflowState:
        ...


def intent_parser(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def planner(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def research_market(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def research_technical(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def research_financial(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def research_legal(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def research_competitor(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def research_sentiment(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def critic(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def human_approval(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def synthesizer(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError


def evaluator(state: WorkflowState) -> WorkflowState:
    raise NotImplementedError
