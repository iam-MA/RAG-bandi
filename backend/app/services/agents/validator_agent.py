"""
Validator Agent: Final step to validate extraction quality.
Checks for completeness, consistency, and identifies issues.
"""
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from datetime import datetime
import re

from .base_agent import BaseAgent, AgentResult
from .agent_schemas import (
    ExtractionResult, DocumentProfile, ValidationResult, ValidationIssue,
    IssueSeverity, IssueCategory
)


# Fields that MUST be present for a valid extraction
REQUIRED_FIELDS = {
    "tender_overview": ["oggetto_appalto", "valore_gara", "cig"],
    "requisito_partecipazione": [],  # At least one required
    "scadenza": ["termine_offerta"],
    "documento_richiesto": [],  # At least one required
}

# Minimum insights per category for high-quality extraction
MIN_INSIGHTS_PER_CATEGORY = {
    "tender_overview": 3,
    "requisito_partecipazione": 2,
    "criterio_punteggio": 1,
    "documento_richiesto": 2,
    "scadenza": 1,
}


VALIDATOR_SYSTEM_PROMPT = """Sei un esperto revisore di analisi di bandi di gara.
Il tuo compito è verificare la qualità di un'estrazione automatica, identificando:
1. Informazioni mancanti critiche
2. Inconsistenze interne
3. Dati potenzialmente errati
4. Suggerimenti per migliorare l'estrazione

Rispondi SEMPRE in formato JSON valido."""


VALIDATOR_USER_PROMPT = """Analizza questa estrazione da un bando di gara e valutane la qualità.

PROFILO DOCUMENTO:
- Settore: {sector}
- Tipo: {tender_type}
- Complessità: {complexity}

RIASSUNTO TENDER:
{tender_summary}

INSIGHTS ESTRATTI ({total_insights} totali):
{insights_summary}

Verifica:
1. Ci sono le informazioni essenziali? (oggetto, valore, scadenze, requisiti)
2. I dati sono coerenti tra loro? (es. importi, date)
3. Manca qualcosa di importante per questo tipo di bando?
4. Ci sono errori evidenti?

Rispondi con un JSON:
{{
  "quality_score": 0.0-1.0,
  "is_complete": true/false,
  "issues": [
    {{
      "severity": "critical|warning|info",
      "category": "missing_field|inconsistency|potential_error|suggestion",
      "field": "nome del campo problematico",
      "description": "descrizione del problema",
      "suggested_action": "azione suggerita"
    }}
  ],
  "summary": "riassunto della validazione"
}}"""


