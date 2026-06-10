#!/usr/bin/env python
"""Fix Airtable types: just rename old format to match Vercel.

Examples from user:
  Others   ->  Non-Hazardous-Others  ... no, this is just renames Others-Gas -> Non-Hazardous-Gas
  Others-Gas   -> Non-Hazardous-Gas
  Others-Oxygen -> Non-Hazardous-Oxygen
All other types stay as-is.
"""
import httpx, urllib.parse
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_DOC_TABLE_ID

FIX = {"Others-Gas": "Non-Hazardous-Gas", "Others-Oxygen": "Non-Hazardous-Oxygen"}

def main():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(AIRTABLE_DOC_TABLE_ID,'')}"
    records = httpx.get(url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"}, params={"pageSize": 100}, timeout=30).json().get("records", [])
    print(f"Total records: {len(records)}")
    updated = skipped = 0
    for rec in records:
        fields = rec["fields"]
        t = fields.get("Type", "")
        new = FIX.get(t, t)
        if new != t:
            patched = httpx.patch(f"{url}/{rec['id']}", headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}, json={"fields": {"Type": new}}, timeout=30)
            patched.raise_for_status()
            print(f"  FIXED '{t}' -> '{new}'")
            updated += 1
        else:
            print(f"  OK '{t}'")
            skipped += 1
    print(f"Updated: {updated}, Skipped: {skipped}")

if __name__ == "__main__":
    main()
