# Development

Documentazione di progetto e schema database.

## File

| File | Descrizione |
|------|-------------|
| `development_log.md` | Log dettagliato di ogni sessione di sviluppo |
| `schema.sql` | Schema completo database Supabase |
| `project_plan.md` | Piano di progetto iniziale |
| `chat_context.md` | Contesto per sessioni AI |

## Database (Supabase)

Tabelle principali:
- `companies` - Aziende clienti
- `company_documents` - Knowledge base aziendali
- `company_chunks` - Chunks per RAG aziendale
- `tenders` - Bandi di gara
- `tender_documents` - Documenti del bando
- `tender_extractions` - Dati estratti Pipeline 1
- `tender_insights` - Insight singoli estratti
- `tender_chunks` - Chunks per RAG bando
- `projects` - Progetti (partecipazione a gare)
