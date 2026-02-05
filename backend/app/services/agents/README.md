# Agents (Pipeline 1 - Analisi Bando)

Sistema multi-agente per l'analisi automatica dei documenti di gara.

## Architettura

```
Planner → Executors (x5) → Validator → Aggregator
```

## File

| File | Ruolo |
|------|-------|
| `base_agent.py` | Classe base per tutti gli agenti |
| `agent_schemas.py` | Schemi Pydantic per input/output |
| `planner_agent.py` | Analizza struttura bando e crea piano |
| `executor_agents.py` | 5 agenti specializzati per estrazione dati |
| `validator_agent.py` | Valida coerenza e completezza |
| `aggregator_agent.py` | Combina risultati in output finale |

## Executor Agents

1. **BasicInfoExecutor** - Info base (CIG, importo, scadenze)
2. **RequirementsExecutor** - Requisiti di partecipazione
3. **CriteriaExecutor** - Criteri di valutazione e punteggi
4. **DocumentsExecutor** - Documenti richiesti
5. **TechnicalExecutor** - Specifiche tecniche
