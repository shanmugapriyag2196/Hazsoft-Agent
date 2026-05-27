import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if exists (for local dev)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# Set defaults for missing env vars (Vercel env vars should override these)
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("QDRANT_URL", "")
os.environ.setdefault("QDRANT_API_KEY", "")
os.environ.setdefault("AIRTABLE_API_KEY", "")
os.environ.setdefault("AIRTABLE_BASE_ID", "")
os.environ.setdefault("AIRTABLE_DOC_TABLE_ID", "")

# Import after env is loaded
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import datetime
import shutil
from typing import Optional, Dict, List
from starlette.responses import FileResponse

# On Vercel, use /tmp for file storage; locally use the configured folder
VERCEL = os.getenv("VERCEL", "")
if VERCEL:
    PDF_FOLDER = Path("/tmp/pdfs")
else:
    from config import PDF_FOLDER as LOCAL_PDF_FOLDER
    PDF_FOLDER = LOCAL_PDF_FOLDER

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_DOC_TABLE_ID = os.getenv("AIRTABLE_DOC_TABLE_ID", "")

AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID", "")
AIRTABLE_TABLE_NAME = AIRTABLE_TABLE_ID or "Response_Data"
AIRTABLE_TABLE = AIRTABLE_TABLE_ID or AIRTABLE_TABLE_NAME

# Lazy import for rag (may fail if Qdrant unavailable)
try:
    from rag import answer_question, index_chunks, rag_status
except Exception:
    answer_question = None
    index_chunks = None
    rag_status = None

app = FastAPI(title="Hazsoft SDS RAG Chatbot")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    question: str

def save_to_airtable(question: str, answer: str, material_type: str = "") -> Optional[Dict]:
    import httpx
    import urllib.parse
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return None
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    payload = {"records": [{"fields": {"Question": question, "Response": answer, "Type": material_type, "Date": datetime.datetime.now().isoformat()}}]}
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

def save_doxc_to_airtable(doxc_name: str) -> Optional[Dict]:
    import httpx
    import urllib.parse
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        return None
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    payload = {"records": [{"fields": {"Date": datetime.datetime.now().isoformat(), "DOXC Name": doxc_name}}]}
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/agent", response_class=HTMLResponse)
def agent(request: Request):
    return templates.TemplateResponse("agent.html", {"request": request, "has_agent": True})

@app.get("/documents", response_class=HTMLResponse)
def documents(request: Request):
    return templates.TemplateResponse("documents.html", {"request": request})

@app.get("/api/documents")
def api_documents():
    import httpx
    import urllib.parse
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        return {"documents": []}
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"}, params={"pageSize": 100}, timeout=30.0)
        r.raise_for_status()
        return {"documents": r.json().get("records", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    # Create /tmp/pdfs on Vercel, or use existing folder locally
    PDF_FOLDER.mkdir(parents=True, exist_ok=True)
    filepath = PDF_FOLDER / file.filename
    
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    
    result = save_doxc_to_airtable(file.filename)
    if not result:
        raise HTTPException(status_code=500, detail="Airtable save failed")
    return {"filename": file.filename, "status": "uploaded"}

@app.delete("/api/documents/{record_id}")
def delete_document(record_id: str):
    import httpx
    import urllib.parse
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        raise HTTPException(status_code=400, detail="Airtable not configured")
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{record_id}"
    try:
        r = httpx.delete(url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"}, timeout=30.0)
        r.raise_for_status()
        return {"deleted": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/{filename:path}")
def serve_pdf(filename: str):
    filepath = PDF_FOLDER / filename
    if filepath.exists() and filepath.suffix.lower() == ".pdf":
        return FileResponse(path=str(filepath), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="File not found")