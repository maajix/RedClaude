-- ---------------------------------------------------------------------------
-- 010_embeddings.sql   (ticket 06, decision 7)
-- ---------------------------------------------------------------------------

-- Side tables keyed by embedding model: switching models inserts rows instead of
-- rewriting the hot tables, and two models coexist during a migration.
CREATE TABLE hypothesis_embeddings (
    hypothesis_id uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    model         text NOT NULL,
    embedding     vector(1536) NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hypothesis_id, model)
);

CREATE TABLE observation_embeddings (
    observation_id uuid NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    model          text NOT NULL,
    embedding      vector(1536) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (observation_id, model)
);

CREATE INDEX hypothesis_embeddings_hnsw
    ON hypothesis_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX observation_embeddings_hnsw
    ON observation_embeddings USING hnsw (embedding vector_cosine_ops);
