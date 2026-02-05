"""
Tender Analyzer Agent

Analyzes tender insights to create a comprehensive profile that guides
the proposal generation process. Determines tender type, sector, scoring
criteria, and critical requirements.
"""

import json
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from app.services.proposal.schemas import (
    TenderProfile, TenderType, Sector, AwardCriteria, Complexity,
    ScoringCriterion, CriticalRequirement, Importance
)
from app.config import get_settings
from app.services.supabase_client import SupabaseService


class TenderAnalyzer:
    """
    Agent 1: Analyzes tender insights to create a TenderProfile.
    
    This profile guides all subsequent agents in generating an appropriate
    proposal tailored to the specific tender type and requirements.
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
    async def analyze(cls, tender_id: str) -> TenderProfile:
        """
        Analyze a tender and create a comprehensive profile.
        
        Args:
            tender_id: UUID of the tender to analyze
            
        Returns:
            TenderProfile with all analyzed information
        """
        # 1. Load tender data
        tender_data = await cls._load_tender_data(tender_id)
        extraction_data = await cls._load_extraction_data(tender_id)
        insights = await cls._load_insights(tender_id)
        
        # 2. Analyze with LLM
        profile_data = await cls._analyze_with_llm(
            tender_data=tender_data,
            extraction_data=extraction_data,
            insights=insights
        )
        
        # 3. Build TenderProfile
        profile = cls._build_profile(
            tender_id=tender_id,
            tender_data=tender_data,
            extraction_data=extraction_data,
            insights=insights,
            llm_analysis=profile_data
        )
        
        return profile
    
    @classmethod
    async def _load_tender_data(cls, tender_id: str) -> Dict[str, Any]:
        """Load basic tender information."""
        db = SupabaseService.get_client()
        result = db.table("tenders").select("*").eq("id", tender_id).execute()
        return result.data[0] if result.data else {}
    
    @classmethod
    async def _load_extraction_data(cls, tender_id: str) -> Dict[str, Any]:
        """Load extraction data from Pipeline 1."""
        db = SupabaseService.get_client()
        result = db.table("tender_extractions").select("*").eq("tender_id", tender_id).execute()
        return result.data[0] if result.data else {}
    
    @classmethod
    async def _load_insights(cls, tender_id: str) -> List[Dict[str, Any]]:
        """Load all insights for the tender."""
        db = SupabaseService.get_client()
        
        # First get extraction_id
        extraction = await cls._load_extraction_data(tender_id)
        if not extraction:
            return []
        
        extraction_id = extraction.get("id")
        result = db.table("tender_insights").select("*").eq("extraction_id", extraction_id).execute()
        return result.data or []
    
    @classmethod
    async def _analyze_with_llm(
        cls,
        tender_data: Dict[str, Any],
        extraction_data: Dict[str, Any],
        insights: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Use LLM to analyze and extract structured information."""
        
        client = cls._get_client()
        
        # Prepare context
        tender_summary = extraction_data.get("tender_summary", {})
        if isinstance(tender_summary, str):
            try:
                tender_summary = json.loads(tender_summary)
            except:
                tender_summary = {}
        
        # Group insights by category
        insights_by_category = {}
        for insight in insights:
            cat = insight.get("category", "altro")
            if cat not in insights_by_category:
                insights_by_category[cat] = []
            insights_by_category[cat].append({
                "title": insight.get("title"),
                "description": insight.get("description"),
                "importance": insight.get("importance"),
                "score_points": insight.get("score_points"),
                "type": insight.get("type")
            })
        
        prompt = f"""Analizza questo bando di gara italiano e fornisci un'analisi strutturata.

DATI DEL BANDO:
- Titolo: {tender_data.get('title', 'N/A')}
- CIG: {tender_data.get('cig', 'N/A')}
- Oggetto: {extraction_data.get('title', 'N/A')}
- Ente appaltante: {extraction_data.get('contracting_authority', 'N/A')}
- Valore stimato: {extraction_data.get('value', 'N/A')} EUR
- Tipo procedura: {extraction_data.get('procedure_type', 'N/A')}
- Settore: {extraction_data.get('sector', 'N/A')}
- Durata: {extraction_data.get('duration_months', 'N/A')} mesi

INSIGHTS ESTRATTI PER CATEGORIA:
{json.dumps(insights_by_category, ensure_ascii=False, indent=2)}

Rispondi in JSON con questa struttura esatta:
{{
    "tender_type": "procedura_aperta|procedura_ristretta|procedura_negoziata|affidamento_diretto|altro",
    "sector": "servizi_pulizia|software|edilizia|sanita|trasporti|formazione|consulenza|forniture|altro",
    "award_criteria": "offerta_economicamente_piu_vantaggiosa|prezzo_piu_basso|costo_fisso",
    "technical_weight": <peso offerta tecnica 0-100>,
    "economic_weight": <peso offerta economica 0-100>,
    "estimated_complexity": "low|medium|high",
    "key_themes": ["tema1", "tema2", ...],
    "scoring_criteria": [
        {{
            "id": "CRIT-001",
            "name": "nome criterio",
            "description": "descrizione",
            "max_points": <punti>
        }}
    ],
    "critical_requirements": [
        {{
            "id": "REQ-001",
            "category": "categoria",
            "description": "descrizione requisito",
            "is_mandatory": true/false
        }}
    ]
}}

IMPORTANTE:
- Estrai i criteri di punteggio dagli insights "criterio_punteggio"
- Identifica i requisiti critici dagli insights con importance="critical" o "high"
- Stima i pesi tecnico/economico in base al tipo di gara se non espliciti
- I key_themes sono i temi principali da enfatizzare nella proposta"""

        response = await client.chat.completions.create(
            model=cls.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un esperto analista di gare d'appalto italiane. Rispondi SOLO in JSON valido."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            return {}
    
    @classmethod
    def _build_profile(
        cls,
        tender_id: str,
        tender_data: Dict[str, Any],
        extraction_data: Dict[str, Any],
        insights: List[Dict[str, Any]],
        llm_analysis: Dict[str, Any]
    ) -> TenderProfile:
        """Build the final TenderProfile from all data sources."""
        
        # Parse tender type
        tender_type_str = llm_analysis.get("tender_type", "altro")
        try:
            tender_type = TenderType(tender_type_str)
        except ValueError:
            tender_type = TenderType.ALTRO
        
        # Parse sector
        sector_str = llm_analysis.get("sector", "altro")
        try:
            sector = Sector(sector_str)
        except ValueError:
            sector = Sector.ALTRO
        
        # Parse award criteria
        award_str = llm_analysis.get("award_criteria", "offerta_economicamente_piu_vantaggiosa")
        try:
            award_criteria = AwardCriteria(award_str)
        except ValueError:
            award_criteria = AwardCriteria.OEPV
        
        # Parse complexity
        complexity_str = llm_analysis.get("estimated_complexity", "medium")
        try:
            complexity = Complexity(complexity_str)
        except ValueError:
            complexity = Complexity.MEDIUM
        
        # Build scoring criteria
        scoring_criteria = []
        for crit in llm_analysis.get("scoring_criteria", []):
            scoring_criteria.append(ScoringCriterion(
                id=crit.get("id", f"CRIT-{len(scoring_criteria)+1:03d}"),
                name=crit.get("name", ""),
                description=crit.get("description", ""),
                max_points=float(crit.get("max_points", 0))
            ))
        
        # Build critical requirements
        critical_requirements = []
        for req in llm_analysis.get("critical_requirements", []):
            importance_str = req.get("importance", "high")
            try:
                importance = Importance(importance_str)
            except ValueError:
                importance = Importance.HIGH
            
            critical_requirements.append(CriticalRequirement(
                id=req.get("id", f"REQ-{len(critical_requirements)+1:03d}"),
                category=req.get("category", "generale"),
                description=req.get("description", ""),
                importance=importance,
                is_mandatory=req.get("is_mandatory", True)
            ))
        
        # Calculate total technical points
        total_tech_points = sum(c.max_points for c in scoring_criteria)
        
        return TenderProfile(
            tender_id=tender_id,
            tender_type=tender_type,
            sector=sector,
            award_criteria=award_criteria,
            technical_weight=float(llm_analysis.get("technical_weight", 70)),
            economic_weight=float(llm_analysis.get("economic_weight", 30)),
            critical_requirements=critical_requirements,
            scoring_criteria=scoring_criteria,
            total_technical_points=total_tech_points,
            estimated_complexity=complexity,
            key_themes=llm_analysis.get("key_themes", []),
            title=extraction_data.get("title"),
            contracting_authority=extraction_data.get("contracting_authority"),
            estimated_value=extraction_data.get("value"),
            duration_months=extraction_data.get("duration_months")
        )
