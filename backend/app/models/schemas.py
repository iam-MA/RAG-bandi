"""
Pydantic Schemas for API requests and responses.
These models define the structure of data exchanged via the API.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from uuid import UUID


# =============================================================================
# Health Check Schemas
# =============================================================================

class HealthResponse(BaseModel):
    """Response model for health check endpoint"""
    status: Literal["healthy", "unhealthy"] = Field(
        description="Overall health status of the service"
    )
    database: Literal["connected", "disconnected"] = Field(
        description="Database connection status"
    )
    timestamp: datetime = Field(
        description="Timestamp of the health check"
    )
    version: str = Field(
        description="API version"
    )
    details: Optional[str] = Field(
        default=None,
        description="Additional details or error message"
    )


# =============================================================================
# Base Schemas (for future use)
# =============================================================================

class CompanyBase(BaseModel):
    """Base schema for Company - matches public.companies table"""
    company_name: Optional[str] = None
    vat_number: Optional[str] = None


class TenderBase(BaseModel):
    """Base schema for Tender - matches public.tenders table"""
    cig: str = Field(description="Codice Identificativo Gara - unique identifier")
    title: Optional[str] = None
    description: Optional[str] = None
    status: Literal["analyzing", "ready", "error"] = "analyzing"


# Note: TenderRequirementBase removed - tender_requirements table deprecated
# New tables: tender_extractions, tender_insights (see schema.sql)


class ProjectBase(BaseModel):
    """Base schema for Project - matches public.projects table"""
    status: str = "draft"
    generated_response: Optional[dict] = None


# =============================================================================
# API Response Wrappers
# =============================================================================

class APIResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool
    message: str
    data: Optional[dict] = None


# =============================================================================
# Tender Upload Schemas
# =============================================================================

class TenderDocumentResponse(BaseModel):
    """Response model for a single uploaded tender document"""
    id: UUID = Field(description="Document UUID")
    name: str = Field(description="Original filename")
    file_path: str = Field(description="Path in Supabase Storage")
    doc_type: Optional[str] = Field(default=None, description="Document type")


class TenderUploadResponse(BaseModel):
    """Response model for tender upload endpoint"""
    id: UUID = Field(description="Tender UUID")
    cig: str = Field(description="Codice Identificativo Gara")
    status: str = Field(description="Tender status")
    number_docs: int = Field(description="Number of uploaded documents")
    documents: list[TenderDocumentResponse] = Field(
        description="List of uploaded documents"
    )
    message: str = Field(description="Status message")


class TenderExistsResponse(BaseModel):
    """Response when tender with CIG already exists"""
    exists: bool = True
    id: UUID = Field(description="Existing tender UUID")
    cig: str = Field(description="Codice Identificativo Gara")
    status: str = Field(description="Current tender status")
    message: str = Field(default="Tender with this CIG already exists")


# =============================================================================
# Text Extraction Schemas
# =============================================================================

class TextExtractionResponse(BaseModel):
    """Response model for text extraction endpoint"""
    cig: str = Field(description="Codice Identificativo Gara")
    success_count: int = Field(description="Number of documents successfully processed")
    fail_count: int = Field(description="Number of documents that failed extraction")
    errors: list[str] = Field(default=[], description="List of error messages")
    message: str = Field(description="Status message")


# =============================================================================
# Embedding Generation Schemas
# =============================================================================

class EmbeddingGenerationResponse(BaseModel):
    """Response model for embedding generation endpoint"""
    cig: str = Field(description="Codice Identificativo Gara")
    chunks_created: int = Field(description="Number of chunks successfully created")
    chunks_failed: int = Field(description="Number of chunks that failed")
    errors: list[str] = Field(default=[], description="List of error messages")
    message: str = Field(description="Status message")


# =============================================================================
# AI Analysis Schemas
# =============================================================================

class AnalysisResponse(BaseModel):
    """Response model for AI analysis endpoint (Pipeline v2.0)"""
    cig: str = Field(description="Codice Identificativo Gara")
    insights_found: int = Field(description="Number of insights extracted")
    docs_analyzed: int = Field(description="Number of documents successfully analyzed")
    quality_score: Optional[float] = Field(default=None, description="Quality score 0-100")
    errors: list[str] = Field(default=[], description="List of error messages")
    analysis: dict = Field(default={}, description="Analysis summary with details")
    message: str = Field(description="Status message")


# =============================================================================
# Company Document Schemas
# =============================================================================

class CompanyDocumentResponse(BaseModel):
    """Response model for a single company document"""
    id: str = Field(description="Document UUID")
    name: str = Field(description="Original filename")
    file_path: str = Field(description="Storage path")
    uploaded_at: str = Field(description="Upload timestamp")


class CompanyDocumentUploadResponse(BaseModel):
    """Response model for company document upload endpoint"""
    company_id: str = Field(description="Company UUID")
    documents: list[CompanyDocumentResponse] = Field(description="List of uploaded documents")
    total_uploaded: int = Field(description="Number of files successfully uploaded")
    total_failed: int = Field(description="Number of files that failed to upload")
    errors: list[str] = Field(default=[], description="List of error messages")
    message: str = Field(description="Status message")


# =============================================================================
# Project Schemas
# =============================================================================

class ProjectCreate(BaseModel):
    """Request model for creating a project"""
    company_id: str = Field(description="UUID of the company (user_id)")
    cig: str = Field(description="CIG of the tender")


class ProjectResponse(BaseModel):
    """Response model for a project"""
    id: str = Field(description="UUID of the project")
    company_id: str = Field(description="UUID of the company")
    tender_id: str = Field(description="UUID of the tender")
    name: Optional[str] = Field(default=None, description="Project name")
    status: str = Field(description="Project status: draft, generating, ready, error")
    generated_response: Optional[dict] = Field(default=None, description="Generated proposal JSON")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")


class ProposalGenerationResponse(BaseModel):
    """Response model for proposal generation endpoint"""
    project_id: str = Field(description="UUID of the project")
    status: str = Field(description="Generation status")
    sections_generated: int = Field(default=0, description="Number of sections generated")
    requirements_addressed: int = Field(default=0, description="Number of requirements addressed")
    errors: list[str] = Field(default=[], description="List of error messages")
    message: str = Field(description="Status message")

