"""
Projects Router
Handles project creation and proposal generation endpoints.
"""

from typing import List
from fastapi import APIRouter, HTTPException, status
from app.services.supabase_client import SupabaseService
from app.services.proposal.orchestrator import ProposalOrchestrator
from app.models.schemas import (
    ProjectCreate,
    ProjectResponse,
    ProposalGenerationResponse
)


router = APIRouter(tags=["Projects"])


@router.post(
    "/create",
    response_model=ProjectResponse,
    summary="Create a Project",
    description="""
Creates a new project linking a company to a tender.

A project represents a company's participation in a tender.
""",
    responses={
        201: {"description": "Project created successfully"},
        404: {"description": "Company or tender not found"},
        409: {"description": "Project already exists"}
    }
)
async def create_project(project_data: ProjectCreate):
    """
    Create a new project.
    
    Args:
        project_data: Company ID and tender CIG
        
    Returns:
        Created project
    """
    db = SupabaseService.get_client()
    
    # Verify company exists (company_id = user_id in current schema)
    company_result = db.table("companies").select("id").eq("id", project_data.company_id).execute()
    if not company_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{project_data.company_id}' not found"
        )
    
    # Get tender by CIG
    tender_result = db.table("tenders").select("id").eq("cig", project_data.cig).execute()
    if not tender_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with CIG '{project_data.cig}' not found"
        )
    
    tender_id = tender_result.data[0]["id"]
    
    # Check if project already exists
    existing = db.table("projects").select("id").eq(
        "company_id", project_data.company_id
    ).eq("tender_id", tender_id).execute()
    
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project already exists for this company and tender"
        )
    
    # Create project
    project_result = db.table("projects").insert({
        "company_id": project_data.company_id,
        "tender_id": tender_id,
        "status": "draft"
    }).execute()
    
    if not project_result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project"
        )
    
    project = project_result.data[0]
    
    return ProjectResponse(
        id=project["id"],
        company_id=project["company_id"],
        tender_id=project["tender_id"],
        name=project.get("name"),
        status=project["status"],
        generated_response=project.get("generated_response"),
        created_at=project.get("created_at")
    )


@router.post(
    "/{project_id}/generate",
    response_model=ProposalGenerationResponse,
    summary="Generate Proposal (Pipeline 2)",
    description="""
Generates a complete professional proposal using the multi-agent Pipeline 2.

**Pipeline (5 Agents):**
1. TenderAnalyzer - Analyzes tender type, sector, scoring criteria
2. ProposalPlanner - Creates proposal structure based on criteria
3. SectionWriter - Writes sections with RAG and anti-hallucination
4. QualityValidator - Validates quality and detects issues
5. ProposalAssembler - Assembles final proposal with executive summary

Result is saved in project's generated_response field.
""",
    responses={
        200: {"description": "Proposal generated successfully"},
        404: {"description": "Project not found"}
    }
)
async def generate_proposal(project_id: str):
    """
    Generate a proposal for a project.
    
    Args:
        project_id: UUID of the project
        
    Returns:
        Generation result with statistics
    """
    db = SupabaseService.get_client()
    
    # Verify project exists
    project_result = db.table("projects").select("id").eq("id", project_id).execute()
    if not project_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found"
        )
    
    print(f"Starting proposal generation for project {project_id}...")
    
    # Generate proposal using Pipeline 2 orchestrator
    success, proposal, errors = await ProposalOrchestrator.generate_proposal(project_id, verbose=True)
    
    if success and proposal:
        metadata = proposal.metadata
        return ProposalGenerationResponse(
            project_id=project_id,
            status="ready",
            sections_generated=metadata.total_sections,
            requirements_addressed=metadata.requirements_addressed,
            errors=[],
            message=f"Successfully generated proposal with {metadata.total_sections} sections, quality score {proposal.overall_quality_score}/100"
        )
    else:
        return ProposalGenerationResponse(
            project_id=project_id,
            status="error",
            sections_generated=0,
            requirements_addressed=0,
            errors=errors,
            message="Failed to generate proposal"
        )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get Project",
    description="Retrieves a project with its generated proposal.",
    responses={
        200: {"description": "Project found"},
        404: {"description": "Project not found"}
    }
)
async def get_project(project_id: str):
    """
    Get a project by ID.
    
    Args:
        project_id: UUID of the project
        
    Returns:
        Project with generated_response
    """
    db = SupabaseService.get_client()
    
    result = db.table("projects").select("*").eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found"
        )
    
    project = result.data[0]
    
    return ProjectResponse(
        id=project["id"],
        company_id=project["company_id"],
        tender_id=project["tender_id"],
        name=project.get("name"),
        status=project["status"],
        generated_response=project.get("generated_response"),
        created_at=project.get("created_at")
    )


