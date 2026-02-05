# Chat Context - AI Tender Architect

> **Ultimo aggiornamento:** 26 Gennaio 2026, 10:30
> **Scopo:** Guida per nuove conversazioni AI sul progetto

---

## 🎯 Cos'è questo progetto

**AI Tender Architect** è una piattaforma SaaS che automatizza la partecipazione ai bandi di gara pubblici. L'utente carica i documenti di un bando, l'AI estrae i requisiti, e poi genera automaticamente la documentazione di candidatura utilizzando la knowledge base aziendale (RAG).

---

## 📊 Stato Attuale del Progetto

### Backend (Python/FastAPI) ✅ COMPLETO

Il backend è **completamente funzionante** e testato:

| Funzionalità | Stato | Endpoint |
|--------------|-------|----------|
| Upload bandi | ✅ | `POST /tenders/upload` |
| Estrazione testo (LlamaParse) | ✅ | `POST /tenders/extract-text/{cig}` |
| Analisi requisiti (GPT-4o-mini) | ✅ | `POST /tenders/analyze/{cig}` |
| Upload documenti aziendali | ✅ | `POST /companies/{id}/upload` |
| RAG con embeddings | ✅ | Supabase RPC `match_company_assets` |
| Generazione proposte | ✅ | `POST /projects/{id}/generate` |

### Frontend (Next.js 16 + TypeScript) 🔄 IN CORSO

**Completato:**
- Setup iniziale (Next.js, Tailwind v4, shadcn/ui, React Query, Zustand)
- Homepage landing page
- Dashboard progetti (grid di card stile NotebookLM)
- Componenti: `ProjectCard`, `NewProjectCard`, `EmptyProjectsState`

**Da fare:**
- Pagina "Nuovo Progetto" (upload bando)
- Pagina dettaglio progetto
- Pagina upload documenti aziendali
- Pagina visualizzazione/modifica proposta generata

---

## 🗂️ Struttura Cartelle

```
bandi/
├── backend/                    # FastAPI Python
│   ├── app/
│   │   ├── main.py            # Entry point
│   │   ├── routers/           # API endpoints
│   │   │   ├── tenders.py
│   │   │   ├── companies.py
│   │   │   └── projects.py
│   │   ├── services/          # Business logic
│   │   │   ├── analysis_service.py
│   │   │   ├── proposal_service.py
│   │   │   ├── similarity_service.py
│   │   │   └── ...
│   │   └── models/schemas.py  # Pydantic models
│   └── requirements.txt
│
├── frontend/                   # Next.js 16
│   ├── src/
│   │   ├── app/               # App Router pages
│   │   │   ├── page.tsx       # Landing page
│   │   │   └── dashboard/     # Dashboard progetti
│   │   ├── components/        # React components
│   │   ├── lib/               # api.ts, supabase.ts
│   │   ├── hooks/             # React Query hooks
│   │   ├── stores/            # Zustand state
│   │   └── providers/         # React Query provider
│   └── package.json
│
└── development/
    ├── development_log.md     # Log dettagliato sessioni
    ├── project_plan.md        # Requisiti e architettura
    ├── schema.sql             # Schema database Supabase
    └── chat_context.md        # Questo file
```

---

## 🔑 Informazioni Importanti

### Database (Supabase)
IMPORTANTE: Leggi prima il file schema.sql per capire la struttura del database.

- **URL:** https://tgoipkcgxvvkraavunyp.supabase.co
- **Tabelle principali:** `tenders`, `tender_documents`, `tender_requirements`, `companies`, `company_documents`, `company_assets`, `projects`
- **RPC:** `match_company_assets` per similarity search

### Company di Test

```
ID: a5817d3f-5462-43c1-beb7-0f8769ac5531
```
Usato per tutti i test. Ha già progetti e documenti caricati.

### Avvio Server

```bash
# Backend (porta 8080)
cd backend && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8080

# Frontend (porta 3000)
cd frontend && npm run dev
```

---

## 🐛 Bug Risolti (Sessione 12)

1. **Caratteri speciali nei filename** (`[]{}`) → `_sanitize_filename()` in `storage_service.py`
2. **Caratteri accentati** (`àèù`) → `unicodedata.normalize()` per translitterazione
3. **LlamaParse "Event loop is closed"** → Nuova istanza + nuovo event loop per ogni file

---

## 📝 Prossimi Passi

1. **Creare pagina "Nuovo Progetto"** (`/projects/new`)
   - Form con input CIG
   - Upload multiplo file PDF
   - Chiamata a `/tenders/upload`
   - Redirect a dashboard dopo creazione

2. **Creare pagina dettaglio progetto** (`/projects/[id]`)
   - Visualizzazione stato
   - Lista requisiti estratti
   - Bottone "Genera Proposta"
   - Visualizzazione proposta generata

3. **Layout condiviso** con sidebar per navigazione

---

## 💡 Note per la Prossima Chat

- Leggi sempre `development_log.md` per dettagli implementativi
- Leggi `project_plan.md` per requisiti e architettura
- Leggi `schema.sql` per struttura database
- Il backend è stabile, focus ora è sul frontend
- L'utente preferisce sviluppo incrementale: una pagina alla volta, con test dopo ogni modifica
