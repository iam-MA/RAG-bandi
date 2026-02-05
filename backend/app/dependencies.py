"""
FastAPI Dependencies
Centralized dependency injection for the application.
"""

from supabase import Client
from app.services.supabase_client import get_supabase


def get_db() -> Client:
    """
    Dependency to get the Supabase database client.
    
    Usage in routers:
        @router.get("/items")
        def get_items(db: Client = Depends(get_db)):
            return db.table("items").select("*").execute()
    """
    return get_supabase()
