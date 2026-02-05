# Backend API

API REST costruita con **FastAPI** per la gestione di bandi di gara.

## Struttura

```
app/
├── main.py           # Entry point FastAPI
├── config.py         # Configurazione (env vars)
├── dependencies.py   # Dependency injection
├── models/           # Schemi Pydantic
├── routers/          # Endpoint API
├── services/         # Logica di business
│   ├── agents/       # Pipeline 1 (Analisi Bando)
│   └── proposal/     # Pipeline 2 (Generazione Proposta)
└── utils/            # Utility varie
```

## Endpoints Principali

| Endpoint | Descrizione |
|----------|-------------|
| `POST /tenders/upload` | Carica documenti bando e avvia analisi |
| `GET /projects/{id}/details` | Dettagli progetto completi |
| `GET /projects/{id}/insights` | Insight estratti dal bando |
| `POST /projects/{id}/generate` | Genera proposta tecnica |

## Avvio

```bash
..\\.venv\\Scripts\\Activate.ps1
uvicorn app.main:app --reload --port 8080
```

## Variabili d'Ambiente

Vedi `.env` per la configurazione di:
- `SUPABASE_URL` / `SUPABASE_KEY`
- `OPENAI_API_KEY`
