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
        # Install Playwright browsers (Chromium)
        print("Installing Chromium browser...")
        result = subprocess.run([
            sys.executable, "-m", "playwright", "install", "chromium"
        ], capture_output=True, text=True, check=True)
        
        print("✅ Chromium browser installed successfully!")
        print("Playwright is ready for HTML→PNG rendering.")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Playwright browsers: {e}")
        print(f"Error output: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Playwright not found. Please install it first:")
        print("   pip install playwright")
        sys.exit(1)

if __name__ == "__main__":
    main()
