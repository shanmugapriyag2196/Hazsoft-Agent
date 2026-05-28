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
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "")
os.environ.setdefault("CLOUDINARY_API_KEY", "")
os.environ.setdefault("CLOUDINARY_API_SECRET", "")

# Import after env is loaded
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import datetime
import shutil
import httpx
import urllib.parse
import base64
from typing import Optional, Dict, List
from starlette.responses import FileResponse

# On Vercel, use /tmp for file storage; locally use the configured folder
VERCEL = os.getenv("VERCEL") == "1" or os.getenv("VERCEL") == "true"
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

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

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

class ChatHistoryItem(BaseModel):
    question: str
    answer: str
    type: str = ""

def save_to_airtable(question: str, answer: str, material_type: str = "") -> Optional[Dict]:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        print("Airtable: Missing API key or base ID")
        return None
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "records": [{
            "fields": {
                "Question": question,
                "Response": answer,
                "Type": material_type,
                "Date": datetime.datetime.now().isoformat(),
            }
        }]
    }
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        print(f"Airtable save success: {result}")
        return result
    except httpx.HTTPStatusError as e:
        print(f"Airtable save error - Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except Exception as e:
        print(f"Airtable save error: {e}")
        return None

def save_doxc_to_airtable(doxc_name: str) -> Optional[Dict]:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        print("Airtable Doc: Missing configuration")
        return None
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "records": [{
            "fields": {
                "Date": datetime.datetime.now().isoformat(),
                "DOXC Name": [{"filename": doxc_name}],
            }
        }]
    }
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        print(f"Airtable Doc save success: {result}")
        return result
    except httpx.HTTPStatusError as e:
        print(f"Airtable Doc save error - Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except Exception as e:
        print(f"Airtable Doc save error: {e}")
        return None

def upload_to_cloudinary(file_content: bytes, filename: str) -> Optional[str]:
    """Upload file to Cloudinary and return the public URL."""
    if not CLOUDINARY_CLOUD_NAME or not CLOUDINARY_API_KEY or not CLOUDINARY_API_SECRET:
        return None
    try:
        import cloudinary
        import cloudinary.uploader
        
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET
        )
        
        result = cloudinary.uploader.upload(
            file_content,
            public_id=filename.replace('.pdf', ''),
            resource_type="raw",
            folder="hazsoft-sds"
        )
        print(f"Cloudinary upload success: {result.get('secure_url')}")
        return result.get('secure_url')
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def determine_document_type(filename: str) -> str:
    """Determine document type based on filename patterns."""
    lower = filename.lower()
    if any(kw in lower for kw in ["gas", "propane", "butane", "hydrogen"]):
        return "Others-Gas"
    if any(kw in lower for kw in ["oxygen", "oxidizer"]):
        return "Others-Oxygen"
    if any(kw in lower for kw in ["chemical", "solvent", "acid", "reagent", "lab", "laboratory"]):
        return "Hazardous-Chemical"
    if any(kw in lower for kw in ["cleaning", "detergent", "soap"]):
        return "Hazardous-Cleaning"
    return "Others"

