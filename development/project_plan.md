# PROGETTO: AI Tender Architect (Gare d'Appalto SaaS)


## 1. Project Overview
**Obiettivo:** Costruire una piattaforma SaaS che automatizza il processo di partecipazione ai bandi di gara pubblici per le aziende.
**Core Value:** Il sistema utilizza agenti AI avanzati per analizzare i documenti dei bandi (spesso complessi e lunghi) e generare automaticamente la documentazione necessaria per la candidatura, attingendo da una "memoria aziendale" (RAG) specifica per ogni utente.


## 2. Technical Stack & Guidelines
Tutto il codice generato deve rispettare rigorosamente questo stack:

### Backend
- **Language:** Python
- **Framework:** FastAPI (per le API REST e la gestione asincrona).
- **Database & Auth:** Supabase (PostgreSQL + pgvector).
- **AI:** ChatGPT (o altro LLM) via API.
- **Parsing:** LlamaParse o librerie Python avanzate per leggere PDF complessi (tabelle).
- **Validazione Dati:** Pydantic.

### Frontend
- **Framework:** Next.js.
- **Styling:** Tailwind CSS, shadcn/ui.
- **State Management:** React Query / Zustand.
- **Supabase Client:** `@supabase/supabase-js`.

### Infrastruttura & Storage (CRUCIALE)
- **Database Schema:** La struttura del database **È GIA DEFINITA**.
    * **File di riferimento:** `backend/schema.sql`
    * **Regola:** Ogni volta che devi scrivere query o interagire con il DB, **leggi prima `backend/schema.sql`** per conoscere nomi delle tabelle, colonne e relazioni. Non inventare o "allucinare" colonne che non esistono in quel file.
- **Object Storage (Supabase Buckets):**
    * Bucket `tenders`: Utilizzato ESCLUSIVAMENTE per i file dei bandi di gara (PDF, DOCX) caricati dagli utenti.
    * Bucket `companies`: Utilizzato ESCLUSIVAMENTE per i documenti aziendali (Visure, CV, Certificazioni, ecc.) che costituiscono la Knowledge Base dell'utente.


## 3. Logical Architecture & Workflows

### A. Onboarding Azienda
L'Utente registra il suo account tramite l'Auth di Supabase.

### B. Flusso Ingestione Bando (Tender Upload)
L'obiettivo è analizzare un bando e salvarne i requisiti evitando di analizzare bandi già caricati in precedenza. Una volta fatto ciò, le informazioni estratte saranno utilizzate per spiegare all'utente le informazioni necessarie a candidarsi per quel bando.
1.  **User Action:** L'utente carica uno o più documenti relativi ad un bando gara e scrive manualmente il CIG (Codice Identificativo Gara).
2.  **Check Cache:** Il sistema verifica nella tabella `tenders` se esiste già un record con quel `cig`.
    * **Se esiste:** Il bando è già stato analizzato, quindi restituisce immediatamente i dati presenti in `analysis` (JSON) senza rieseguire l'analisi AI.
    * **Se non esiste:** Carica il file nel bucket `tenders`, crea il record DB e avvia il processo di analisi AI.
3.  **AI Analysis (Agentico):**
    * Il modello legge il documento.
    * Estrae metadati chiave (Scadenza, Importo, Categorie SOA).
    * Popola la tabella `tender_requirements` e successivamente il campo JSON `analysis`.
    * Aggiorna lo stato del bando su `ready`.
4.  **Restituzione informazioni:** Le informazioni estratte e salvate in `analysis`, insieme a quelle savlate in `tender_requirements`, verranno restituite all'utente, in modo che quest'ultimo possa basarsi su esse per recuperare la documentazione necessaria per candidarsi al bando.

### C. Flusso Knowledge Base (Company Assets)
L'obiettivo è creare una memoria a lungo termine dell'azienda, così da utilizzarla per compilare autonomamente le candidature ai bandi gara senza bisogno di chiedere ogni volta la documentazione aziendale all'utente. Per farlo si sfrutta il primo bando per cui l'utente utilizza la piattaforma.
1.  **User Action:** L'utente carica documenti aziendali (es. Visura, Bilancio, CV Dipendenti). I documenti che carica sono quelli che contengono le informazioni per compilare la candidatura al bando gara.
2.  **Processing:**
    * Salvataggio file nel bucket `companies`.
    * Record creati in `company_documents`.
3.  **RAG Ingestion (per ogni documento):**
    * Il testo viene estratto dal documento.
    * Il testo viene diviso in chunk.
    * Vengono generati gli embedding.
    * I dati vengono salvati in `company_assets` (content + embedding vector).

### D. Flusso Generazione Risposta (Proposal Generation):
L'obiettivo è scrivere la documentazione di gara.
1.  **Trigger:** Al via dell'utente, il programma seleziona le informazioni contenute in `analysis` e le richieste in `tender_requirements`.
2.  **Retrieval:** L'Agente analizza i requisiti del bando. Per ogni requisito:
    * Esegue una ricerca semantica (similarity search) su `company_assets` filtrando per `company_id`.
    * Recupera i chunk più rilevanti (es. se il bando chiede "esperienza ponti", cerca progetti di ponti nel DB dell'azienda).
3.  **Generation:** L'LLM combina i Requisiti del Bando + I Dati Aziendali Recuperati per scrivere una risposta formale e persuasiva.
4.  **Output:** Il testo generato viene salvato in `projects.generated_response` (JSONB) e poi mostrato all'utente per la revisione finale.

### E. Export:
Generazione file Word (.docx) nativo con formattazione corretta.

### F. Spiegazione extra del flusso AI
Aggiungo una spiegazone extra del flusso di documenti AI. È molto approssimativa, ma serve per avere in mente la struttura generale.

0) L'utente carica i documenti relativi al bando
1) Un modello crea il vectordb con i dati del bando;
2) Il programma analizza il testo dei bandi. Non con il vectordb o il RAG, ma con una pipeline apposita che tramite vari step va a suddividere il documento e lo fa elaborare da un modello. Da questa elaborazione del punto (2), il modello ottiene una serie di vincoli e informazioni necessarie per applicare al bando, quindi presenta queste informazioni all'utente;
3) L'utente carica tutti i documenti della sua azienda necessari, e il programma fa il solito ciclo: upload Supabase + estrazione dati;
4) Un modello crea il vectordb delle informazioni dell'utente;
5) Quando è ora di scrivere il testo per la gara, il programma recupera le informazioni elaborate al punto (2), i chunk di testo rilevanti ottenuti al punto (1) e le informazioni dell'azienda tramite il RAG del punto (4). Dopodiché passa tutte queste informazioni ad una seconda pipeline che scrive la bozza per applicare alla gara, tenendo in considerazione tutte le informazioni relative;
6) Il programma mostra all'utente il testo finale, che potrà essere modificato ed esportato in docx o pdf.


## 4. Development Rules
- **Agentic First:** Non scrivere script lineari semplici per l'estrazione dati complessi. Crea flussi logici che prevedano controllo degli errori e auto-correzione (es. se l'OCR fallisce, riprova con parametri diversi).
- **Sicurezza (Supabase RLS):** Row Level Security (RLS) su Supabase. Tieni a mente che esistono policy di sicurezza. Le operazioni sui dati aziendali devono sempre essere fatte nel contesto dell'utente proprietario (`user_id`). I dati di un'azienda sono inaccessibili alle altre.
- **Modularità:** Scrivi piccoli agenti/funzioni (es. `analyze_tender_sector`, `generate_chapter`).
- **Consistency:** Usa sempre i nomi delle variabili presenti in `backend/schema.sql`.
