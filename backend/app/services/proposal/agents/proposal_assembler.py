"""
Proposal Assembler Agent

Assembles all validated sections into a complete, coherent proposal
with executive summary, table of contents, and transitions.
"""

import json
from typing import List, Dict, Any
from datetime import datetime, timezone
from openai import AsyncOpenAI

from app.services.proposal.schemas import (
    ValidatedSection, TenderProfile, GeneratedProposal,
    ProposalMetadata, MissingDataSummary, MissingData, Importance
)
from app.config import get_settings


class ProposalAssembler:
    """
    Agent 5: Assembles sections into final proposal.
    
    Creates:
    1. Executive summary
    2. Table of contents
    3. Section transitions
    4. Missing data summary
    5. Quality statistics
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
    async def assemble(
        cls,
        sections: List[ValidatedSection],
        tender_profile: TenderProfile,
        company_id: str,
        company_name: str,
        tender_cig: str = None
    ) -> GeneratedProposal:
        """
        Assemble all sections into a final proposal.
        
        Args:
            sections: Validated sections in order
            tender_profile: Tender analysis
            company_id: Company UUID
            company_name: Company name
            tender_cig: Optional tender CIG code
            
        Returns:
            Complete GeneratedProposal
        """
        # 1. Sort sections by order (using section ID as proxy)
        sorted_sections = sorted(sections, key=lambda s: s.section.id)
        
        # 2. Generate executive summary
        executive_summary = await cls._generate_executive_summary(
            sections=sorted_sections,
            tender_profile=tender_profile,
            company_name=company_name
        )
        
        # 3. Build table of contents
        toc = cls._build_table_of_contents(sorted_sections)
        
        # 4. Compile missing data
        missing_summary = cls._compile_missing_data(sorted_sections)
        
        # 5. Calculate statistics
        metadata = cls._calculate_metadata(
            sections=sorted_sections,
            tender_profile=tender_profile,
            company_id=company_id,
            company_name=company_name,
            tender_cig=tender_cig
        )
        
        # 6. Calculate overall quality
        quality_score, quality_notes = cls._calculate_quality(sorted_sections)
        
        return GeneratedProposal(
            metadata=metadata,
            executive_summary=executive_summary,
            table_of_contents=toc,
            sections=sorted_sections,
            tender_profile=tender_profile,
            missing_data_summary=missing_summary,
            overall_quality_score=quality_score,
            quality_notes=quality_notes
        )
    
    @classmethod
    async def _generate_executive_summary(
        cls,
        sections: List[ValidatedSection],
        tender_profile: TenderProfile,
        company_name: str
    ) -> str:
        """Generate an executive summary of the proposal."""
        
        client = cls._get_client()
        
        # Build section summaries
        section_summaries = []
        for s in sections:
            # Take first 200 chars of each section as preview
            preview = s.section.content[:300].replace('\n', ' ')
            section_summaries.append(f"- {s.section.title}: {preview}...")
        
        prompt = f"""Scrivi un EXECUTIVE SUMMARY professionale per questa proposta di gara.

AZIENDA: {company_name}
GARA: {tender_profile.title or "Gara d'appalto"}
ENTE APPALTANTE: {tender_profile.contracting_authority or "N/A"}
SETTORE: {tender_profile.sector.value}
VALORE: {tender_profile.estimated_value or "N/A"} EUR

TEMI CHIAVE DA ENFATIZZARE: {', '.join(tender_profile.key_themes)}

SEZIONI DELLA PROPOSTA:
{chr(10).join(section_summaries)}

L'executive summary deve:
1. Presentare brevemente l'azienda
2. Evidenziare i punti di forza principali
3. Anticipare come l'offerta risponde ai requisiti chiave
4. Essere convincente e professionale
5. Essere lungo circa 300-400 parole

