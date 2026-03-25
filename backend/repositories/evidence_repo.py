"""Repository APIs for workflow evidence persistence keyed by workflow_id."""

from __future__ import annotations

from typing import Any


class EvidenceRepository:
    """CRUD-style persistence APIs for workflow evidence entities."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @staticmethod
    def _fetchall_dict(cursor: Any) -> list[dict[str, Any]]:
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def create_workflow(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "pending",
        created_by: str | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO workflows (name, description, status, created_by)
            VALUES (%s, %s, %s, %s)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(query, (name, description, status, created_by))
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._connection.cursor() as cur:
            cur.execute("SELECT * FROM workflows ORDER BY created_at DESC")
            return self._fetchall_dict(cur)

    def insert_subtask(
        self,
        *,
        workflow_id: str,
        title: str,
        description: str | None = None,
        status: str = "pending",
        assigned_agent: str | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO subtasks (workflow_id, title, description, status, assigned_agent)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(query, (workflow_id, title, description, status, assigned_agent))
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def insert_finding(
        self,
        *,
        workflow_id: str,
        content: str,
        subtask_id: str | None = None,
        claim_id: str | None = None,
        source_url: str | None = None,
        source_timestamp: Any | None = None,
        agent_name: str | None = None,
        confidence: float | None = None,
        contradiction_flag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO findings (
                workflow_id,
                subtask_id,
                claim_id,
                content,
                source_url,
                source_timestamp,
                agent_name,
                confidence,
                contradiction_flag,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(
                query,
                (
                    workflow_id,
                    subtask_id,
                    claim_id,
                    content,
                    source_url,
                    source_timestamp,
                    agent_name,
                    confidence,
                    contradiction_flag,
                    metadata or {},
                ),
            )
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def insert_source(
        self,
        *,
        workflow_id: str,
        source_url: str,
        finding_id: str | None = None,
        claim_id: str | None = None,
        source_timestamp: Any | None = None,
        title: str | None = None,
        publisher: str | None = None,
        agent_name: str | None = None,
        confidence: float | None = None,
        contradiction_flag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO sources (
                workflow_id,
                finding_id,
                claim_id,
                source_url,
                source_timestamp,
                title,
                publisher,
                agent_name,
                confidence,
                contradiction_flag,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(
                query,
                (
                    workflow_id,
                    finding_id,
                    claim_id,
                    source_url,
                    source_timestamp,
                    title,
                    publisher,
                    agent_name,
                    confidence,
                    contradiction_flag,
                    metadata or {},
                ),
            )
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def insert_critique(
        self,
        *,
        workflow_id: str,
        critique: str,
        finding_id: str | None = None,
        claim_id: str | None = None,
        agent_name: str | None = None,
        confidence: float | None = None,
        contradiction_flag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO critiques (
                workflow_id, finding_id, claim_id, critique,
                agent_name, confidence, contradiction_flag, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(
                query,
                (
                    workflow_id,
                    finding_id,
                    claim_id,
                    critique,
                    agent_name,
                    confidence,
                    contradiction_flag,
                    metadata or {},
                ),
            )
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def insert_approval(
        self,
        *,
        workflow_id: str,
        approved: bool,
        finding_id: str | None = None,
        output_id: str | None = None,
        reviewer: str | None = None,
        notes: str | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO approvals (
                workflow_id, finding_id, output_id, approved,
                reviewer, notes, confidence, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(
                query,
                (workflow_id, finding_id, output_id, approved, reviewer, notes, confidence, metadata or {}),
            )
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def insert_output(
        self,
        *,
        workflow_id: str,
        output_type: str,
        content: Any,
        claim_id: str | None = None,
        agent_name: str | None = None,
        confidence: float | None = None,
        contradiction_flag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO outputs (
                workflow_id, claim_id, output_type, content,
                agent_name, confidence, contradiction_flag, metadata
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(
                query,
                (
                    workflow_id,
                    claim_id,
                    output_type,
                    content,
                    agent_name,
                    confidence,
                    contradiction_flag,
                    metadata or {},
                ),
            )
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def insert_evaluation(
        self,
        *,
        workflow_id: str,
        evaluator_name: str,
        output_id: str | None = None,
        claim_id: str | None = None,
        score: float | None = None,
        rubric: str | None = None,
        notes: str | None = None,
        confidence: float | None = None,
        contradiction_flag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = """
            INSERT INTO evaluations (
                workflow_id, output_id, claim_id, evaluator_name,
                score, rubric, notes, confidence, contradiction_flag, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """
        with self._connection.cursor() as cur:
            cur.execute(
                query,
                (
                    workflow_id,
                    output_id,
                    claim_id,
                    evaluator_name,
                    score,
                    rubric,
                    notes,
                    confidence,
                    contradiction_flag,
                    metadata or {},
                ),
            )
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def get_by_workflow_id(self, table: str, workflow_id: str) -> list[dict[str, Any]]:
        """Read records from a known evidence table by workflow_id."""
        allowed_tables = {
            "subtasks",
            "findings",
            "sources",
            "critiques",
            "approvals",
            "outputs",
            "evaluations",
        }
        if table not in allowed_tables:
            raise ValueError(f"Unsupported table: {table}")

        query = f"SELECT * FROM {table} WHERE workflow_id = %s ORDER BY created_at DESC"
        with self._connection.cursor() as cur:
            cur.execute(query, (workflow_id,))
            return self._fetchall_dict(cur)