def save_doxc_to_airtable_with_file(doxc_name: str, file_content: bytes) -> Optional[Dict]:
    """Upload PDF file to Airtable attachment field via Cloudinary URL."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        return None
    
    # Upload to Cloudinary first (required for Airtable attachments)
    file_url = upload_to_cloudinary(file_content, doxc_name)
    if not file_url:
        print("Failed to upload to Cloudinary")
        return None
    
    doc_type = determine_document_type(doxc_name)
    
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "records": [{
            "fields": {
                "Date": datetime.datetime.now().isoformat(),
                "DOXC Name": [{
                    "url": file_url,
                    "filename": doxc_name
                }],
                "Type": doc_type,
            }
        }]
    }
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        result = response.json()
        print(f"Airtable Doc upload success: {result}")
        return result
    except httpx.HTTPStatusError as e:
        print(f"Airtable Doc upload error - Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except Exception as e:
        print(f"Airtable Doc upload error: {e}")
        return None



def get_doxc_records() -> List[Dict]:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        return []
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    try:
        response = httpx.get(url, headers=headers, params={"pageSize": 100}, timeout=30.0)
        response.raise_for_status()
        return response.json().get("records", [])
    except Exception as e:
        print(f"Failed to fetch DOXC records: {e}")
        return []

def get_all_airtable_doxc_names() -> set:
    records = get_doxc_records()
    names = set()
    for r in records:
        doxc_field = r.get("fields", {}).get("DOXC Name")
        if doxc_field:
            if isinstance(doxc_field, list):
                for item in doxc_field:
                    if isinstance(item, dict) and item.get("filename"):
                        names.add(item["filename"])
            elif isinstance(doxc_field, str):
                names.add(doxc_field)
    return names

def get_chat_history(limit: int = 20) -> List[Dict]:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return []
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"pageSize": limit}
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        return response.json().get("records", [])
    except httpx.HTTPStatusError as e:
        print(f"Airtable history error - Status: {e.response.status_code}, Body: {e.response.text}")
        return []
    except Exception as e:
        print(f"Airtable history error: {e}")
        return []

def determine_material_type(question: str, answer: str) -> str:
    combined = (question + " " + answer).lower()
    material_keywords = {
        "Gas": ["gas", "propane", "butane", "natural gas", "hydrogen"],
        "Chemicals": ["chemical", "solvent", "acid", "base", "reagent"],
        "Cleaning Products": ["cleaning", "detergent", "soap", "disinfectant"],
        "Laboratory Chemicals": ["lab", "laboratory", "lab chemical"]
    }
    for material, keywords in material_keywords.items():
        if any(kw in combined for kw in keywords):
            for kw in ["hazard", "danger", "warning", "dangerous", "toxic", "flammable",
                      "corrosive", "explosive", "reactivity", "health hazard"]:
                if kw in combined:
                    return f"Hazardous - {material}"
            return f"Non-Hazardous - {material}"
    return "Others"

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
    try:
        records = get_doxc_records()
        return {"documents": records}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/debug/airtable")
def debug_airtable():
    status = {
        "api_key_set": bool(AIRTABLE_API_KEY),
        "base_id": AIRTABLE_BASE_ID,
        "table_id": AIRTABLE_TABLE_ID,
        "doc_table_id": AIRTABLE_DOC_TABLE_ID,
        "table_used": AIRTABLE_TABLE,
    }
    if AIRTABLE_API_KEY and AIRTABLE_BASE_ID and AIRTABLE_DOC_TABLE_ID:
        encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        try:
            response = httpx.get(url, headers=headers, params={"pageSize": 1}, timeout=10.0)
            status["doc_test_status"] = response.status_code
        except Exception as e:
            status["doc_test_error"] = str(e)
    return status

@app.post("/chat")
def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")
    try:
        result = answer_question(question)
        material_type = determine_material_type(question, result.get("answer", ""))
        save_to_airtable(question, result["answer"], material_type)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/history")
def get_history():
    try:
        history = get_chat_history(20)
        return {"history": history}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.delete("/history/{record_id}")
def delete_history(record_id: str):
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        raise HTTPException(status_code=400, detail="Airtable not configured")
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    try:
        response = httpx.delete(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return {"deleted": record_id}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    try:
        return rag_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post("/admin/ingest")
def admin_ingest_post():
    try:
        chunks = index_chunks(PDF_FOLDER)
        return {"indexed_chunks": chunks, "status": rag_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/admin/ingest")
def admin_ingest_get():
    return admin_ingest_post()

@app.post("/admin/save-docs")
def save_docs():
    try:
        if PDF_FOLDER.exists():
            existing = get_all_airtable_doxc_names()
            saved = []
            for pdf_path in PDF_FOLDER.glob("*.pdf"):
                if pdf_path.name not in existing:
                    save_doxc_to_airtable(pdf_path.name)
                    saved.append(pdf_path.name)
            return {"saved_files": saved, "count": len(saved)}
        return {"error": "PDF folder not found"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    content = await file.read()
    
    if VERCEL:
        # Vercel: upload to Airtable attachment only
        result = save_doxc_to_airtable_with_file(file.filename, content)
        if not result:
            raise HTTPException(status_code=500, detail="Airtable save failed")
        return {"filename": file.filename, "status": "uploaded", "url": result.get("records", [{}])[0].get("fields", {}).get("DOXC Name", [])}
    else:
        # Local: save to folder AND Airtable
        PDF_FOLDER.mkdir(parents=True, exist_ok=True)
        filepath = PDF_FOLDER / file.filename
        with open(filepath, "wb") as buffer:
            buffer.write(content)
        save_doxc_to_airtable(file.filename)
        return {"filename": file.filename, "status": "uploaded"}

@app.get("/files/{filename:path}")
def serve_pdf(filename: str):
    if VERCEL:
        # On Vercel, files are in /tmp/pdfs
        filepath = PDF_FOLDER / filename
        if filepath.exists() and filepath.suffix.lower() == ".pdf":
            return FileResponse(path=str(filepath), media_type="application/pdf")
    else:
        # Local: serve from PDF_FOLDER
        filepath = PDF_FOLDER / filename
        if filepath.exists() and filepath.suffix.lower() == ".pdf":
            return FileResponse(path=str(filepath), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="File not found")

@app.delete("/api/documents/{record_id}")
def delete_document(record_id: str):
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        raise HTTPException(status_code=400, detail="Airtable not configured")
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        if response.status_code == 200:
            record = response.json()
            doxc_name = record.get("fields", {}).get("DOXC Name")
            if doxc_name and not VERCEL:
                filepath = PDF_FOLDER / doxc_name
                if filepath.exists():
                    filepath.unlink()
        del_response = httpx.delete(url, headers=headers, timeout=30.0)
        del_response.raise_for_status()
        return {"deleted": record_id}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/download-from-airtable")
def download_from_airtable():
    """Download Airtable attachments to local PDF_FOLDER (local only)."""
    if VERCEL:
        raise HTTPException(status_code=400, detail="Not available on Vercel")
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        raise HTTPException(status_code=400, detail="Airtable not configured")
    
    PDF_FOLDER.mkdir(parents=True, exist_ok=True)
    downloaded = []
    failed = []
    
    records = get_doxc_records()
    for rec in records:
        fields = rec.get("fields", {})
        name = fields.get("DOXC Name")
        attachment = fields.get("Attachment")
        
        if name and attachment:
            attach_url = attachment[0].get("url") if isinstance(attachment, list) else attachment.get("url")
            if attach_url and not (PDF_FOLDER / name).exists():
                try:
                    resp = httpx.get(attach_url, timeout=60.0)
                    resp.raise_for_status()
                    (PDF_FOLDER / name).write_bytes(resp.content)
                    downloaded.append(name)
                except Exception as e:
                    failed.append({"name": name, "error": str(e)})
    
    return {"downloaded": downloaded, "count": len(downloaded), "failed": failed}