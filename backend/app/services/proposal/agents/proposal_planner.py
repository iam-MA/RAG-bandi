"""
Proposal Planner Agent

Creates a detailed proposal outline tailored to the specific tender,
determining section structure based on scoring criteria for maximum points.
"""

import json
from typing import List, Dict, Any
from openai import AsyncOpenAI

from app.services.proposal.schemas import (
    TenderProfile, ProposalOutline, PlannedSection, SectionRequirement,
    Importance, Sector, AwardCriteria, ScoringCriterion
)
from app.config import get_settings


class ProposalPlanner:
    """
    Agent 2: Plans the proposal structure based on tender scoring criteria.
    
    Creates an outline where each section maps directly to a scoring criterion
    from the tender, ensuring maximum alignment with evaluation criteria.
    """
    
    MODEL = "gpt-4o-mini"
    _client: AsyncOpenAI = None
    
    @classmethod
    def _get_client(cls) -> AsyncOpenAI:
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return cls._client
    
    @classmethod
    async def plan(
        cls,
        tender_profile: TenderProfile,
        insights: List[Dict[str, Any]]
    ) -> ProposalOutline:
        """
        Create a detailed proposal outline based on tender scoring criteria.
        
        The structure follows this logic:
        1. Presentazione Aziendale (always first)
        2. One section per scoring criterion (ordered by points descending)
        3. Any additional sections for mandatory requirements not in criteria
        
        Args:
            tender_profile: Analyzed tender profile from TenderAnalyzer
            insights: Raw insights from Pipeline 1
            
        Returns:
            ProposalOutline with sections mapped to scoring criteria
        """
        # 1. Build sections from scoring criteria
        criteria_sections = cls._build_sections_from_criteria(
            tender_profile=tender_profile,
            insights=insights
        )
        
        # 2. Enrich sections with LLM for KB queries and instructions
        enriched_sections = await cls._enrich_sections_with_llm(
            sections=criteria_sections,
            tender_profile=tender_profile,
            insights=insights
        )
        
        # 3. Build final outline
        outline = cls._build_outline(enriched_sections, tender_profile)
        
        return outline
    
    @classmethod
    def _build_sections_from_criteria(
        cls,
        tender_profile: TenderProfile,
        insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Build sections directly from scoring criteria.
        Each criterion becomes a dedicated section.
        """
        sections = []
        section_order = 1
        
        # Section 0: Always start with company presentation
        sections.append({
            "id": str(section_order),
            "title": "Presentazione Aziendale",
            "order": section_order,
            "target_words": 1500,
            "max_points": 0,
            "is_intro": True,
            "criterion_id": None,
            "criterion_name": None,
            "criterion_description": "Sezione introduttiva che presenta l'azienda offerente",
            "requirements": [],
            "kb_queries": ["storia aziendale", "missione e visione", "valori aziendali", "certificazioni"],
            "instructions": "Presentare l'azienda in modo professionale, evidenziando punti di forza e differenziatori."
        })
        section_order += 1
        
        # Sort criteria by points (descending) - most important first
        sorted_criteria = sorted(
            tender_profile.scoring_criteria,
            key=lambda c: c.max_points,
            reverse=True
        )
        
        # Filter out criteria with 0 points (informative only) and economic offer
        technical_criteria = [
            c for c in sorted_criteria 
            if c.max_points > 0 and "economic" not in c.name.lower() and "prezzo" not in c.name.lower() and "sconto" not in c.name.lower()
        ]
        
        # Create a section for each scoring criterion
        for criterion in technical_criteria:
            # Find related insights for this criterion
            related_insights = cls._find_related_insights(criterion, insights)
            
            # Calculate target words based on points (more points = more words)
            # Base: 500 words per 5 points, min 800, max 3000
            target_words = max(800, min(3000, int(criterion.max_points * 100)))
            
            # Build requirements from related insights
            requirements = []
            for insight in related_insights:
                req_importance = cls._parse_importance(insight.get("importance", "medium"))
                requirements.append({
                    "id": str(insight.get("id", "")),
                    "description": insight.get("description", insight.get("title", "")),
                    "importance": req_importance,
                    "max_points": criterion.max_points,
                    "source_text": insight.get("source_text"),
                    "insight_id": str(insight.get("id"))
                })
            
            sections.append({
                "id": str(section_order),
                "title": cls._criterion_to_section_title(criterion.name),
                "order": section_order,
                "target_words": target_words,
                "max_points": criterion.max_points,
                "is_intro": False,
                "criterion_id": criterion.id,
                "criterion_name": criterion.name,
                "criterion_description": criterion.description,
                "requirements": requirements,
                "kb_queries": [],  # Will be enriched by LLM
                "instructions": ""  # Will be enriched by LLM
            })
            section_order += 1
        
        return sections
    
    @classmethod
    def _criterion_to_section_title(cls, criterion_name: str) -> str:
        """Convert a criterion name to a proper section title."""
        # If it's already a good title, keep it
        if len(criterion_name) > 5:
            return criterion_name.title() if criterion_name.isupper() else criterion_name
        return criterion_name
    
    @classmethod
    def _find_related_insights(
        cls,
        criterion: ScoringCriterion,
        insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find insights related to a scoring criterion."""
        related = []
        criterion_text = (criterion.name + " " + (criterion.description or "")).lower()
        
        for insight in insights:
            insight_text = (
                insight.get("title", "") + " " + 
                insight.get("description", "") + " " +
                insight.get("source_text", "")
            ).lower()
            
            # Check for keyword overlap
            criterion_words = set(criterion_text.split())
            insight_words = set(insight_text.split())
            
            # Remove common words
            common_words = {"il", "la", "le", "i", "di", "del", "della", "e", "a", "per", "con", "in", "un", "una", "che", "da", "al", "alla", "degli", "delle", "dei"}
            criterion_words -= common_words
            insight_words -= common_words
            
            overlap = criterion_words & insight_words
            if len(overlap) >= 2:  # At least 2 meaningful words in common
                related.append(insight)
        
        return related
    
    @classmethod
    def _parse_importance(cls, value: str) -> Importance:
        """Parse importance string to enum."""
        try:
            return Importance(value.lower())
        except ValueError:
            return Importance.MEDIUM
    
    @classmethod
    async def _enrich_sections_with_llm(
        cls,
        sections: List[Dict[str, Any]],
        tender_profile: TenderProfile,
        insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Use LLM to add KB queries and specific instructions to each section."""
        
        client = cls._get_client()
        
        # Prepare sections summary for prompt
        sections_for_prompt = []
        for s in sections:
            sections_for_prompt.append({
                "id": s["id"],
                "title": s["title"],
                "criterion": s["criterion_name"],
                "description": s["criterion_description"],
                "max_points": s["max_points"]
            })
        
        prompt = f"""Sei un esperto consulente per gare d'appalto italiane.

CONTESTO DEL BANDO:
- Settore: {tender_profile.sector.value}
- Criterio aggiudicazione: {tender_profile.award_criteria.value}
- Temi chiave: {', '.join(tender_profile.key_themes)}

SEZIONI DA ARRICCHIRE (basate sui criteri di punteggio del bando):
{json.dumps(sections_for_prompt, ensure_ascii=False, indent=2)}

Per OGNI sezione, fornisci:
1. kb_queries: 3-5 query specifiche per cercare nella Knowledge Base aziendale
2. instructions: istruzioni dettagliate su COSA scrivere per massimizzare il punteggio

Rispondi in JSON:
{{
    "sections": [
        {{
            "id": "1",
            "kb_queries": ["query1", "query2", "query3"],
            "instructions": "Descrizione dettagliata di cosa scrivere..."
        }}
    ],
    "key_differentiators": ["punto di forza da enfatizzare"],
    "risks_to_address": ["debolezza da mitigare"]
}}

IMPORTANTE:
- Le query KB devono cercare documenti REALI (CV, certificazioni, progetti precedenti, metodologie)
- Le istruzioni devono essere SPECIFICHE per il criterio, non generiche
- Usa la terminologia del bando nelle istruzioni"""

        response = await client.chat.completions.create(
            model=cls.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un consulente esperto di gare d'appalto. Aiuti a massimizzare il punteggio tecnico. Rispondi SOLO in JSON valido."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=4000
        )
        
        try:
            llm_result = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            llm_result = {"sections": [], "key_differentiators": [], "risks_to_address": []}
        
        # Merge LLM output into sections
        llm_sections_by_id = {s["id"]: s for s in llm_result.get("sections", [])}
        
        for section in sections:
            llm_section = llm_sections_by_id.get(section["id"], {})
            if llm_section:
                section["kb_queries"] = llm_section.get("kb_queries", section["kb_queries"])
                section["instructions"] = llm_section.get("instructions", section["instructions"])
        
        # Store differentiators and risks for outline
        cls._last_differentiators = llm_result.get("key_differentiators", [])
        cls._last_risks = llm_result.get("risks_to_address", [])
        
        return sections
    
    @classmethod
    def _build_outline(
        cls,
        sections: List[Dict[str, Any]],
        tender_profile: TenderProfile
    ) -> ProposalOutline:
        """Build the final ProposalOutline from enriched sections."""
        
        planned_sections = []
        total_words = 0
        
        for section_data in sections:
            # Convert requirements dict to SectionRequirement objects
            requirements = []
            for req in section_data.get("requirements", []):
                if isinstance(req, dict):
                    requirements.append(SectionRequirement(
                        id=req.get("id", ""),
                        description=req.get("description", ""),
                        importance=req.get("importance", Importance.MEDIUM),
                        max_points=req.get("max_points"),
                        source_text=req.get("source_text"),
                        insight_id=req.get("insight_id")
                    ))
            
            target_words = section_data.get("target_words", 1000)
            total_words += target_words
            
            # Add criterion reference to instructions if available
            instructions = section_data.get("instructions", "")
            if section_data.get("criterion_name") and section_data.get("criterion_description"):
                criterion_ref = f"\n\n[CRITERIO DI VALUTAZIONE: {section_data['criterion_name']} - {section_data['max_points']} punti]\n{section_data['criterion_description']}"
                instructions = criterion_ref + "\n\n" + instructions
            
            planned_sections.append(PlannedSection(
                id=section_data.get("id", ""),
                title=section_data.get("title", ""),
                order=section_data.get("order", 0),
                target_words=target_words,
                requirements=requirements,
                kb_queries=section_data.get("kb_queries", []),
                max_points=section_data.get("max_points", 0),
                instructions=instructions
            ))
        
        # Estimate pages (approx 400 words per page)
        estimated_pages = max(1, total_words // 400)
        
        return ProposalOutline(
            sections=planned_sections,
            total_target_words=total_words,
            estimated_pages=estimated_pages,
            key_differentiators=getattr(cls, '_last_differentiators', []),
            risks_to_address=getattr(cls, '_last_risks', [])
        )
