#!/usr/bin/env python3
"""
CI setup script for HTML→PNG renderer.
Installs Playwright and system dependencies for headless browser rendering.
"""

import subprocess
import sys
import platform
import shutil
import os
import textwrap
from pathlib import Path

def has_command(command):
    """Check if a command is available in PATH."""
    return shutil.which(command) is not None

def run_command(cmd, description, check=True, capture_output=True):
    """Run a command with proper error handling."""
    print(f"Running: {description}")
    try:
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        if result.stdout:
            print(f"Output: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {description}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return e
    except FileNotFoundError as e:
        print(f"❌ Command not found: {description}")
        print(f"Error: {e}")
        return None

def detect_package_manager():
    """Detect available package manager and privilege level."""
    package_managers = {
        'apt-get': 'apt-get',
        'apt': 'apt',
        'yum': 'yum',
        'dnf': 'dnf',
        'pacman': 'pacman',
        'apk': 'apk'
    }
    
    for cmd, name in package_managers.items():
        if has_command(cmd):
            # Check if we can run without sudo
            test_cmd = [cmd, '--version']
            result = run_command(test_cmd, f"Testing {name}", check=False)
            if result and result.returncode == 0:
                return name, False  # No sudo needed
            elif has_command('sudo'):
                return name, True   # Sudo needed
            else:
                print(f"⚠️  {name} found but requires sudo and sudo not available")
    
    return None, False

def install_linux_dependencies():
    """Install Linux dependencies using detected package manager."""
    print("Installing Linux dependencies for Playwright...")
    
    pkg_mgr, needs_sudo = detect_package_manager()
    if not pkg_mgr:
        print("⚠️  No supported package manager found. Trying Playwright's dependency installer...")
        return install_playwright_dependencies()
    
    # Common dependencies across distributions
    dependencies = [
        "libnss3", "libatk-bridge2.0-0", "libx11-xcb1",
        "libxcomposite1", "libxdamage1", "libxrandr2",
        "libgbm1", "libasound2", "libdrm2", "libxss1",
        "libgtk-3-0", "libxshmfence1"
    ]
    
    # Distribution-specific package names
    package_mappings = {
        'apt-get': dependencies,
        'apt': dependencies,
        'yum': [pkg.replace('libgtk-3-0', 'gtk3') for pkg in dependencies],
        'dnf': [pkg.replace('libgtk-3-0', 'gtk3') for pkg in dependencies],
        'pacman': [pkg.replace('libgtk-3-0', 'gtk3') for pkg in dependencies],
        'apk': [pkg.replace('libgtk-3-0', 'gtk3') for pkg in dependencies]
    }
    
    pkgs = package_mappings.get(pkg_mgr, dependencies)
    
    # Build command
    if pkg_mgr in ['apt-get', 'apt']:
        update_cmd = [pkg_mgr, 'update']
        install_cmd = [pkg_mgr, 'install', '-y'] + pkgs
    elif pkg_mgr in ['yum', 'dnf']:
        update_cmd = [pkg_mgr, 'update']
        install_cmd = [pkg_mgr, 'install', '-y'] + pkgs
    elif pkg_mgr == 'pacman':
        update_cmd = [pkg_mgr, '-Sy']
        install_cmd = [pkg_mgr, '-S', '--noconfirm'] + pkgs
    elif pkg_mgr == 'apk':
        update_cmd = [pkg_mgr, 'update']
        install_cmd = [pkg_mgr, 'add'] + pkgs
    
    # Add sudo if needed
    if needs_sudo:
        update_cmd = ['sudo'] + update_cmd
        install_cmd = ['sudo'] + install_cmd
    
    # Run commands
    result = run_command(update_cmd, f"Updating package list with {pkg_mgr}")
    if result and result.returncode != 0:
        print(f"⚠️  Package update failed, trying installation anyway...")
    
    result = run_command(install_cmd, f"Installing dependencies with {pkg_mgr}")
    if result and result.returncode == 0:
        print("✅ Linux dependencies installed successfully")
        return True
    else:
        print("⚠️  Package manager installation failed, trying Playwright's dependency installer...")
        return install_playwright_dependencies()

def install_playwright_dependencies():
    """Use Playwright's built-in dependency installer."""
    print("Using Playwright's dependency installer...")
    
    try:
        result = run_command([
            sys.executable, "-m", "playwright", "install-deps", "chromium"
        ], "Installing Playwright system dependencies")
        
        if result and result.returncode == 0:
            print("✅ Playwright dependencies installed successfully")
            return True
        else:
            print("❌ Playwright dependency installation failed")
            return False
    except Exception as e:
        print(f"❌ Failed to run Playwright dependency installer: {e}")
        return False

def install_system_dependencies():
    """Install system dependencies for Playwright."""
    system = platform.system().lower()
    
    if system == "linux":
        return install_linux_dependencies()
    
    elif system == "darwin":
        print("macOS detected - no additional system dependencies needed")
        return True
    
    elif system == "windows":
        print("Windows detected - no additional system dependencies needed")
        return True
    
    else:
        print(f"❌ Unsupported operating system: {system}")
        print("Supported systems: Linux, macOS, Windows")
        return False

def install_playwright():
    """Install Playwright and Chromium browser."""
    print("Installing Playwright and Chromium...")
    
    # First, verify or install the Playwright Python package
    try:
        import playwright
        print("✅ Playwright Python package found")
    except ImportError:
        print("⚠️  Playwright Python package not found, installing...")
        install_result = run_command([
            sys.executable, "-m", "pip", "install", "playwright"
        ], "Installing Playwright Python package")
        
        if not install_result or install_result.returncode != 0:
            print("❌ Failed to install Playwright Python package")
            if install_result:
                print(f"stdout: {install_result.stdout}")
                print(f"stderr: {install_result.stderr}")
            return False
    
    try:
        # Build the install command
        install_cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        
        # Add --with-deps flag on Linux
        if sys.platform.startswith("linux"):
            install_cmd.append("--with-deps")
            print("Linux detected - using --with-deps flag")
        
        # Install Playwright browsers (Chromium)
        result = run_command(install_cmd, "Installing Chromium browser")
        
        if result and result.returncode == 0:
            print("✅ Chromium browser installed successfully!")
            return True
        else:
            print("❌ Failed to install Playwright browsers")
            if result:
                print(f"stdout: {result.stdout}")
                print(f"stderr: {result.stderr}")
            return False
            
    except FileNotFoundError as e:
        print("❌ Playwright CLI not found. The Python package may be installed but the CLI is missing.")
        print("   Please run: pip install playwright")
        print(f"   Error details: {e}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Playwright installation failed with return code {e.returncode}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False

def verify_installation():
    """Verify that Playwright is working correctly."""
    print("Verifying Playwright installation...")
    
    # Test basic Playwright functionality
    test_script = textwrap.dedent("""
        import asyncio
        from playwright.async_api import async_playwright

        async def test_playwright():
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.set_viewport_size({"width": 1080, "height": 1920})
                    await page.goto("data:text/html,<h1>Test</h1>")
                    await page.screenshot(path="test_screenshot.png")
                    await browser.close()
                    return True
            except Exception as e:
                print(f"Test error: {e}")
                return False

        result = asyncio.run(test_playwright())
        print("✅ Playwright test successful" if result else "❌ Playwright test failed")
    """)
    
    # Write test script to temp file
    test_file = Path("test_playwright_ci.py")
    screenshot_file = Path("test_screenshot.png")
    
    try:
        test_file.write_text(test_script)
        
        # Run test
        result = run_command([
            sys.executable, str(test_file)
        ], "Running Playwright verification test")
        
        # Print subprocess output for CI logs
        if result:
            if result.stdout:
                print(f"Test stdout: {result.stdout}")
            if result.stderr:
                print(f"Test stderr: {result.stderr}")
        
        if result and result.returncode == 0:
            print("✅ Playwright verification successful!")
            return True
        else:
            print("❌ Playwright verification failed")
            if result:
                print(f"Return code: {result.returncode}")
            return False
        
    except Exception as e:
        print(f"❌ Playwright verification failed: {e}")
        return False
    finally:
        # Clean up temporary files
        test_file.unlink(missing_ok=True)
        screenshot_file.unlink(missing_ok=True)

def main():
    """Main CI setup function."""
    print("🚀 Setting up CI environment for HTML→PNG renderer...")
    print(f"Platform: {platform.system()} {platform.release()}")
    
    # Install system dependencies
    if not install_system_dependencies():
        print("❌ System dependency installation failed")
        sys.exit(1)
    
    # Install Playwright
    if not install_playwright():
        print("❌ Playwright installation failed")
        sys.exit(1)
    
    # Verify installation
    if not verify_installation():
        print("❌ Playwright verification failed")
        sys.exit(1)
    
    print("🎉 CI setup completed successfully!")
    print("Playwright is ready for HTML→PNG rendering in CI environment.")

if __name__ == "__main__":
    main()
