"""Repository for pgvector storage and semantic retrieval in Supabase/Postgres."""

from __future__ import annotations

from typing import Any


class VectorRepository:
    """Stores and retrieves semantic evidence vectors keyed by workflow_id."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @staticmethod
    def _fetchall_dict(cursor: Any) -> list[dict[str, Any]]:
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _to_vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(v) for v in embedding) + "]"

    def upsert_embedding(
        self,
        *,
        workflow_id: str,
        content: str,
        embedding: list[float],
        finding_id: str | None = None,
        claim_id: str | None = None,
        source_url: str | None = None,
        source_timestamp: Any | None = None,
        agent_name: str | None = None,
        confidence: float | None = None,
        contradiction_flag: bool = False,
        metadata: dict[str, Any] | None = None,
        vector_id: str | None = None,
    ) -> dict[str, Any]:
        vector_literal = self._to_vector_literal(embedding)

        if vector_id:
            query = """
                UPDATE evidence_vectors
                SET
                    workflow_id = %s,
                    finding_id = %s,
                    claim_id = %s,
                    content = %s,
                    source_url = %s,
                    source_timestamp = %s,
                    agent_name = %s,
                    confidence = %s,
                    contradiction_flag = %s,
                    embedding = %s::vector,
                    metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
            """
            params = (
                workflow_id,
                finding_id,
                claim_id,
                content,
                source_url,
                source_timestamp,
                agent_name,
                confidence,
                contradiction_flag,
                vector_literal,
                metadata or {},
                vector_id,
            )
        else:
            query = """
                INSERT INTO evidence_vectors (
                    workflow_id,
                    finding_id,
                    claim_id,
                    content,
                    source_url,
                    source_timestamp,
                    agent_name,
                    confidence,
                    contradiction_flag,
                    embedding,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb)
                RETURNING *
            """
            params = (
                workflow_id,
                finding_id,
                claim_id,
                content,
                source_url,
                source_timestamp,
                agent_name,
                confidence,
                contradiction_flag,
                vector_literal,
                metadata or {},
            )

        with self._connection.cursor() as cur:
            cur.execute(query, params)
            row = self._fetchall_dict(cur)[0]
        self._connection.commit()
        return row

    def semantic_search(
        self,
        *,
        workflow_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        only_non_contradictory: bool = False,
    ) -> list[dict[str, Any]]:
        vector_literal = self._to_vector_literal(query_embedding)
        where_clause = "workflow_id = %s"

        if only_non_contradictory:
            where_clause += " AND contradiction_flag = FALSE"

        query = f"""
            SELECT
                id,
                workflow_id,
                finding_id,
                claim_id,
                content,
                source_url,
                source_timestamp,
                agent_name,
                confidence,
                contradiction_flag,
                metadata,
                created_at,
                updated_at,
                1 - (embedding <=> %s::vector) AS similarity
            FROM evidence_vectors
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        # query vector is used for both similarity projection and ordering.
        params: tuple[Any, ...] = (vector_literal, workflow_id, vector_literal, top_k)

        with self._connection.cursor() as cur:
            cur.execute(query, params)
            return self._fetchall_dict(cur)

    def list_workflow_vectors(self, workflow_id: str) -> list[dict[str, Any]]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM evidence_vectors
                WHERE workflow_id = %s
                ORDER BY created_at DESC
                """,
                (workflow_id,),
            )
            return self._fetchall_dict(cur)
