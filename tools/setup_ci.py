#!/usr/bin/env python3
"""
CI setup script for HTML→PNG renderer.
Installs Playwright and system dependencies for headless browser rendering.
"""

import subprocess
import sys
import platform
from pathlib import Path

def install_system_dependencies():
    """Install system dependencies for Playwright."""
    system = platform.system().lower()
    
    if system == "linux":
        print("Installing Linux dependencies for Playwright...")
        try:
            # Install required libraries for headless browser
            subprocess.run([
                "sudo", "apt-get", "update"
            ], check=True, capture_output=True)
            
            subprocess.run([
                "sudo", "apt-get", "install", "-y",
                "libnss3", "libatk-bridge2.0-0", "libx11-xcb1",
                "libxcomposite1", "libxdamage1", "libxrandr2",
                "libgbm1", "libasound2", "libdrm2", "libxss1",
                "libgtk-3-0", "libxshmfence1"
            ], check=True, capture_output=True)
            
            print("✅ Linux dependencies installed")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install Linux dependencies: {e}")
            return False
    
    elif system == "darwin":
        print("macOS detected - no additional system dependencies needed")
    
    else:
        print(f"⚠️  Unsupported system: {system}")
    
    return True

def install_playwright():
    """Install Playwright and Chromium browser."""
    print("Installing Playwright and Chromium...")
    
    try:
        # Install Playwright browsers (Chromium)
        result = subprocess.run([
            sys.executable, "-m", "playwright", "install", "chromium"
        ], capture_output=True, text=True, check=True)
        
        print("✅ Chromium browser installed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Playwright browsers: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ Playwright not found. Please install it first:")
        print("   pip install playwright")
        return False

def verify_installation():
    """Verify that Playwright is working correctly."""
    print("Verifying Playwright installation...")
    
    try:
        # Test basic Playwright functionality
        test_script = """
import asyncio
from playwright.async_api import async_playwright

async def test_playwright():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1080, "height": 1920})
        await page.goto("data:text/html,<h1>Test</h1>")
        await page.screenshot(path="test_screenshot.png")
        await browser.close()
        return True

result = asyncio.run(test_playwright())
print("✅ Playwright test successful" if result else "❌ Playwright test failed")
"""
        
        # Write test script to temp file
        test_file = Path("test_playwright_ci.py")
        test_file.write_text(test_script)
        
        # Run test
        result = subprocess.run([
            sys.executable, str(test_file)
        ], capture_output=True, text=True, check=True)
        
        # Clean up
        test_file.unlink(missing_ok=True)
        Path("test_screenshot.png").unlink(missing_ok=True)
        
        print("✅ Playwright verification successful!")
        return True
        
    except Exception as e:
        print(f"❌ Playwright verification failed: {e}")
        return False

def main():
    """Main CI setup function."""
    print("🚀 Setting up CI environment for HTML→PNG renderer...")
    
    # Install system dependencies
    if not install_system_dependencies():
        sys.exit(1)
    
    # Install Playwright
    if not install_playwright():
        sys.exit(1)
    
    # Verify installation
    if not verify_installation():
        sys.exit(1)
    
    print("🎉 CI setup completed successfully!")
    print("Playwright is ready for HTML→PNG rendering in CI environment.")

if __name__ == "__main__":
    main()