NON inventare dati specifici. Mantieni un tono generale ma convincente."""

        response = await client.chat.completions.create(
            model=cls.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un esperto redattore di proposte di gara. Scrivi in modo professionale e convincente."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )
        
        return response.choices[0].message.content.strip()
    
    @classmethod
    def _build_table_of_contents(
        cls,
        sections: List[ValidatedSection]
    ) -> List[Dict[str, Any]]:
        """Build a structured table of contents."""
        toc = []
        
        for idx, s in enumerate(sections, 1):
            toc.append({
                "number": str(idx),
                "section_id": s.section.id,
                "title": s.section.title,
                "word_count": s.section.word_count,
                "page_estimate": max(1, s.section.word_count // 400)
            })
        
        return toc
    
    @classmethod
    def _compile_missing_data(
        cls,
        sections: List[ValidatedSection]
    ) -> MissingDataSummary:
        """Compile all missing data across sections."""
        all_missing = []
        
        for s in sections:
            for m in s.section.missing_data:
                # Add section context
                all_missing.append(MissingData(
                    description=f"[{s.section.title}] {m.description}",
                    importance=m.importance,
                    suggested_source=m.suggested_source
                ))
        
        # Sort by importance
        importance_order = {
            Importance.CRITICAL: 0,
            Importance.HIGH: 1,
            Importance.MEDIUM: 2,
            Importance.LOW: 3
        }
        all_missing.sort(key=lambda m: importance_order.get(m.importance, 4))
        
        return MissingDataSummary(items=all_missing)
    
    @classmethod
    def _calculate_metadata(
        cls,
        sections: List[ValidatedSection],
        tender_profile: TenderProfile,
        company_id: str,
        company_name: str,
        tender_cig: str = None
    ) -> ProposalMetadata:
        """Calculate proposal metadata and statistics."""
        
        total_words = sum(s.section.word_count for s in sections)
        total_missing = sum(len(s.section.missing_data) for s in sections)
        total_gen_time = sum(s.section.generation_time_ms for s in sections)
        
        # Calculate average source coverage
        source_coverages = [s.quality_report.source_coverage for s in sections]
        avg_source = sum(source_coverages) / len(source_coverages) if source_coverages else 0
        
        # Calculate requirements coverage
        total_reqs = sum(s.quality_report.requirements_total for s in sections)
        covered_reqs = sum(s.quality_report.requirements_covered for s in sections)
        coverage_pct = (covered_reqs / total_reqs * 100) if total_reqs > 0 else 100
        
        return ProposalMetadata(
            generated_at=datetime.now(timezone.utc),
            tender_id=tender_profile.tender_id,
            tender_cig=tender_cig,
            company_id=company_id,
            company_name=company_name,
            total_sections=len(sections),
            total_words=total_words,
            estimated_pages=max(1, total_words // 400),
            total_points_targeted=sum(s.section.points_targeted for s in sections),
            requirements_total=total_reqs,
            requirements_addressed=covered_reqs,
            coverage_percentage=round(coverage_pct, 1),
            avg_source_coverage=round(avg_source, 2),
            total_missing_data=total_missing,
            total_generation_time_ms=total_gen_time
        )
    
    @classmethod
    def _calculate_quality(
        cls,
        sections: List[ValidatedSection]
    ) -> tuple[float, List[str]]:
        """Calculate overall quality score and notes."""
        
        notes = []
        
        # Count issues by severity
        total_errors = sum(s.quality_report.error_count for s in sections)
        total_warnings = sum(s.quality_report.warning_count for s in sections)
        
        # Sections that passed validation
        passed_count = sum(1 for s in sections if s.quality_report.passed)
        
        # Calculate base score
        if not sections:
            return 0, ["Nessuna sezione generata"]
        
        # Start at 100 and deduct
        score = 100
        
        # Deduct for errors (critical)
        score -= total_errors * 10
        
        # Deduct for warnings
        score -= total_warnings * 2
        
        # Bonus for source coverage
        avg_source = sum(s.quality_report.source_coverage for s in sections) / len(sections)
        if avg_source > 0.8:
            score += 5
            notes.append("✓ Ottima copertura delle fonti")
        elif avg_source < 0.3:
            notes.append("⚠ Poche citazioni delle fonti")
        
        # Bonus for coverage
        avg_coverage = sum(s.quality_report.coverage_score for s in sections) / len(sections)
        if avg_coverage > 0.9:
            score += 5
            notes.append("✓ Eccellente copertura dei requisiti")
        elif avg_coverage < 0.7:
            notes.append("⚠ Alcuni requisiti non coperti")
        
        # Cap score
        score = max(0, min(100, score))
        
        # Add summary notes
        if total_errors > 0:
            notes.append(f"✗ {total_errors} errori critici da risolvere")
        if total_warnings > 0:
            notes.append(f"⚠ {total_warnings} avvertimenti da verificare")
        if passed_count == len(sections):
            notes.append("✓ Tutte le sezioni hanno superato la validazione")
        
        return round(score, 1), notes
