"""
Tenders Router
Handles tender upload and management endpoints.
"""

from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, BackgroundTasks
from app.services.supabase_client import SupabaseService
from app.services.storage_service import StorageService
from app.services.pdf_parser_service import PDFParserService
from app.services.embedding_service import EmbeddingService
from app.services.analysis_service import AnalysisService
from app.models.schemas import (
    TenderUploadResponse,
    TenderDocumentResponse,
    TenderExistsResponse,
    TextExtractionResponse,
    EmbeddingGenerationResponse,
    AnalysisResponse
)


router = APIRouter(tags=["Tenders"])


@router.post(
    "/upload",
    response_model=TenderUploadResponse,
    summary="Upload Tender Documents",
    description="""
Upload one or more tender documents along with the CIG (Codice Identificativo Gara).

**Flow:**
1. Checks if a tender with the same CIG already exists
2. If exists, returns the existing tender info (409 Conflict)
3. If not, creates a new tender record
4. Uploads all files to Supabase Storage
5. Creates tender_documents records for each file
6. Returns the created tender with document details
    """,
    responses={
        200: {"description": "Tender created and documents uploaded successfully"},
        409: {"description": "Tender with this CIG already exists", "model": TenderExistsResponse},
        400: {"description": "No files provided"},
        500: {"description": "Upload or database error"}
    }
)
async def upload_tender(
    files: List[UploadFile] = File(..., description="One or more tender documents (PDF, DOCX, etc.)"),
    cig: str = Form(..., description="Codice Identificativo Gara - unique tender identifier"),
    name: str = Form(..., description="Project name")
):
    """
    Upload tender documents and create database records.
    
    Args:
        files: List of files to upload
        cig: Unique tender identifier (CIG)
        
    Returns:
        TenderUploadResponse with tender and document details
    """
    # Validate input
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required"
        )
    
    if not cig or not cig.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CIG is required"
        )
    
    cig = cig.strip()
    client = SupabaseService.get_client()
    
    # Check if tender with this CIG already exists
    existing = client.table("tenders").select("id, cig, status").eq("cig", cig).execute()
    
    if existing.data and len(existing.data) > 0:
        tender = existing.data[0]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "exists": True,
                "id": tender["id"],
                "cig": tender["cig"],
                "status": tender["status"],
                "message": "Tender with this CIG already exists"
            }
        )
    
    try:
        # Create tender record
        tender_data = {
            "cig": cig,
            "number_docs": len(files),
            "status": "analyzing"
        }
        
        tender_result = client.table("tenders").insert(tender_data).execute()
        
        if not tender_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create tender record"
            )
        
        tender = tender_result.data[0]
        tender_id = tender["id"]
        
        # Upload files and create tender_documents records
        uploaded_documents: List[TenderDocumentResponse] = []
        
        for file in files:
            # Upload to Supabase Storage
            success, file_path, error = await StorageService.upload_tender_file(
                file=file,
                tender_id=tender_id
            )
            
            if not success:
                # Rollback: delete the tender record (cascade will clean up)
                client.table("tenders").delete().eq("id", tender_id).execute()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to upload file {file.filename}: {error}"
                )
            
            # Create tender_document record
            doc_data = {
                "tender_id": tender_id,
                "name": file.filename,
                "file_path": file_path
                # doc_type left as NULL
            }
            
            doc_result = client.table("tender_documents").insert(doc_data).execute()
            
            if not doc_result.data:
                # Rollback: delete uploaded file and tender
                await StorageService.delete_tender_file(file_path)
                client.table("tenders").delete().eq("id", tender_id).execute()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create document record for {file.filename}"
                )
            
            doc = doc_result.data[0]
            uploaded_documents.append(TenderDocumentResponse(
                id=doc["id"],
                name=doc["name"],
                file_path=doc["file_path"],
                doc_type=doc.get("doc_type")
            ))
        
        # Trigger text extraction in background (non-blocking)
        # If extraction fails, files are still uploaded successfully
        try:
            print(f"Starting automatic text extraction for CIG {cig}...")
            await PDFParserService.extract_and_save_for_tender(cig)
            print(f"Text extraction completed for CIG {cig}")
        except Exception as extraction_error:
            # Log error but don't fail the upload
            import traceback
            print(f"Warning: Text extraction failed for CIG {cig}: {extraction_error}")
            print(f"Traceback: {traceback.format_exc()}")
        
        # Create project record linking tender to company
        # TODO: Replace hardcoded company_id with authenticated user's company
        TEST_COMPANY_ID = "a5817d3f-5462-43c1-beb7-0f8769ac5531"
        
        try:
            project_data = {
                "company_id": TEST_COMPANY_ID,
                "tender_id": tender_id,
                "name": name.strip() if name else None,
                "status": "analyzing"
            }
            project_result = client.table("projects").insert(project_data).execute()
            
            if project_result.data:
                print(f"Created project {project_result.data[0]['id']} for tender {tender_id}")
            else:
                print(f"Warning: Failed to create project for tender {tender_id}")
        except Exception as project_error:
            # Log error but don't fail the upload
            print(f"Warning: Project creation failed for tender {tender_id}: {project_error}")
        
        return TenderUploadResponse(
            id=tender_id,
            cig=cig,
            status="analyzing",
            number_docs=len(files),
            documents=uploaded_documents,
            message=f"Successfully uploaded {len(files)} document(s)"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post(
    "/extract-text/{cig}",
    response_model=TextExtractionResponse,
    summary="Extract Text from Tender Documents",
    description="""
Extracts text from all PDF documents of a tender and saves it to the database.

**Use cases:**
- Re-run extraction after upload if it initially failed
- Force re-extraction to update text
- Test extraction on existing tenders

**Note:** This endpoint will overwrite any existing extracted_text.
    """,
    responses={
        200: {"description": "Extraction completed (check success/fail counts)"},
        404: {"description": "Tender not found"}
    }
)
async def extract_text_for_tender(cig: str):
    """
    Extract text from all documents of a tender.
    
    Args:
        cig: Codice Identificativo Gara
        
    Returns:
        TextExtractionResponse with success/fail counts and errors
    """
    # Verify tender exists
    client = SupabaseService.get_client()
    tender_result = client.table("tenders").select("id").eq("cig", cig).execute()
    
    if not tender_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with CIG '{cig}' not found"
        )
    
    # Run extraction with force=True to overwrite existing text
    success_count, fail_count, errors = await PDFParserService.extract_and_save_for_tender(cig, force=True)
    
    # Build response message
    if fail_count == 0:
        message = f"Successfully extracted text from {success_count} document(s)"
    else:
        message = f"Extracted text from {success_count} document(s), {fail_count} failed"
    
    return TextExtractionResponse(
        cig=cig,
        success_count=success_count,
        fail_count=fail_count,
        errors=errors,
        message=message
    )


