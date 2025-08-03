#!/usr/bin/env python3
"""
Quick GPU performance test for M2M service
"""
import torch
import time
import requests
import json

def test_pytorch_gpu():
    """Test basic PyTorch GPU functionality."""
    print("=== PyTorch GPU Test ===")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
        print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        
        # Simple GPU speed test
        print("\n=== GPU Speed Test ===")
        device = torch.device("cuda")
        size = 1000
        
        # GPU test
        start = time.time()
        a = torch.randn(size, size, device=device)
        b = torch.randn(size, size, device=device)
        c = torch.matmul(a, b)
        torch.cuda.synchronize()
        gpu_time = time.time() - start
        
        # CPU test
        device_cpu = torch.device("cpu")
        start = time.time()
        a_cpu = torch.randn(size, size, device=device_cpu)
        b_cpu = torch.randn(size, size, device=device_cpu)
        c_cpu = torch.matmul(a_cpu, b_cpu)
        cpu_time = time.time() - start
        
        print(f"GPU matrix multiplication ({size}x{size}): {gpu_time:.3f}s")
        print(f"CPU matrix multiplication ({size}x{size}): {cpu_time:.3f}s")
        print(f"GPU speedup: {cpu_time/gpu_time:.1f}x faster")
    
    else:
        print("❌ CUDA not available!")

def test_m2m_service():
    """Test M2M service if running."""
    print("\n=== M2M Service Test ===")
    try:
        # Test health endpoint
        response = requests.get("http://localhost:8001/health", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print("✅ M2M service is running")
            print(f"GPU available in service: {stats.get('gpu_available', False)}")
            print(f"GPU memory allocated: {stats.get('gpu_memory_allocated', 0) / 1024**2:.1f} MB")
            print(f"Model loaded: {stats.get('model_loaded', False)}")
            
            # Test translation
            print("\n=== Translation Speed Test ===")
            test_data = {
                "session_id": "test_session",
                "text": "approach",
                "source_lang": "en",
                "target_lang": "ru",
                "use_context": False
            }
            
            start = time.time()
            response = requests.post("http://localhost:8001/translate", 
                                   json=test_data, timeout=10)
            total_time = time.time() - start
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Translation successful in {total_time:.3f}s")
                print(f"Text: '{test_data['text']}'")
                print(f"Translation: '{result['translation']}'")
                print(f"Service latency: {result['metadata']['latency_ms']:.1f}ms")
            else:
                print(f"❌ Translation failed: {response.status_code}")
        else:
            print(f"❌ M2M service not responding: {response.status_code}")
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to M2M service: {e}")
        print("Make sure the service is running on http://localhost:8001")

if __name__ == "__main__":
    test_pytorch_gpu()
    test_m2m_service()
