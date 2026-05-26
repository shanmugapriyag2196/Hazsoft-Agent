from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import datetime
from typing import Optional, Dict, List

from config import PDF_FOLDER
from config import AIRTABLE_API_KEY
from config import AIRTABLE_BASE_ID
from config import AIRTABLE_TABLE_ID
from config import AIRTABLE_TABLE_NAME

AIRTABLE_TABLE = AIRTABLE_TABLE_ID or AIRTABLE_TABLE_NAME

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


def get_chat_history(limit: int = 20) -> List[Dict]:
    """Get recent chat history from Airtable."""
    import httpx
    import urllib.parse
    import json

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


@app.get("/debug/airtable")
def debug_airtable():
    """Debug endpoint to check Airtable configuration."""
    import httpx
    import urllib.parse
    
    status = {
        "api_key_set": bool(AIRTABLE_API_KEY),
        "base_id": AIRTABLE_BASE_ID,
        "table_id": AIRTABLE_TABLE_ID,
        "table_used": AIRTABLE_TABLE,
    }
    
    if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
        encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        
        try:
            response = httpx.get(url, headers=headers, params={"pageSize": 1}, timeout=10.0)
            status["test_status"] = response.status_code
            status["test_result"] = response.json() if response.status_code == 200 else response.text
        except Exception as e:
            status["test_error"] = str(e)
    
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
                    return f"Hazardous - {material}"
            return f"Non-Hazardous - {material}"
    
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