-- ⚠️ REFERENCE ONLY ⚠️
-- Questo file serve SOLO come documentazione della struttura del Database su Supabase.
-- NON ESEGUIRE questo file come migrazione automatica.
-- NON MODIFICARE questo file se non cambiamo strutturalmente il DB.


-- 1. Abilita l'estensione per l'AI (Vector Embeddings)
create extension if not exists vector;

-- 2. Tabella CLIENTI (Collega l'Auth di Supabase al tuo gestionale)
create table public.companies (
  id uuid references auth.users on delete cascade primary key,  -- Collegamento all'utente loggato
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data d'iscrizione
  company_name text,  -- Nome dell'azienda
  vat_number text  -- Partita IVA dell'azienda
);

-- 3. Tabella documenti clienti
create table public.company_documents (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  company_id uuid references public.companies(id) on delete cascade not null,  -- Collegamento al cliente
  created_at timestamp with time zone default now(),  -- Data di caricamento file
  name text not null,  -- Nome del file
  file_path text not null,  -- Path nello Storage (es. "companies/{id}/visura.pdf")
  extracted_text text  -- Il testo estratto dal documento
);

-- 4. ASSET AZIENDALI (La Memoria - RAG)
create table public.company_assets (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  company_id uuid references public.companies(id) on delete cascade not null,  -- Collegamento all'azienda
  file_id uuid references public.company_documents(id) on delete cascade not null,  -- Collegamento al documento
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di creazione
  content text, -- Chunk di tetso del documento
  embedding vector(1536), -- embedding del testo
  chunk_index integer,  -- Per mantenere l'ordine del testo originale
  metadata jsonb -- Es: {"anno": 2023, "tipo": "progetto_ospedale"}, pagina, sezione, ecc.
);

-- 5. Tabella BANDI
create table public.tenders (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data d'inserimento
  cig text not null unique,  -- Codice Identificativo Gara. È un codice univoco delle gare. Lo utilizzo per evitare di inserire più volte la stessa gara
  number_docs int,  -- Numero di documenti del bando
  status text default 'analyzing',  -- 'analyzing' | 'ready' | 'error'. Per monitorare lo stato dell'analisi
  analysis jsonb  -- Un po' di info salvate, come "Settore Pulizie", "Tono Formale", ecc. Potrei rimuoverlo in seguito
);

-- 6. Tabella DOCUMENTI BANDO (I PDF caricati)
create table public.tender_documents (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  tender_id uuid references public.tenders(id) on delete cascade not null,  -- Collegamento al bando
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di caricamento
  name text,  -- Il nome del documento
  file_path text not null,  -- Percorso su Supabase Storage dove salviamo il file
  extracted_text text,  -- Testo estratto dal documento
  doc_type text  -- 'disciplinare' | 'capitolato' | 'altro'. Come se fosse la categoria di documento
);

-- 7. Tabella ESTRAZIONE BANDO (Output della Pipeline di Analisi)
-- Questa tabella contiene i dati estratti dalla pipeline agentica 1. Macroanalisi
create table public.tender_extractions (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  tender_id uuid references public.tenders(id) on delete cascade not null unique,  -- Collegamento al bando
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di estrazione
  title text,  -- Oggetto dell'appalto
  contracting_authority text,  -- Ente appaltante
  value numeric(15,2),  -- Importo base gara
  currency text default 'EUR',  -- Valuta
  deadline timestamp with time zone,  -- Scadenza presentazione offerta
  sector text,  -- Es: 'servizi_pulizia', 'software', 'edilizia'
  procedure_type text,  -- Es: 'procedura_aperta', 'negoziata'
  duration_months integer,  -- Durata contratto in mesi
  quality_score numeric(5,2),  -- Score di validazione (0-100) dallo Step 5

  -- === DATI COMPLETI (JSONB flessibili per Pipeline 2) ===
  full_result jsonb not null,  -- L'intero ExtractionResult (step 4)
  tender_summary jsonb,  -- Solo l'header del json sopra (tender_summary estratto nello step 4)
  action_summary jsonb,  -- action_summary estratto nello step 4
  document_profile jsonb  -- document_profile estratto nello step 4
);

-- Indici per query comuni sul frontend
create index idx_extraction_tender on public.tender_extractions(tender_id);
create index idx_extraction_deadline on public.tender_extractions(deadline);
create index idx_extraction_sector on public.tender_extractions(sector);

-- 7b. Tabella INSIGHTS (Singoli insight estratti dalla pipeline)
-- Ogni insight è una riga. Utile per query granulari. Microanalisi
create table public.tender_insights (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  extraction_id uuid references public.tender_extractions(id) on delete cascade not null,  -- Collegamento all'estrazione
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di estrazione
  
  -- Campi principali dell'Insight
  insight_id text,                     -- ID interno (es: "REQ-001", "DEAD-003")
  category text not null,              -- 'requisito_partecipazione', 'scadenza', 'criterio_punteggio', etc.
  type text,                           -- Sottotipo (es: 'fatturato_minimo', 'termine_offerta')
  importance text,                     -- 'critical', 'high', 'medium', 'low'
  
  -- Finding
  title text,                          -- Titolo breve dell'insight
  description text,                    -- Descrizione completa
  source_text text,                    -- Testo originale del bando da cui è estratto
  source_location text,                -- Riferimento alla sezione (es: "Art. 6.3")
  
  -- Dettagli specifici (per criteri a punteggio)
  score_points integer,                -- Punti assegnati (se applicabile)
  
  -- Dati completi per flessibilità
  full_insight jsonb                   -- L'intero oggetto Insight originale
);

-- Indici per query sugli insights
create index idx_insight_extraction on public.tender_insights(extraction_id);
create index idx_insight_category on public.tender_insights(category);
create index idx_insight_importance on public.tender_insights(importance);

-- 8. PROGETTI (Le partecipazioni dei clienti ai bandi)
create table public.projects (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  company_id uuid references public.companies(id) not null,  -- Collegamento all'azienda
  tender_id uuid references public.tenders(id) not null,  -- Collegamento al bando
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di creazione
  name text,  -- nome del progetto
  status text default 'draft',
  generated_response jsonb, -- La bozza finale scritta dall'AI
  unique(company_id, tender_id) -- Un'azienda fa un solo progetto per quel bando
);

-- 9. CHUNK DEI BANDI (Per il RAG sui documenti di gara)
create table public.tender_chunks (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  tender_id uuid references public.tenders(id) on delete cascade not null,  -- Collegamento al bando
  document_id uuid references public.tender_documents(id) on delete cascade not null,  -- Collegamento al documento
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di creazione
  content text,  -- Il chunk di testo
  embedding vector(1536),  -- Il vettore
  chunk_index integer,  -- Per mantenere l'ordine del testo originale
  metadata jsonb  -- Es: {"page": 5, "source": "disciplinare.pdf"}
);

-- Creiamo un indice HNSW per rendere la ricerca tra i bandi veloce
create index on public.tender_chunks using hnsw (embedding vector_cosine_ops);

-- 10. FUNZIONE DI RICERCA BANDI (NECESSARIA PER IL RAG)
-- Questa funzione verrà chiamata da Python via .rpc()
create or replace function match_tender_chunks (
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  filter_tender_id uuid
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    tender_chunks.id,
    tender_chunks.content,
    tender_chunks.metadata,
    1 - (tender_chunks.embedding <=> query_embedding) as similarity
  from tender_chunks
  where 1 - (tender_chunks.embedding <=> query_embedding) > match_threshold
  and tender_chunks.tender_id = filter_tender_id -- Cerca SOLO nel bando specifico
  order by tender_chunks.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- Creiamo un indice HNSW per rendere la ricerca tra le informazioni aziendali veloce
create index on public.company_assets using hnsw (embedding vector_cosine_ops);

-- 11. FUNZIONE DI RICERCA AZIENDALE
-- Questa funzione verrà chiamata da Python
create or replace function match_company_assets (
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  filter_company_id uuid
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    company_assets.id,
    company_assets.content,
    company_assets.metadata,
    1 - (company_assets.embedding <=> query_embedding) as similarity
  from company_assets
  where 1 - (company_assets.embedding <=> query_embedding) > match_threshold
  and company_assets.company_id = filter_company_id -- Cerca SOLO nei documenti di QUESTA azienda
  order by company_assets.embedding <=> query_embedding
  limit match_count;
end;
$$;


-- 12. Tabella con l'elenco per sito
create table public.anac (
  id uuid default gen_random_uuid() primary key,  -- id della tabella
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,  -- Data di caricamento nel db
  titolo text,  -- Titolo della gara
  committente text,  -- Committente della gara
  scadenza timestamptz,  -- Scadenza della gara
  link_gara text,  -- Link al sito del committente, dove l'utente può trovare la gara
  cig text,  -- CIG della gara
  natura_principale text,  -- Natura principale della gara
  descrizione text,  -- Descrizione della gara
  cpv text,  -- Codice CPV della gara
  valore numeric(15,2),  -- Valore economico in eurodella gara
  luogo_istat text,  -- Luogo ISTAT della gara
  criterio_aggiudicazione text  -- Criterio di aggiudicazione della gara
);


-- ABILITA LA SICUREZZA (Row Level Security - RLS)
-- Per ora lasciamo tutto aperto per testare facile, ma abilitiamo la struttura
alter table companies enable row level security;
alter table company_assets enable row level security;
-- (Le policy vere le metteremo dopo, ora lavoriamo con la "Service Role Key" che bypassa tutto)