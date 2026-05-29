#!/usr/bin/env python
"""Check Airtable Doc table counts"""
import httpx
import urllib.parse
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_DOC_TABLE_ID

def check_counts():
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    response = httpx.get(url, headers=headers, params={"pageSize": 100}, timeout=30.0)
    if response.status_code == 200:
        records = response.json().get("records", [])
        print(f"Total records: {len(records)}")
        
        type_counts = {}
        for rec in records:
            fields = rec.get("fields", {})
            doxc_name = fields.get("DOXC Name")
            doc_type = fields.get("Type", "Others")
            
            print(f"  Record {rec.get('id')}: Type='{doc_type}', DOXC Name={doxc_name}")
            
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        
        print(f"\nType breakdown:")
        for t, c in type_counts.items():
            print(f"  {t}: {c}")
        
        hazardous = sum(c for t, c in type_counts.items() if t.startswith("Hazardous") or t == "Oxygen")
        others = sum(c for t, c in type_counts.items() if t.startswith("Others") or t == "Others" or t == "Non Hazardous")
        print(f"\nHazardous count: {hazardous}")
        print(f"Others count: {others}")

if __name__ == "__main__":
    check_counts()