"""
Embedding Service
Handles embedding generation with OpenAI and storage in Supabase.
"""

import json
from typing import List, Dict, Any, Tuple, Optional
from openai import OpenAI
from app.config import get_settings
from app.services.supabase_client import SupabaseService
from app.services.chunking_service import ChunkingService


class EmbeddingService:
    """
    Service for generating embeddings using OpenAI API and storing them in Supabase.
    
    Uses OpenAI's text-embedding-3-small model (1536 dimensions).
    """
    
    # OpenAI embedding model
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS = 1536
    
    # Batch size for API calls (OpenAI allows up to 2048 inputs per request)
    BATCH_SIZE = 100
    
    _client: Optional[OpenAI] = None
    
    @classmethod
    def _get_openai_client(cls) -> OpenAI:
        """Get or create OpenAI client."""
        if cls._client is None:
            settings = get_settings()
            cls._client = OpenAI(api_key=settings.openai_api_key)
        return cls._client
    
    @classmethod
    def generate_embedding(cls, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (1536 dimensions)
        """
        client = cls._get_openai_client()
        
        response = client.embeddings.create(
            model=cls.EMBEDDING_MODEL,
            input=text
        )
        
        return response.data[0].embedding
    
    @classmethod
    def generate_embeddings_batch(cls, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embeddings (each 1536 dimensions)
        """
        if not texts:
            return []
        
        client = cls._get_openai_client()
        
        response = client.embeddings.create(
            model=cls.EMBEDDING_MODEL,
            input=texts
        )
        
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
    
    @classmethod
    async def generate_and_save_for_tender(
        cls,
        cig: str,
        force: bool = False
    ) -> Tuple[int, int, List[str]]:
        """
        Generate embeddings for all documents of a tender and save to tender_chunks.
        
        Args:
            cig: Codice Identificativo Gara
            force: If True, delete existing chunks and regenerate
            
        Returns:
            Tuple of (chunks_created: int, chunks_failed: int, errors: list)
        """
        db = SupabaseService.get_client()
        
        # Get tender
        tender_result = db.table("tenders").select("id").eq("cig", cig).execute()
        
        if not tender_result.data:
            return 0, 0, [f"Tender with CIG '{cig}' not found"]
        
        tender_id = tender_result.data[0]["id"]
        
        # If force, delete existing chunks for this tender
        if force:
            try:
                db.table("tender_chunks").delete().eq("tender_id", tender_id).execute()
            except Exception as e:
                return 0, 0, [f"Failed to delete existing chunks: {str(e)}"]
        
        # Get all documents with extracted text
        docs_result = db.table("tender_documents").select(
            "id, name, extracted_text"
        ).eq("tender_id", tender_id).execute()
        
        if not docs_result.data:
            return 0, 0, ["No documents found for this tender"]
        
        chunks_created = 0
        chunks_failed = 0
        errors = []
        
        for doc in docs_result.data:
            if not doc.get("extracted_text"):
                errors.append(f"{doc['name']}: No extracted text available")
                continue
            
            try:
                # Create chunks with metadata
                chunks = ChunkingService.create_chunks_with_metadata(
                    text=doc["extracted_text"],
                    source_filename=doc["name"],
                    document_id=doc["id"]
                )
                
                if not chunks:
                    errors.append(f"{doc['name']}: No chunks created (empty text?)")
                    continue
                
                # Generate embeddings in batches
                chunk_texts = [c["content"] for c in chunks]
                
                # Process in batches
                for batch_start in range(0, len(chunk_texts), cls.BATCH_SIZE):
                    batch_end = min(batch_start + cls.BATCH_SIZE, len(chunk_texts))
                    batch_texts = chunk_texts[batch_start:batch_end]
                    batch_chunks = chunks[batch_start:batch_end]
                    
                    try:
                        # Generate embeddings
                        embeddings = cls.generate_embeddings_batch(batch_texts)
                        
                        # Prepare records for insertion
                        records = []
                        for chunk, embedding in zip(batch_chunks, embeddings):
                            records.append({
                                "tender_id": tender_id,
                                "document_id": doc["id"],
                                "content": chunk["content"],
                                "embedding": embedding,
                                "chunk_index": chunk["chunk_index"],
                                "metadata": chunk["metadata"]
                            })
                        
                        # Insert into database
                        db.table("tender_chunks").insert(records).execute()
                        chunks_created += len(records)
                        
                    except Exception as e:
                        chunks_failed += len(batch_texts)
                        errors.append(f"{doc['name']} batch {batch_start}-{batch_end}: {str(e)}")
                
            except Exception as e:
                import traceback
                chunks_failed += 1
                errors.append(f"{doc['name']}: {str(e)}\n{traceback.format_exc()}")
        
        return chunks_created, chunks_failed, errors
    
    @classmethod
    async def generate_and_save_for_company(
        cls,
        company_id: str,
        force: bool = False
    ) -> Tuple[int, int, List[str]]:
        """
        Generate embeddings for all documents of a company and save to company_assets.
        
        Args:
            company_id: UUID of the company (same as user_id in this schema)
            force: If True, delete existing chunks and regenerate
            
        Returns:
            Tuple of (chunks_created: int, chunks_failed: int, errors: list)
        """
        db = SupabaseService.get_client()
        
        # Verify company exists
        company_result = db.table("companies").select("id").eq("id", company_id).execute()
        
        if not company_result.data:
            return 0, 0, [f"Company with ID '{company_id}' not found"]
        
        # If force, delete existing chunks for this company
        if force:
            try:
                db.table("company_assets").delete().eq("company_id", company_id).execute()
            except Exception as e:
                return 0, 0, [f"Failed to delete existing chunks: {str(e)}"]
        
        # Get all documents with extracted text
        docs_result = db.table("company_documents").select(
            "id, name, extracted_text"
        ).eq("company_id", company_id).execute()
        
        if not docs_result.data:
            return 0, 0, ["No documents found for this company"]
        
        chunks_created = 0
        chunks_failed = 0
        errors = []
        
        for doc in docs_result.data:
            if not doc.get("extracted_text"):
                errors.append(f"{doc['name']}: No extracted text available")
                continue
            
            try:
                # Create chunks with metadata
                chunks = ChunkingService.create_chunks_with_metadata(
                    text=doc["extracted_text"],
                    source_filename=doc["name"],
                    document_id=doc["id"]
                )
                
                if not chunks:
                    errors.append(f"{doc['name']}: No chunks created (empty text?)")
                    continue
                
                # Generate embeddings in batches
                chunk_texts = [c["content"] for c in chunks]
                
                # Process in batches
                for batch_start in range(0, len(chunk_texts), cls.BATCH_SIZE):
                    batch_end = min(batch_start + cls.BATCH_SIZE, len(chunk_texts))
                    batch_texts = chunk_texts[batch_start:batch_end]
                    batch_chunks = chunks[batch_start:batch_end]
                    
                    try:
                        # Generate embeddings
                        embeddings = cls.generate_embeddings_batch(batch_texts)
                        
                        # Prepare records for insertion into company_assets
                        records = []
                        for chunk, embedding in zip(batch_chunks, embeddings):
                            records.append({
                                "company_id": company_id,
                                "file_id": doc["id"],  # Note: company_assets uses file_id, not document_id
                                "content": chunk["content"],
                                "embedding": embedding,
                                "chunk_index": chunk["chunk_index"],
                                "metadata": chunk["metadata"]
                            })
                        
                        # Insert into database
                        db.table("company_assets").insert(records).execute()
                        chunks_created += len(records)
                        
                    except Exception as e:
                        chunks_failed += len(batch_texts)
                        errors.append(f"{doc['name']} batch {batch_start}-{batch_end}: {str(e)}")
                
            except Exception as e:
                chunks_failed += 1
                errors.append(f"{doc['name']}: {str(e)}")
        
        return chunks_created, chunks_failed, errors

