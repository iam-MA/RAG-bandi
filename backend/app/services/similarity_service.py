"""
Similarity Service
Handles semantic search on company knowledge base using embeddings.
"""

from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.config import get_settings
from app.services.supabase_client import SupabaseService


class SimilarityService:
    """
    Service for semantic similarity search on company_assets.
    
    Uses OpenAI embeddings and Supabase RPC function match_company_assets.
    """
    
    EMBEDDING_MODEL = "text-embedding-3-small"
    DEFAULT_THRESHOLD = 0.5
    DEFAULT_LIMIT = 10
    
    _client: AsyncOpenAI = None
    
    @classmethod
    def _get_openai_client(cls) -> AsyncOpenAI:
        """Get or create async OpenAI client."""
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return cls._client
    
    @classmethod
    async def generate_embedding(cls, text: str) -> List[float]:
        """
        Generate embedding for a text query using OpenAI.
        
        Args:
            text: The text to embed
            
        Returns:
            List of floats representing the embedding vector (1536 dimensions)
        """
        client = cls._get_openai_client()
        
        response = await client.embeddings.create(
            model=cls.EMBEDDING_MODEL,
            input=text
        )
        
        return response.data[0].embedding
    
    @classmethod
    async def search_company_assets(
        cls,
        company_id: str,
        query: str,
        threshold: float = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search company knowledge base for relevant chunks.
        
        Uses the match_company_assets RPC function in Supabase.
        
        Args:
            company_id: UUID of the company (filters to only this company's assets)
            query: The search query text
            threshold: Minimum similarity score (0-1), default 0.5
            limit: Maximum number of results, default 10
            
        Returns:
            List of matching chunks with id, content, metadata, similarity
        """
        if threshold is None:
            threshold = cls.DEFAULT_THRESHOLD
        if limit is None:
            limit = cls.DEFAULT_LIMIT
        
        # Generate embedding for the query
        query_embedding = await cls.generate_embedding(query)
        
        # Call Supabase RPC function
        db = SupabaseService.get_client()
        
        result = db.rpc(
            "match_company_assets",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
                "filter_company_id": company_id
            }
        ).execute()
        
        return result.data or []
    
    @classmethod
    async def search_for_requirement(
        cls,
        company_id: str,
        requirement_description: str,
        requirement_category: str = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search company KB for content relevant to a specific tender requirement.
        
        Builds an optimized query from the requirement.
        
        Args:
            company_id: UUID of the company
            requirement_description: The requirement text
            requirement_category: Optional category for context
            limit: Max results per requirement
            
        Returns:
            List of relevant chunks with similarity scores
        """
        # Build search query with category context if available
        if requirement_category:
            query = f"[{requirement_category}] {requirement_description}"
        else:
            query = requirement_description
        
        # Use lower threshold for more results, we'll rank them
        results = await cls.search_company_assets(
            company_id=company_id,
            query=query,
            threshold=0.4,  # Lower threshold to catch more potential matches
            limit=limit
        )
        
        return results
    
    @classmethod
    async def search_bulk(
        cls,
        company_id: str,
        queries: List[str],
        threshold: float = 0.5,
        limit_per_query: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search for multiple queries in parallel.
        
        Args:
            company_id: UUID of the company
            queries: List of query strings
            threshold: Minimum similarity
            limit_per_query: Max results per query
            
        Returns:
            Dict mapping query -> results
        """
        import asyncio
        
        async def search_one(query: str) -> tuple:
            results = await cls.search_company_assets(
                company_id=company_id,
                query=query,
                threshold=threshold,
                limit=limit_per_query
            )
            return (query, results)
        
        # Run all searches in parallel
        results = await asyncio.gather(*[search_one(q) for q in queries])
        
        return dict(results)
