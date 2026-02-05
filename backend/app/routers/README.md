# Routers

Endpoint API FastAPI organizzati per risorsa.

## File

| File | Risorsa | Endpoint Base |
|------|---------|---------------|
| `health.py` | Sistema | `/health` |
| `companies.py` | Aziende | `/companies` |
| `tenders.py` | Bandi | `/tenders` |
| `projects.py` | Progetti | `/projects` |

## Endpoint Chiave

### Tenders
- `POST /tenders/upload` - Upload documenti e avvio analisi

### Projects
- `GET /projects/{id}/details` - Dati completi progetto
- `GET /projects/{id}/insights` - Insight estratti
- `POST /projects/{id}/generate` - Genera proposta

### Companies
- `POST /companies` - Crea azienda
- `POST /companies/{id}/documents` - Carica knowledge base
