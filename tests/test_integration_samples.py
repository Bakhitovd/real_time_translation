"""
Integration tests for Module 6: System Audio Capture with real audio samples.
Tests M4A file processing, format conversion, and speech detection.
"""

import pytest
import os
import logging
from pathlib import Path
import soundfile as sf
from app.system_audio_capture import (
    SystemAudioCaptureHandler,
    create_system_audio_handler,
    process_system_audio
)

# Configure logging for test output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test data paths
INPUT_AUDIO_DIR = Path("input_audio")
OUTPUT_AUDIO_DIR = Path("output_audio")
OUTPUT_AUDIO_DIR.mkdir(exist_ok=True)

class TestSampleFileProcessing:
    """Test Module 6 with real audio samples."""
    
    @pytest.fixture
    def handler(self):
        """Create SystemAudioCaptureHandler instance."""
        return create_system_audio_handler()
    
    @pytest.fixture
    def sample_files(self):
        """Get available sample files."""
        files = {}
        for sample_file in INPUT_AUDIO_DIR.glob("*.m4a"):
            if "en" in sample_file.name:
                files["english"] = sample_file
            elif "ru" in sample_file.name:
                files["russian"] = sample_file
        return files
    
    def test_sample_files_exist(self, sample_files):
        """Verify sample files are available for testing."""
        assert len(sample_files) > 0, "No sample files found in input_audio/"
        logger.info(f"Found sample files: {list(sample_files.keys())}")
        
        for lang, file_path in sample_files.items():
            assert file_path.exists(), f"Sample file not found: {file_path}"
            assert file_path.suffix == ".m4a", f"Expected M4A format: {file_path}"
            logger.info(f"{lang.capitalize()} sample: {file_path.name}")
    
    def test_m4a_format_validation(self, handler, sample_files):
        """Test M4A format detection and validation."""
        for lang, file_path in sample_files.items():
            logger.info(f"Testing M4A validation for {lang} sample...")
            
            # Read file data
            with open(file_path, "rb") as f:
                audio_data = f.read()
            
            # Test format validation
            is_valid = handler.validate_audio_data(audio_data)
            assert is_valid, f"M4A validation failed for {lang} sample"
            
            # Test audio info extraction
            audio_info = handler.extract_audio_info(audio_data)
            assert audio_info is not None, f"Audio info extraction failed for {lang}"
            assert audio_info.get("format"), f"Format not detected for {lang}"
            assert audio_info.get("duration_seconds", 0) > 0, f"Duration not detected for {lang}"
            
            logger.info(f"{lang.capitalize()} sample info: {audio_info}")
    
    def test_m4a_to_wav_conversion(self, handler, sample_files):
        """Test M4A to WAV conversion with quality validation."""
        for lang, file_path in sample_files.items():
            logger.info(f"Testing M4A→WAV conversion for {lang} sample...")
            
            # Read source file
            with open(file_path, "rb") as f:
                source_audio = f.read()
            
            # Convert to WAV
            wav_audio = handler.convert_to_wav(source_audio)
            assert wav_audio is not None, f"WAV conversion failed for {lang}"
            assert len(wav_audio) > 0, f"Empty WAV output for {lang}"
            
            # Save converted WAV for manual verification
            output_path = OUTPUT_AUDIO_DIR / f"converted_{lang}_sample.wav"
            with open(output_path, "wb") as f:
                f.write(wav_audio)
            
            logger.info(f"Saved converted WAV: {output_path}")
            
            # Validate WAV format and properties
            try:
                import io
                wav_io = io.BytesIO(wav_audio)
                audio_array, sample_rate = sf.read(wav_io)
                
                # Check target format (16kHz mono)
                assert sample_rate == 16000, f"Expected 16kHz, got {sample_rate}Hz for {lang}"
                
                # Check if mono (1D array) or stereo converted to mono
                if len(audio_array.shape) > 1:
                    assert audio_array.shape[1] == 1, f"Expected mono output for {lang}"
                
                duration = len(audio_array) / sample_rate
                assert duration > 0, f"Invalid audio duration for {lang}"
                
                logger.info(f"{lang.capitalize()} WAV: {sample_rate}Hz, {duration:.1f}s, {len(audio_array)} samples")
                
            except Exception as e:
                pytest.fail(f"WAV validation failed for {lang}: {e}")
    
    def test_speech_activity_detection(self, handler, sample_files):
        """Test speech detection on converted audio samples."""
        for lang, file_path in sample_files.items():
            logger.info(f"Testing speech detection for {lang} sample...")
            
            # Read and convert audio
            with open(file_path, "rb") as f:
                source_audio = f.read()
            
            wav_audio = handler.convert_to_wav(source_audio)
            
            # Test speech detection with multiple sensitivity levels
            sensitivities = [0.3, 0.5, 0.8]
            
            for sensitivity in sensitivities:
                has_speech = handler.detect_speech_activity(wav_audio, sensitivity)
                
                # Expect speech in 1-minute samples at reasonable sensitivity
                if sensitivity >= 0.5:
                    assert has_speech, f"No speech detected for {lang} at sensitivity {sensitivity}"
                
                logger.info(f"{lang.capitalize()} speech detected at {sensitivity}: {has_speech}")
    
    def test_full_process_system_audio(self, sample_files):
        """Test complete system audio processing workflow."""
        for lang, file_path in sample_files.items():
            logger.info(f"Testing full processing workflow for {lang} sample...")
            
            # Read source file
            with open(file_path, "rb") as f:
                audio_data = f.read()
            
            # Process through system audio handler
            result = process_system_audio(audio_data, sensitivity=0.7)
            
            assert result is not None, f"System audio processing failed for {lang}"
            assert result.get("success"), f"Processing not successful for {lang}: {result.get('error')}"
            assert result.get("wav_audio"), f"No WAV output for {lang}"
            assert result.get("has_speech"), f"No speech detected for {lang}"
            
            # Save processed result
            output_path = OUTPUT_AUDIO_DIR / f"processed_{lang}_sample.wav"
            with open(output_path, "wb") as f:
                f.write(result["wav_audio"])
            
            logger.info(f"Full processing result for {lang}: {result.get('metadata', {})}")
            logger.info(f"Saved processed audio: {output_path}")
    
    def test_performance_benchmarks(self, handler, sample_files):
        """Test processing performance with timing benchmarks."""
        import time
        
        for lang, file_path in sample_files.items():
            logger.info(f"Benchmarking {lang} sample processing...")
            
            with open(file_path, "rb") as f:
                audio_data = f.read()
            
            # Benchmark conversion time
            start_time = time.time()
            wav_audio = handler.convert_to_wav(audio_data)
            conversion_time = time.time() - start_time
            
            # Benchmark speech detection time  
            start_time = time.time()
            has_speech = handler.detect_speech_activity(wav_audio)
            detection_time = time.time() - start_time
            
            # Benchmark full processing
            start_time = time.time()
            result = process_system_audio(audio_data)
            total_time = time.time() - start_time
            
            logger.info(f"{lang.capitalize()} performance:")
            logger.info(f"  Conversion: {conversion_time:.3f}s")
            logger.info(f"  Detection:  {detection_time:.3f}s") 
            logger.info(f"  Total:      {total_time:.3f}s")
            
            # Performance assertions (reasonable for 1-minute audio)
            assert conversion_time < 10.0, f"Conversion too slow for {lang}: {conversion_time:.3f}s"
            assert detection_time < 1.0, f"Detection too slow for {lang}: {detection_time:.3f}s"
            assert total_time < 15.0, f"Total processing too slow for {lang}: {total_time:.3f}s"


if __name__ == "__main__":
    """Run integration tests directly."""
    pytest.main([__file__, "-v", "-s"])
