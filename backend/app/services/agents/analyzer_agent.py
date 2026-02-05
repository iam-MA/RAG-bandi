"""
Analyzer Agent: First step of the pipeline.
Analyzes the document to understand its structure, sector, and complexity.
"""
from typing import Optional
from openai import AsyncOpenAI

from .base_agent import BaseAgent, AgentResult
from .agent_schemas import DocumentProfile, DocumentSection


ANALYZER_SYSTEM_PROMPT = """Sei un analista esperto di bandi di gara italiani con 20 anni di esperienza.
Il tuo compito è analizzare un documento di gara e produrre un profilo strutturato che aiuterà gli step successivi a estrarre le informazioni rilevanti.

DEVI identificare:
1. Il SETTORE della gara (es: servizi_pulizia, software, edilizia, forniture, consulenza, sanita, trasporti, ecc.)
2. Il TIPO di procedura (es: procedura_aperta, procedura_negoziata, affidamento_diretto, ecc.)
3. La COMPLESSITÀ del documento (low/medium/high)
4. La QUALITÀ della struttura (poor/fair/good/excellent)
5. Le SEZIONI principali con titolo e posizione nel documento
6. OSSERVAZIONI chiave sulla struttura e contenuto

Rispondi SEMPRE in formato JSON valido."""


ANALYZER_USER_PROMPT = """Analizza questo documento di gara e produci un profilo strutturato.

DOCUMENTO:
```
{document}
```

INFORMAZIONI AGGIUNTIVE:
- Numero totale di righe: {total_lines}

Rispondi con un JSON nel seguente formato:
{{
  "sector": "string - settore del bando (es: servizi_pulizia, software, edilizia)",
  "tender_type": "string - tipo procedura (es: procedura_aperta, affidamento_diretto)",
  "complexity": "low|medium|high",
  "total_lines": {total_lines},
  "total_sections": "int - numero di sezioni identificate",
  "language": "it",
  "structure_quality": "poor|fair|good|excellent",
  "sections": [
    {{
      "title": "string - titolo della sezione",
      "start_line": "int - riga di inizio (approssimativa)",
      "end_line": "int - riga di fine (approssimativa)",
      "content_summary": "string - breve descrizione del contenuto"
    }}
  ],
  "key_observations": [
    "string - osservazione 1",
    "string - osservazione 2"
  ]
}}

Identifica TUTTE le sezioni principali del documento. Concentrati su:
- Oggetto dell'appalto
- Requisiti di partecipazione (generali, economici, tecnici)
- Criteri di valutazione/punteggio
- Documentazione richiesta
- Scadenze e tempistiche
- Specifiche tecniche del servizio/fornitura"""


class AnalyzerAgent(BaseAgent):
    """
    Analyzer Agent: First step in the pipeline.
    
    Responsibility:
    - Read the entire document (or a sample if too long)
    - Identify sector, complexity, structure
    - Map main sections and their content
    
    Output: DocumentProfile
    """
    
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
        max_document_chars: int = 100000  # ~25k tokens
    ):
        super().__init__(client, model)
        self.max_document_chars = max_document_chars
    
    def get_system_prompt(self) -> str:
        return ANALYZER_SYSTEM_PROMPT
    
    def get_user_prompt(self, document: str, total_lines: int) -> str:
        return ANALYZER_USER_PROMPT.format(
            document=document,
            total_lines=total_lines
        )
    
    def _prepare_document(self, document: str) -> tuple[str, bool]:
        """
        Prepare document for analysis.
        If too long, take beginning + end to capture key info.
        
        Returns:
            (prepared_document, was_truncated)
        """
        if len(document) <= self.max_document_chars:
            return document, False
        
        # Take first 60% and last 40% to capture intro and requirements
        first_part_size = int(self.max_document_chars * 0.6)
        last_part_size = self.max_document_chars - first_part_size
        
        first_part = document[:first_part_size]
        last_part = document[-last_part_size:]
        
        truncated = f"{first_part}\n\n[... DOCUMENTO TRONCATO PER LUNGHEZZA ...]\n\n{last_part}"
        return truncated, True
    
    async def run(self, document: str) -> AgentResult:
        """
        Analyze a tender document and produce a DocumentProfile.
        
        Args:
            document: The full markdown text of the tender document
            
        Returns:
            AgentResult with DocumentProfile in .data if successful
        """
        # Count lines
        total_lines = document.count('\n') + 1
        
        # Prepare document (truncate if needed)
        prepared_doc, was_truncated = self._prepare_document(document)
        
        # Build prompt
        user_prompt = self.get_user_prompt(prepared_doc, total_lines)
        
        # Call LLM
        result = await self.call_llm(
            user_prompt=user_prompt,
            json_mode=True,
            response_model=DocumentProfile
        )
        
        # Add truncation warning if needed
        if result.success and was_truncated:
            if isinstance(result.data, DocumentProfile):
                result.data.key_observations.append(
                    f"NOTA: Documento troncato per analisi (originale: {len(document)} caratteri)"
                )
        
        return result
