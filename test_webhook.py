#!/usr/bin/env python3
"""
Simple test script for webhook endpoints
"""

import requests
import json
import time

def test_webhook_endpoints():
    base_url = "http://localhost:8000"
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health")
        print(f"Health check: {response.status_code} - {response.json()}")
    except requests.exceptions.ConnectionError:
        print("❌ Webhook server not running. Start it with: python webhook_server.py")
        return False
    
    # Test record start endpoint
    payload = {
        "story_id": "story_20250827_pr34",
        "date": "2025-08-27"
    }
    
    try:
        response = requests.post(
            f"{base_url}/control/record/start",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        print(f"Record start: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"❌ Record start failed: {e}")
        return False
    
    # Test record stop endpoint
    try:
        response = requests.post(
            f"{base_url}/control/record/stop",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        print(f"Record stop: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"❌ Record stop failed: {e}")
        return False
    
    print("✅ All webhook endpoints working!")
    return True

if __name__ == "__main__":
    test_webhook_endpoints()
