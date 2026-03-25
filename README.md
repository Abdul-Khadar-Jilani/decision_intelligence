# Decision Intelligence Workspace

A modular Python workspace for building and evaluating a **decision-intelligence pipeline** with:
- shared typed models,
- a graph-style orchestrator,
- research/critique/synthesis nodes,
- HITL (human-in-the-loop) checkpoint controls,
- a demo Streamlit control-center UI,
- batch evaluation scenarios with regression tracking.

## What this code does

At a high level, the repository gives you reusable components to orchestrate decision workflows:

1. **Represent state and artifacts** with shared Pydantic models (`shared/`).
2. **Route and orchestrate tasks** through graph nodes (`graph/`).
3. **Pause for approvals and resume execution** through workflow checkpoint APIs (`backend/api/routes/workflows.py`).
4. **Visualize workflow progress** in a demo UI (`ui/streamlit_app/app.py`).
5. **Run offline eval scenarios** and track score deltas over snapshots (`evals/run_eval.py`).

## Repository layout

- `shared/` – cross-project data models (query, plan, findings, critique, synthesis, evaluation).
- `graph/` – orchestration logic and node-level helpers.
  - `graph/graph_builder.py` – stateful graph builder with conditional edges, retries, and JSON checkpoint persistence.
  - `graph/nodes/critic.py` – critique engine that flags missing dimensions, unsupported claims, stale sources, contradictions, and low-confidence clusters.
  - `graph/llm/router.py` – policy-based model selection with fallback execution and logging.
- `backend/` – API-layer building blocks.
  - `backend/api/routes/workflows.py` – approve/reject/request_refine/resume endpoints for checkpointed workflows (in-memory placeholder stores).
- `ui/streamlit_app/app.py` – operator-facing demo dashboard.
- `evals/` – scenario JSON files and a batch evaluator script with leaderboard/regression output.

## Quick start

### 1) Prerequisites

- Python **3.11+**
- `pip`

### 2) Install dependencies

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[api,graph,ui,evals]
```

If you only need specific areas, you can install a subset of extras:

```bash
pip install -e .[graph]
pip install -e .[ui]
```

### 3) Sanity check the code

```bash
python -m compileall .
```

## How to use each part

## A) Run the Streamlit demo UI

```bash
streamlit run ui/streamlit_app/app.py
```

The UI demonstrates:
- node timeline,
- per-agent findings and source links,
- critique warnings/contradictions,
- approval controls,
- final-output metrics,
- workflow replay mode for demos.

## B) Use the workflow checkpoint endpoints (FastAPI router)

`backend/api/routes/workflows.py` provides an `APIRouter` with:
- `POST /workflows/{checkpoint_id}/approve`
- `POST /workflows/{checkpoint_id}/reject`
- `POST /workflows/{checkpoint_id}/request_refine`
- `POST /workflows/{checkpoint_id}/resume`

This file is a router module (not a full app). To run it, mount `router` in your own `FastAPI()` application.

Example minimal app (`backend/api/main.py`):

```python
from fastapi import FastAPI
from backend.api.routes.workflows import router as workflow_router

app = FastAPI(title="Decision Intelligence API")
app.include_router(workflow_router)
```

Then run:

```bash
uvicorn backend.api.main:app --reload
```

## C) Run batch evaluations

```bash
python evals/run_eval.py
```

Useful flags:

```bash
python evals/run_eval.py --seed 42 --max-workers 4 --regression-threshold -1.0
```

Outputs are written to:
- `evals/artifacts/latest_results.json`
- `evals/artifacts/snapshots/<commit>_seed<seed>.json`
- `evals/artifacts/leaderboard.md`
- `evals/artifacts/regression_report.md`

## D) Build your own graph flow

Use `graph/graph_builder.py` to:
- register nodes (`add_node`),
- wire default/conditional transitions (`add_edge`, `add_conditional_edge`),
- add retries (`add_retry_rule`),
- pause/resume through checkpoint persistence (`run`, `resume`).

`build_default_graph(...)` contains a ready template for intent → planning → specialized research → critique → HITL approval → synthesis → evaluation.

## Current status and caveats

- This repository is currently a **workspace scaffold + reference implementation** for major components.
- Some modules are intentionally mock/demo-oriented (for example, in-memory checkpoint stores in the workflow router and demo data in the Streamlit app).
- You should expect to wire in your own production components for:
  - durable storage,
  - auth/access control,
  - real model/provider clients,
  - real data connectors and tool integrations.

## Suggested next steps for production hardening

1. Add a first-class API app entrypoint (`backend/api/main.py`) and dependency injection for storage/services.
2. Replace in-memory stores with durable backing services (DB/Redis).
3. Add unit tests for graph transitions, critic checks, and route fallbacks.
4. Add integration tests for approval/resume workflow.
5. Add lint/typecheck/CI workflow and a Docker deployment path.

## Development notes

- Package metadata is defined in `pyproject.toml` and already points `readme = "README.md"`.
- The project currently uses optional extras (`api`, `graph`, `ui`, `evals`) so teams can install only what they need.
