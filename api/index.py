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
from fastapi.responses import HTMLResponse, RedirectResponse
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

class UserCreate(BaseModel):
    fullName: str
    email: str
    role: str
    status: str
    password: str = "temp123"  # Default password

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    fullName: str
    email: str
    role: str
    status: str
    # Note: password is not included in response for security

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

def determine_document_type_from_content(file_content: bytes) -> str:
    """Parse PDF content to determine document type (Hazardous-gas, Hazardous-chemical, Oxygen, Non Hazardous, Others-Gas, Others)."""
    try:
        from pypdf import PdfReader
        import io
        
        reader = PdfReader(io.BytesIO(file_content))
        text = ""
        for page in reader.pages[:3]:
            if page.extract_text():
                text += page.extract_text().lower() + " "
        
        hazard_indicators = ["hazard", "dangerous", "flammable", "corrosive", "explosive", "warning", "toxic"]
        has_hazard = any(hw in text for hw in hazard_indicators)
        
        gas_patterns = ["propane", "butane", "hydrogen", "natural gas", "methane", "gas cylinder"]
        if any(kw in text for kw in gas_patterns):
            return "Hazardous-gas" if has_hazard else "Others-Gas"
        
        oxygen_patterns = ["oxygen", "oxidizer", "ox. gas", "oxidising"]
        if any(kw in text for kw in oxygen_patterns):
            return "Oxygen"
        
        chemical_patterns = ["chemical", "solvent", "acid", "reagent", "lab", "laboratory"]
        if any(kw in text for kw in chemical_patterns):
            return "Hazardous-chemical" if has_hazard else "Others-chemical"
        
        return "Non Hazardous" if has_hazard else "Others"
    except Exception as e:
        print(f"PDF parsing error: {e}")
        return "Others"

