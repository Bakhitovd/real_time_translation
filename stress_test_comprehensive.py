#!/usr/bin/env python3
"""
Comprehensive Stress Test Suite for Real-Time Speech Translation Service
Validates claims in project_current_state_report.md
"""
import asyncio
import aiohttp
import time
import statistics
import torch
import json
import subprocess
import threading
import websockets
import concurrent.futures
from typing import List, Dict, Any
import tempfile
import wave
import numpy as np

class SystemStressTest:
    """Comprehensive stress testing for the real-time translation system."""
    
    def __init__(self):
        self.m2m_url = "http://localhost:8001"
        self.ws_url = "ws://localhost:8000/ws"
        self.api_url = "http://localhost:8000"
        self.results = {}
        
    def test_gpu_acceleration(self):
        """Test GPU acceleration performance vs CPU baseline."""
        print("=== GPU Acceleration Stress Test ===")
        
        # Check PyTorch GPU setup
        gpu_available = torch.cuda.is_available()
        print(f"CUDA Available: {gpu_available}")
        
        if gpu_available:
            print(f"GPU Device: {torch.cuda.get_device_name(0)}")
            print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            
            # Matrix multiplication benchmark
            sizes = [100, 500, 1000, 2000]
            gpu_times = []
            cpu_times = []
            
            for size in sizes:
                # GPU test
                device = torch.device("cuda")
                torch.cuda.synchronize()
                start = time.time()
                a = torch.randn(size, size, device=device)
                b = torch.randn(size, size, device=device)
                c = torch.matmul(a, b)
                torch.cuda.synchronize()
                gpu_time = time.time() - start
                gpu_times.append(gpu_time)
                
                # CPU test
                device_cpu = torch.device("cpu")
                start = time.time()
                a_cpu = torch.randn(size, size, device=device_cpu)
                b_cpu = torch.randn(size, size, device=device_cpu)
                c_cpu = torch.matmul(a_cpu, b_cpu)
                cpu_time = time.time() - start
                cpu_times.append(cpu_time)
                
                speedup = cpu_time / gpu_time if gpu_time > 0 else 1
                print(f"Matrix {size}x{size}: GPU={gpu_time:.3f}s, CPU={cpu_time:.3f}s, Speedup={speedup:.1f}x")
            
            # Handle division by zero for very fast GPU operations
            speedups = []
            for i in range(len(sizes)):
                if gpu_times[i] > 0:
                    speedups.append(cpu_times[i]/gpu_times[i])
                else:
                    speedups.append(1.0)  # Default to 1x if GPU time is 0
            
            avg_speedup = statistics.mean(speedups) if speedups else 1.0
            self.results['gpu_acceleration'] = {
                'available': True,
                'average_speedup': avg_speedup,
                'gpu_times': gpu_times,
                'cpu_times': cpu_times
            }
            print(f"Average GPU Speedup: {avg_speedup:.1f}x")
        else:
            self.results['gpu_acceleration'] = {'available': False}
            print("❌ GPU acceleration not available")
    
    async def test_m2m_service_performance(self):
        """Test M2M-100 translation service under load."""
        print("\n=== M2M Translation Service Stress Test ===")
        
        test_texts = [
            "Привет, как дела? Это тест производительности.",
            "Добро пожаловать на нашу встречу. Давайте начнем обсуждение.",
            "Я хочу обсудить важные вопросы по проекту.",
            "Сегодня у нас много работы, но мы справимся.",
            "Спасибо за ваше время и внимание к деталям."
        ]
        
        # Sequential test
        sequential_times = []
        async with aiohttp.ClientSession() as session:
            for i, text in enumerate(test_texts):
                test_data = {
                    "session_id": f"stress_test_{i}",
                    "text": text,
                    "source_lang": "ru",
                    "target_lang": "en",
                    "use_context": False
                }
                
                start = time.time()
                try:
                    async with session.post(f"{self.m2m_url}/translate", json=test_data) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            latency = time.time() - start
                            sequential_times.append(latency)
                            service_latency = result['metadata']['latency_ms']
                            print(f"Text {i+1}: {latency:.3f}s (service: {service_latency:.1f}ms)")
                        else:
                            print(f"❌ Translation {i+1} failed: {resp.status}")
                except Exception as e:
                    print(f"❌ Translation {i+1} error: {e}")
        
        # Concurrent test
        print("\n--- Concurrent Translation Test ---")
        concurrent_times = []
        
        async def translate_concurrent(session, text, session_id):
            test_data = {
                "session_id": f"concurrent_{session_id}",
                "text": text,
                "source_lang": "ru", 
                "target_lang": "en",
                "use_context": False
            }
            
            start = time.time()
            try:
                async with session.post(f"{self.m2m_url}/translate", json=test_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        latency = time.time() - start
                        return latency, result['metadata']['latency_ms']
                    else:
                        return None, None
            except Exception:
                return None, None
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i, text in enumerate(test_texts * 3):  # 15 concurrent requests
                tasks.append(translate_concurrent(session, text, i))
            
            results = await asyncio.gather(*tasks)
            successful = [r for r in results if r[0] is not None]
            concurrent_times = [r[0] for r in successful]
            service_times = [r[1] for r in successful]
        
        print(f"Concurrent translations: {len(successful)}/{len(tasks)} successful")
        if concurrent_times:
            print(f"Concurrent avg latency: {statistics.mean(concurrent_times):.3f}s")
            print(f"Service avg latency: {statistics.mean(service_times):.1f}ms")
        
        self.results['m2m_performance'] = {
            'sequential_times': sequential_times,
            'concurrent_times': concurrent_times,
            'concurrent_success_rate': len(successful) / len(tasks) if tasks else 0,
            'avg_sequential': statistics.mean(sequential_times) if sequential_times else 0,
            'avg_concurrent': statistics.mean(concurrent_times) if concurrent_times else 0
        }
    
    async def test_websocket_concurrent_load(self):
        """Test WebSocket system under concurrent load."""
        print("\n=== WebSocket Concurrent Load Test ===")
        
        # Generate test audio data
        def generate_test_audio():
            duration = 2.0  # 2 seconds
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            # Generate a simple sine wave
            audio_data = np.sin(2 * np.pi * 440 * t) * 0.3  # 440 Hz tone
            
            # Convert to 16-bit PCM
            audio_data_int = (audio_data * 32767).astype(np.int16)
            
            # Create WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                with wave.open(tmp.name, 'w') as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_data_int.tobytes())
                return tmp.name
        
        # Test concurrent WebSocket connections
        connection_times = []
        message_times = []
        
        async def test_websocket_connection(connection_id):
            try:
                start_connect = time.time()
                async with websockets.connect(self.ws_url) as websocket:
                    connect_time = time.time() - start_connect
                    connection_times.append(connect_time)
                    
                    # Send test audio data
                    test_audio_file = generate_test_audio()
                    with open(test_audio_file, 'rb') as f:
                        audio_data = f.read()
                    
                    start_message = time.time()
                    await websocket.send(audio_data)
                    
                    # Wait for response
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        message_time = time.time() - start_message
                        message_times.append(message_time)
                        print(f"Connection {connection_id}: connect={connect_time:.3f}s, process={message_time:.3f}s")
                        return True
                    except asyncio.TimeoutError:
                        print(f"❌ Connection {connection_id}: timeout waiting for response")
                        return False
            except Exception as e:
                print(f"❌ Connection {connection_id} failed: {e}")
                return False
        
        # Test with increasing concurrent connections
        for concurrent_count in [1, 3, 5, 10]:
            print(f"\n--- Testing {concurrent_count} concurrent WebSocket connections ---")
            tasks = [test_websocket_connection(i) for i in range(concurrent_count)]
            
            start_batch = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_time = time.time() - start_batch
            
            successful = sum(1 for r in results if r is True)
            print(f"Batch {concurrent_count}: {successful}/{concurrent_count} successful in {batch_time:.3f}s")
        
        self.results['websocket_load'] = {
            'connection_times': connection_times,
            'message_times': message_times,
            'avg_connection_time': statistics.mean(connection_times) if connection_times else 0,
            'avg_message_time': statistics.mean(message_times) if message_times else 0
        }
    
    def test_latency_compliance(self):
        """Test latency compliance against project claims."""
        print("\n=== Latency Compliance Test ===")
        
        # Project claims: Sub-1800ms end-to-end latency with ≥90% compliance
        target_latency = 1800  # ms
        
        if 'websocket_load' in self.results:
            message_times_ms = [t * 1000 for t in self.results['websocket_load']['message_times']]
            if message_times_ms:
                compliant_count = sum(1 for t in message_times_ms if t <= target_latency)
                compliance_rate = compliant_count / len(message_times_ms)
                
                print(f"Target latency: {target_latency}ms")
                print(f"Average latency: {statistics.mean(message_times_ms):.1f}ms")
                print(f"Compliance rate: {compliance_rate:.1%} ({compliant_count}/{len(message_times_ms)})")
                print(f"P95 latency: {np.percentile(message_times_ms, 95):.1f}ms")
                print(f"P99 latency: {np.percentile(message_times_ms, 99):.1f}ms")
                
                self.results['latency_compliance'] = {
                    'target_ms': target_latency,
                    'average_ms': statistics.mean(message_times_ms),
                    'compliance_rate': compliance_rate,
                    'p95_ms': np.percentile(message_times_ms, 95),
                    'p99_ms': np.percentile(message_times_ms, 99),
                    'meets_target': compliance_rate >= 0.9  # 90% compliance target
                }
                
                if compliance_rate >= 0.9:
                    print("✅ Latency compliance target met")
                else:
                    print("❌ Latency compliance target not met")
    
    def run_pytest_coverage(self):
        """Run pytest to validate test coverage claims."""
        print("\n=== Test Coverage Validation ===")
        
        try:
            result = subprocess.run([
                'python', '-m', 'pytest', '--cov=app', '--cov-report=term-missing', 
                'tests/', '-v'
            ], capture_output=True, text=True, timeout=120)
            
            print("Test execution completed")
            if result.returncode == 0:
                print("✅ All tests passed")
            else:
                print(f"❌ Some tests failed (return code: {result.returncode})")
            
            # Extract coverage information
            coverage_lines = [line for line in result.stdout.split('\n') if 'TOTAL' in line or '%' in line]
            print("\nCoverage Summary:")
            for line in coverage_lines[-5:]:  # Last few lines usually contain summary
                if line.strip():
                    print(line)
                    
            self.results['test_coverage'] = {
                'tests_passed': result.returncode == 0,
                'output': result.stdout[-1000:],  # Last 1000 chars
                'coverage_info': coverage_lines
            }
            
        except subprocess.TimeoutExpired:
            print("❌ Test execution timed out")
            self.results['test_coverage'] = {'tests_passed': False, 'error': 'timeout'}
        except Exception as e:
            print(f"❌ Test execution failed: {e}")
            self.results['test_coverage'] = {'tests_passed': False, 'error': str(e)}
    
    def generate_stress_test_report(self):
        """Generate comprehensive stress test report."""
        print("\n" + "="*60)
        print("COMPREHENSIVE STRESS TEST REPORT")
        print("="*60)
        
        # GPU Acceleration Assessment
        print("\n🔥 GPU ACCELERATION:")
        if self.results.get('gpu_acceleration', {}).get('available'):
            speedup = self.results['gpu_acceleration']['average_speedup']
            print(f"✅ GPU acceleration available with {speedup:.1f}x average speedup")
        else:
            print("❌ GPU acceleration not available")
        
        # M2M Service Performance
        print("\n🔄 M2M SERVICE PERFORMANCE:")
        if 'm2m_performance' in self.results:
            perf = self.results['m2m_performance']
            print(f"Sequential avg: {perf['avg_sequential']:.3f}s")
            print(f"Concurrent avg: {perf['avg_concurrent']:.3f}s")
            print(f"Concurrent success rate: {perf['concurrent_success_rate']:.1%}")
            
            if perf['avg_concurrent'] < 0.4:  # 400ms target per project report
                print("✅ Translation latency meets target (<400ms)")
            else:
                print("❌ Translation latency exceeds target")
        
        # WebSocket Load Performance
        print("\n🌐 WEBSOCKET PERFORMANCE:")
        if 'websocket_load' in self.results:
            ws = self.results['websocket_load']
            print(f"Average connection time: {ws['avg_connection_time']:.3f}s")
            print(f"Average message processing: {ws['avg_message_time']:.3f}s")
        
        # Latency Compliance
        print("\n⏱️ LATENCY COMPLIANCE:")
        if 'latency_compliance' in self.results:
            comp = self.results['latency_compliance']
            print(f"Target: {comp['target_ms']}ms")
            print(f"Average: {comp['average_ms']:.1f}ms")
            print(f"Compliance rate: {comp['compliance_rate']:.1%}")
            print(f"P95: {comp['p95_ms']:.1f}ms, P99: {comp['p99_ms']:.1f}ms")
            
            if comp['meets_target']:
                print("✅ Meets latency compliance target (≥90%)")
            else:
                print("❌ Does not meet latency compliance target")
        
        # Test Coverage
        print("\n🧪 TEST COVERAGE:")
        if 'test_coverage' in self.results:
            if self.results['test_coverage']['tests_passed']:
                print("✅ All tests passed")
            else:
                print("❌ Some tests failed")
        
        # Overall Assessment
        print("\n📊 OVERALL PROJECT ASSESSMENT:")
        
        criteria_met = 0
        total_criteria = 4
        
        # GPU acceleration
        if self.results.get('gpu_acceleration', {}).get('available'):
            criteria_met += 1
            print("✅ GPU acceleration working")
        else:
            print("❌ GPU acceleration not working")
        
        # Translation performance
        if self.results.get('m2m_performance', {}).get('avg_concurrent', 1) < 0.4:
            criteria_met += 1
            print("✅ Translation service meets performance targets")
        else:
            print("❌ Translation service performance below target")
        
        # Latency compliance
        if self.results.get('latency_compliance', {}).get('meets_target', False):
            criteria_met += 1
            print("✅ System meets latency compliance targets")
        else:
            print("❌ System does not meet latency compliance targets")
        
        # Test coverage
        if self.results.get('test_coverage', {}).get('tests_passed', False):
            criteria_met += 1
            print("✅ Test suite passes")
        else:
            print("❌ Test suite has failures")
        
        print(f"\n🎯 FINAL SCORE: {criteria_met}/{total_criteria} criteria met")
        
        if criteria_met == total_criteria:
            print("🎉 PROJECT REPORT CLAIMS VALIDATED - PRODUCTION READY")
        elif criteria_met >= 3:
            print("⚠️ PROJECT MOSTLY READY - MINOR ISSUES TO RESOLVE")
        else:
            print("❌ PROJECT NOT READY - SIGNIFICANT ISSUES FOUND")
        
        return criteria_met, total_criteria

async def main():
    """Run comprehensive stress test suite."""
    tester = SystemStressTest()
    
    print("Starting Comprehensive Stress Test Suite...")
    print("This will validate claims in project_current_state_report.md\n")
    
    # Run GPU tests first
    tester.test_gpu_acceleration()
    
    # Test M2M service (requires service to be running)
    try:
        await tester.test_m2m_service_performance()
    except Exception as e:
        print(f"❌ M2M service test failed: {e}")
        print("Make sure M2M service is running on http://localhost:8001")
    
    # Test WebSocket system (requires main service to be running)
    try:
        await tester.test_websocket_concurrent_load()
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        print("Make sure main service is running on http://localhost:8000")
    
    # Test latency compliance
    tester.test_latency_compliance()
    
    # Run test coverage validation
    tester.run_pytest_coverage()
    
    # Generate final report
    score, total = tester.generate_stress_test_report()
    
    # Save results
    with open('stress_test_results.json', 'w') as f:
        json.dump(tester.results, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results saved to: stress_test_results.json")
    return score, total

if __name__ == "__main__":
    asyncio.run(main())
