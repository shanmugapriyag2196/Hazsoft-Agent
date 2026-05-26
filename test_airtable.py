#!/usr/bin/env python
"""Test Airtable integration"""
import httpx
import datetime
import urllib.parse
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID, AIRTABLE_TABLE_NAME

AIRTABLE_TABLE = AIRTABLE_TABLE_ID or AIRTABLE_TABLE_NAME

def test_airtable():
    print(f"AIRTABLE_API_KEY set: {bool(AIRTABLE_API_KEY)}")
    if AIRTABLE_API_KEY:
        print(f"AIRTABLE_API_KEY format: {AIRTABLE_API_KEY[:10]}...")
    print(f"AIRTABLE_BASE_ID: {AIRTABLE_BASE_ID}")
    print(f"AIRTABLE_TABLE_ID: {AIRTABLE_TABLE_ID}")
    print(f"AIRTABLE_TABLE_NAME: {AIRTABLE_TABLE_NAME}")
    print(f"AIRTABLE_TABLE used: {AIRTABLE_TABLE}")
    
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    print(f"URL: {url}")
    
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    try:
        response = httpx.get(url, headers=headers, params={"pageSize": 1}, timeout=10.0)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Success: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_airtable()