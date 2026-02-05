"""
Companies Router
Handles company document upload and management endpoints.
"""

from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from app.services.supabase_client import SupabaseService
from app.services.storage_service import StorageService
from app.services.pdf_parser_service import PDFParserService
from app.services.embedding_service import EmbeddingService
from app.models.schemas import (
    CompanyDocumentUploadResponse,
    CompanyDocumentResponse,
    TextExtractionResponse,
    EmbeddingGenerationResponse
)


router = APIRouter(tags=["Companies"])


@router.post(
    "/upload",
    response_model=CompanyDocumentUploadResponse,
    summary="Upload Company Documents",
    description="""
Uploads company documents for the Knowledge Base.

**Flow:**
1. Receives user_id (will come from auth in production)
2. Retrieves company_id from companies table
3. Uploads files to 'companies' bucket in Storage
4. Creates records in company_documents table

**Note:** In production, user_id will be extracted from JWT token.
For now, it must be provided as a form parameter.
    """,
    responses={
        200: {"description": "Files uploaded successfully"},
        404: {"description": "Company not found for this user"}
    }
)
async def upload_company_documents(
    user_id: str = Form(..., description="User UUID (from auth in production)"),
    files: List[UploadFile] = File(..., description="PDF or DOCX files to upload")
):
    """
    Upload company documents.
    
    Args:
        user_id: UUID of the authenticated user
        files: List of files to upload
        
    Returns:
        CompanyDocumentUploadResponse with upload results
    """
    client = SupabaseService.get_client()
    
    # In this schema, companies.id = auth.users.id (1:1 relationship)
    # So user_id IS the company_id
    company_id = user_id
    
    # Verify company exists
    company_result = client.table("companies").select("id").eq("id", company_id).execute()
    
    if not company_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No company found for user '{user_id}'. Please create a company first."
        )
    
    # Track uploads
    uploaded_docs = []
    failed_count = 0
    errors = []
    
    for file in files:
        # Validate file type
        if not file.filename.lower().endswith(('.pdf', '.docx')):
            errors.append(f"{file.filename}: Unsupported file type (only PDF and DOCX allowed)")
            failed_count += 1
            continue
        
        # Upload to storage
        success, file_path, error = await StorageService.upload_company_file(
            file=file,
            company_id=company_id
        )
        
        if not success:
            errors.append(f"{file.filename}: {error}")
            failed_count += 1
            continue
        
        # Create database record
        try:
            doc_result = client.table("company_documents").insert({
                "company_id": company_id,
                "name": file.filename,
                "file_path": file_path
            }).execute()
            
            if doc_result.data:
                doc = doc_result.data[0]
                uploaded_docs.append(CompanyDocumentResponse(
                    id=doc["id"],
                    name=doc["name"],
                    file_path=doc["file_path"],
                    uploaded_at=doc["created_at"]
                ))
        except Exception as e:
            errors.append(f"{file.filename}: Database error - {str(e)}")
            failed_count += 1
    
    # Build response message
    total_uploaded = len(uploaded_docs)
    if failed_count == 0 and total_uploaded > 0:
        message = f"Successfully uploaded {total_uploaded} document(s)"
    elif total_uploaded == 0:
        message = "No documents uploaded"
    else:
        message = f"Uploaded {total_uploaded} document(s), {failed_count} failed"
    
    return CompanyDocumentUploadResponse(
        company_id=company_id,
        documents=uploaded_docs,
        total_uploaded=total_uploaded,
        total_failed=failed_count,
        errors=errors,
        message=message
    )


@router.get(
    "/documents/{user_id}",
    response_model=List[CompanyDocumentResponse],
    summary="List Company Documents",
    description="Lists all documents for a user's company.",
    responses={
        200: {"description": "List of documents"},
        404: {"description": "Company not found"}
    }
)
async def list_company_documents(user_id: str):
    """
    List all documents for a user's company.
    
    Args:
        user_id: UUID of the user
        
    Returns:
        List of CompanyDocumentResponse
    """
    client = SupabaseService.get_client()
    
    # In this schema, companies.id = auth.users.id (1:1 relationship)
    company_id = user_id
    
    # Verify company exists
    company_result = client.table("companies").select("id").eq("id", company_id).execute()
    
    if not company_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No company found for user '{user_id}'"
        )
    
    # Get documents
    docs_result = client.table("company_documents").select("*").eq("company_id", company_id).execute()
    
    return [
        CompanyDocumentResponse(
            id=doc["id"],
            name=doc["name"],
            file_path=doc["file_path"],
            uploaded_at=doc["created_at"]
        )
        for doc in (docs_result.data or [])
    ]


@router.post(
    "/extract-text/{user_id}",
    response_model=TextExtractionResponse,
    summary="Extract Text from Company Documents",
    description="""
Extracts text from all PDF documents of a company and saves to database.

**Note:** This will overwrite any existing extracted text (force=True).
    """,
    responses={
        200: {"description": "Text extraction completed"},
        404: {"description": "Company not found"}
    }
)
async def extract_text_for_company(user_id: str):
    """
    Extract text from all company documents.
    
    Args:
        user_id: UUID of the user (same as company_id in this schema)
        
    Returns:
        TextExtractionResponse with extraction results
    """
    # In this schema, companies.id = auth.users.id
    company_id = user_id
    
    # Verify company exists
    client = SupabaseService.get_client()
    company_result = client.table("companies").select("id").eq("id", company_id).execute()
    
    if not company_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found"
        )
    
    # Run extraction with force=True to overwrite existing text
    success_count, fail_count, errors = await PDFParserService.extract_and_save_for_company(
        company_id=company_id,
        force=True
    )
    
    # Build response message
    if fail_count == 0 and success_count > 0:
        message = f"Successfully extracted text from {success_count} document(s)"
    elif success_count == 0:
        message = "No documents processed"
    else:
        message = f"Extracted text from {success_count} document(s), {fail_count} failed"
    
    return TextExtractionResponse(
        cig=user_id,  # Reusing cig field for user_id
        success_count=success_count,
        fail_count=fail_count,
        errors=errors,
        message=message
    )


@router.post(
    "/generate-embeddings/{user_id}",
    response_model=EmbeddingGenerationResponse,
    summary="Generate Embeddings for Company Documents",
    description="""
Generates embeddings for all company documents and saves to company_assets table.

**Process:**
1. Retrieves extracted_text from all company documents
2. Splits text into chunks (1000 chars, 200 overlap)
3. Generates embeddings via OpenAI API
4. Saves chunks with embeddings to company_assets table

**Note:** This will delete and regenerate all existing chunks (force=True).
    """,
    responses={
        200: {"description": "Embeddings generated successfully"},
        404: {"description": "Company not found"}
    }
)
async def generate_embeddings_for_company(user_id: str):
    """
    Generate embeddings for all company documents.
    
    Args:
        user_id: UUID of the user (same as company_id in this schema)
        
    Returns:
        EmbeddingGenerationResponse with generation results
    """
    # In this schema, companies.id = auth.users.id
    company_id = user_id
    
    # Verify company exists
    client = SupabaseService.get_client()
    company_result = client.table("companies").select("id").eq("id", company_id).execute()
    
    if not company_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found"
        )
    
    # Generate embeddings with force=True to regenerate
    chunks_created, chunks_failed, errors = await EmbeddingService.generate_and_save_for_company(
        company_id=company_id,
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
        cig=user_id,  # Reusing cig field for user_id
        chunks_created=chunks_created,
        chunks_failed=chunks_failed,
        errors=errors,
        message=message
    )
