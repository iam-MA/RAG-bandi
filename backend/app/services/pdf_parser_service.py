"""
PDF Parser Service
Handles text extraction from PDF documents stored in Supabase Storage.
"""

import io
import os
import tempfile
from typing import Optional, Tuple
import fitz  # PyMuPDF
from llama_parse import LlamaParse
from app.services.supabase_client import SupabaseService
from app.services.storage_service import StorageService
from app.config import get_settings


class PDFParserService:
    """
    Service for extracting text from PDF documents.
    
    Supports:
    - PDF files via LlamaParse (for tenders - advanced parsing)
    - PDF files via PyMuPDF (for company documents - local parsing)
    """
    
    SUPPORTED_EXTENSIONS = ['.pdf']
    
    _llama_parser: LlamaParse = None  # Deprecated: do not use cache
    
    @classmethod
    def _create_llama_parser(cls) -> LlamaParse:
        """Create a NEW LlamaParse client (no caching to avoid event loop issues)."""
        settings = get_settings()
        return LlamaParse(
            api_key=settings.llama_cloud_api_key,
            result_type="markdown",
            verbose=False
        )
    
    @classmethod
    def _parse_with_llamaparse_sync(cls, tmp_path: str) -> list:
        """
        Synchronous wrapper for LlamaParse parsing.
        Creates fresh event loop AND fresh parser instance.
        """
        import asyncio
        
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Create a NEW parser instance each time (no caching!)
            # This avoids the "Event loop is closed" error
            parser = cls._create_llama_parser()
            return parser.load_data(tmp_path)
        finally:
            loop.close()
    
    @classmethod
    async def _extract_text_with_llamaparse(cls, file_content: bytes, filename: str) -> str:
        """
        Extracts text from PDF using LlamaParse API.
        
        Args:
            file_content: Raw bytes of the PDF file
            filename: Original filename
            
        Returns:
            Extracted text in markdown format
        """
        import asyncio
        
        # LlamaParse requires a file path, so we save to temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_path = tmp_file.name
        
        try:
            # Run LlamaParse in a separate thread to avoid event loop conflicts
            # LlamaParse.load_data() uses its own event loop internally
            documents = await asyncio.to_thread(cls._parse_with_llamaparse_sync, tmp_path)
            
            # Combine all document texts
            text_parts = []
            for i, doc in enumerate(documents, start=1):
                if doc.text.strip():
                    text_parts.append(f"--- Page {i} ---\n{doc.text}")
            
            return "\n\n".join(text_parts)
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    @classmethod
    def _extract_text_from_pdf(cls, file_content: bytes) -> str:
        """
        Extracts text from PDF file content using PyMuPDF (local).
        Used for company documents.
        
        Args:
            file_content: Raw bytes of the PDF file
            
        Returns:
            Extracted text from all pages
        """
        text_parts = []
        
        # Open PDF from bytes
        with fitz.open(stream=file_content, filetype="pdf") as doc:
            for page_num, page in enumerate(doc, start=1):
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}")
        
        return "\n\n".join(text_parts)
    
    @classmethod
    def _is_pdf(cls, filename: str) -> bool:
        """Check if filename has PDF extension."""
        return filename.lower().endswith('.pdf')
    
    @classmethod
    async def extract_text_from_storage(
        cls,
        file_path: str,
        filename: str,
        bucket: str = None,
        use_llamaparse: bool = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Downloads a file from Supabase Storage and extracts text.
        
        Args:
            file_path: Path to file in Storage (e.g., "{id}/{uuid}_{filename}")
            filename: Original filename (to determine file type)
            bucket: Storage bucket name (defaults to BUCKET_TENDERS)
            use_llamaparse: If True, use LlamaParse API. If None, auto-detect based on bucket.
            
        Returns:
            Tuple of (success: bool, extracted_text: Optional[str], error: Optional[str])
        """
        try:
            # Check if file type is supported
            if not cls._is_pdf(filename):
                return False, None, f"Unsupported file type: {filename}. Only PDF is currently supported."
            
            # Download file from Supabase Storage
            client = SupabaseService.get_client()
            
            # Use provided bucket or default to tenders
            storage_bucket = bucket or StorageService.BUCKET_TENDERS
            
            # Download file content
            file_content = client.storage.from_(storage_bucket).download(file_path)
            
            if not file_content:
                return False, None, f"Failed to download file: {file_path}"
            
            # Determine which parser to use
            # LlamaParse for tenders (more accurate), PyMuPDF for companies (faster/local)
            should_use_llamaparse = use_llamaparse
            if should_use_llamaparse is None:
                should_use_llamaparse = (storage_bucket == StorageService.BUCKET_TENDERS)
            
            # Extract text based on parser choice
            if should_use_llamaparse:
                extracted_text = await cls._extract_text_with_llamaparse(file_content, filename)
            else:
                extracted_text = cls._extract_text_from_pdf(file_content)
            
            if not extracted_text.strip():
                return True, "", None  # Success but empty text (e.g., scanned PDF without OCR)
            
            return True, extracted_text, None
            
        except Exception as e:
            return False, None, f"Text extraction failed: {str(e)}"
    
    @classmethod
    async def extract_and_save_for_tender(cls, cig: str, force: bool = False) -> Tuple[int, int, list]:
        """
        Extracts text from all documents of a tender and saves to database.
        
        Args:
            cig: Codice Identificativo Gara
            force: If True, re-extract even if text already exists
            
        Returns:
            Tuple of (success_count: int, fail_count: int, errors: list)
        """
        client = SupabaseService.get_client()
        
        # Get tender
        tender_result = client.table("tenders").select("id").eq("cig", cig).execute()
        
        if not tender_result.data:
            return 0, 0, [f"Tender with CIG '{cig}' not found"]
        
        tender_id = tender_result.data[0]["id"]
        
        # Get all documents for this tender
        docs_result = client.table("tender_documents").select("id, name, file_path, extracted_text").eq("tender_id", tender_id).execute()
        
        if not docs_result.data:
            return 0, 0, ["No documents found for this tender"]
        
        success_count = 0
        fail_count = 0
        errors = []
        
        for doc in docs_result.data:
            # Skip if already extracted (unless force is True)
            if doc.get("extracted_text") and not force:
                success_count += 1
                continue
            
            # Extract text
            success, extracted_text, error = await cls.extract_text_from_storage(
                file_path=doc["file_path"],
                filename=doc["name"]
            )
            
            if success:
                # Save to database
                try:
                    client.table("tender_documents").update({
                        "extracted_text": extracted_text
                    }).eq("id", doc["id"]).execute()
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    errors.append(f"Failed to save text for {doc['name']}: {str(e)}")
            else:
                fail_count += 1
                errors.append(f"{doc['name']}: {error}")
        
        return success_count, fail_count, errors
    
    @classmethod
    async def extract_and_save_for_company(
        cls,
        company_id: str,
        force: bool = False
    ) -> Tuple[int, int, list]:
        """
        Extracts text from all documents of a company and saves to database.
        
        Args:
            company_id: UUID of the company (same as user_id in this schema)
            force: If True, re-extract even if text already exists
            
        Returns:
            Tuple of (success_count: int, fail_count: int, errors: list)
        """
        client = SupabaseService.get_client()
        
        # Verify company exists
        company_result = client.table("companies").select("id").eq("id", company_id).execute()
        
        if not company_result.data:
            return 0, 0, [f"Company with ID '{company_id}' not found"]
        
        # Get all documents for this company
        docs_result = client.table("company_documents").select(
            "id, name, file_path, extracted_text"
        ).eq("company_id", company_id).execute()
        
        if not docs_result.data:
            return 0, 0, ["No documents found for this company"]
        
        success_count = 0
        fail_count = 0
        errors = []
        
        for doc in docs_result.data:
            # Skip if already extracted (unless force is True)
            if doc.get("extracted_text") and not force:
                success_count += 1
                continue
            
            # Extract text from companies bucket
            success, extracted_text, error = await cls.extract_text_from_storage(
                file_path=doc["file_path"],
                filename=doc["name"],
                bucket=StorageService.BUCKET_COMPANIES
            )
            
            if success:
                # Save to database
                try:
                    client.table("company_documents").update({
                        "extracted_text": extracted_text
                    }).eq("id", doc["id"]).execute()
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    errors.append(f"Failed to save text for {doc['name']}: {str(e)}")
            else:
                fail_count += 1
                errors.append(f"{doc['name']}: {error}")
        
        return success_count, fail_count, errors