class ValidatorAgent(BaseAgent):
    """
    Validator Agent: Final quality check on extraction results.
    
    Responsibility:
    - Verify completeness (all critical fields present)
    - Check consistency (no contradictions)
    - Identify potential errors
    - Calculate quality score
    - Suggest improvements
    
    Output: ValidationResult
    """
    
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        super().__init__(client, model)
    
    def get_system_prompt(self) -> str:
        return VALIDATOR_SYSTEM_PROMPT
    
    def _rule_based_validation(self, result: ExtractionResult) -> List[Dict]:
        """
        Perform rule-based validation before LLM check.
        Returns list of issues found.
        """
        issues = []
        
        # Count insights by category
        category_counts = {}
        insight_types = {}
        
        for insight in result.insights:
            cat = insight.get("category", "unknown")
            itype = insight.get("type", "unknown")
            
            category_counts[cat] = category_counts.get(cat, 0) + 1
            
            if cat not in insight_types:
                insight_types[cat] = set()
            insight_types[cat].add(itype)
        
        # Check minimum insights per category
        for cat, min_count in MIN_INSIGHTS_PER_CATEGORY.items():
            actual = category_counts.get(cat, 0)
            if actual < min_count:
                issues.append({
                    "severity": "warning",
                    "category": "missing_field",
                    "field": cat,
                    "description": f"Solo {actual} insights per '{cat}', attesi almeno {min_count}",
                    "suggested_action": f"Verificare se il documento contiene più informazioni per la categoria {cat}"
                })
        
        # Check required fields per category
        for cat, required_types in REQUIRED_FIELDS.items():
            found_types = insight_types.get(cat, set())
            for req_type in required_types:
                if req_type not in found_types:
                    issues.append({
                        "severity": "critical",
                        "category": "missing_field",
                        "field": req_type,
                        "description": f"Campo obbligatorio '{req_type}' non trovato in '{cat}'",
                        "suggested_action": f"Verificare nel documento originale la presenza di {req_type}"
                    })
        
        # Check tender summary completeness
        summary = result.tender_summary
        if not summary.title or summary.title == "Bando di gara":
            issues.append({
                "severity": "warning",
                "category": "missing_field",
                "field": "tender_summary.title",
                "description": "Titolo del bando generico o mancante",
                "suggested_action": "Estrarre il titolo specifico dall'oggetto dell'appalto"
            })
        
        if summary.value is None:
            issues.append({
                "severity": "critical",
                "category": "missing_field",
                "field": "tender_summary.value",
                "description": "Valore della gara non estratto",
                "suggested_action": "Verificare la sezione 'valore a base di gara' del documento"
            })
        
        if summary.contracting_authority is None:
            issues.append({
                "severity": "warning",
                "category": "missing_field",
                "field": "tender_summary.contracting_authority",
                "description": "Ente appaltante non identificato",
                "suggested_action": "Verificare l'intestazione del documento"
            })
        
        # Check for insights without source_text
        insights_without_source = sum(
            1 for i in result.insights 
            if not i.get("finding", {}).get("source_text")
        )
        if insights_without_source > 0:
            ratio = insights_without_source / max(len(result.insights), 1)
            if ratio > 0.2:
                issues.append({
                    "severity": "warning",
                    "category": "potential_error",
                    "field": "source_text",
                    "description": f"{insights_without_source} insights senza source_text ({ratio:.0%})",
                    "suggested_action": "Migliorare l'estrazione per includere sempre il testo originale"
                })
        
        # Check for date format in deadlines
        for insight in result.insights:
            if insight.get("category") == "scadenza":
                source = insight.get("finding", {}).get("source_text", "")
                description = insight.get("finding", {}).get("description", "")
                combined = f"{source} {description}"
                
                # Multiple patterns for Italian date formats
                date_patterns = [
                    r'\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}',  # 10/05/2024, 10-05-2024
                    r'\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}',  # 10 maggio 2024
                    r'(?:ore|entro)\s+\d{1,2}[:.]\d{2}',  # ore 12:00, entro 14.00
                    r'\d{4}',  # Just a year (2024) as minimal coverage
                ]
                
                date_found = any(re.search(pattern, combined, re.IGNORECASE) for pattern in date_patterns)
                
                if combined.strip() and not date_found:
                    issues.append({
                        "severity": "info",
                        "category": "potential_error",
                        "field": f"scadenza.{insight.get('id')}",
                        "description": "Data non trovata nel source_text della scadenza",
                        "suggested_action": "Verificare che la data sia stata estratta correttamente"
                    })
        
        return issues
    
    def _calculate_quality_score(self, result: ExtractionResult, issues: List[Dict]) -> float:
        """Calculate quality score based on issues found."""
        score = 1.0
        
        for issue in issues:
            severity = issue.get("severity", "info")
            if severity == "critical":
                score -= 0.15
            elif severity == "warning":
                score -= 0.05
            elif severity == "info":
                score -= 0.02
        
        # Bonus for having source_text
        sources_present = sum(
            1 for i in result.insights 
            if i.get("finding", {}).get("source_text")
        )
        source_ratio = sources_present / max(len(result.insights), 1)
        score += source_ratio * 0.1
        
        return max(0.0, min(1.0, score))
    
    def _get_insights_summary(self, insights: List[Dict]) -> str:
        """Create a summary of insights for LLM validation."""
        summary_parts = []
        
        # Group by category
        by_category = {}
        for i in insights:
            cat = i.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(i)
        
        for cat, cat_insights in by_category.items():
            summary_parts.append(f"\n[{cat.upper()}] ({len(cat_insights)} insights):")
            for insight in cat_insights[:3]:  # Show first 3 per category
                title = insight.get("finding", {}).get("title", "N/A")
                itype = insight.get("type", "N/A")
                importance = insight.get("impact", {}).get("importance", "N/A")
                summary_parts.append(f"  - {title} (type: {itype}, importance: {importance})")
            if len(cat_insights) > 3:
                summary_parts.append(f"  ... e altri {len(cat_insights) - 3}")
        
        return "\n".join(summary_parts)
    
    async def run(self, result: ExtractionResult) -> AgentResult:
        """
        Validate an extraction result.
        
        Args:
            result: The ExtractionResult to validate
            
        Returns:
            AgentResult with ValidationResult in .data if successful
        """
        # Step 1: Rule-based validation
        rule_issues = self._rule_based_validation(result)
        
        # Step 2: Calculate initial score
        quality_score = self._calculate_quality_score(result, rule_issues)
        
        # Step 3: LLM-based validation for deeper analysis
        profile = result.document_profile
        
        tender_summary_text = f"""
- Titolo: {result.tender_summary.title}
- Ente: {result.tender_summary.contracting_authority or 'N/A'}
- Valore: €{result.tender_summary.value or 'N/A'}
- Durata: {result.tender_summary.duration_months or 'N/A'} mesi
- Procedura: {result.tender_summary.procedure or 'N/A'}
"""
        
        insights_summary = self._get_insights_summary(result.insights)
        
        user_prompt = VALIDATOR_USER_PROMPT.format(
            sector=profile.sector if profile else "N/A",
            tender_type=profile.tender_type if profile else "N/A",
            complexity=profile.complexity if profile else "N/A",
            tender_summary=tender_summary_text,
            total_insights=len(result.insights),
            insights_summary=insights_summary
        )
        
        llm_result = await self.call_llm(user_prompt, json_mode=True)
        
        # Combine results
        all_issues = rule_issues.copy()
        
        if llm_result.success and isinstance(llm_result.data, dict):
            llm_data = llm_result.data
            
            # Add LLM issues
            llm_issues = llm_data.get("issues", [])
            for issue in llm_issues:
                # Avoid duplicates
                if not any(
                    i.get("field") == issue.get("field") and 
                    i.get("category") == issue.get("category")
                    for i in all_issues
                ):
                    all_issues.append(issue)
            
            # Blend scores
            llm_score = llm_data.get("quality_score", quality_score)
            quality_score = (quality_score + llm_score) / 2
            
            summary = llm_data.get("summary", "Validazione completata")
        else:
            summary = "Validazione rule-based completata (LLM non disponibile)"
        
        # Determine if extraction is complete
        critical_issues = [i for i in all_issues if i.get("severity") == "critical"]
        is_complete = len(critical_issues) == 0
        
        # Build ValidationResult
        validation_result = ValidationResult(
            quality_score=round(quality_score, 2),
            is_complete=is_complete,
            total_issues=len(all_issues),
            critical_issues=len(critical_issues),
            warning_issues=len([i for i in all_issues if i.get("severity") == "warning"]),
            info_issues=len([i for i in all_issues if i.get("severity") == "info"]),
            issues=all_issues,
            summary=summary,
            validated_at=datetime.now()
        )
        
        return AgentResult(
            success=True,
            data=validation_result,
            error=None,
            raw_response=llm_result.raw_response,
            retries_used=llm_result.retries_used
        )
