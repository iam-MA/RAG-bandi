"""
Aggregator Agent: Combines all extracted insights into a unified result.
Resolves duplicates and inconsistencies.
"""
from typing import List, Dict, Any
from openai import AsyncOpenAI
from collections import defaultdict
import re

from .base_agent import BaseAgent, AgentResult
from .agent_schemas import (
    Insight, InsightCategory, ExtractionResult, ExtractionMetadata,
    TenderSummary, ActionSummary, DocumentProfile, ExtractionPlan
)
from datetime import datetime


class AggregatorAgent(BaseAgent):
    """
    Aggregator Agent: Final step before validation.
    
    Responsibility:
    - Collect all insights from executor agents
    - Remove duplicates
    - Resolve conflicts
    - Create summary statistics
    - Produce final ExtractionResult
    """
    
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        super().__init__(client, model)
    
    def _deduplicate_insights(self, all_insights: List[Dict]) -> List[Dict]:
        """
        Remove duplicate insights based on similar titles/content.
        Simple deduplication - can be enhanced with LLM later.
        """
        seen_titles = set()
        unique_insights = []
        
        for insight in all_insights:
            title = insight.get("finding", {}).get("title", "").lower().strip()
            
            # Simple title-based deduplication
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_insights.append(insight)
            elif not title:
                # Keep insights without titles
                unique_insights.append(insight)
        
        return unique_insights
    
    def _create_tender_summary(
        self, 
        insights: List[Dict],
        profile: DocumentProfile
    ) -> TenderSummary:
        """Extract tender summary from general info insights."""
        
        summary = TenderSummary(
            title="Bando di gara",  # Default
            sector=profile.sector
        )
        
        # Find specific insights to populate summary
        for insight in insights:
            insight_type = insight.get("type", "")
            finding = insight.get("finding", {})
            
            if insight_type == "oggetto_appalto":
                summary.title = finding.get("title", summary.title)
            elif insight_type == "ente_appaltante":
                summary.contracting_authority = finding.get("description")
            elif insight_type == "valore_gara":
                # Robust value extraction - look for Euro/€ patterns
                desc = finding.get("description", "")
                source = finding.get("source_text", desc)
                combined = f"{desc} {source}"
                
                # Pattern 1: "Euro X.XXX.XXX,XX" or "Euro X.XXX,XX" (Italian format)
                # Pattern 2: "€ X.XXX.XXX,XX" or "€X.XXX,XX"
                # Pattern 3: "€ X,XXX,XXX.XX" (English format with €)
                patterns = [
                    r'[Ee]uro\s*([\d.]+)[,.](\\d{2})',  # Euro 810.000,00
                    r'€\s*([\d.]+)[,.](\\d{2})',        # € 810.000,00
                    r'[Ee]uro\s*([\d,]+)\.(\\d{2})',    # Euro 810,000.00
                    r'€\s*([\d,]+)\.(\\d{2})',          # € 810,000.00
                ]
                
                value_found = None
                for pattern in patterns:
                    match = re.search(pattern, combined)
                    if match:
                        # Parse the matched value
                        int_part = match.group(1).replace(".", "").replace(",", "")
                        dec_part = match.group(2)
                        try:
                            value_found = float(f"{int_part}.{dec_part}")
                            # Sanity check: tender values should be >= 1000
                            if value_found >= 1000:
                                summary.value = value_found
                                break
                        except:
                            pass
                
                # Fallback: look for large numbers (>= 10000) near keywords
                if summary.value is None:
                    # Look for numbers >= 10000 that appear near "importo", "valore", "base"
                    fallback_match = re.search(
                        r'(?:importo|valore|base)[^\d]{0,30}([\d.]+)[,.](\\d{2})',
                        combined.lower()
                    )
                    if fallback_match:
                        int_part = fallback_match.group(1).replace(".", "")
                        dec_part = fallback_match.group(2)
                        try:
                            value_found = float(f"{int_part}.{dec_part}")
                            if value_found >= 10000:
                                summary.value = value_found
                        except:
                            pass
                        
            elif insight_type == "durata_contratto":
                desc = finding.get("description", "")
                match = re.search(r'(\d+)\s*(ann|mes)', desc.lower())
                if match:
                    num = int(match.group(1))
                    unit = match.group(2)
                    summary.duration_months = num * 12 if "ann" in unit else num
            elif insight_type == "procedura_tipo":
                summary.procedure = finding.get("description")
        
        # Fallback for contracting authority: search in all insights if not found
        if summary.contracting_authority is None:
            for insight in insights:
                if insight.get("category") == "tender_overview":
                    desc = insight.get("finding", {}).get("description", "")
                    # Look for common patterns indicating contracting authority
                    ente_patterns = [
                        r'([A-Z][A-Za-z\s]+(?:S\.?p\.?A\.?|S\.?r\.?l\.?|S\.?c\.?a\.?r\.?l\.?))',  # Company names
                        r'(Comune di [A-Za-z]+)',
                        r'(Provincia di [A-Za-z]+)',
                        r'(Regione [A-Za-z]+)',
                        r'(Università [A-Za-z\s]+)',
                        r'(Azienda [A-Za-z\s]+)',
                    ]
                    for pattern in ente_patterns:
                        match = re.search(pattern, desc)
                        if match:
                            summary.contracting_authority = match.group(1).strip()
                            break
                if summary.contracting_authority:
                    break
        
        return summary
    
    def _create_action_summary(self, insights: List[Dict]) -> ActionSummary:
        """Create action summary from all insights."""
        
        summary = ActionSummary()
        key_focus = []
        
        for insight in insights:
            category = insight.get("category", "")
            impact = insight.get("impact", {})
            importance = impact.get("importance", "")
            finding = insight.get("finding", {})
            
            # Count critical requirements
            if category == "requisito_partecipazione" and importance == "critical":
                summary.critical_requirements += 1
                key_focus.append(finding.get("title", ""))
            
            # Count documents
            if category == "documento_richiesto":
                summary.documents_to_prepare += 1
            
            # Sum potential points
            if category == "criterio_punteggio":
                points = impact.get("points_available")
                if points:
                    try:
                        summary.potential_extra_points += int(points)
                    except:
                        pass
        
        # Limit key focus areas
        summary.key_focus_areas = key_focus[:5]
        
        return summary
    
    def aggregate(
        self,
        executor_results: Dict[str, List[Dict]],
        profile: DocumentProfile,
        plan: ExtractionPlan,
        document_name: str = "document.md"
    ) -> ExtractionResult:
        """
        Aggregate all executor results into final output.
        
        Args:
            executor_results: Dict mapping agent_type to list of insights
            profile: Document profile from analyzer
            plan: Extraction plan from planner
            document_name: Name of source document
            
        Returns:
            Complete ExtractionResult
        """
        # Collect all insights
        all_insights = []
        for agent_type, insights in executor_results.items():
            for insight in insights:
                # Add category based on agent type
                if "category" not in insight:
                    # Map agent type to category
                    category_map = {
                        "GeneralInfoExtractor": "tender_overview",
                        "RequirementsExtractor": "requisito_partecipazione",
                        "ScoringExtractor": "criterio_punteggio",
                        "DocumentsExtractor": "documento_richiesto",
                        "DeadlinesExtractor": "scadenza",
                        "TechnicalSpecsExtractor": "specifica_tecnica",
                    }
                    insight["category"] = category_map.get(agent_type, "tender_overview")
                
                all_insights.append(insight)
        
        # Deduplicate
        unique_insights = self._deduplicate_insights(all_insights)
        
        # Calculate confidence
        total_insights = len(unique_insights)
        confident_insights = sum(
            1 for i in unique_insights 
            if i.get("finding", {}).get("source_text")
        )
        confidence = confident_insights / max(total_insights, 1)
        
        # Create summaries
        tender_summary = self._create_tender_summary(unique_insights, profile)
        action_summary = self._create_action_summary(unique_insights)
        
        # Build final result
        result = ExtractionResult(
            extraction_metadata=ExtractionMetadata(
                document_name=document_name,
                extraction_date=datetime.now(),
                pipeline_version="2.0",
                confidence_overall=round(confidence, 2),
                warnings=[]
            ),
            tender_summary=tender_summary,
            insights=unique_insights,  # Will be converted to Insight objects
            action_summary=action_summary,
            document_profile=profile,
            extraction_plan=plan
        )
        
        return result
