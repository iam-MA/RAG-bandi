"""
Supabase Client Service
Provides a centralized, singleton Supabase client instance.
"""

from typing import Optional
from supabase import create_client, Client
from app.config import get_settings


class SupabaseService:
    """
    Singleton service for Supabase client management.
    
    Usage:
        supabase = SupabaseService.get_client()
        result = supabase.table("companies").select("*").execute()
    """
    
    _client: Optional[Client] = None
    
    @classmethod
    def get_client(cls) -> Client:
        """
        Returns the Supabase client instance.
        Creates a new client if one doesn't exist (lazy initialization).
        """
        if cls._client is None:
            settings = get_settings()
            cls._client = create_client(
                supabase_url=settings.supabase_url,
                supabase_key=settings.supabase_key
            )
        return cls._client
    
    @classmethod
    def reset_client(cls) -> None:
        """
        Resets the client instance.
        Useful for testing or when credentials change.
        """
        cls._client = None
    
    @classmethod
    async def test_connection(cls) -> tuple[bool, str]:
        """
        Tests the database connection by executing a simple query.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            client = cls.get_client()
            
            # Execute a simple query to test connection
            # We query the 'tenders' table with limit 1 - this works even if empty
            result = client.table("tenders").select("id").limit(1).execute()
            
            # If we get here without exception, connection is successful
            return True, "Database connection successful"
            
        except Exception as e:
            error_msg = str(e)
            return False, f"Database connection failed: {error_msg}"


# Convenience function for dependency injection
def get_supabase() -> Client:
    """
    Dependency function to get Supabase client.
    Use with FastAPI's Depends().
    
    Example:
        @router.get("/items")
        def get_items(db: Client = Depends(get_supabase)):
            return db.table("items").select("*").execute()
    """
    return SupabaseService.get_client()
