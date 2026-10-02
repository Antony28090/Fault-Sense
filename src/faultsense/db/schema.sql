create table if not exists manuals (
    id text primary key,
    family text not null,
    title text not null,
    doc_ref text not null,
    version text not null,
    file_name text not null,
    sha256 text not null,
    page_count int not null,
    ingested_at timestamptz not null default now()
);

create table if not exists chunks (
    id text primary key,
    manual_id text not null references manuals(id) on delete cascade,
    kind text not null,  -- section | fault | safety, open-ended so Phase 4 can add confirmed fixes
    heading_path text not null,
    page_start int not null,
    page_end int not null,
    text text not null,
    tsv tsvector generated always as (
        setweight(to_tsvector('english', heading_path), 'A') ||
        setweight(to_tsvector('english', text), 'B')
    ) stored,
    embedding vector(1024) not null
);

create index if not exists chunks_tsv_idx on chunks using gin (tsv);
create index if not exists chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);
create index if not exists chunks_manual_idx on chunks (manual_id);

create table if not exists fault_codes (
    manual_id text not null references manuals(id) on delete cascade,
    code text not null,
    code_key text not null,
    name text not null,
    description text not null default '',
    causes jsonb not null,
    remedies jsonb not null,
    clearing text not null default '',
    page int not null,
    page_end int not null,
    layout text not null,
    shared_with text[] not null default '{}',
    chunk_id text not null references chunks(id) on delete cascade,
    primary key (manual_id, code_key)
);

create index if not exists fault_codes_key_idx on fault_codes (code_key);

create table if not exists lexicon (
    manual_id text not null references manuals(id) on delete cascade,
    kind text not null check (kind in ('fault', 'hmi', 'token', 'label')),
    code text not null,
    code_key text not null,
    label text,
    first_page int not null,
    primary key (manual_id, kind, code_key)
);
