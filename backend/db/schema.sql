-- Core persistence schema for workflow evidence tracking and retrieval.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subtasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subtasks_workflow_id ON subtasks(workflow_id);

CREATE TABLE IF NOT EXISTS findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    subtask_id UUID REFERENCES subtasks(id) ON DELETE SET NULL,
    claim_id TEXT,
    content TEXT NOT NULL,
    source_url TEXT,
    source_timestamp TIMESTAMPTZ,
    agent_name TEXT,
    confidence DOUBLE PRECISION,
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_findings_workflow_id ON findings(workflow_id);
CREATE INDEX IF NOT EXISTS idx_findings_claim_id ON findings(claim_id);

CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    finding_id UUID REFERENCES findings(id) ON DELETE SET NULL,
    claim_id TEXT,
    source_url TEXT NOT NULL,
    source_timestamp TIMESTAMPTZ,
    title TEXT,
    publisher TEXT,
    agent_name TEXT,
    confidence DOUBLE PRECISION,
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sources_workflow_id ON sources(workflow_id);
CREATE INDEX IF NOT EXISTS idx_sources_claim_id ON sources(claim_id);

CREATE TABLE IF NOT EXISTS critiques (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    finding_id UUID REFERENCES findings(id) ON DELETE SET NULL,
    claim_id TEXT,
    critique TEXT NOT NULL,
    agent_name TEXT,
    confidence DOUBLE PRECISION,
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_critiques_workflow_id ON critiques(workflow_id);

CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    finding_id UUID REFERENCES findings(id) ON DELETE SET NULL,
    output_id UUID,
    approved BOOLEAN NOT NULL,
    reviewer TEXT,
    notes TEXT,
    confidence DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approvals_workflow_id ON approvals(workflow_id);

CREATE TABLE IF NOT EXISTS outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    claim_id TEXT,
    output_type TEXT NOT NULL,
    content JSONB NOT NULL,
    agent_name TEXT,
    confidence DOUBLE PRECISION,
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outputs_workflow_id ON outputs(workflow_id);

CREATE TABLE IF NOT EXISTS evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    output_id UUID REFERENCES outputs(id) ON DELETE SET NULL,
    claim_id TEXT,
    evaluator_name TEXT,
    score DOUBLE PRECISION,
    rubric TEXT,
    notes TEXT,
    confidence DOUBLE PRECISION,
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluations_workflow_id ON evaluations(workflow_id);

CREATE TABLE IF NOT EXISTS evidence_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    finding_id UUID REFERENCES findings(id) ON DELETE SET NULL,
    claim_id TEXT,
    content TEXT NOT NULL,
    source_url TEXT,
    source_timestamp TIMESTAMPTZ,
    agent_name TEXT,
    confidence DOUBLE PRECISION,
    contradiction_flag BOOLEAN NOT NULL DEFAULT FALSE,
    embedding VECTOR(1536) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_vectors_workflow_id ON evidence_vectors(workflow_id);
CREATE INDEX IF NOT EXISTS idx_evidence_vectors_claim_id ON evidence_vectors(claim_id);

-- Use cosine distance for semantic retrieval.
CREATE INDEX IF NOT EXISTS idx_evidence_vectors_embedding
    ON evidence_vectors
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
