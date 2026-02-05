# Proposal (Pipeline 2 - Generazione Proposta)

Sistema per la generazione automatica di proposte tecniche.

## Architettura

```
Orchestrator → Section Agents → Final Assembly
```

## File Principali

| File | Descrizione |
|------|-------------|
| `orchestrator.py` | Coordina la generazione delle sezioni |
| `schemas.py` | Schemi Pydantic per la proposta |

## Cartella `agents/`

Agenti specializzati per ogni sezione della proposta tecnica:
- Metodologia
- Team di progetto
- Cronoprogramma
- Gestione qualità
- Altri contenuti richiesti

Ogni agente usa RAG per recuperare informazioni rilevanti dalla knowledge base aziendale.
