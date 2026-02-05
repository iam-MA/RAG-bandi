"""
Proposal Orchestrator

Main entry point for Pipeline 2 - Professional Proposal Generation.
Coordinates all agents to generate a complete proposal.
"""

import asyncio
import time
from typing import Tuple, List, Dict, Any, Optional

from app.services.proposal.schemas import GeneratedProposal, TenderProfile, ProposalOutline
from app.services.proposal.agents import (
    TenderAnalyzer,
    ProposalPlanner,
    SectionWriter,
    QualityValidator,
    ProposalAssembler
)
from app.services.supabase_client import SupabaseService


class ProposalOrchestrator:
    """
    Main orchestrator for the proposal generation pipeline.
    
    Coordinates the 5-agent system:
    1. TenderAnalyzer - Analyze tender type and requirements
    2. ProposalPlanner - Create proposal structure
    3. SectionWriter - Write sections with RAG
    4. QualityValidator - Validate and detect hallucinations
    5. ProposalAssembler - Assemble final proposal
    """
    
    @classmethod
    async def generate_proposal(
        cls,
        project_id: str,
        verbose: bool = False
    ) -> Tuple[bool, Optional[GeneratedProposal], List[str]]:
        """
        Generate a complete proposal for a project.
        
        Args:
            project_id: UUID of the project
            verbose: Print progress messages (for debugging)
            
        Returns:
            Tuple of (success, proposal, errors)
        """
        start_time = time.time()
        errors = []
        db = SupabaseService.get_client()
        
        def log(msg: str):
            if verbose:
                print(msg)
        
        try:
            # =====================================================
            # Load project data
            # =====================================================
            log("\n" + "="*60)
            log("  Pipeline 2 - Professional Proposal Generation")
            log("="*60)
            
            log(f"\n[0/5] Loading project data...")
            
            project = await cls._load_project(project_id)
            if not project:
                return False, None, [f"Project {project_id} not found"]
            
            company_id = project["company_id"]
            tender_id = project["tender_id"]
            project_name = project.get("name", "Proposta di Gara")
            
            # Get company info
            company_result = db.table("companies").select("company_name").eq("id", company_id).execute()
            company_name = company_result.data[0].get("company_name", "L'Azienda") if company_result.data else "L'Azienda"
            
            # Get tender info (CIG only, title is now in project)
            tender_result = db.table("tenders").select("cig").eq("id", tender_id).execute()
            tender_cig = tender_result.data[0].get("cig", "") if tender_result.data else ""
            
            log(f"      Company: {company_name}")
            log(f"      Project: {project_name}")
            log(f"      CIG: {tender_cig}")
            
            # Update status
            db.table("projects").update({"status": "generating"}).eq("id", project_id).execute()
            
            # =====================================================
            # Step 1: Tender Analysis
            # =====================================================
            log(f"\n[1/5] Analyzing tender...")
            
            tender_profile = await TenderAnalyzer.analyze(tender_id)
            
            log(f"      Type: {tender_profile.tender_type.value}")
            log(f"      Sector: {tender_profile.sector.value}")
            log(f"      Award criteria: {tender_profile.award_criteria.value}")
            log(f"      Technical weight: {tender_profile.technical_weight}%")
            log(f"      Scoring criteria: {len(tender_profile.scoring_criteria)}")
            log(f"      Critical requirements: {len(tender_profile.critical_requirements)}")
            log(f"      Key themes: {', '.join(tender_profile.key_themes[:3])}...")
            
            # =====================================================
            # Step 2: Proposal Planning
            # =====================================================
            log(f"\n[2/5] Planning proposal structure...")
            
            # Load insights for the planner
            insights = await cls._load_insights(tender_id)
            
            outline = await ProposalPlanner.plan(tender_profile, insights)
            
            log(f"      Sections planned: {len(outline.sections)}")
            log(f"      Target words: {outline.total_target_words:,}")
            log(f"      Estimated pages: {outline.estimated_pages}")
            log(f"      Key differentiators: {len(outline.key_differentiators)}")
            
            for section in outline.sections:
                log(f"        - {section.title} ({section.target_words} words)")
            
            # =====================================================
            # Step 3: Section Writing
            # =====================================================
            log(f"\n[3/5] Writing {len(outline.sections)} sections...")
            log(f"      (This may take a few minutes...)")
            
            written_sections = await SectionWriter.write_all(
                sections=outline.sections,
                company_id=company_id,
                company_name=company_name,
                project_name=project_name
            )
            
            total_words = sum(s.word_count for s in written_sections)
            total_missing = sum(len(s.missing_data) for s in written_sections)
            
            log(f"      Total words written: {total_words:,}")
            log(f"      Sources cited: {sum(len(s.sources_used) for s in written_sections)}")
            log(f"      Missing data markers: {total_missing}")
            
            # =====================================================
            # Step 4: Quality Validation
            # =====================================================
            log(f"\n[4/5] Validating sections...")
            
            validated_sections = await QualityValidator.validate_all(
                written_sections=written_sections,
                planned_sections=outline.sections
            )
            
            passed = sum(1 for s in validated_sections if s.quality_report.passed)
            total_errors = sum(s.quality_report.error_count for s in validated_sections)
            total_warnings = sum(s.quality_report.warning_count for s in validated_sections)
            
            log(f"      Sections passed: {passed}/{len(validated_sections)}")
            log(f"      Errors: {total_errors}")
            log(f"      Warnings: {total_warnings}")
            
            # =====================================================
            # Step 5: Assembly
            # =====================================================
            log(f"\n[5/5] Assembling final proposal...")
            
            proposal = await ProposalAssembler.assemble(
                sections=validated_sections,
                tender_profile=tender_profile,
                company_id=company_id,
                company_name=company_name,
                tender_cig=tender_cig
            )
            
            log(f"      Total pages: {proposal.metadata.estimated_pages}")
            log(f"      Quality score: {proposal.overall_quality_score}/100")
            log(f"      Missing data items: {proposal.missing_data_summary.critical_count} critical, {proposal.missing_data_summary.high_count} high")
            
            # =====================================================
            # Save to database
            # =====================================================
            log(f"\n      Saving to database...")
            
            try:
                # Convert proposal to JSON for storage
                proposal_json = proposal.to_json()
                log(f"      Proposal JSON size: {len(str(proposal_json))} chars")
                
                # Save to database
                save_result = db.table("projects").update({
                    "status": "ready",
                    "generated_response": proposal_json
                }).eq("id", project_id).execute()
                
                if save_result.data:
                    log(f"      ✅ Saved to database successfully")
                else:
                    log(f"      ⚠️ Save returned no data: {save_result}")
                    
            except Exception as save_error:
                log(f"      ❌ Error saving to database: {save_error}")
                import traceback
                traceback.print_exc()
                # Don't fail the whole operation, just log the error
                errors.append(f"Database save error: {str(save_error)}")
            
            elapsed = time.time() - start_time
            
            log(f"\n{'='*60}")
            log(f"  ✅ PROPOSAL GENERATED SUCCESSFULLY")
            log(f"  Time: {elapsed:.1f} seconds")
            log(f"  Words: {proposal.metadata.total_words:,}")
            log(f"  Pages: {proposal.metadata.estimated_pages}")
            log(f"  Quality: {proposal.overall_quality_score}/100")
            log(f"{'='*60}\n")
            
            return True, proposal, errors
            
        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {str(e)}"
            errors.append(error_msg)
            
            if verbose:
                print(f"\n❌ ERROR: {error_msg}")
                traceback.print_exc()
            
            # Update status to error
            try:
                db.table("projects").update({"status": "error"}).eq("id", project_id).execute()
            except:
                pass
            
            return False, None, errors
    
    @classmethod
    def _generate_markdown(cls, proposal: GeneratedProposal) -> str:
        """Generate a Markdown version of the proposal."""
        lines = []
        
        lines.append(f"# {proposal.tender_profile.title or 'Proposta di Gara'}\n")
        lines.append(f"**Azienda:** {proposal.metadata.company_name}")
        lines.append(f"**CIG:** {proposal.metadata.tender_cig}")
        lines.append(f"**Data generazione:** {proposal.metadata.generated_at}")
        lines.append(f"**Qualità:** {proposal.overall_quality_score}/100\n")
        lines.append("---\n")
        
        # Executive Summary
        if proposal.executive_summary:
            lines.append("## Executive Summary\n")
            lines.append(proposal.executive_summary)
            lines.append("\n---\n")
        
        # Table of Contents
        lines.append("## Indice\n")
        for item in proposal.table_of_contents:
            lines.append(f"{item['number']}. {item['title']} ({item['word_count']} parole)")
        lines.append("\n---\n")
        
        # Sections
        for section in proposal.sections:
            lines.append(f"## {section.section.title}\n")
            lines.append(section.section.content)
            lines.append("\n")
            if section.quality_report.issues:
                lines.append(f"*Validazione: {len(section.quality_report.issues)} note*")
            lines.append("\n---\n")
        
        # Missing Data Summary
        if proposal.missing_data_summary.items:
            lines.append("## ⚠️ Dati Mancanti\n")
            lines.append("I seguenti dati non sono presenti nella Knowledge Base e devono essere forniti:\n")
            for item in proposal.missing_data_summary.items:
                lines.append(f"- **[{item.importance.value.upper()}]** {item.description}")
        
        return "\n".join(lines)
    
    @classmethod
    async def _load_project(cls, project_id: str) -> Dict[str, Any]:
        """Load project data from database."""
        db = SupabaseService.get_client()
        result = db.table("projects").select("*").eq("id", project_id).execute()
        return result.data[0] if result.data else None
    
    @classmethod
    async def _load_insights(cls, tender_id: str) -> List[Dict[str, Any]]:
        """Load all insights for a tender."""
        db = SupabaseService.get_client()
        
        # Get extraction_id first
        extraction_result = db.table("tender_extractions").select("id").eq("tender_id", tender_id).execute()
        if not extraction_result.data:
            return []
        
        extraction_id = extraction_result.data[0]["id"]
        
        # Get insights
        insights_result = db.table("tender_insights").select("*").eq("extraction_id", extraction_id).execute()
        return insights_result.data or []


# Convenience function for direct usage
async def generate_proposal(project_id: str, verbose: bool = False):
    """Generate a proposal for the given project ID."""
    return await ProposalOrchestrator.generate_proposal(project_id, verbose)
