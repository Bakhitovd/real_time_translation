"""
Temporary File Manager Module
Provides robust temporary file handling with Windows-compatible cleanup.
"""

import os
import time
import tempfile
import logging
import uuid
import contextlib
from typing import Optional, Generator, Union
from pathlib import Path


class TemporaryFileError(Exception):
    """Custom exception for temporary file operations."""
    pass


class WindowsFileLockError(TemporaryFileError):
    """Exception for Windows-specific file locking issues."""
    pass


def create_unique_temp_name(suffix: str = ".tmp", prefix: str = "rtt_") -> str:
    """Generate a unique temporary filename.
    
    Args:
        suffix: File extension (default: .tmp)
        prefix: Filename prefix (default: rtt_)
        
    Returns:
        Unique temporary filename
    """
    unique_id = str(uuid.uuid4())[:8]
    timestamp = str(int(time.time() * 1000))[-6:]  # Last 6 digits of milliseconds
    return f"{prefix}{timestamp}_{unique_id}{suffix}"


def safe_file_delete(file_path: Union[str, Path], max_retries: int = 5, base_delay: float = 0.05) -> bool:
    """Safely delete a file with retry logic for Windows file locking.
    
    Args:
        file_path: Path to file to delete
        max_retries: Maximum number of deletion attempts
        base_delay: Base delay between retries (exponential backoff)
        
    Returns:
        True if file was deleted successfully, False otherwise
    """
    if not file_path or not os.path.exists(file_path):
        return True
        
    file_path = str(file_path)
    
    for attempt in range(max_retries):
        try:
            os.unlink(file_path)
            logging.debug(f"[TempFile] Successfully deleted: {file_path}")
            return True
            
        except PermissionError as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logging.debug(f"[TempFile] File locked, retrying deletion in {delay:.3f}s (attempt {attempt + 1}/{max_retries}): {file_path}")
                time.sleep(delay)
            else:
                logging.warning(f"[TempFile] Failed to delete file after {max_retries} attempts: {file_path} - {e}")
                raise WindowsFileLockError(f"Cannot delete file {file_path}: {e}")
                
        except FileNotFoundError:
            # File already deleted by another process
            logging.debug(f"[TempFile] File already deleted: {file_path}")
            return True
            
        except Exception as e:
            logging.error(f"[TempFile] Unexpected error deleting file {file_path}: {e}")
            return False
            
    return False


@contextlib.contextmanager
def managed_temp_file(suffix: str = ".tmp", prefix: str = "rtt_", 
                     delete_on_exit: bool = True) -> Generator[str, None, None]:
    """Context manager for temporary files with guaranteed cleanup.
    
    Args:
        suffix: File extension
        prefix: Filename prefix
        delete_on_exit: Whether to delete file when exiting context
        
    Yields:
        Path to temporary file
        
    Raises:
        TemporaryFileError: If file creation fails
    """
    temp_dir = tempfile.gettempdir()
    temp_name = create_unique_temp_name(suffix, prefix)
    temp_path = os.path.join(temp_dir, temp_name)
    
    try:
        # Ensure the file exists by touching it
        Path(temp_path).touch()
        logging.debug(f"[TempFile] Created managed temp file: {temp_path}")
    except Exception as e:
        logging.error(f"[TempFile] Failed to create temp file: {e}")
        raise TemporaryFileError(f"Failed to create temporary file: {e}")
    
    try:
        yield temp_path
    finally:
        # Always attempt cleanup, regardless of what happened in the context
        if delete_on_exit and os.path.exists(temp_path):
            try:
                safe_file_delete(temp_path)
            except WindowsFileLockError:
                # Log warning but don't fail the operation
                logging.warning(f"[TempFile] Could not clean up temp file (will be cleaned by OS): {temp_path}")


def write_bytes_to_temp_file(data: bytes, suffix: str = ".tmp", prefix: str = "rtt_") -> str:
    """Write bytes to a temporary file and return the path.
    
    Args:
        data: Bytes to write
        suffix: File extension
        prefix: Filename prefix
        
    Returns:
        Path to temporary file
        
    Raises:
        TemporaryFileError: If write operation fails
    """
    temp_dir = tempfile.gettempdir()
    temp_name = create_unique_temp_name(suffix, prefix)
    temp_path = os.path.join(temp_dir, temp_name)
    
    try:
        with open(temp_path, 'wb') as f:
            f.write(data)
        logging.debug(f"[TempFile] Wrote {len(data)} bytes to: {temp_path}")
        return temp_path
        
    except Exception as e:
        # Clean up on failure
        if os.path.exists(temp_path):
            safe_file_delete(temp_path)
        raise TemporaryFileError(f"Failed to write bytes to temp file: {e}")


def cleanup_temp_files_by_prefix(prefix: str = "rtt_", max_age_hours: int = 24) -> int:
    """Clean up old temporary files with specified prefix.
    
    Args:
        prefix: Filename prefix to match
        max_age_hours: Maximum age in hours before cleanup
        
    Returns:
        Number of files cleaned up
    """
    temp_dir = tempfile.gettempdir()
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    cleaned_count = 0
    
    try:
        for filename in os.listdir(temp_dir):
            if not filename.startswith(prefix):
                continue
                
            filepath = os.path.join(temp_dir, filename)
            try:
                # Check file age
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    if safe_file_delete(filepath):
                        cleaned_count += 1
                        logging.debug(f"[TempFile] Cleaned up old temp file: {filepath}")
                        
            except (OSError, WindowsFileLockError):
                # Skip files we can't access/delete
                continue
                
    except OSError as e:
        logging.warning(f"[TempFile] Error during temp file cleanup: {e}")
        
    if cleaned_count > 0:
        logging.info(f"[TempFile] Cleaned up {cleaned_count} old temporary files")
        
    return cleaned_count