@router.get(
    "/{cig}",
    summary="Get Tender by CIG",
    description="Retrieve tender information by CIG code",
    responses={
        200: {"description": "Tender found"},
        404: {"description": "Tender not found"}
    }
)
async def get_tender_by_cig(cig: str):
    """
    Get tender details by CIG code.
    
    Args:
        cig: Codice Identificativo Gara
        
    Returns:
        Tender data with documents
    """
    client = SupabaseService.get_client()
    
    # Get tender
    result = client.table("tenders").select("*").eq("cig", cig).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with CIG '{cig}' not found"
        )
    
    tender = result.data[0]
    
    # Get associated documents
    docs_result = client.table("tender_documents").select("*").eq("tender_id", tender["id"]).execute()
    
    return {
        "tender": tender,
        "documents": docs_result.data if docs_result.data else []
    }


@router.get(
    "/by-id/{tender_id}",
    summary="Get Tender by ID",
    description="Retrieve tender information by UUID",
    responses={
        200: {"description": "Tender found"},
        404: {"description": "Tender not found"}
    }
)
async def get_tender_by_id(tender_id: str):
    """Get tender details by ID (UUID)."""
    client = SupabaseService.get_client()
    
    result = client.table("tenders").select("*").eq("id", tender_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with ID '{tender_id}' not found"
        )
    
    return result.data[0]


