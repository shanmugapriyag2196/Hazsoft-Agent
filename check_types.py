import httpx, urllib.parse
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_DOC_TABLE_ID
url = f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe="")}'
r = httpx.get(url, headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'}, params={'pageSize': 100}, timeout=30.0)
records = r.json().get('records', [])
for rec in records:
    f = rec.get('fields', {})
    dt = f.get('Type', '')
    dx = f.get('DOXC Name', '')
    if isinstance(dx, list):
        dx = dx[0].get('filename', '') if dx else ''
    print(f"{dt:25s} | {dx}")
