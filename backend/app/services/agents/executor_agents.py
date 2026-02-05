"""
Executor Agents: Specialized agents for extracting specific types of information.
Each agent focuses on one category of insights.
"""
from typing import List, Optional
from openai import AsyncOpenAI

from .base_agent import BaseAgent, AgentResult
from .agent_schemas import Insight, InsightCategory, ImportanceLevel, Finding, Impact, Action, InsightMetadata


# =============================================================================
# BASE EXECUTOR
# =============================================================================

class BaseExecutorAgent(BaseAgent):
    """Base class for all executor agents."""
    
    category: InsightCategory = InsightCategory.TENDER_OVERVIEW
    agent_name: str = "BaseExecutor"
    
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        super().__init__(client, model)
        self.name = self.agent_name
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        """Override in subclasses to provide specific extraction prompt."""
        raise NotImplementedError
    
    async def run(self, document_sections: str, focus_areas: List[str] = None) -> AgentResult:
        """Execute extraction on the given sections."""
        prompt = self.get_extraction_prompt(document_sections, focus_areas or [])
        return await self.call_llm(prompt, json_mode=True)


# =============================================================================
# GENERAL INFO EXTRACTOR
# =============================================================================

GENERAL_INFO_PROMPT = """Analizza queste sezioni di un bando di gara ed estrai le INFORMAZIONI GENERALI.

SEZIONI:
{sections}

FOCUS SU: {focus}

Estrai TUTTE le informazioni generali trovate. Per ogni informazione, indica:
- Cosa hai trovato (titolo e descrizione)
- Il testo originale da cui l'hai estratta
- Perché è importante per chi vuole partecipare
- Cosa deve fare l'utente con questa informazione

Rispondi con un JSON:
{{
  "insights": [
    {{
      "id": "GEN-001",
      "type": "oggetto_appalto|ente_appaltante|valore_gara|durata_contratto|settore|procedura_tipo|cig|altro",
      "finding": {{
        "title": "Titolo breve",
        "description": "Descrizione completa",
        "source_text": "Testo originale dal documento",
        "source_location": "Quale sezione"
      }},
      "impact": {{
        "importance": "critical|high|medium|low",
        "reason": "Perché è importante"
      }},
      "action": {{
        "suggestion": "Cosa deve fare l'utente",
        "documents_needed": ["lista documenti se servono"],
        "preparation_hint": "Suggerimento per prepararsi"
      }}
    }}
  ]
}}

IMPORTANTE: 
- "valore_gara" è ALWAYS critical
- "cig" è importante per le ricerche
- Estrai TUTTO quello che trovi, non solo il minimo"""


class GeneralInfoExtractor(BaseExecutorAgent):
    """Extracts general tender information: object, authority, value, duration."""
    
    category = InsightCategory.TENDER_OVERVIEW
    agent_name = "GeneralInfoExtractor"
    
    def get_system_prompt(self) -> str:
        return "Sei un esperto analista di bandi di gara. Estrai le informazioni generali in modo preciso e completo."
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        focus = ", ".join(focus_areas) if focus_areas else "tutte le informazioni generali"
        return GENERAL_INFO_PROMPT.format(sections=document_sections, focus=focus)


# =============================================================================
# REQUIREMENTS EXTRACTOR
# =============================================================================

REQUIREMENTS_PROMPT = """Analizza queste sezioni ed estrai tutti i REQUISITI DI PARTECIPAZIONE.

SEZIONI:
{sections}

FOCUS SU: {focus}

Estrai OGNI requisito che un'azienda deve soddisfare per partecipare. Include:
- Requisiti generali (assenza cause esclusione)
- Requisiti di idoneità professionale (iscrizioni albi, registri)
- Requisiti economico-finanziari (fatturato minimo, ecc.)
- Requisiti tecnico-professionali (esperienze, certificazioni)

Rispondi con un JSON:
{{
  "insights": [
    {{
      "id": "REQ-001",
      "type": "requisito_generale|idoneita_professionale|fatturato_minimo|esperienza_pregressa|certificazione_richiesta|iscrizione_albo|altro",
      "finding": {{
        "title": "Titolo del requisito",
        "description": "Descrizione dettagliata",
        "source_text": "Testo originale ESATTO",
        "source_location": "Sezione/paragrafo"
      }},
      "impact": {{
        "importance": "critical|high|medium|low",
        "reason": "Perché è importante - se è obbligatorio indicare CHIARAMENTE"
      }},
      "action": {{
        "suggestion": "Cosa deve verificare/fare l'utente",
        "documents_needed": ["Documenti da preparare"],
        "preparation_hint": "Come prepararsi SE non si ha il requisito"
      }}
    }}
  ]
}}

IMPORTANTE:
- I requisiti OBBLIGATORI sono CRITICAL (senza = esclusione)
- Indica chiaramente soglie numeriche (es. "€1.000.000 nel triennio")
- Per certificazioni, indica categoria e classe se specificate"""