def determine_document_type(filename: str) -> str:
    """Determine document type based on filename patterns."""
    lower = filename.lower()
    if any(kw in lower for kw in ["gas", "propane", "butane", "hydrogen"]):
        return "Others-Gas"
    if any(kw in lower for kw in ["oxygen", "oxidizer"]):
        return "Oxygen"
    if any(kw in lower for kw in ["chemical", "solvent", "acid", "reagent", "lab", "laboratory"]):
        return "Hazardous-chemical"
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
    
    doc_type = determine_document_type_from_content(file_content)
    
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
    params = {"pageSize": limit, "sort[0][field]": "Date", "sort[0][direction]": "desc"}
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
    return RedirectResponse(url="/login", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("hazsoft_token")
    response.delete_cookie("hazsoft_user")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
def signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/agent", response_class=HTMLResponse)
def agent(request: Request):
    return templates.TemplateResponse("agent.html", {"request": request, "has_agent": True})

@app.get("/documents", response_class=HTMLResponse)
def documents(request: Request):
    return templates.TemplateResponse("documents.html", {"request": request})

@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
def users(request: Request):
    print("Users route accessed")  # Debug line
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/api/documents")
def api_documents():
    try:
        records = get_doxc_records()
        return {"documents": records}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/api/stats")
def api_stats():
    try:
        records = get_doxc_records()
        total = 0
        for r in records:
            doxc_field = r.get("fields", {}).get("DOXC Name")
            if doxc_field:
                total += 1
        
        counts = {}
        
        hazardous_count = 0
        others_count = 0
        
        for rec in records:
            doc_type = rec.get("fields", {}).get("Type", "Others")
            counts[doc_type] = (counts.get(doc_type, 0) or 0) + 1
            
            if doc_type.startswith("Hazardous"):
                hazardous_count += 1
            else:
                others_count += 1
        
        # Calculate compliance stats based on document types
        # This is a placeholder logic - in reality, this would come from actual compliance data
        hazardous_chemical_count = counts.get("Hazardous-Chemical", 0)
        hazardous_gas_count = counts.get("Hazardous-gas", 0)
        others_gas_count = counts.get("Others-Gas", 0)
        others_oxygen_count = counts.get("Others-Oxygen", 0)
        others_type_count = counts.get("Others", 0)
        
        # Simple compliance logic (placeholder):
        # - Compliant: Others types (assumed to be properly handled non-hazardous materials)
        # - Needs review: Hazardous gases (may need special handling checks)
        # - Action required: Hazardous chemicals (require immediate safety measures)
        compliant_count = others_gas_count + others_oxygen_count + others_type_count
        needs_review_count = hazardous_gas_count
        action_required_count = hazardous_chemical_count
        
        # Avoid division by zero
        if total == 0:
            compliant_pct = 0
            needs_review_pct = 0
            action_required_pct = 0
        else:
            compliant_pct = round((compliant_count / total) * 100)
            needs_review_pct = round((needs_review_count / total) * 100)
            action_required_pct = round((action_required_count / total) * 100)
            
            # Adjust to ensure we don't lose precision due to rounding
            # Assign remainder to the largest category to make total 100%
            total_pct = compliant_pct + needs_review_pct + action_required_pct
            if total_pct != 100:
                diff = 100 - total_pct
                # Add to the largest category
                if compliant_pct >= needs_review_pct and compliant_pct >= action_required_pct:
                    compliant_pct += diff
                elif needs_review_pct >= compliant_pct and needs_review_pct >= action_required_pct:
                    needs_review_pct += diff
                else:
                    action_required_pct += diff
        
        return {
            "total": total,
            "hazardous_count": hazardous_count,
            "others_count": others_count,
            "counts": counts,
            "compliance": {
                "compliant": compliant_pct,
                "needs_review": needs_review_pct,
                "action_required": action_required_pct
            }
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/api/users")
def api_get_users():
    try:
        # For the users table, we need to use a different table ID
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            return []
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        try:
            response = httpx.get(url, headers=headers, params={"pageSize": 100}, timeout=30.0)
            response.raise_for_status()
            records = response.json().get("records", [])
            
            # Format the response to match what the frontend expects
            users = []
            for record in records:
                fields = record.get("fields", {})
                user = {
                    "id": record.get("id"),
                    "FullName": fields.get("FullName", ""),
                    "Email": fields.get("Email", ""),
                    "Role": fields.get("Role", ""),
                    "Status": fields.get("Status", ""),
                    "LastLogin": fields.get("Last Login", fields.get("LastLogin", "Never")),
                    "Password": fields.get("Password", "")  # Though we shouldn't really return passwords
                }
                users.append(user)
            return users
        except Exception as e:
            print(f"Failed to fetch users: {e}")
            return []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post("/api/users")
def api_create_user(user: UserCreate):
    try:
        # For the users table, we need to use a different table ID
        AIRTABLE_USERS_TABLE_ID = "tbl1E5Pu8DpEAharu"
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # Prepare the payload for Airtable
        payload = {
            "fields": {
                "FullName": user.fullName,
                "Email": user.email,
                "Role": user.role,
                "Status": user.status,
                "Password": user.password
            }
        }
        
        # Debug: Print the payload
        print(f"Sending payload to Airtable: {payload}")
        
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        print(f"Airtable response status: {response.status_code}")
        print(f"Airtable response text: {response.text}")
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"Error in api_create_user: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.put("/api/users/{user_id}")
def api_update_user(user_id: str, user: UserCreate):
    try:
        # For the users table, we need to use a different table ID
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{user_id}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # Prepare the payload for Airtable
        payload = {
            "fields": {
                "FullName": user.fullName,
                "Email": user.email,
                "Role": user.role,
                "Status": user.status,
                "Password": user.password
            }
        }
        
        response = httpx.put(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: str):
    try:
        # For the users table, we need to use a different table ID
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{user_id}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        }
        
        response = httpx.delete(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()
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

@app.post("/api/auth/register")
def api_register_user(user: UserCreate):
    try:
        # For the users table, we need to use a different table ID
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        
        # Check if email already exists
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        
        # Check for existing email
        check_response = httpx.get(url, headers=headers, params={"filterByFormula": f"{{Email}} = '{user.email}'"}, timeout=30.0)
        if check_response.status_code == 200:
            check_data = check_response.json()
            if check_data.get("records") and len(check_data["records"]) > 0:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        # Prepare the payload for Airtable
        payload = {
            "fields": {
                "FullName": user.fullName,
                "Email": user.email,
                "Role": user.role,
                "Status": user.status,
                "Password": user.password
            }
        }
        
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        created_user = response.json()
        
        # Return user data without password
        return UserResponse(
            id=created_user["id"],
            fullName=created_user["fields"]["FullName"],
            email=created_user["fields"]["Email"],
            role=created_user["fields"]["Role"],
            status=created_user["fields"]["Status"]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post("/api/auth/login")
def api_login_user(user: UserLogin):
    try:
        # For the users table, we need to use a different table ID
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # Find user by email
        params = {"filterByFormula": f"{{Email}} = '{user.email}'"}
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("records") or len(data["records"]) == 0:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        record = data["records"][0]
        fields = record.get("fields", {})
        
        # Verify password (in production, use hashed password comparison)
        if fields.get("Password") != user.password:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Return user data without password
        return UserResponse(
            id=record["id"],
            fullName=fields.get("FullName", ""),
            email=fields.get("Email", ""),
            role=fields.get("Role", ""),
            status=fields.get("Status", "")
        )
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
        filepath = PDF_FOLDER / filename
        if filepath.exists() and filepath.suffix.lower() == ".pdf":
            return FileResponse(path=str(filepath), media_type="application/pdf")
    else:
        filepath = PDF_FOLDER / filename
        if filepath.exists() and filepath.suffix.lower() == ".pdf":
            return FileResponse(path=str(filepath), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="File not found")

static_dir = Path(__file__).parent.parent / "static"

@app.get("/static/{filename:path}")
def serve_static(filename: str):
    filepath = static_dir / filename
    if filepath.exists():
        return FileResponse(path=str(filepath))
    raise HTTPException(status_code=404, detail="Static file not found")

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