@router.get(
    "/by-company/{company_id}",
    response_model=List[ProjectResponse],
    summary="List Company Projects",
    description="Lists all projects for a company.",
    responses={
        200: {"description": "Projects list"}
    }
)
async def list_company_projects(company_id: str):
    """
    List all projects for a company.
    
    Args:
        company_id: UUID of the company
        
    Returns:
        List of projects
    """
    db = SupabaseService.get_client()
    
    result = db.table("projects").select("*").eq("company_id", company_id).execute()
    
    projects = []
    for project in result.data or []:
        projects.append(ProjectResponse(
            id=project["id"],
            company_id=project["company_id"],
            tender_id=project["tender_id"],
            name=project.get("name"),
            status=project["status"],
            generated_response=project.get("generated_response"),
            created_at=project.get("created_at")
        ))
    
    return projects


@router.get(
    "/{project_id}/details",
    summary="Get Project Details",
    description="""
Retrieves complete project details for the project detail page.
Includes project info, tender info, extraction data, and documents.
""",
    responses={
        200: {"description": "Project details retrieved"},
        404: {"description": "Project not found"}
    }
)
async def get_project_details(project_id: str):
    """
    Get comprehensive project details for the detail page.
    
    Returns:
        - project: Basic project info
        - tender: Tender info (cig)
        - extraction: Data from tender_extractions
        - documents: List from tender_documents
    """
    db = SupabaseService.get_client()
    
    # 1. Get project
    project_result = db.table("projects").select("*").eq("id", project_id).execute()
    
    if not project_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found"
        )
    
    project = project_result.data[0]
    tender_id = project["tender_id"]
    
    # 2. Get tender info
    tender_result = db.table("tenders").select("id, cig, status").eq("id", tender_id).execute()
    tender = tender_result.data[0] if tender_result.data else None
    
    # 3. Get extraction data
    extraction_result = db.table("tender_extractions").select(
        "id, title, contracting_authority, value, currency, deadline, sector, procedure_type, duration_months, quality_score, created_at"
    ).eq("tender_id", tender_id).execute()
    extraction = extraction_result.data[0] if extraction_result.data else None
    
    # 4. Get documents
    documents_result = db.table("tender_documents").select(
        "id, name, file_path, doc_type, created_at"
    ).eq("tender_id", tender_id).execute()
    documents = documents_result.data or []
    
    return {
        "project": {
            "id": project["id"],
            "name": project.get("name"),
            "status": project["status"],
            "created_at": project.get("created_at")
        },
        "tender": tender,
        "extraction": extraction,
        "documents": documents
    }


@router.get(
    "/{project_id}/insights",
    summary="Get Project Insights",
    description="""
Retrieves all tender insights for the project's tender.
Returns insights grouped by category with importance statistics.
""",
    responses={
        200: {"description": "Insights retrieved"},
        404: {"description": "Project or insights not found"}
    }
)
async def get_project_insights(project_id: str):
    """
    Get all tender insights for the Analysis page.
    
    Returns:
        - insights: List of all insights
        - categories: Insights grouped by category
        - stats: Count by importance
    """
    db = SupabaseService.get_client()
    
    # 1. Get project
    project_result = db.table("projects").select("tender_id").eq("id", project_id).execute()
    
    if not project_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found"
        )
    
    tender_id = project_result.data[0]["tender_id"]
    
    # 2. Get extraction_id
    extraction_result = db.table("tender_extractions").select("id").eq("tender_id", tender_id).execute()
    
    if not extraction_result.data:
        return {
            "insights": [],
            "categories": {},
            "stats": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        }
    
    extraction_id = extraction_result.data[0]["id"]
    
    # 3. Get all insights
    insights_result = db.table("tender_insights").select(
        "id, insight_id, category, type, importance, title, description, source_text, source_location, score_points"
    ).eq("extraction_id", extraction_id).execute()
    
    insights = insights_result.data or []
    
    # 4. Group by category
    categories = {}
    stats = {"total": len(insights), "critical": 0, "high": 0, "medium": 0, "low": 0}
    
    for insight in insights:
        cat = insight.get("category", "altro")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(insight)
        
        # Count importance
        importance = insight.get("importance", "low")
        if importance in stats:
            stats[importance] += 1
    
    return {
        "insights": insights,
        "categories": categories,
        "stats": stats
    }
