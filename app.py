from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import datetime
from typing import Optional, Dict, List

from config import PDF_FOLDER
from config import AIRTABLE_API_KEY
from config import AIRTABLE_BASE_ID
from config import AIRTABLE_TABLE_NAME

from rag import answer_question, index_chunks, rag_status

app = FastAPI(title="Hazsoft SDS RAG Chatbot")
templates = Jinja2Templates(directory="templates")


class ChatRequest(BaseModel):
    question: str


class ChatHistoryItem(BaseModel):
    question: str
    answer: str
    type: str = ""


def save_to_airtable(question: str, answer: str, material_type: str = "") -> Optional[Dict]:
    """Save chat to Airtable. Returns None if Airtable not configured."""
    import httpx

    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return None

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "records": [{
            "fields": {
                "Question": question,
                "Answer": answer,
                "Type": material_type,
                "Date": datetime.datetime.now().isoformat(),
            }
        }]
    }

    try:
        response = httpx.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Airtable save error: {e}")
        return None


def get_chat_history(limit: int = 20) -> List[Dict]:
    """Get recent chat history from Airtable."""
    import httpx

    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return []

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    }
    params = {"pageSize": limit, "sort": [{"field": "Date", "direction": "desc"}]}

    try:
        response = httpx.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("records", [])
    except Exception as e:
        print(f"Airtable history error: {e}")
        return []


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/agent", response_class=HTMLResponse)
def agent(request: Request):
    return templates.TemplateResponse("agent.html", {"request": request})


@app.post("/chat")
def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    try:
        result = answer_question(question)
        material_type = ""
        question_lower = question.lower()
        if "gas" in question_lower:
            material_type = "Gas"
        elif "chemical" in question_lower:
            material_type = "Chemicals"
        elif "cleaning" in question_lower:
            material_type = "Cleaning Products"
        elif "lab" in question_lower or "laboratory" in question_lower:
            material_type = "Laboratory Chemicals"
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


@app.get("/health")
def health():
    try:
        return rag_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def run_ingestion():
    try:
        count = index_chunks(PDF_FOLDER)
        return {"indexed_chunks": count, "status": rag_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/admin/ingest")
def admin_ingest_post():
    return run_ingestion()


@app.get("/admin/ingest")
def admin_ingest_get():
    return run_ingestion()