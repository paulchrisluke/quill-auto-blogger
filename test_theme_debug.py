#!/usr/bin/env python3
"""
Debug script to test theme rendering
"""

import os
from pathlib import Path
from tools.renderer_html import get_renderer_config, HtmlSlideRenderer

# Get config (will use environment variable if set)
config = get_renderer_config()
print(f"Theme: {config['theme']}")

# Create renderer
renderer = HtmlSlideRenderer()

# Test intro template
test_packet = {
    "title_human": "Test Dark Theme",
    "repo": "test/repo",
    "pr_number": "123",
    "date": "2025-01-15"
}

# Render intro slide
intro_path = Path("test_dark_intro.png")
renderer.render_intro(test_packet, intro_path)

print(f"Rendered dark theme intro: {intro_path}")
print(f"File exists: {intro_path.exists()}")
print(f"File size: {intro_path.stat().st_size if intro_path.exists() else 'N/A'} bytes")
