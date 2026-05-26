#!/usr/bin/env python
"""Test Airtable integration - Check your API key format"""
import httpx
import datetime
import urllib.parse
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME

def test_airtable():
    print(f"AIRTABLE_API_KEY format: {'pat...' if AIRTABLE_API_KEY.startswith('pat') else 'key...' if AIRTABLE_API_KEY.startswith('key') else f'{AIRTABLE_API_KEY[:4]}... (unknown format)'}")
    print(f"AIRTABLE_BASE_ID: {AIRTABLE_BASE_ID}")
    print(f"AIRTABLE_TABLE_NAME: {AIRTABLE_TABLE_NAME}")
    
    encoded_table_name = urllib.parse.quote(AIRTABLE_TABLE_NAME, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table_name}"
    print(f"URL: {url}")
    
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # Test read
    try:
        response = httpx.get(url, headers=headers, params={"pageSize": 1}, timeout=10.0)
        print(f"READ status: {response.status_code}")
        if response.status_code == 200:
            print(f"READ success: {response.json()}")
        else:
            print(f"READ error: {response.text}")
            if "AUTHENTICATION_REQUIRED" in response.text:
                print("\n>>> ERROR: Your Airtable token is invalid or wrong type.")
                print(">>> Use a Personal Access Token (pat...) from https://airtable.com/developers/web/guides/get-access-token")
    except Exception as e:
        print(f"READ error: {e}")

if __name__ == "__main__":
    test_airtable()