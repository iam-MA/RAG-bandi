"""
Chunking Service
Handles text splitting into chunks for embedding generation.
"""

from typing import List, Dict, Any


class ChunkingService:
    """
    Service for splitting text into chunks suitable for embedding.
    
    Uses a simple character-based splitting with overlap to maintain context.
    """
    
    # Default configuration
    DEFAULT_CHUNK_SIZE = 1000  # Characters per chunk
    DEFAULT_CHUNK_OVERLAP = 200  # Overlap between chunks
    
    @classmethod
    def split_text(
        cls,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[str]:
        """
        Splits text into overlapping chunks.
        
        Args:
            text: The text to split
            chunk_size: Maximum characters per chunk
            chunk_overlap: Number of overlapping characters between chunks
            
        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []
        
        # Clean text
        text = text.strip()
        
        # If text is smaller than chunk size, return as single chunk
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Calculate end position
            end = start + chunk_size
            
            # If not at the end, try to break at a sentence or paragraph
            if end < len(text):
                # Look for paragraph break first
                paragraph_break = text.rfind('\n\n', start, end)
                if paragraph_break > start + chunk_size // 2:
                    end = paragraph_break
                else:
                    # Look for sentence break
                    sentence_break = max(
                        text.rfind('. ', start, end),
                        text.rfind('.\n', start, end),
                        text.rfind('? ', start, end),
                        text.rfind('! ', start, end)
                    )
                    if sentence_break > start + chunk_size // 2:
                        end = sentence_break + 1  # Include the period
            
            # Extract chunk
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position (with overlap)
            new_start = end - chunk_overlap
            
            # Avoid infinite loop: ensure we always make progress
            if new_start <= start:
                start = end
            else:
                start = new_start
        
        return chunks
    
    @classmethod
    def create_chunks_with_metadata(
        cls,
        text: str,
        source_filename: str,
        document_id: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Creates chunks with associated metadata.
        
        Args:
            text: The text to split
            source_filename: Name of the source document
            document_id: UUID of the source document
            chunk_size: Maximum characters per chunk
            chunk_overlap: Number of overlapping characters
            
        Returns:
            List of dicts with 'content', 'chunk_index', and 'metadata'
        """
        chunks = cls.split_text(text, chunk_size, chunk_overlap)
        
        result = []
        for index, chunk_content in enumerate(chunks):
            result.append({
                "content": chunk_content,
                "chunk_index": index,
                "metadata": {
                    "source": source_filename,
                    "document_id": document_id,
                    "chunk_index": index,
                    "total_chunks": len(chunks),
                    "char_count": len(chunk_content)
                }
            })
        
        return result
