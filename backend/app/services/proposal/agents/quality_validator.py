"""
Quality Validator Agent

Validates each proposal section for quality, source coverage,
hallucination detection, and requirement fulfillment.
"""

import asyncio
import json
import re
from typing import List, Dict, Any, Tuple
from openai import AsyncOpenAI

from app.services.proposal.schemas import (
    WrittenSection, PlannedSection, QualityReport, ValidationIssue,
    ValidatedSection
)
from app.config import get_settings


class QualityValidator:
    """
    Agent 4: Validates section quality and detects issues.
    
    Performs multiple checks:
    1. Coverage: Are all requirements addressed?
    2. Sources: Are claims backed by cited sources?
    3. Length: Does it meet target word count?
    4. Consistency: Is it coherent and professional?
    5. Hallucination: Are there unsupported claims?
    """
    
    MODEL = "gpt-4o-mini"
    MAX_CONCURRENT = 5
    _client: AsyncOpenAI = None
    
    @classmethod
    def _get_client(cls) -> AsyncOpenAI:
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return cls._client
    
    @classmethod
    async def validate_all(
        cls,
        written_sections: List[WrittenSection],
        planned_sections: List[PlannedSection]
    ) -> List[ValidatedSection]:
        """
        Validate all sections with controlled concurrency.
        
        Args:
            written_sections: Sections from SectionWriter
            planned_sections: Original plans for comparison
            
        Returns:
            List of validated sections with quality reports
        """
        semaphore = asyncio.Semaphore(cls.MAX_CONCURRENT)
        
        # Create a map of planned sections by ID
        planned_map = {s.id: s for s in planned_sections}
        
        async def validate_one(section: WrittenSection) -> ValidatedSection:
            async with semaphore:
                planned = planned_map.get(section.id)
                return await cls.validate_section(section, planned)
        
        tasks = [validate_one(section) for section in written_sections]
        return await asyncio.gather(*tasks)
    
    @classmethod
    async def validate_section(
        cls,
        section: WrittenSection,
        planned: PlannedSection = None
    ) -> ValidatedSection:
        """
        Validate a single section.
        
        Args:
            section: The written section to validate
            planned: Optional planned section for comparison
            
        Returns:
            ValidatedSection with quality report
        """
        issues = []
        
        # 1. Length check
        length_compliance, length_issues = cls._check_length(section, planned)
        issues.extend(length_issues)
        
        # 2. Source check
        source_coverage, source_issues = cls._check_sources(section)
        issues.extend(source_issues)
        
        # 3. Missing data check
        missing_issues = cls._check_missing_data(section)
        issues.extend(missing_issues)
        
        # 4. Coverage check
        coverage_score, coverage_issues = await cls._check_coverage(section, planned)
        issues.extend(coverage_issues)
        
        # 5. Hallucination check (LLM-based)
        hallucination_issues = await cls._check_hallucinations(section)
        issues.extend(hallucination_issues)
        
        # Calculate if passed
        error_count = sum(1 for i in issues if i.severity == "error")
        passed = error_count == 0
        
        # Count claims with sources
        source_pattern = r'\[Fonte:\s*[^\]]+\]'
        claims_with_sources = len(re.findall(source_pattern, section.content))
        
        # Estimate total claims (sentences with facts)
        sentences = section.content.split('.')
        claims_total = max(claims_with_sources, len([s for s in sentences if len(s.strip()) > 30]))
        
        quality_report = QualityReport(
            section_id=section.id,
            passed=passed,
            coverage_score=coverage_score,
            source_coverage=claims_with_sources / max(claims_total, 1),
            length_compliance=length_compliance,
            issues=issues,
            requirements_covered=len(section.requirements_addressed),
            requirements_total=len(planned.requirements) if planned else 0,
            claims_with_sources=claims_with_sources,
            claims_total=claims_total
        )
        
        return ValidatedSection(
            section=section,
            quality_report=quality_report,
            was_revised=False
        )
    
    @classmethod
    def _check_length(
        cls,
        section: WrittenSection,
        planned: PlannedSection = None
    ) -> Tuple[float, List[ValidationIssue]]:
        """Check if section meets target length."""
        issues = []
        
        if not planned:
            return 1.0, issues
        
        target = planned.target_words
        actual = section.word_count
        ratio = actual / target if target > 0 else 1.0
        
        if ratio < 0.7:
            issues.append(ValidationIssue(
                severity="warning",
                category="length",
                message=f"Sezione troppo corta: {actual} parole vs {target} target ({int(ratio*100)}%)",
                suggestion=f"Aggiungere circa {target - actual} parole di contenuto"
            ))
        elif ratio > 1.5:
            issues.append(ValidationIssue(
                severity="info",
                category="length",
                message=f"Sezione più lunga del target: {actual} parole vs {target} target",
                suggestion="Considerare di sintetizzare se necessario"
            ))
        
        # Normalize compliance to 0-1
        compliance = min(1.0, ratio) if ratio <= 1.0 else max(0.5, 2.0 - ratio)
        return compliance, issues
    
    @classmethod
    def _check_sources(cls, section: WrittenSection) -> Tuple[float, List[ValidationIssue]]:
        """Check source citation coverage."""
        issues = []
        
        # Count source citations
        source_pattern = r'\[Fonte:\s*[^\]]+\]'
        citations = re.findall(source_pattern, section.content)
        
        # Count paragraphs (as proxy for claims)
        paragraphs = [p for p in section.content.split('\n\n') if len(p.strip()) > 50]
        
        if len(paragraphs) > 0 and len(citations) == 0:
            issues.append(ValidationIssue(
                severity="warning",
                category="source",
                message="Nessuna fonte citata nella sezione",
                suggestion="Aggiungere citazioni [Fonte: ...] per le affermazioni sull'azienda"
            ))
        
        coverage = len(citations) / max(len(paragraphs), 1)
        coverage = min(1.0, coverage)  # Cap at 1.0
        
        return coverage, issues
    
    @classmethod
    def _check_missing_data(cls, section: WrittenSection) -> List[ValidationIssue]:
        """Check for missing data markers."""
        issues = []
        
        for missing in section.missing_data:
            severity = "error" if missing.importance.value in ["critical", "high"] else "warning"
            issues.append(ValidationIssue(
                severity=severity,
                category="coverage",
                message=f"Dato mancante: {missing.description}",
                suggestion=f"Fornire: {missing.description}"
            ))
        
        return issues
    
    @classmethod
    async def _check_coverage(
        cls,
        section: WrittenSection,
        planned: PlannedSection = None
    ) -> Tuple[float, List[ValidationIssue]]:
        """Check if requirements are adequately covered."""
        issues = []
        
        if not planned or not planned.requirements:
            return 1.0, issues
        
        # Simple coverage: addressed / total
        total_reqs = len(planned.requirements)
        addressed = len(section.requirements_addressed)
        
        coverage = addressed / total_reqs if total_reqs > 0 else 1.0
        
        if coverage < 0.8:
            issues.append(ValidationIssue(
                severity="warning",
                category="coverage",
                message=f"Copertura requisiti bassa: {addressed}/{total_reqs} ({int(coverage*100)}%)",
                suggestion="Verificare che tutti i requisiti siano affrontati"
            ))
        
        return coverage, issues
    
    @classmethod
    async def _check_hallucinations(cls, section: WrittenSection) -> List[ValidationIssue]:
        """Use LLM to detect potential hallucinations."""
        issues = []
        
        # Skip if section is short
        if section.word_count < 100:
            return issues
        
        client = cls._get_client()
        
        # Build sources context
        sources_text = "\n".join([
            f"- {m.source_document}: {m.content[:200]}..."
            for m in section.source_citations[:10]
        ]) if section.source_citations else "NESSUNA FONTE DISPONIBILE"
        
        prompt = f"""Analizza questa sezione di una proposta di gara e identifica POTENZIALI ALLUCINAZIONI.

Un'allucinazione è un'affermazione specifica sull'azienda (numeri, date, nomi, certificazioni, progetti) 
che NON è supportata dalle fonti disponibili e NON ha una citazione [Fonte: ...].

SEZIONE DA ANALIZZARE:
{section.content}

FONTI DISPONIBILI:
{sources_text}

Rispondi in JSON:
{{
    "potential_hallucinations": [
        {{
            "text": "frase sospetta",
            "reason": "perché sembra inventata"
        }}
    ]
}}

Se non trovi allucinazioni evidenti, rispondi con lista vuota.
Ignora affermazioni generiche, cerca solo fatti specifici non supportati."""

        try:
            response = await client.chat.completions.create(
                model=cls.MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "Sei un validatore di documenti. Identifica affermazioni non supportate."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1000
            )
            
            result = json.loads(response.choices[0].message.content)
            
            for h in result.get("potential_hallucinations", []):
                issues.append(ValidationIssue(
                    severity="warning",
                    category="hallucination",
                    message=f"Possibile dato non verificato: {h.get('text', '')[:100]}",
                    location=h.get("text", "")[:50],
                    suggestion=h.get("reason", "Verificare con documenti aziendali")
                ))
        except Exception as e:
            # Don't fail validation on LLM errors
            pass
        
        return issues
