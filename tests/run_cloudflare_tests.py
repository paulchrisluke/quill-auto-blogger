#!/usr/bin/env python3
"""
Simple test runner for Cloudflare Worker tests
"""

import subprocess
import sys
import time
import os

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import requests
        print("✅ requests library found")
    except ImportError:
        print("❌ requests library not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        print("✅ requests library installed")

def start_worker():
    """Start the Cloudflare Worker in development mode"""
    print("🚀 Starting Cloudflare Worker...")
    
    # Change to cloudflare-worker directory
    worker_dir = os.path.join(os.path.dirname(__file__), "..", "cloudflare-worker")
    os.chdir(worker_dir)
    
    # Start worker in background
    try:
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for worker to start
        print("⏳ Waiting for worker to start...")
        time.sleep(10)
        
        return process
        
    except Exception as e:
        print(f"❌ Failed to start worker: {e}")
        return None

def run_tests():
    """Run the Cloudflare Worker tests"""
    print("🧪 Running Cloudflare Worker tests...")
    
    # Change to tests directory
    tests_dir = os.path.dirname(__file__)
    os.chdir(tests_dir)
    
    try:
        result = subprocess.run(
            [sys.executable, "test_cloudflare_worker.py"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ Tests timed out")
        return False
    except Exception as e:
        print(f"❌ Failed to run tests: {e}")
        return False

def main():
    """Main test runner"""
    print("🧪 Cloudflare Worker Test Runner")
    print("=" * 40)
    
    # Check dependencies
    check_dependencies()
    
    # Start worker
    worker_process = start_worker()
    if not worker_process:
        print("❌ Failed to start worker. Exiting.")
        sys.exit(1)
    
    try:
        # Run tests
        success = run_tests()
        
        if success:
            print("\n🎉 All tests passed!")
        else:
            print("\n❌ Some tests failed!")
            
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        if worker_process:
            worker_process.terminate()
            worker_process.wait()
            print("✅ Worker stopped")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
