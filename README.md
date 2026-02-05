# Bandi - Sistema di Gestione Gare d'Appalto

Applicazione per l'analisi automatica di bandi di gara e la generazione di proposte tecniche.

## Struttura del Progetto

```
bandi/
├── backend/          # API FastAPI (Python)
├── frontend/         # Web App Next.js (TypeScript)
└── development/      # Documentazione e schema DB
```

## Quick Start

### Backend
```bash
cd backend
..\\.venv\\Scripts\\Activate.ps1
uvicorn app.main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm run dev
```

## Documentazione

- `development/development_log.md` - Log di sviluppo dettagliato
- `development/schema.sql` - Schema database Supabase
- `development/project_plan.md` - Piano di progetto iniziale
