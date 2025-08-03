"""
Test suite for temp_file_manager module.
Comprehensive testing with pytest and hypothesis for robust file handling.
"""

import pytest
import os
import time
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, mock_open
from hypothesis import given, strategies as st, settings

from app.temp_file_manager import (
    create_unique_temp_name,
    safe_file_delete,
    managed_temp_file,
    write_bytes_to_temp_file,
    cleanup_temp_files_by_prefix,
    TemporaryFileError,
    WindowsFileLockError
)


class TestCreateUniqueTempName:
    """Test unique temporary filename generation."""
    
    @given(
        suffix=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))).map(lambda x: f".{x}"),
        prefix=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
    )
    @settings(max_examples=25)
    def test_unique_name_generation(self, suffix, prefix):
        """Test that unique names are generated with various suffixes and prefixes."""
        name1 = create_unique_temp_name(suffix, prefix)
        name2 = create_unique_temp_name(suffix, prefix)
        
        assert name1 != name2
        assert name1.startswith(prefix)
        assert name1.endswith(suffix)
        assert name2.startswith(prefix)
        assert name2.endswith(suffix)
    
    def test_default_parameters(self):
        """Test default suffix and prefix."""
        name = create_unique_temp_name()
        assert name.startswith("rtt_")
        assert name.endswith(".tmp")
    
    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=25)
    def test_concurrent_name_generation(self, thread_count):
        """Test that concurrent name generation produces unique names."""
        names = []
        results = []
        
        def generate_name():
            name = create_unique_temp_name()
            results.append(name)
        
        # Use minimum of thread_count or 10 to avoid excessive resource usage
        actual_thread_count = min(thread_count, 10)
        threads = [threading.Thread(target=generate_name) for _ in range(actual_thread_count)]
        
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # All names should be unique
        assert len(results) == len(set(results))


class TestSafeFileDelete:
    """Test safe file deletion with retry logic."""
    
    def test_delete_nonexistent_file(self):
        """Test deleting a file that doesn't exist."""
        result = safe_file_delete("/nonexistent/path/file.txt")
        assert result is True
    
    def test_delete_valid_file(self):
        """Test deleting a valid temporary file."""
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            temp_path = tf.name
            tf.write(b"test data")
        
        assert os.path.exists(temp_path)
        result = safe_file_delete(temp_path)
        assert result is True
        assert not os.path.exists(temp_path)
    
    @patch('os.unlink')
    def test_permission_error_retry(self, mock_unlink):
        """Test retry logic for permission errors."""
        mock_unlink.side_effect = [
            PermissionError("File locked"),
            PermissionError("Still locked"),
            None  # Success on third try
        ]
        
        with tempfile.NamedTemporaryFile() as tf:
            result = safe_file_delete(tf.name, max_retries=3, base_delay=0.001)
            assert result is True
            assert mock_unlink.call_count == 3
    
    @patch('os.unlink')
    def test_permission_error_max_retries(self, mock_unlink):
        """Test that WindowsFileLockError is raised after max retries."""
        mock_unlink.side_effect = PermissionError("Persistent lock")
        
        with tempfile.NamedTemporaryFile() as tf:
            with pytest.raises(WindowsFileLockError):
                safe_file_delete(tf.name, max_retries=2, base_delay=0.001)
    
    @patch('os.unlink')
    def test_file_not_found_during_retry(self, mock_unlink):
        """Test handling of FileNotFoundError during retry."""
        mock_unlink.side_effect = FileNotFoundError("Already deleted")
        
        with tempfile.NamedTemporaryFile() as tf:
            result = safe_file_delete(tf.name)
            assert result is True
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=25)
    def test_delete_with_various_paths(self, path_component):
        """Test file deletion with various path formats."""
        # Create a safe temporary file path
        temp_dir = tempfile.mkdtemp()
        safe_filename = "".join(c for c in path_component if c.isalnum() or c in "._-")[:50]
        if not safe_filename:
            safe_filename = "test"
        
        temp_path = os.path.join(temp_dir, f"{safe_filename}.tmp")
        
        try:
            # Create the file
            with open(temp_path, 'w') as f:
                f.write("test")
            
            result = safe_file_delete(temp_path)
            assert result is True
            assert not os.path.exists(temp_path)
        finally:
            # Cleanup directory
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)


class TestManagedTempFile:
    """Test managed temporary file context manager."""
    
    def test_basic_context_manager(self):
        """Test basic functionality of managed temp file."""
        with managed_temp_file(suffix=".test", prefix="test_") as temp_path:
            assert os.path.exists(temp_path)
            assert temp_path.endswith(".test")
            assert "test_" in os.path.basename(temp_path)
            
            # Write some data
            with open(temp_path, 'w') as f:
                f.write("test data")
        
        # File should be cleaned up
        assert not os.path.exists(temp_path)
    
    def test_no_delete_on_exit(self):
        """Test keeping file when delete_on_exit=False."""
        temp_path = None
        try:
            with managed_temp_file(delete_on_exit=False) as path:
                temp_path = path
                assert os.path.exists(path)
            
            # File should still exist
            assert os.path.exists(temp_path)
        finally:
            # Manual cleanup
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_exception_in_context(self):
        """Test that file is cleaned up even when exception occurs."""
        temp_path = None
        with pytest.raises(ValueError, match="Test exception"):
            with managed_temp_file() as path:
                temp_path = path
                assert os.path.exists(path)
                raise ValueError("Test exception")
        
        # File should still be cleaned up
        assert not os.path.exists(temp_path)
    
    @patch('app.temp_file_manager.safe_file_delete')
    def test_cleanup_failure_handling(self, mock_delete):
        """Test handling of cleanup failures."""
        mock_delete.side_effect = WindowsFileLockError("Cannot delete")
        
        # Should not raise exception even if cleanup fails
        with managed_temp_file() as temp_path:
            assert os.path.exists(temp_path)
        
        mock_delete.assert_called_once()


