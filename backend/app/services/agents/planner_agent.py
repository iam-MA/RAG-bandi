"""
Planner Agent: Creates an extraction plan based on document profile.
Decides which executor agents to use and on which sections.
"""
from typing import List
from openai import AsyncOpenAI

from .base_agent import BaseAgent, AgentResult
from .agent_schemas import DocumentProfile, ExtractionPlan, ExtractionTask


PLANNER_SYSTEM_PROMPT = """Sei un esperto di bandi di gara italiani e devi pianificare l'estrazione delle informazioni.

Dato il profilo di un documento di gara, devi creare un PIANO DI ESTRAZIONE che indica:
1. Quali agenti specializzati usare
2. Su quali sezioni del documento devono lavorare
3. Cosa devono cercare specificamente

AGENTI DISPONIBILI:
- GeneralInfoExtractor: estrae informazioni generali (oggetto, ente, importo, durata)
- RequirementsExtractor: estrae requisiti di partecipazione (generali, economici, tecnici)
- ScoringExtractor: estrae criteri di valutazione e punteggi
- DocumentsExtractor: estrae elenco documenti richiesti
- DeadlinesExtractor: estrae scadenze e date importanti
- TechnicalSpecsExtractor: estrae specifiche tecniche del servizio/fornitura

Crea un piano che copra TUTTE le informazioni rilevanti, evitando duplicazioni.
Rispondi SEMPRE in formato JSON valido."""


PLANNER_USER_PROMPT = """Crea un piano di estrazione per questo documento di gara.

PROFILO DOCUMENTO:
- Settore: {sector}
- Tipo procedura: {tender_type}
- Complessità: {complexity}
- Qualità struttura: {structure_quality}
- Totale righe: {total_lines}

SEZIONI IDENTIFICATE:
{sections_text}

OSSERVAZIONI:
{observations_text}

Rispondi con un JSON nel seguente formato:
{{
  "strategy": "string - descrizione della strategia di estrazione",
  "tasks": [
    {{
      "id": 1,
      "agent_type": "GeneralInfoExtractor|RequirementsExtractor|ScoringExtractor|DocumentsExtractor|DeadlinesExtractor|TechnicalSpecsExtractor",
      "target_sections": ["Titolo sezione 1", "Titolo sezione 2"],
      "focus_areas": ["Cosa cercare specificamente"],
      "priority": "high|medium|low"
    }}
  ],
  "estimated_api_calls": "int - numero stimato di chiamate API",
  "notes": "string - eventuali note aggiuntive"
}}

REGOLE:
1. Ogni agente deve avere almeno una sezione target
2. Includi TUTTI gli agenti necessari per un'estrazione completa
3. Per settori specifici (es. software, edilizia) il TechnicalSpecsExtractor è importante
4. RequirementsExtractor e ScoringExtractor sono SEMPRE necessari
5. Ordina i task per priorità (high prima)"""


class PlannerAgent(BaseAgent):
    """
    Planner Agent: Creates extraction plan based on document profile.
    
    Responsibility:
    - Analyze the document profile
    - Decide which executor agents to use
    - Map sections to agents
    - Create ordered task list
    
    Output: ExtractionPlan
    """
    
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        super().__init__(client, model)
    
    def get_system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT
    
    def get_user_prompt(self, profile: DocumentProfile) -> str:
        # Format sections
        sections_text = "\n".join([
            f"- {s.title}: {s.content_summary or 'N/A'}"
            for s in profile.sections
        ])
        
        # Format observations
        observations_text = "\n".join([
            f"- {obs}" for obs in profile.key_observations
        ])
        
        return PLANNER_USER_PROMPT.format(
            sector=profile.sector,
            tender_type=profile.tender_type,
            complexity=profile.complexity,
            structure_quality=profile.structure_quality,
            total_lines=profile.total_lines,
            sections_text=sections_text or "Nessuna sezione identificata",
            observations_text=observations_text or "Nessuna osservazione"
        )
    
    async def run(self, profile: DocumentProfile) -> AgentResult:
        """
        Create an extraction plan based on document profile.
        
        Args:
            profile: DocumentProfile from the Analyzer Agent
            
        Returns:
            AgentResult with ExtractionPlan in .data if successful
        """
        user_prompt = self.get_user_prompt(profile)
        
        result = await self.call_llm(
            user_prompt=user_prompt,
            json_mode=True,
            response_model=ExtractionPlan
        )
        
        return result
