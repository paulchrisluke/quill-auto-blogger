#!/usr/bin/env python3
"""
Simple test runner for the activity fetcher project.
"""

import subprocess
import sys
from pathlib import Path


def run_tests():
    """Run the test suite."""
    print("Running Activity Fetcher Test Suite")
    print("=" * 40)
    
    # Check if pytest is available
    try:
        import pytest
    except ImportError:
        print("❌ pytest not found. Please install it with: pip install pytest")
        return False
    
    # Run tests
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/", "-v"
        ], capture_output=True, text=True)
        
        print(result.stdout)
        
        if result.stderr:
            print("Errors/Warnings:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ All tests passed!")
            return True
        else:
            print("❌ Some tests failed!")
            return False
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
