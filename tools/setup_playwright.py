#!/usr/bin/env python3
"""
Setup script for Playwright browser automation.
Installs Chromium browser for HTML→PNG rendering.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Install Playwright and Chromium browser."""
    print("Setting up Playwright for HTML→PNG rendering...")
    
    try:
        # Install Playwright browsers (Chromium) with dependencies
        print("Installing Chromium browser...")
        subprocess.run([
            sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"
        ], timeout=300, check=True)
        
        print("✅ Chromium browser installed successfully!")
        print("Playwright is ready for HTML→PNG rendering.")
        
    except subprocess.TimeoutExpired as e:
        print(f"❌ Playwright browser installation timed out after 300 seconds")
        if e.stdout:
            print(f"Partial stdout: {e.stdout.decode()}")
        if e.stderr:
            print(f"Partial stderr: {e.stderr.decode()}")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Playwright browsers: {e}")
        print("Note: Output was streamed to console during execution")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Playwright not found. Please install it first:")
        print("   pip install playwright")
        sys.exit(1)

if __name__ == "__main__":
    main()
