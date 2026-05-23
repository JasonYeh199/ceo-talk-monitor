CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(16) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE executives (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(64) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]',
    CONSTRAINT uq_executive_company_name_role UNIQUE (company_id, name, role)
);

CREATE TABLE talks (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    source_url TEXT UNIQUE NOT NULL,
    external_id VARCHAR(255),
    title TEXT NOT NULL,
    description TEXT,
    published_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    company_ticker VARCHAR(16) NOT NULL,
    executive_name VARCHAR(255),
    executive_role VARCHAR(64),
    relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    relevance_reasons JSONB NOT NULL DEFAULT '[]',
    audio_path TEXT,
    transcript_path TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE transcript_segments (
    id SERIAL PRIMARY KEY,
    talk_id INTEGER REFERENCES talks(id) ON DELETE CASCADE,
    start_seconds DOUBLE PRECISION NOT NULL,
    end_seconds DOUBLE PRECISION NOT NULL,
    speaker VARCHAR(128),
    text TEXT NOT NULL
);

CREATE TABLE summaries (
    id SERIAL PRIMARY KEY,
    talk_id INTEGER UNIQUE REFERENCES talks(id) ON DELETE CASCADE,
    one_liner TEXT NOT NULL,
    management_tone VARCHAR(64) NOT NULL,
    core_topics JSONB NOT NULL DEFAULT '[]',
    signals JSONB NOT NULL DEFAULT '{}',
    quotes JSONB NOT NULL DEFAULT '[]',
    changes_vs_prior TEXT,
    investable_hypotheses JSONB NOT NULL DEFAULT '[]',
    risks JSONB NOT NULL DEFAULT '[]',
    source_url TEXT,
    raw_summary JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE ingestion_runs (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    source VARCHAR(64) NOT NULL DEFAULT 'all',
    company_ticker VARCHAR(16),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    parameters JSONB NOT NULL DEFAULT '{}',
    metrics JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    exit_code INTEGER,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_talks_company_ticker ON talks(company_ticker);
CREATE INDEX ix_talks_published_at ON talks(published_at);
CREATE INDEX ix_transcript_segments_talk_id ON transcript_segments(talk_id);
CREATE INDEX ix_ingestion_runs_job_name ON ingestion_runs(job_name);
CREATE INDEX ix_ingestion_runs_status ON ingestion_runs(status);
CREATE INDEX ix_ingestion_runs_started_at ON ingestion_runs(started_at);
