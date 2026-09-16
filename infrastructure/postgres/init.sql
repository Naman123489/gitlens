-- Extensions RepoLens uses when they are available.
-- pgvector backs the similarity engine's ANN search; pg_trgm accelerates the
-- text search used by candidate and repository lookups.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