class TestWriteBytesToTempFile:
    """Test writing bytes to temporary files."""
    
    @given(st.binary(min_size=0, max_size=1024))
    @settings(max_examples=25)
    def test_write_various_byte_data(self, data):
        """Test writing various byte patterns to temp files."""
        temp_path = write_bytes_to_temp_file(data, suffix=".bin", prefix="test_")
        
        try:
            assert os.path.exists(temp_path)
            assert ".bin" in temp_path
            assert "test_" in os.path.basename(temp_path)
            
            with open(temp_path, 'rb') as f:
                read_data = f.read()
            
            assert read_data == data
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_empty_data(self):
        """Test writing empty data."""
        temp_path = write_bytes_to_temp_file(b"")
        
        try:
            assert os.path.exists(temp_path)
            assert os.path.getsize(temp_path) == 0
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    @patch('builtins.open', side_effect=OSError("Write failed"))
    def test_write_failure(self, mock_open):
        """Test handling of write failures."""
        with pytest.raises(TemporaryFileError, match="Failed to write bytes"):
            write_bytes_to_temp_file(b"test data")


class TestCleanupTempFilesByPrefix:
    """Test cleanup of old temporary files."""
    
    def test_cleanup_old_files(self):
        """Test cleanup of files older than specified age."""
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Create some test files
            old_file = os.path.join(temp_dir, "test_old_file.tmp")
            new_file = os.path.join(temp_dir, "test_new_file.tmp")
            other_file = os.path.join(temp_dir, "other_file.tmp")
            
            # Create files
            for filepath in [old_file, new_file, other_file]:
                with open(filepath, 'w') as f:
                    f.write("test")
            
            # Make old_file appear old by modifying its timestamp
            old_time = time.time() - (25 * 3600)  # 25 hours ago
            os.utime(old_file, (old_time, old_time))
            
            with patch('tempfile.gettempdir', return_value=temp_dir):
                cleaned = cleanup_temp_files_by_prefix("test_", max_age_hours=24)
            
            assert cleaned == 1  # Only old_file should be cleaned
            assert not os.path.exists(old_file)
            assert os.path.exists(new_file)
            assert os.path.exists(other_file)  # Different prefix
            
        finally:
            # Cleanup
            for filepath in [new_file, other_file]:
                if os.path.exists(filepath):
                    os.unlink(filepath)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
    
    def test_cleanup_no_matching_files(self):
        """Test cleanup when no files match the prefix."""
        cleaned = cleanup_temp_files_by_prefix("nonexistent_prefix_")
        assert cleaned == 0
    
    @patch('tempfile.gettempdir')
    @patch('os.listdir', side_effect=OSError("Access denied"))
    def test_cleanup_directory_access_error(self, mock_listdir, mock_gettempdir):
        """Test handling of directory access errors."""
        mock_gettempdir.return_value = "/inaccessible"
        cleaned = cleanup_temp_files_by_prefix("test_")
        assert cleaned == 0


class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_full_temp_file_workflow(self):
        """Test complete workflow from creation to cleanup."""
        test_data = b"Integration test data"
        
        # Step 1: Write data to temp file
        temp_path = write_bytes_to_temp_file(test_data, suffix=".integration", prefix="workflow_")
        
        try:
            # Step 2: Verify file exists and has correct data
            assert os.path.exists(temp_path)
            with open(temp_path, 'rb') as f:
                assert f.read() == test_data
            
            # Step 3: Test safe deletion
            result = safe_file_delete(temp_path)
            assert result is True
            assert not os.path.exists(temp_path)
            
        finally:
            # Ensure cleanup even if test fails
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    def test_concurrent_file_operations(self):
        """Test concurrent file operations for thread safety."""
        results = []
        errors = []
        
        def worker():
            try:
                # Each thread creates and cleans up its own temp file
                with managed_temp_file(prefix="concurrent_") as temp_path:
                    with open(temp_path, 'w') as f:
                        f.write(f"Thread {threading.current_thread().ident}")
                    results.append(temp_path)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        assert len(set(results)) == 5  # All paths should be unique
        
        # All files should be cleaned up
        for temp_path in results:
            assert not os.path.exists(temp_path)


# Parametrized tests for edge cases
@pytest.mark.parametrize("max_retries,base_delay", [
    (1, 0.001),
    (3, 0.01),
    (5, 0.1),
    (10, 0.001)
])
def test_safe_delete_retry_parameters(max_retries, base_delay):
    """Test safe_file_delete with various retry parameters."""
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        temp_path = tf.name
    
    result = safe_file_delete(temp_path, max_retries=max_retries, base_delay=base_delay)
    assert result is True
    assert not os.path.exists(temp_path)


@pytest.mark.parametrize("suffix,prefix", [
    (".wav", "asr_"),
    (".mp3", "audio_"),
    (".json", "config_"),
    (".tmp", "temp_"),
    ("", "no_suffix_")
])
def test_managed_temp_file_extensions(suffix, prefix):
    """Test managed temp file with various extensions and prefixes."""
    with managed_temp_file(suffix=suffix, prefix=prefix) as temp_path:
        assert os.path.exists(temp_path)
        if suffix:
            assert temp_path.endswith(suffix)
        assert prefix in os.path.basename(temp_path)
    
    assert not os.path.exists(temp_path)
