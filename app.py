from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import datetime
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, List

import base64
import mimetypes

from config import PDF_FOLDER
from config import AIRTABLE_API_KEY
from config import AIRTABLE_BASE_ID
from config import AIRTABLE_TABLE_ID
from config import AIRTABLE_TABLE_NAME
from config import AIRTABLE_DOC_TABLE_ID

AIRTABLE_TABLE = AIRTABLE_TABLE_ID or AIRTABLE_TABLE_NAME

from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from rag import answer_question, index_chunks, rag_status

app = FastAPI(title="Hazsoft SDS RAG Chatbot")
templates = Jinja2Templates(directory="templates")


class ChatRequest(BaseModel):
    question: str


class ChatHistoryItem(BaseModel):
    question: str
    answer: str
    type: str = ""


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    feedback: str
    score: float = 0.0


FEEDBACK_FILE = Path("feedback.jsonl")


def save_feedback_to_airtable(question: str, answer: str, feedback: str, score: float) -> Optional[Dict]:
    """Save feedback to Airtable."""
    import httpx
    import urllib.parse

    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        print("Airtable: Missing API key or base ID for feedback")
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
                "Type": "Feedback",
                "Date": datetime.datetime.now().isoformat(),
                "Feedback": feedback,
                "Score": score,
            }
        }]
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        print(f"Airtable feedback save success: {result}")
        return result
    except httpx.HTTPStatusError as e:
        print(f"Airtable feedback save error - Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except Exception as e:
        print(f"Airtable feedback save error: {e}")
        return None


def save_to_airtable(question: str, answer: str, material_type: str = "") -> Optional[Dict]:
    """Save chat to Airtable. Returns None if Airtable not configured."""
    import httpx
    import urllib.parse

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
    """Save SDS file name to Doc Airtable table."""
    import httpx
    import urllib.parse

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
                "DOXC Name": doxc_name,
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


def get_doxc_names() -> set:
    """Get existing DOXC names from Doc table."""
    import httpx
    import urllib.parse

    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        return set()

    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    try:
        response = httpx.get(url, headers=headers, params={"pageSize": 100}, timeout=30.0)
        response.raise_for_status()
        records = response.json().get("records", [])
        return {r.get("fields", {}).get("DOXC Name") for r in records if r.get("fields", {}).get("DOXC Name")}
    except Exception as e:
        print(f"Failed to fetch DOXC names: {e}")
        return set()


def get_doxc_records() -> List[Dict]:
    """Get all DOXC records from Doc table."""
    import httpx
    import urllib.parse

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


def get_chat_history(limit: int = 20) -> List[Dict]:
    """Get recent chat history from Airtable."""
    import httpx
    import urllib.parse

    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return []

    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    }
    params = {
        "pageSize": limit
    }

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
    """Debug endpoint to check Airtable configuration."""
    import httpx
    import urllib.parse

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


@app.post("/feedback")
def feedback(request: FeedbackRequest):
    score = 0.15 if request.feedback == "up" else -0.15 if request.feedback == "down" else request.score
    try:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "question": request.question,
            "answer": request.answer,
            "feedback": request.feedback,
            "score": score,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        save_feedback_to_airtable(request.question, request.answer, request.feedback, score)
        return {"status": "saved", "score": score, "fetch_more": request.feedback == "up"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def determine_material_type(question: str, answer: str) -> str:
    """Determine material type based on question and answer content."""
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
                    return f"Hazardous-{material}"
            return f"Non-Hazardous-{material}"

    return "Others"


@app.get("/history")
def get_history():
    try:
        history = get_chat_history(20)
        return {"history": history}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/history/{record_id}")
def delete_history(record_id: str):
    import httpx
    import urllib.parse

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


def run_ingestion():
    try:
        chunks = index_chunks(PDF_FOLDER)
        return {"indexed_chunks": chunks, "status": rag_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/admin/ingest")
def admin_ingest_post():
    return run_ingestion()


@app.get("/admin/ingest")
def admin_ingest_get():
    return run_ingestion()


@app.post("/admin/save-docs")
def save_docs():
    """Save new PDF files to Airtable Doc table."""
    try:
        if PDF_FOLDER.exists():
            existing = get_doxc_names()
            saved = []
            for pdf_path in PDF_FOLDER.glob("*.pdf"):
                if pdf_path.name not in existing:
                    save_doxc_to_airtable(pdf_path.name)
                    saved.append(pdf_path.name)
            return {"saved_files": saved, "count": len(saved)}
        return {"error": "PDF folder not found"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/files/{filename:path}")
def serve_pdf(filename: str):
    """Serve PDF files from the PDF folder."""
    filepath = PDF_FOLDER / filename
    if filepath.exists() and filepath.suffix.lower() == ".pdf":
        return FileResponse(path=str(filepath), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="File not found")


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """Handle file upload via form data."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    filepath = PDF_FOLDER / file.filename
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    save_doxc_to_airtable(file.filename)
    return {"filename": file.filename, "status": "uploaded"}


@app.delete("/api/documents/{record_id}")
def delete_document(record_id: str):
    import httpx
    import urllib.parse

    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        raise HTTPException(status_code=400, detail="Airtable not configured")

    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
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