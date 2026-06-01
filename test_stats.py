#!/usr/bin/env python
"""Test the /api/stats endpoint"""
import sys
sys.path.insert(0, '.')

from api.index import app
from fastapi.testclient import TestClient

def test_stats_endpoint():
    client = TestClient(app)
    response = client.get("/api/stats")
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_stats_endpoint()