class RequirementsExtractor(BaseExecutorAgent):
    """Extracts participation requirements: general, professional, economic, technical."""
    
    category = InsightCategory.REQUISITO_PARTECIPAZIONE
    agent_name = "RequirementsExtractor"
    
    def get_system_prompt(self) -> str:
        return "Sei un esperto di requisiti per gare d'appalto. Identifica TUTTI i requisiti, anche quelli impliciti."
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        focus = ", ".join(focus_areas) if focus_areas else "tutti i requisiti di partecipazione"
        return REQUIREMENTS_PROMPT.format(sections=document_sections, focus=focus)


# =============================================================================
# SCORING EXTRACTOR
# =============================================================================

SCORING_PROMPT = """Analizza queste sezioni ed estrai tutti i CRITERI DI VALUTAZIONE e PUNTEGGI.

SEZIONI:
{sections}

FOCUS SU: {focus}

Estrai OGNI criterio di punteggio, inclusi:
- Criteri tecnici con relativi pesi
- Criteri economici e formule
- Elementi premianti (bonus)
- Soglie minime
- Scale di valutazione

Rispondi con un JSON:
{{
  "insights": [
    {{
      "id": "SCORE-001",
      "type": "criterio_tecnico|criterio_economico|elemento_premiante|soglia_minima|scala_valutazione",
      "finding": {{
        "title": "Nome del criterio",
        "description": "Descrizione dettagliata",
        "source_text": "Testo originale",
        "source_location": "Sezione"
      }},
      "impact": {{
        "importance": "critical|high|medium|low",
        "reason": "Impatto sul punteggio finale",
        "points_available": 15
      }},
      "action": {{
        "suggestion": "Come massimizzare il punteggio",
        "documents_needed": ["Cosa preparare"],
        "preparation_hint": "Strategia per ottenere punti"
      }}
    }}
  ]
}}

IMPORTANTE:
- Indica SEMPRE i punti disponibili (points_available) se specificati
- Spiega come si ottiene il punteggio massimo
- Identifica elementi che possono fare la differenza competitiva"""


class ScoringExtractor(BaseExecutorAgent):
    """Extracts scoring criteria, weights, and formulas."""
    
    category = InsightCategory.CRITERIO_PUNTEGGIO
    agent_name = "ScoringExtractor"
    
    def get_system_prompt(self) -> str:
        return "Sei un esperto di criteri di valutazione per gare. Identifica ogni criterio e spiega come massimizzare il punteggio."
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        focus = ", ".join(focus_areas) if focus_areas else "tutti i criteri di punteggio"
        return SCORING_PROMPT.format(sections=document_sections, focus=focus)


# =============================================================================
# DOCUMENTS EXTRACTOR
# =============================================================================

DOCUMENTS_PROMPT = """Analizza queste sezioni ed estrai tutti i DOCUMENTI RICHIESTI.

SEZIONI:
{sections}

FOCUS SU: {focus}

Estrai OGNI documento che deve essere preparato/presentato:
- Documenti amministrativi (domanda, DGUE, dichiarazioni)
- Documenti tecnici (relazione, organigrammi)
- Documenti economici (offerta economica)
- Garanzie (provvisoria, definitiva)
- Allegati e certificati

Rispondi con un JSON:
{{
  "insights": [
    {{
      "id": "DOC-001",
      "type": "documento_amministrativo|documento_tecnico|documento_economico|garanzia|dichiarazione|certificato|allegato",
      "finding": {{
        "title": "Nome documento",
        "description": "Descrizione e requisiti del documento",
        "source_text": "Testo originale",
        "source_location": "Sezione"
      }},
      "impact": {{
        "importance": "critical|high|medium|low",
        "reason": "Perché è necessario"
      }},
      "action": {{
        "suggestion": "Come preparare il documento",
        "documents_needed": ["Elementi necessari per prepararlo"],
        "preparation_hint": "Formato richiesto, firme, ecc."
      }}
    }}
  ]
}}

IMPORTANTE:
- Indica se il documento è a PENA DI ESCLUSIONE
- Specifica formato richiesto (PDF, firmato digitalmente, ecc.)
- Indica se ci sono modelli/facsimile da usare"""


class DocumentsExtractor(BaseExecutorAgent):
    """Extracts required documents list."""
    
    category = InsightCategory.DOCUMENTO_RICHIESTO
    agent_name = "DocumentsExtractor"
    
    def get_system_prompt(self) -> str:
        return "Sei un esperto di documentazione per gare d'appalto. Crea una checklist completa di tutti i documenti necessari."
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        focus = ", ".join(focus_areas) if focus_areas else "tutti i documenti richiesti"
        return DOCUMENTS_PROMPT.format(sections=document_sections, focus=focus)


# =============================================================================
# DEADLINES EXTRACTOR
# =============================================================================

