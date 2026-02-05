"""
Supabase Storage Service
Handles file uploads to Supabase Storage buckets.
"""

import uuid
from typing import Optional
from fastapi import UploadFile
from app.services.supabase_client import SupabaseService


class StorageService:
    """
    Service for managing file uploads to Supabase Storage.
    
    Buckets:
        - tenders: Documents related to tender bids
        - companies: Company documents for knowledge base
    """
    
    BUCKET_TENDERS = "tenders"
    BUCKET_COMPANIES = "companies"
    
    @classmethod
    def _generate_unique_filename(cls, original_filename: str) -> str:
        """
        Generates a unique filename using UUID prefix.
        
        Args:
            original_filename: The original filename from upload
            
        Returns:
            Unique filename in format: {uuid}_{sanitized_filename}
        """
        unique_id = uuid.uuid4().hex[:8]
        # Sanitize filename: remove/replace chars not allowed by Supabase Storage
        sanitized = cls._sanitize_filename(original_filename)
        return f"{unique_id}_{sanitized}"
    
    @classmethod
    def _sanitize_filename(cls, filename: str) -> str:
        """
        Sanitize filename by removing/replacing characters not allowed by Supabase Storage.
        
        Supabase doesn't allow: [ ] { } | \\ ^ ` and accented characters in keys.
        """
        import re
        import unicodedata
        
        # Step 1: Transliterate accented characters to ASCII (à→a, è→e, ù→u, etc.)
        # NFD decomposes characters (à = a + combining accent)
        # Then we filter out the combining marks
        normalized = unicodedata.normalize('NFD', filename)
        ascii_filename = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # Step 2: Replace problematic special characters with underscores
        sanitized = re.sub(r'[\[\]\{\}\|\\\^`<>]', '_', ascii_filename)
        
        # Step 3: Replace multiple underscores with single
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Step 4: Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        return sanitized
    
    @classmethod
    async def upload_tender_file(
        cls,
        file: UploadFile,
        tender_id: str
    ) -> tuple[bool, str, Optional[str]]:
        """
        Uploads a file to the tenders bucket.
        
        Args:
            file: The uploaded file
            tender_id: UUID of the tender (used as folder name)
            
        Returns:
            Tuple of (success: bool, file_path: str, error: Optional[str])
        """
        try:
            client = SupabaseService.get_client()
            
            # Generate unique filename
            unique_filename = cls._generate_unique_filename(file.filename)
            
            # Build path: tenders/{tender_id}/{unique_filename}
            file_path = f"{tender_id}/{unique_filename}"
            
            # Read file content
            content = await file.read()
            
            # Upload to Supabase Storage
            result = client.storage.from_(cls.BUCKET_TENDERS).upload(
                path=file_path,
                file=content,
                file_options={
                    "content-type": file.content_type or "application/octet-stream"
                }
            )
            
            return True, file_path, None
            
        except Exception as e:
            error_msg = str(e)
            return False, "", f"Upload failed: {error_msg}"
    
    @classmethod
    async def delete_tender_file(cls, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Deletes a file from the tenders bucket.
        
        Args:
            file_path: Path to the file in storage
            
        Returns:
            Tuple of (success: bool, error: Optional[str])
        """
        try:
            client = SupabaseService.get_client()
            client.storage.from_(cls.BUCKET_TENDERS).remove([file_path])
            return True, None
        except Exception as e:
            return False, str(e)
    
    @classmethod
    async def upload_company_file(
        cls,
        file: UploadFile,
        company_id: str
    ) -> tuple[bool, str, Optional[str]]:
        """
        Uploads a file to the companies bucket.
        
        Args:
            file: The uploaded file
            company_id: UUID of the company (used as folder name)
            
        Returns:
            Tuple of (success: bool, file_path: str, error: Optional[str])
        """
        try:
            client = SupabaseService.get_client()
            
            # Generate unique filename
            unique_filename = cls._generate_unique_filename(file.filename)
            
            # Build path: companies/{company_id}/{unique_filename}
            file_path = f"{company_id}/{unique_filename}"
            
            # Read file content
            content = await file.read()
            
            # Upload to Supabase Storage
            result = client.storage.from_(cls.BUCKET_COMPANIES).upload(
                path=file_path,
                file=content,
                file_options={
                    "content-type": file.content_type or "application/octet-stream"
                }
            )
            
            return True, file_path, None
            
        except Exception as e:
            error_msg = str(e)
            return False, "", f"Upload failed: {error_msg}"

