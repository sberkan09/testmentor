-- testmentor orchestrator store (paket 5, worker/store_pg.py). Idempotent: run on every connect.
-- Node history is append-only: tm_node_versions keeps every version, tm_nodes the current one
-- (a removed node has no row there and keeps its history).

CREATE TABLE IF NOT EXISTS tm_projects (
    project_id  text PRIMARY KEY,
    record      jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tm_nodes (
    project_id  text NOT NULL,
    kind        text NOT NULL,
    key         text NOT NULL,
    version     integer NOT NULL CHECK (version >= 1),
    status      text NOT NULL,
    node        jsonb NOT NULL,
    PRIMARY KEY (project_id, kind, key)
);

CREATE TABLE IF NOT EXISTS tm_node_versions (
    id          bigserial PRIMARY KEY,
    project_id  text NOT NULL,
    kind        text NOT NULL,
    key         text NOT NULL,
    version     integer NOT NULL,
    node        jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tm_node_versions_ref ON tm_node_versions (project_id, kind, key, id);

CREATE TABLE IF NOT EXISTS tm_output_cache (
    project_id  text NOT NULL,
    cache_key   text NOT NULL,
    result      jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, cache_key)
);

CREATE TABLE IF NOT EXISTS tm_events (
    project_id  text NOT NULL,
    seq         bigint NOT NULL,
    actor       text NOT NULL,
    event       jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, seq)
);

CREATE TABLE IF NOT EXISTS tm_jobs (
    project_id  text NOT NULL,
    job_id      text NOT NULL,
    record      jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, job_id)
);