DEADLINES_PROMPT = """Analizza queste sezioni ed estrai tutte le DATE e SCADENZE.

SEZIONI:
{sections}

FOCUS SU: {focus}

Estrai OGNI data e scadenza importante:
- Termine presentazione offerte
- Scadenza sopralluogo
- Termine richiesta chiarimenti
- Data apertura buste
- Inizio/fine contratto
- Altre date rilevanti

Rispondi con un JSON:
{{
  "insights": [
    {{
      "id": "DEAD-001",
      "type": "termine_offerta|sopralluogo|richiesta_chiarimenti|apertura_buste|inizio_contratto|altro",
      "finding": {{
        "title": "Nome scadenza",
        "description": "Descrizione completa",
        "source_text": "Testo originale con data",
        "source_location": "Sezione"
      }},
      "impact": {{
        "importance": "critical|high|medium|low",
        "reason": "Perché è importante rispettare questa data"
      }},
      "action": {{
        "suggestion": "Cosa fare PRIMA di questa scadenza",
        "documents_needed": [],
        "preparation_hint": "Tempo consigliato per prepararsi"
      }}
    }}
  ]
}}

IMPORTANTE:
- Le scadenze per presentazione offerta sono SEMPRE critical
- Indica ORA oltre alla data se specificata
- Il sopralluogo obbligatorio è critical"""


class DeadlinesExtractor(BaseExecutorAgent):
    """Extracts all deadlines and important dates."""
    
    category = InsightCategory.SCADENZA
    agent_name = "DeadlinesExtractor"
    
    def get_system_prompt(self) -> str:
        return "Sei un esperto di tempistiche per gare d'appalto. Crea un calendario completo di tutte le scadenze."
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        focus = ", ".join(focus_areas) if focus_areas else "tutte le date e scadenze"
        return DEADLINES_PROMPT.format(sections=document_sections, focus=focus)


# =============================================================================
# TECHNICAL SPECS EXTRACTOR
# =============================================================================

TECHNICAL_SPECS_PROMPT = """Analizza queste sezioni ed estrai le SPECIFICHE TECNICHE del servizio/fornitura.

SEZIONI:
{sections}

FOCUS SU: {focus}

Estrai ogni specifica tecnica rilevante:
- Prestazioni richieste
- Standard qualitativi
- Personale necessario (figure professionali, qualifiche)
- Attrezzature/materiali
- Modalità operative

Rispondi con un JSON:
{{
  "insights": [
    {{
      "id": "TECH-001",
      "type": "prestazione_richiesta|standard_qualita|personale_richiesto|attrezzatura|materiali|modalita_operative",
      "finding": {{
        "title": "Titolo specifica",
        "description": "Descrizione dettagliata",
        "source_text": "Testo originale",
        "source_location": "Sezione"
      }},
      "impact": {{
        "importance": "critical|high|medium|low",
        "reason": "Perché questa specifica è importante"
      }},
      "action": {{
        "suggestion": "Come soddisfare questa specifica",
        "documents_needed": ["Attestati, certificati necessari"],
        "preparation_hint": "Come presentare al meglio le proprie capacità"
      }}
    }}
  ]
}}

IMPORTANTE:
- Per il personale, indica qualifiche specifiche richieste
- Per attrezzature, indica se devono essere di proprietà o disponibili
- Collega le specifiche ai criteri di punteggio se possibile"""


class TechnicalSpecsExtractor(BaseExecutorAgent):
    """Extracts technical specifications of the service/work."""
    
    category = InsightCategory.SPECIFICA_TECNICA
    agent_name = "TechnicalSpecsExtractor"
    
    def get_system_prompt(self) -> str:
        return "Sei un esperto tecnico di capitolati d'appalto. Estrai ogni dettaglio tecnico rilevante."
    
    def get_extraction_prompt(self, document_sections: str, focus_areas: List[str]) -> str:
        focus = ", ".join(focus_areas) if focus_areas else "tutte le specifiche tecniche"
        return TECHNICAL_SPECS_PROMPT.format(sections=document_sections, focus=focus)


# =============================================================================
# EXECUTOR REGISTRY
# =============================================================================

EXECUTOR_REGISTRY = {
    "GeneralInfoExtractor": GeneralInfoExtractor,
    "RequirementsExtractor": RequirementsExtractor,
    "ScoringExtractor": ScoringExtractor,
    "DocumentsExtractor": DocumentsExtractor,
    "DeadlinesExtractor": DeadlinesExtractor,
    "TechnicalSpecsExtractor": TechnicalSpecsExtractor,
}


def get_executor(agent_type: str, client: AsyncOpenAI, model: str = "gpt-4o-mini") -> BaseExecutorAgent:
    """Get an executor agent by type name."""
    if agent_type not in EXECUTOR_REGISTRY:
        raise ValueError(f"Unknown executor type: {agent_type}. Available: {list(EXECUTOR_REGISTRY.keys())}")
    return EXECUTOR_REGISTRY[agent_type](client, model)
