"""
Analysis Service
Orchestrates AI analysis of tender documents using multi-agent pipeline.

New Pipeline (v2.0):
1. Analyzer Agent - Understand document structure
2. Planner Agent - Create extraction plan  
3. Executor Agents - Extract specific information (parallel)
4. Aggregator Agent - Combine and deduplicate insights
5. Validator Agent - Quality check
"""

import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
from uuid import UUID

from app.services.supabase_client import SupabaseService
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.agents import ExtractionResult, ValidationResult


class AnalysisService:
    """
    Service for AI analysis of tender documents.
    
    Uses the new multi-agent pipeline and saves results to:
    - tender_extractions (main extraction data)
    - tender_insights (individual insights for querying)
    """
    
    @classmethod
    async def analyze_tender(cls, cig: str) -> Tuple[int, int, List[str], Dict[str, Any]]:
        """
        Run the full analysis pipeline on a tender.
        
        Args:
            cig: Codice Identificativo Gara
            
        Returns:
            Tuple of (insights_found, docs_analyzed, errors, analysis_summary)
        """
        db = SupabaseService.get_client()
        
        # Get tender
        tender_result = db.table("tenders").select("id").eq("cig", cig).execute()
        
        if not tender_result.data:
            return 0, 0, [f"Tender with CIG '{cig}' not found"], {}
        
        tender_id = tender_result.data[0]["id"]
        
        # Delete existing extractions for this tender (fresh analysis)
        try:
            db.table("tender_extractions").delete().eq("tender_id", tender_id).execute()
        except Exception as e:
            print(f"Warning: Could not delete existing extractions: {e}")
        
        # Get all documents with extracted text
        docs_result = db.table("tender_documents").select(
            "id, name, extracted_text"
        ).eq("tender_id", tender_id).execute()
        
        if not docs_result.data:
            return 0, 0, ["No documents found for this tender"], {}
        
        total_insights = 0
        docs_analyzed = 0
        errors = []
        all_insights = []
        analysis_details = {
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": "2.0",
            "documents": []
        }
        
        # Initialize pipeline
        pipeline = AnalysisPipeline()
        
        # Process each document
        for doc in docs_result.data:
            if not doc.get("extracted_text"):
                errors.append(f"{doc['name']}: No extracted text available")
                continue
            
            doc_stats = {
                "filename": doc["name"],
                "insights_found": 0,
                "quality_score": 0,
                "is_complete": False
            }
            
            try:
                print(f"  Processing {doc['name']}...")
                
                # Run the pipeline
                extraction_result, validation_result = await pipeline.run(
                    document=doc["extracted_text"],
                    document_name=doc["name"]
                )
                
                doc_stats["insights_found"] = len(extraction_result.insights)
                doc_stats["quality_score"] = validation_result.quality_score
                doc_stats["is_complete"] = validation_result.is_complete
                
                # Save to database
                await cls._save_extraction_to_db(
                    db=db,
                    tender_id=tender_id,
                    extraction_result=extraction_result,
                    validation_result=validation_result
                )
                
                total_insights += len(extraction_result.insights)
                all_insights.extend(extraction_result.insights)
                docs_analyzed += 1
                analysis_details["documents"].append(doc_stats)
                
                print(f"  ✓ Saved {len(extraction_result.insights)} insights for {doc['name']}")
                
            except Exception as e:
                errors.append(f"{doc['name']}: {str(e)}")
                print(f"  ✗ Error processing {doc['name']}: {e}")
        
        # Update tender status
        try:
            db.table("tenders").update({
                "status": "ready" if not errors else "analyzing",
                "analysis": analysis_details
            }).eq("id", tender_id).execute()
        except Exception as e:
            errors.append(f"Failed to update tender status: {str(e)}")
        
        analysis_summary = {
            "total_insights": total_insights,
            "documents_analyzed": docs_analyzed,
            "pipeline_version": "2.0",
            "details": analysis_details
        }
        
        return total_insights, docs_analyzed, errors, analysis_summary
    
    @classmethod
    async def _save_extraction_to_db(
        cls,
        db,
        tender_id: str,
        extraction_result: ExtractionResult,
        validation_result: ValidationResult
    ) -> None:
        """
        Save extraction results to the database.
        
        Args:
            db: Supabase client
            tender_id: UUID of the tender
            extraction_result: Result from aggregator
            validation_result: Result from validator
        """
        summary = extraction_result.tender_summary
        action_summary = extraction_result.action_summary
        
        # Prepare tender_extractions record
        extraction_record = {
            "tender_id": tender_id,
            "title": summary.title,
            "contracting_authority": summary.contracting_authority,
            "value": summary.value,
            "currency": "EUR",
            "deadline": None,  # TODO: Extract from deadline insights
            "sector": summary.sector,
            "procedure_type": summary.procedure,
            "duration_months": summary.duration_months,
            "quality_score": validation_result.quality_score * 100,  # Convert to 0-100
            "full_result": extraction_result.model_dump(mode="json"),
            "tender_summary": summary.model_dump(mode="json"),
            "action_summary": action_summary.model_dump(mode="json"),
            "document_profile": extraction_result.document_profile.model_dump(mode="json") if extraction_result.document_profile else None
        }
        
        # Insert/upsert tender_extractions
        try:
            # First try to get existing extraction
            existing = db.table("tender_extractions").select("id").eq("tender_id", tender_id).execute()
            
            if existing.data:
                # Update existing
                extraction_id = existing.data[0]["id"]
                db.table("tender_extractions").update(extraction_record).eq("id", extraction_id).execute()
            else:
                # Insert new
                insert_result = db.table("tender_extractions").insert(extraction_record).execute()
                extraction_id = insert_result.data[0]["id"]
            
            # Save individual insights
            await cls._save_insights_to_db(db, extraction_id, extraction_result.insights)
            
        except Exception as e:
            raise RuntimeError(f"Failed to save extraction: {e}")
    
    @classmethod
    async def _save_insights_to_db(
        cls,
        db,
        extraction_id: str,
        insights: List[Dict[str, Any]]
    ) -> None:
        """
        Save individual insights to tender_insights table.
        
        Args:
            db: Supabase client
            extraction_id: UUID of the parent extraction
            insights: List of insight dicts
        """
        # Delete existing insights for this extraction
        try:
            db.table("tender_insights").delete().eq("extraction_id", extraction_id).execute()
        except Exception as e:
            print(f"Warning: Could not delete existing insights: {e}")
        
        if not insights:
            return
        
        # Prepare insight records
        insight_records = []
        for insight in insights:
            finding = insight.get("finding", {})
            impact = insight.get("impact", {})
            
            record = {
                "extraction_id": extraction_id,
                "insight_id": insight.get("id"),
                "category": insight.get("category"),
                "type": insight.get("type"),
                "importance": impact.get("importance"),
                "title": finding.get("title"),
                "description": finding.get("description"),
                "source_text": finding.get("source_text"),
                "source_location": finding.get("source_location"),
                "score_points": impact.get("points_available"),
                "full_insight": insight
            }
            insight_records.append(record)
        
        # Batch insert
        try:
            db.table("tender_insights").insert(insight_records).execute()
        except Exception as e:
            print(f"Warning: Failed to save some insights: {e}")
