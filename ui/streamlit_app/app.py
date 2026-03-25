from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st


@dataclass
class WorkflowStep:
    node: str
    status: str
    owner: str
    timestamp: datetime
    summary: str


st.set_page_config(page_title="Decision Intelligence Control Center", layout="wide")
st.title("Decision Intelligence Workflow Console")


def build_demo_workflow() -> list[WorkflowStep]:
    start = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=20)
    return [
        WorkflowStep(
            node="intake",
            status="completed",
            owner="orchestrator",
            timestamp=start,
            summary="Captured request and constraints.",
        ),
        WorkflowStep(
            node="research",
            status="completed",
            owner="research-agent",
            timestamp=start + timedelta(minutes=4),
            summary="Collected source set with confidence scores.",
        ),
        WorkflowStep(
            node="synthesis",
            status="in_progress",
            owner="synthesizer",
            timestamp=start + timedelta(minutes=10),
            summary="Building candidate recommendation set.",
        ),
        WorkflowStep(
            node="critique",
            status="pending",
            owner="critic",
            timestamp=start + timedelta(minutes=15),
            summary="Awaiting synthesis output before contradiction pass.",
        ),
    ]


def build_demo_findings() -> dict[str, list[dict[str, str]]]:
    return {
        "research-agent": [
            {
                "finding": "Primary sources align on core KPI movement this quarter.",
                "source": "https://example.org/source-a",
            },
            {
                "finding": "Lagging indicator suggests regional variance is non-trivial.",
                "source": "https://example.org/source-b",
            },
        ],
        "synthesizer": [
            {
                "finding": "Two robust options satisfy timeline and budget constraints.",
                "source": "https://example.org/source-c",
            }
        ],
    }


def build_demo_critic_notes() -> list[dict[str, Any]]:
    return [
        {
            "severity": "high",
            "warning": "Assumption mismatch between forecast horizon (12m) and cited model (6m).",
            "contradiction": "Source C says risk is stable, Source B signals volatility in region west.",
        },
        {
            "severity": "medium",
            "warning": "Cost estimate omits integration effort.",
            "contradiction": "Timeline assumes immediate vendor onboarding, procurement policy requires 2-week review.",
        },
    ]


def render_current_node_and_timeline(steps: list[WorkflowStep]) -> None:
    st.subheader("Current Node + Status Timeline")
    current_step = steps[-1]
    m1, m2, m3 = st.columns(3)
    m1.metric("Current Node", current_step.node)
    m2.metric("Status", current_step.status)
    m3.metric("Owner", current_step.owner)

    timeline_df = pd.DataFrame(
        {
            "timestamp": [step.timestamp.strftime("%Y-%m-%d %H:%M") for step in steps],
            "node": [step.node for step in steps],
            "status": [step.status for step in steps],
            "owner": [step.owner for step in steps],
            "summary": [step.summary for step in steps],
        }
    )
    st.dataframe(timeline_df, use_container_width=True, hide_index=True)


def render_findings(findings: dict[str, list[dict[str, str]]]) -> None:
    st.subheader("Per-Agent Findings and Sources")
    for agent_name, rows in findings.items():
        with st.expander(f"{agent_name}", expanded=True):
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)


def render_critic_notes(notes: list[dict[str, Any]]) -> None:
    st.subheader("Critic Warnings and Contradictions")
    for note in notes:
        if note["severity"] == "high":
            st.error(f"⚠️ {note['warning']}")
        elif note["severity"] == "medium":
            st.warning(f"⚠️ {note['warning']}")
        else:
            st.info(note["warning"])
        st.caption(f"Contradiction: {note['contradiction']}")


def render_approval_controls() -> None:
    st.subheader("Approval Controls")
    approver = st.text_input("Approver", value="Team Lead")
    decision = st.radio("Decision", ["Approve", "Request Revisions", "Reject"], horizontal=True)
    rationale = st.text_area("Approval Notes", placeholder="Document rationale and constraints.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Submit Decision", use_container_width=True):
            st.success(f"Decision '{decision}' submitted by {approver}.")
            if rationale:
                st.caption(f"Notes: {rationale}")
    with c2:
        if st.button("Escalate", use_container_width=True):
            st.info("Escalation sent to governance reviewer.")


def render_final_outputs() -> None:
    st.subheader("Final Outputs and Evaluation Metrics")
    st.markdown("""
- **Recommended path:** Option B (balanced risk/reward)
- **Decision packet:** Ready for export
- **Confidence summary:** Moderate-high
""")

    metric_df = pd.DataFrame(
        [
            {"metric": "Evidence coverage", "value": 0.91},
            {"metric": "Contradiction resolution", "value": 0.76},
            {"metric": "Policy compliance", "value": 0.98},
            {"metric": "Expected impact score", "value": 0.83},
        ]
    )
    st.dataframe(metric_df, use_container_width=True, hide_index=True)
    st.bar_chart(metric_df.set_index("metric"))


def filter_steps_for_replay(steps: list[WorkflowStep], replay_mode: bool, replay_index: int) -> list[WorkflowStep]:
    if not replay_mode:
        return steps
    return steps[: replay_index + 1]


workflow_steps = build_demo_workflow()
agent_findings = build_demo_findings()
critic_notes = build_demo_critic_notes()

with st.sidebar:
    st.header("Workflow Replay")
    replay_mode = st.toggle("Enable replay mode", value=False)
    replay_index = st.slider(
        "Replay step",
        min_value=0,
        max_value=len(workflow_steps) - 1,
        value=len(workflow_steps) - 1,
        disabled=not replay_mode,
        help="Move backward through workflow states for demos/storytelling.",
    )

visible_steps = filter_steps_for_replay(workflow_steps, replay_mode, replay_index)

if replay_mode:
    st.info(
        f"Replay mode active: showing step {replay_index + 1} of {len(workflow_steps)} "
        f"({visible_steps[-1].node})."
    )

pane_current, pane_findings, pane_critic, pane_approval, pane_final = st.tabs(
    [
        "Current + Timeline",
        "Agent Findings",
        "Critic",
        "Approval",
        "Final Outputs",
    ]
)

with pane_current:
    render_current_node_and_timeline(visible_steps)

with pane_findings:
    render_findings(agent_findings)

with pane_critic:
    render_critic_notes(critic_notes)

with pane_approval:
    render_approval_controls()

with pane_final:
    render_final_outputs()
