# Services

Moduli di logica di business che implementano le funzionalità core dell'applicazione.

## File Principali

| File | Descrizione |
|------|-------------|
| `analysis_pipeline.py` | Orchestratore Pipeline 1 (analisi bandi) |
| `analysis_service.py` | Servizio di analisi documenti |
| `pdf_parser_service.py` | Parsing PDF con layout analysis |
| `chunking_service.py` | Splitting testo per RAG |
| `embedding_service.py` | Generazione embedding OpenAI |
| `similarity_service.py` | Ricerca similarità vettoriale |
| `storage_service.py` | Upload file su Supabase Storage |
| `supabase_client.py` | Client Supabase singleton |

## Sottocartelle

### `agents/`
Agenti LLM per la **Pipeline 1** (Analisi del Bando):
- `planner_agent.py` - Pianifica l'analisi
- `executor_agents.py` - Estrae dati specifici
- `validator_agent.py` - Valida i risultati
- `aggregator_agent.py` - Aggrega in output finale

### `proposal/`
Agenti LLM per la **Pipeline 2** (Generazione Proposta):
- `orchestrator.py` - Coordina la generazione
- `agents/` - Agenti per ogni sezione della proposta
