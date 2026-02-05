"""
Section Writer Agent

Generates individual proposal sections using RAG-based context retrieval
with strict anti-hallucination measures, source citations, and iterative expansion.
"""

import asyncio
import json
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from openai import AsyncOpenAI

from app.services.proposal.schemas import (
    PlannedSection, WrittenSection, SectionContext, KBMatch,
    MissingData, Importance
)
from app.config import get_settings
from app.services.similarity_service import SimilarityService


class SectionWriter:
    """
    Agent 3: Writes proposal sections using RAG with anti-hallucination.
    
    For each section:
    1. Retrieves relevant content from company KB
    2. Generates initial content using retrieved context
    3. Iteratively expands if content is too short
    4. Explicitly cites sources
    5. Marks missing data as placeholders
    """
    
    MODEL = "gpt-4o-mini"
    MAX_CONCURRENT = 5
    MIN_WORD_RATIO = 0.70  # Minimum 70% of target words
    MAX_ITERATIONS = 3  # Maximum expansion iterations
    _client: AsyncOpenAI = None
    
    @classmethod
    def _get_client(cls) -> AsyncOpenAI:
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return cls._client
    
    @classmethod
    async def write_all(
        cls,
        sections: List[PlannedSection],
        company_id: str,
        company_name: str,
        project_name: str
    ) -> List[WrittenSection]:
        """
        Write all sections with controlled concurrency.
        
        Args:
            sections: Planned sections from ProposalPlanner
            company_id: UUID of the company
            company_name: Name of the company for personalization
            project_name: Title of the tender for context
            
        Returns:
            List of written sections with content and sources
        """
        semaphore = asyncio.Semaphore(cls.MAX_CONCURRENT)
        
        async def write_one(section: PlannedSection) -> WrittenSection:
            async with semaphore:
                return await cls.write_section(
                    section=section,
                    company_id=company_id,
                    company_name=company_name,
                    project_name=project_name
                )
        
        tasks = [write_one(section) for section in sections]
        return await asyncio.gather(*tasks)
    
    @classmethod
    async def write_section(
        cls,
        section: PlannedSection,
        company_id: str,
        company_name: str,
        project_name: str
    ) -> WrittenSection:
        """
        Write a single section with RAG context and iterative expansion.
        
        Args:
            section: The planned section to write
            company_id: UUID of the company
            company_name: Company name
            project_name: Tender title for context
            
        Returns:
            WrittenSection with content, sources, and missing data
        """
        start_time = time.time()
        
        # 1. Retrieve context from KB
        context = await cls._retrieve_context(section, company_id)
        
        # 2. Generate initial section content
        content, sources_used, missing_data = await cls._generate_content(
            section=section,
            context=context,
            company_name=company_name,
            project_name=project_name
        )
        
        # 3. Iterative expansion if too short
        word_count = len(content.split())
        min_words = int(section.target_words * cls.MIN_WORD_RATIO)
        iteration = 0
        
        while word_count < min_words and iteration < cls.MAX_ITERATIONS:
            iteration += 1
            content, new_sources, new_missing = await cls._expand_content(
                section=section,
                current_content=content,
                context=context,
                company_name=company_name,
                project_name=project_name,
                target_words=section.target_words,
                current_words=word_count
            )
            sources_used = list(set(sources_used) | set(new_sources))
            missing_data.extend(new_missing)
            word_count = len(content.split())
        
        generation_time = int((time.time() - start_time) * 1000)
        
        return WrittenSection(
            id=section.id,
            title=section.title,
            content=content,
            word_count=word_count,
            sources_used=sources_used,
            source_citations=context.matches,
            missing_data=missing_data,
            requirements_addressed=[req.id for req in section.requirements],
            points_targeted=section.max_points,
            generation_time_ms=generation_time,
            model_used=cls.MODEL
        )
    
    @classmethod
    async def _retrieve_context(
        cls,
        section: PlannedSection,
        company_id: str
    ) -> SectionContext:
        """Retrieve KB content relevant to this section."""
        
        all_matches = []
        seen_ids = set()
        
        # Search for each KB query
        for query in section.kb_queries:
            results = await SimilarityService.search_company_assets(
                company_id=company_id,
                query=query,
                threshold=0.4,  # Lower threshold to get more results
                limit=5
            )
            
            for r in results:
                if r.get("id") not in seen_ids:
                    seen_ids.add(r.get("id"))
                    
                    # Extract source document name from metadata
                    metadata = r.get("metadata", {}) or {}
                    source_doc = metadata.get("source") or metadata.get("filename") or "documento aziendale"
                    
                    all_matches.append(KBMatch(
                        chunk_id=str(r.get("id")),
                        content=r.get("content", ""),
                        similarity=float(r.get("similarity", 0)),
                        source_document=source_doc,
                        metadata=metadata
                    ))
        
        # Also search for requirement descriptions
        for req in section.requirements[:5]:  # Limit to avoid too many searches
            results = await SimilarityService.search_for_requirement(
                company_id=company_id,
                requirement_description=req.description,
                requirement_category=None,
                limit=3
            )
            
            for r in results:
                if r.get("id") not in seen_ids:
                    seen_ids.add(r.get("id"))
                    metadata = r.get("metadata", {}) or {}
                    source_doc = metadata.get("source") or metadata.get("filename") or "documento aziendale"
                    
                    all_matches.append(KBMatch(
                        chunk_id=str(r.get("id")),
                        content=r.get("content", ""),
                        similarity=float(r.get("similarity", 0)),
                        source_document=source_doc,
                        metadata=metadata
                    ))
        
        # Sort by similarity and take top results
        all_matches.sort(key=lambda m: m.similarity, reverse=True)
        top_matches = all_matches[:15]  # Max 15 chunks per section
        
        avg_sim = sum(m.similarity for m in top_matches) / len(top_matches) if top_matches else 0
        
        return SectionContext(
            section_id=section.id,
            matches=top_matches,
            total_matches=len(all_matches),
            avg_similarity=avg_sim
        )
    
    @classmethod
    async def _generate_content(
        cls,
        section: PlannedSection,
        context: SectionContext,
        company_name: str,
        project_name: str
    ) -> Tuple[str, List[str], List[MissingData]]:
        """Generate initial section content using LLM with strict anti-hallucination."""
        
        client = cls._get_client()
        
        # Build context block from KB matches
        context_blocks = []
        sources_used = set()
        
        for match in context.matches:
            source = match.source_document or f"KB-{match.chunk_id[:8]}"
            sources_used.add(source)
            context_blocks.append(f"[{source}]\n{match.content}")
        
        context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else "NESSUN DOCUMENTO AZIENDALE DISPONIBILE"
        
        # Build requirements block
        requirements_text = "\n".join([
            f"- {req.description}" + (f" [max {req.max_points} punti]" if req.max_points else "")
            for req in section.requirements
        ]) if section.requirements else "Nessun requisito specifico"
        
        # System prompt with strict anti-hallucination rules
        system_prompt = """Sei un esperto redattore di offerte tecniche per gare d'appalto italiane.

REGOLE CRITICHE - DEVI SEGUIRLE RIGOROSAMENTE:

1. USA SOLO LE INFORMAZIONI FORNITE nella sezione "DOCUMENTI AZIENDALI DISPONIBILI"
2. Per OGNI affermazione specifica sull'azienda, CITA LA FONTE tra parentesi quadre, es: [Fonte: nome_documento]
3. Se NON hai informazioni per un requisito, scrivi ESATTAMENTE: [DATO MANCANTE: descrizione di cosa serve]
4. NON INVENTARE MAI:
   - Numeri, percentuali, statistiche
   - Date, anni di esperienza
   - Nomi di clienti, progetti, certificazioni
   - Fatturati, numero dipendenti
5. Scrivi in modo professionale, convincente e MOLTO DETTAGLIATO
6. Struttura il contenuto con:
   - Introduzione al tema
   - Paragrafi dettagliati per ogni aspetto principale
   - Sottosezioni dove appropriato (usa ## e ###)
   - Esempi concreti tratti dai documenti
   - Conclusione che riassume i punti di forza
7. Se i documenti non contengono informazioni pertinenti, indicalo chiaramente

IMPORTANTE: Scrivi contenuto SOSTANZIOSO e APPROFONDITO. Devi raggiungere almeno il 70% del target parole.

PUNIZIONE: Se inventi dati non presenti nei documenti, la proposta sarà SQUALIFICATA."""

        user_prompt = f"""SCRIVI LA SEZIONE: "{section.title}"

GARA: {project_name}
AZIENDA: {company_name}
LUNGHEZZA TARGET: circa {section.target_words} parole (MINIMO {int(section.target_words * 0.7)} parole)

{f"ISTRUZIONI SPECIFICHE: {section.instructions}" if section.instructions else ""}

REQUISITI DA SODDISFARE IN QUESTA SEZIONE:
{requirements_text}

DOCUMENTI AZIENDALI DISPONIBILI:
{context_text}

---

Scrivi il contenuto della sezione seguendo rigorosamente le regole. 
Usa i documenti forniti come fonte per ogni affermazione sull'azienda.
Se un requisito non può essere soddisfatto con le informazioni disponibili, usa [DATO MANCANTE: ...].

RICORDA: Devi scrivere ALMENO {int(section.target_words * 0.7)} parole per questa sezione."""

        response = await client.chat.completions.create(
            model=cls.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=6000  # Increased for longer content
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract missing data markers
        missing_data = cls._extract_missing_data(content)
        
        return content, list(sources_used), missing_data
    
    @classmethod
    async def _expand_content(
        cls,
        section: PlannedSection,
        current_content: str,
        context: SectionContext,
        company_name: str,
        project_name: str,
        target_words: int,
        current_words: int
    ) -> Tuple[str, List[str], List[MissingData]]:
        """Expand content that is too short using iterative refinement."""
        
        client = cls._get_client()
        
        # Build context block from KB matches (same as initial)
        context_blocks = []
        sources_used = set()
        
        for match in context.matches:
            source = match.source_document or f"KB-{match.chunk_id[:8]}"
            sources_used.add(source)
            context_blocks.append(f"[{source}]\n{match.content}")
        
        context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else "NESSUN DOCUMENTO AZIENDALE DISPONIBILE"
        
        words_needed = target_words - current_words
        
        system_prompt = """Sei un esperto redattore di offerte tecniche per gare d'appalto italiane.

Il tuo compito è ESPANDERE e APPROFONDIRE una sezione esistente che è troppo corta.

REGOLE CRITICHE:
1. USA SOLO LE INFORMAZIONI dai documenti aziendali forniti
2. Mantieni TUTTO il contenuto esistente
3. AGGIUNGI nuovi paragrafi, dettagli, esempi
4. CITA SEMPRE le fonti [Fonte: nome_documento]
5. NON INVENTARE dati - usa [DATO MANCANTE: ...] se necessario
6. Espandi con:
   - Maggiori dettagli tecnici
   - Esempi concreti da progetti passati
   - Descrizioni più approfondite di metodologie
   - Vantaggi e benefici per il cliente
   - Garanzie e impegni specifici"""

        user_prompt = f"""ESPANDI QUESTA SEZIONE: "{section.title}"

SITUAZIONE ATTUALE:
- Parole attuali: {current_words}
- Parole target: {target_words}
- Parole da aggiungere: almeno {words_needed}

CONTENUTO ATTUALE DA ESPANDERE:
{current_content}

DOCUMENTI AZIENDALI DISPONIBILI (usa questi per aggiungere dettagli):
{context_text}

---

ISTRUZIONI:
1. Riscrivi la sezione COMPLETA mantenendo tutto il contenuto esistente
2. AGGIUNGI almeno {words_needed} parole di nuovo contenuto
3. Approfondisci ogni argomento con più dettagli
4. Usa i documenti per aggiungere esempi concreti e specifiche
5. La risposta deve essere la sezione COMPLETA espansa"""

        response = await client.chat.completions.create(
            model=cls.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,  # Slightly higher for variety
            max_tokens=8000  # More tokens for expanded content
        )
        
        expanded_content = response.choices[0].message.content.strip()
        
        # Extract any new missing data markers
        new_missing = cls._extract_missing_data(expanded_content)
        
        return expanded_content, list(sources_used), new_missing
    
    @classmethod
    def _extract_missing_data(cls, content: str) -> List[MissingData]:
        """Extract [DATO MANCANTE: ...] markers from content."""
        
        missing = []
        pattern = r'\[DATO MANCANTE:\s*([^\]]+)\]'
        matches = re.findall(pattern, content)
        
        for match in matches:
            # Determine importance based on keywords
            importance = Importance.MEDIUM
            match_lower = match.lower()
            if any(kw in match_lower for kw in ["certificazione", "fatturato", "requisito", "obbligatorio"]):
                importance = Importance.CRITICAL
            elif any(kw in match_lower for kw in ["esperienza", "referenza", "progetto"]):
                importance = Importance.HIGH
            
            missing.append(MissingData(
                description=match.strip(),
                importance=importance
            ))
        
        return missing
