-- 0004_voyage_embeddings.sql
-- Switch reference_chunks.embedding to vector(1024) to match Voyage-3
-- (spec §19 default embedding provider). Safe because no chunks exist yet.
-- Also installs the match_reference_chunks RPC used for top-k retrieval.

drop index if exists reference_chunks_embedding_idx;
alter table reference_chunks drop column if exists embedding;
alter table reference_chunks add column embedding vector(1024);

create index reference_chunks_embedding_idx
  on reference_chunks
  using hnsw (embedding vector_cosine_ops);

create or replace function match_reference_chunks(
  query_embedding vector(1024),
  match_count int default 10,
  document_ids uuid[] default null
)
returns table (
  id uuid,
  document_id uuid,
  content text,
  chunk_position int,
  similarity float
)
language sql
stable
as $$
  select
    c.id,
    c.document_id,
    c.content,
    c.position as chunk_position,
    1 - (c.embedding <=> query_embedding) as similarity
  from reference_chunks c
  where document_ids is null or c.document_id = any(document_ids)
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
