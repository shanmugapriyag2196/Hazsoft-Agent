#!/usr/bin/env python
"""
Final sync: apply correct Hazardous/Non-Hazardous classifications from PDF analysis.
Based on thorough content review of all 15 PDFs.
"""
import httpx
import urllib.parse
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_DOC_TABLE_ID

# Correct final types from thorough PDF content analysis
CORRECT_TYPES = {
    "03162020.pdf":                     "Non-Hazardous-Chemical",
    "11859.pdf":                        "Hazardous-Chemical",
    "11860.pdf":                        "Hazardous-Chemical",
    "10416.pdf":                        "Non-Hazardous-Oxygen",
    "15587.pdf":                        "Non-Hazardous-Chemical",
    "201044.pdf":                       "Hazardous-Chemical",
    "201259.pdf":                       "Non-Hazardous-Chemical",
    "265638.pdf":                       "Hazardous-Chemical",
    "266380.pdf":                       "Hazardous-Chemical",
    "267068.pdf":                       "Hazardous-Chemical",
    "267394.pdf":                       "Hazardous-Chemical",
    "280125.pdf":                       "Non-Hazardous-Chemical",
    "284554.pdf":                       "Non-Hazardous-Chemical",
    "291286.pdf":                       "Non-Hazardous-Chemical",
    "1038049 - MSDS - EN - US.pdf":     "Non-Hazardous-Chemical",
}

def get_filename(doxc_field):
    if isinstance(doxc_field, list):
        return next((i.get("filename", "") for i in doxc_field if isinstance(i, dict)), "")
    return doxc_field if isinstance(doxc_field, str) else ""

def main():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    resp = httpx.get(url, headers=headers, params={"pageSize": 100}, timeout=30)
    resp.raise_for_status()
    records = resp.json().get("records", [])

    print(f"Total records: {len(records)}\n")
    n_up = n_ok = n_skip = 0

    for rec in records:
        fields = rec["fields"]
        old = fields.get("Type", "")
        fname = get_filename(fields.get("DOXC Name"))
        if not fname:
            n_skip += 1
            continue
        new = CORRECT_TYPES.get(fname, old)
        if new != old:
            patch = httpx.patch(
                f"{url}/{rec['id']}",
                headers={**headers, "Content-Type": "application/json"},
                json={"fields": {"Type": new}},
                timeout=30,
            )
            patch.raise_for_status()
            print(f"[FIXED] {fname}: '{old}' -> '{new}'")
            n_up += 1
        else:
            print(f"[OK] {fname}: '{old}'")
            n_ok += 1

    print(f"\n=== DONE: {n_up} fixed, {n_ok} unchanged, {n_skip} skipped ===")

if __name__ == "__main__":
    main()
