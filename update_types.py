import os
import httpx
import urllib.parse
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('AIRTABLE_API_KEY')
base_id = os.getenv('AIRTABLE_BASE_ID')
doc_table = os.getenv('AIRTABLE_DOC_TABLE_ID', 'tblPtRp43f3w6k56X')

def determine_type(filename):
    lower = filename.lower()
    if any(kw in lower for kw in ['gas', 'propane', 'butane', 'hydrogen']):
        return 'Others-Gas'
    if any(kw in lower for kw in ['oxygen', 'oxidizer']):
        return 'Others-Oxygen'
    if any(kw in lower for kw in ['chemical', 'solvent', 'acid', 'reagent', 'lab', 'laboratory']):
        return 'Hazardous-Chemical'
    if any(kw in lower for kw in ['cleaning', 'detergent', 'soap']):
        return 'Hazardous-Cleaning'
    return 'Others'

table = urllib.parse.quote(doc_table, safe='')
url = 'https://api.airtable.com/v0/' + base_id + '/' + table
headers = {'Authorization': 'Bearer ' + api_key}

# Get all records
r = httpx.get(url, headers=headers, params={'pageSize': 100})
records = r.json().get('records', [])

for rec in records:
    attach = rec.get('fields', {}).get('DOXC Name')
    if attach and isinstance(attach, list) and attach[0].get('filename'):
        fname = attach[0]['filename']
        doc_type = determine_type(fname)
        # Update record
        patch_url = 'https://api.airtable.com/v0/' + base_id + '/' + table + '/' + rec['id']
        patch_resp = httpx.patch(patch_url, headers=headers, json={'fields': {'Type': doc_type}})
        print('Updated ' + fname + ': ' + doc_type)