@router.post(
    "/generate-embeddings/{cig}",
    response_model=EmbeddingGenerationResponse,
    summary="Generate Embeddings for Tender Documents",
    description="""
Generates embeddings for all documents of a tender and saves them to tender_chunks.

**Process:**
1. Retrieves extracted_text from all tender_documents
2. Splits text into chunks (with overlap for context)
3. Generates embeddings using OpenAI API
4. Saves chunks with embeddings to tender_chunks table

**Note:** Existing chunks for this tender will be deleted and regenerated.
    """,
    responses={
        200: {"description": "Embedding generation completed"},
        404: {"description": "Tender not found"}
    }
)
async def generate_embeddings_for_tender(cig: str):
    """
    Generate embeddings for all documents of a tender.
    
    Args:
        cig: Codice Identificativo Gara
        
    Returns:
        EmbeddingGenerationResponse with chunk counts and errors
    """
    # Verify tender exists
    client = SupabaseService.get_client()
    tender_result = client.table("tenders").select("id").eq("cig", cig).execute()
    
    if not tender_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with CIG '{cig}' not found"
        )
    
    # Generate embeddings (force=True to regenerate)
    chunks_created, chunks_failed, errors = await EmbeddingService.generate_and_save_for_tender(
        cig=cig,
        force=True
    )
    
    # Build response message
    if chunks_failed == 0 and chunks_created > 0:
        message = f"Successfully created {chunks_created} chunks with embeddings"
    elif chunks_created == 0:
        message = "No chunks created - check if documents have extracted text"
    else:
        message = f"Created {chunks_created} chunks, {chunks_failed} failed"
    
    return EmbeddingGenerationResponse(
        cig=cig,
        chunks_created=chunks_created,
        chunks_failed=chunks_failed,
        errors=errors,
        message=message
    )


@router.post(
    "/analyze/{cig}",
    response_model=AnalysisResponse,
    summary="Analyze Tender Documents with AI (Pipeline v2.0)",
    description="""
Analyzes tender documents using the multi-agent AI pipeline and extracts insights.

**Pipeline v2.0:**
1. **Analyzer** - Understand document structure (sector, complexity, sections)
2. **Planner** - Create extraction strategy
3. **Executors** - 6 specialized agents extract information in parallel
4. **Aggregator** - Combine and deduplicate insights
5. **Validator** - Quality check and score

**Output:** Insights saved to tender_extractions + tender_insights tables.
Categories: tender_overview, requisito_partecipazione, criterio_punteggio, documento_richiesto, scadenza, specifica_tecnica
    """,
    responses={
        200: {"description": "Analysis completed"},
        404: {"description": "Tender not found"}
    }
)
async def analyze_tender(cig: str):
    """
    Analyze tender documents with AI multi-agent pipeline.
    
    Args:
        cig: Codice Identificativo Gara
        
    Returns:
        AnalysisResponse with extracted insights and quality score
    """
    # Verify tender exists
    client = SupabaseService.get_client()
    tender_result = client.table("tenders").select("id").eq("cig", cig).execute()
    
    if not tender_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with CIG '{cig}' not found"
        )
    
    print(f"Starting analysis pipeline v2.0 for CIG {cig}...")
    
    # Run analysis pipeline
    insights_found, docs_analyzed, errors, analysis = await AnalysisService.analyze_tender(cig)
    
    print(f"Analysis complete: {insights_found} insights found from {docs_analyzed} documents")
    
    # Extract quality score from analysis details if available
    quality_score = None
    if analysis.get("details", {}).get("documents"):
        scores = [d.get("quality_score", 0) for d in analysis["details"]["documents"]]
        if scores:
            quality_score = sum(scores) / len(scores) * 100  # Average as percentage
    
    # Build response message
    if insights_found > 0:
        message = f"Successfully extracted {insights_found} insights from {docs_analyzed} document(s)"
    elif docs_analyzed > 0:
        message = f"Analyzed {docs_analyzed} document(s) but no insights found"
    else:
        message = "No documents analyzed - check if documents have extracted text"
    
    return AnalysisResponse(
        cig=cig,
        insights_found=insights_found,
        docs_analyzed=docs_analyzed,
        quality_score=quality_score,
        errors=errors,
        analysis=analysis,
        message=message
    )




