"""
ANAC Tenders Router - Public endpoint for Italian public procurement tenders.
No authentication required.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID

from app.config import get_settings

router = APIRouter()
settings = get_settings()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ANACTender(BaseModel):
    """Single ANAC tender record"""
    id: UUID
    created_at: datetime
    titolo: Optional[str] = None
    committente: Optional[str] = None
    scadenza: Optional[datetime] = None
    link_gara: Optional[str] = None
    cig: Optional[str] = None
    natura_principale: Optional[str] = None
    descrizione: Optional[str] = None
    cpv: Optional[str] = None
    valore: Optional[float] = None
    luogo_istat: Optional[str] = None
    criterio_aggiudicazione: Optional[str] = None

    class Config:
        from_attributes = True


class ANACTendersResponse(BaseModel):
    """Paginated response for ANAC tenders"""
    success: bool = True
    data: list[ANACTender]
    total: int = Field(description="Total number of records matching the query")
    page: int = Field(description="Current page number")
    limit: int = Field(description="Records per page")
    total_pages: int = Field(description="Total number of pages")


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/tenders", response_model=ANACTendersResponse)
async def get_anac_tenders(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Records per page"),
    search: Optional[str] = Query(default=None, description="Search in titolo and descrizione"),
    committente: Optional[str] = Query(default=None, description="Filter by committente (partial match)"),
    cpv: Optional[str] = Query(default=None, description="Filter by CPV code (partial match)"),
    natura: Optional[str] = Query(default=None, description="Filter by natura_principale"),
    valore_min: Optional[float] = Query(default=None, ge=0, description="Minimum value filter"),
    valore_max: Optional[float] = Query(default=None, ge=0, description="Maximum value filter"),
    scadenza_da: Optional[datetime] = Query(default=None, description="Filter tenders with scadenza >= this date"),
    order_by: str = Query(default="scadenza", description="Order by field"),
    order_dir: str = Query(default="desc", description="Order direction: asc or desc"),
):
    """
    Fetch ANAC tenders with filtering and pagination.
    This is a public endpoint - no authentication required.
    """
    try:
        from app.services.supabase_client import SupabaseService
        supabase = SupabaseService.get_client()
        
        # Build the base query
        query = supabase.table("anac").select("*", count="exact")
        
        # Apply filters
        if search:
            # Use ilike for case-insensitive partial match
            query = query.or_(f"titolo.ilike.%{search}%,descrizione.ilike.%{search}%")
        
        if committente:
            query = query.ilike("committente", f"%{committente}%")
        
        if cpv:
            query = query.ilike("cpv", f"%{cpv}%")
        
        if natura:
            query = query.ilike("natura_principale", f"%{natura}%")
        
        if valore_min is not None:
            query = query.gte("valore", valore_min)
        
        if valore_max is not None:
            query = query.lte("valore", valore_max)
        
        if scadenza_da:
            query = query.gte("scadenza", scadenza_da.isoformat())
        
        # Apply ordering
        valid_order_fields = ["scadenza", "valore", "created_at", "titolo", "committente"]
        if order_by not in valid_order_fields:
            order_by = "scadenza"
        
        is_desc = order_dir.lower() == "desc"
        query = query.order(order_by, desc=is_desc)
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        response = query.execute()
        
        total = response.count if response.count else 0
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
        return ANACTendersResponse(
            success=True,
            data=response.data,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tenders: {str(e)}")
