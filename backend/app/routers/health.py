"""
Health Check Router
Provides endpoint to verify API and database connectivity.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import HealthResponse
from app.services.supabase_client import SupabaseService
from app.config import get_settings


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Verifies API health and database connectivity. Returns 200 if healthy, 503 if database is unreachable.",
    responses={
        200: {"description": "Service is healthy and database is connected"},
        503: {"description": "Service is unhealthy - database connection failed"}
    }
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint that performs a real database query.
    
    This endpoint:
    1. Attempts to connect to Supabase
    2. Executes a test query on the 'tenders' table
    3. Returns 200 OK if successful, 503 Service Unavailable if not
    
    Use this endpoint to verify that:
    - The API is running
    - Environment variables are correctly configured
    - Database connection is active
    """
    settings = get_settings()
    
    # Test database connection
    is_connected, message = await SupabaseService.test_connection()
    
    response = HealthResponse(
        status="healthy" if is_connected else "unhealthy",
        database="connected" if is_connected else "disconnected",
        timestamp=datetime.now(timezone.utc),
        version=settings.version,
        details=message if not is_connected else None
    )
    
    if not is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump()
        )
    
    return response
