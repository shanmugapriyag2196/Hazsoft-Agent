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
import json
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

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    feedback: str
    score: float = 0.0
    update_only: bool = False

FEEDBACK_FILE = Path("/tmp/feedback.jsonl") if VERCEL else Path("feedback.jsonl")

def save_feedback_to_airtable(question: str, answer: str, feedback: str, score: float, update_only: bool = False) -> Optional[Dict]:
    """Save feedback to Airtable with aggregated counts."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        print("Airtable: Missing API key or base ID for feedback")
        return None
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    existing_record_id = None
    thumbs_up = 0
    thumbs_down = 0

    try:
        safe_question = question.replace("'", "\\'")
        filter_formula = f"{{Question}}='{safe_question}'"
        response = httpx.get(
            url,
            headers=headers,
            params={"filterByFormula": filter_formula, "pageSize": 1},
            timeout=30.0,
        )
        response.raise_for_status()
        records = response.json().get("records", [])
        if records:
            existing = records[0]
            existing_record_id = existing.get("id")
            fields = existing.get("fields", {})
            thumbs_up = int(fields.get("ThumbsUpCount", 0) or 0)
            thumbs_down = int(fields.get("ThumbsDownCount", 0) or 0)
            if not thumbs_up and not thumbs_down:
                existing_response = fields.get("Response", "")
                import re
                up_match = re.search(r"ThumbsUp=(\d+)", existing_response)
                down_match = re.search(r"ThumbsDown=(\d+)", existing_response)
                if up_match:
                    thumbs_up = int(up_match.group(1))
                if down_match:
                    thumbs_down = int(down_match.group(1))
    except Exception as e:
        print(f"Airtable feedback lookup error: {e}")

    if not update_only:
        if feedback == "up":
            thumbs_up += 1
        elif feedback == "down":
            thumbs_down += 1

    total_interactions = thumbs_up + thumbs_down
    computed_score = 1.0 + (thumbs_up * 0.15) - (thumbs_down * 0.15)

    fields = {
        "Question": question,
        "Response": answer,
        "Type": "Feedback",
        "Date": datetime.datetime.now().isoformat(),
        "Score": computed_score,
        "ThumbsUpCount": thumbs_up,
        "ThumbsDownCount": thumbs_down,
        "TotalInteractions": total_interactions,
    }

    try:
        if existing_record_id:
            response = httpx.patch(
                f"{url}/{existing_record_id}",
                headers=headers,
                json={"fields": fields},
                timeout=30.0,
            )
        else:
            response = httpx.post(url, headers=headers, json={"records": [{"fields": fields}]}, timeout=30.0)
        
        if response.status_code in (200, 201):
            result = response.json()
            print(f"Airtable feedback save success: {result}")
            return {
                "status": "saved",
                "score": computed_score,
                "thumbs_up": thumbs_up,
                "thumbs_down": thumbs_down,
                "total_interactions": total_interactions,
                "fetch_more": feedback == "up",
            }
        
        # If fields don't exist in Airtable, retry without unknown fields and append metrics to Response
        if response.status_code == 422:
            error_msg = response.text
            if "UNKNOWN_FIELD_NAME" in error_msg:
                print(f"Airtable unknown field, retrying with fallback: {error_msg}")
                # Try with only known fields
                fallback_fields = {
                    "Question": question,
                    "Response": f"{answer} | [Metrics: ThumbsUp={thumbs_up}, ThumbsDown={thumbs_down}, Score={computed_score}, Interactions={total_interactions}]",
                    "Type": "Feedback",
                    "Date": datetime.datetime.now().isoformat(),
                    "Score": computed_score,
                    "TotalInteractions": total_interactions,
                }
                if existing_record_id:
                    response = httpx.patch(
                        f"{url}/{existing_record_id}",
                        headers=headers,
                        json={"fields": fallback_fields},
                        timeout=30.0,
                    )
                else:
                    response = httpx.post(url, headers=headers, json={"records": [{"fields": fallback_fields}]}, timeout=30.0)
                
                if response.status_code in (200, 201):
                    result = response.json()
                    print(f"Airtable feedback save success (fallback): {result}")
                    return {
                        "status": "saved",
                        "score": computed_score,
                        "thumbs_up": thumbs_up,
                        "thumbs_down": thumbs_down,
                        "total_interactions": total_interactions,
                        "fetch_more": feedback == "up",
                        "note": "ThumbsUpCount/ThumbsDownCount fields missing in Airtable. Metrics stored in Response field.",
                    }
        
        response.raise_for_status()
        return None
    except httpx.HTTPStatusError as e:
        print(f"Airtable feedback save error - Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except Exception as e:
        print(f"Airtable feedback save error: {e}")
        return None


def get_feedback_weight(question: str, answer: str) -> float:
    """Get feedback weight from Airtable for a Q&A pair."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return 1.0
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    try:
        safe_question = question.replace("'", "\\'")
        filter_formula = f"{{Question}}='{safe_question}'"
        response = httpx.get(
            url,
            headers=headers,
            params={"filterByFormula": filter_formula, "pageSize": 1},
            timeout=30.0,
        )
        response.raise_for_status()
        records = response.json().get("records", [])
        if records:
            fields = records[0].get("fields", {})
            score = float(fields.get("Score", 1.0) or 1.0)
            return max(0.1, min(3.0, score))
    except Exception as e:
        print(f"Airtable weight lookup error: {e}")

    return 1.0

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

def save_to_airtable(question: str, answer: str, material_type: str = "", search_score: float = 0.0, rank: int = 0) -> Optional[Dict]:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        print("Airtable: Missing API key or base ID")
        return None
    encoded_table = urllib.parse.quote(AIRTABLE_TABLE, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    fields = {
        "Question": question,
        "Response": answer,
        "Type": material_type,
        "Date": datetime.datetime.now().isoformat(),
    }
    if search_score:
        fields["SearchScore"] = search_score
    if rank:
        fields["Rank"] = rank
    payload = {
        "records": [{
            "fields": fields
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

def save_doxc_to_airtable(doxc_name: str, file_content: Optional[bytes] = None) -> Optional[Dict]:
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        print("Airtable Doc: Missing configuration")
        return None
    
    if file_content:
        doc_type = determine_document_type_from_content(file_content)
    elif PDF_FOLDER:
        pdf_path = PDF_FOLDER / doxc_name
        if pdf_path.exists():
            try:
                doc_type = determine_document_type_from_content(pdf_path.read_bytes())
            except Exception as e:
                print(f"PDF read error for {doxc_name}: {e}")
                doc_type = "Others"
        else:
            print(f"PDF not found at {pdf_path}, falling back to filename")
            doc_type = determine_document_type(doxc_name)
    else:
        doc_type = determine_document_type(doxc_name)
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    fields = {
        "Date": datetime.datetime.now().isoformat(),
        "Type": doc_type,
    }
    if file_content:
        file_url = upload_to_cloudinary(file_content, doxc_name)
        if file_url:
            fields["DOXC Name"] = [{"url": file_url, "filename": doxc_name}]
        else:
            fields["DOXC Name"] = [{"filename": doxc_name}]
    else:
        fields["DOXC Name"] = [{"filename": doxc_name}]
    payload = {
        "records": [{
            "fields": fields
        }]
    }
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        print(f"Airtable Doc save success: Type={doc_type}")
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
    """Parse PDF content to determine document type with Hazardous/Non-Hazardous prefix."""
    try:
        from pypdf import PdfReader
        import io
        
        reader = PdfReader(io.BytesIO(file_content))
        text = ""
        for page in reader.pages[:3]:
            if page.extract_text():
                text += page.extract_text().lower() + " "
        
        prefix = classify_hazard(text)

        # Determine material type - check Oxygen BEFORE Gas (oxygen contains "gas")
        # 1. Oxygen
        oxygen_patterns = ["oxygen", "oxidizer", "ox. gas", "oxidising", "compressed oxygen"]
        if any(kw in text for kw in oxygen_patterns):
            return f"{prefix}-Oxygen"
        
        # 2. Gas (use specific gas types, not just "gas" which matches "oxygen")
        gas_patterns = ["lpg", "liquefied petroleum", "propane gas", "butane fuel", "natural gas", "gas cylinder", "cylinder"]
        if any(kw in text for kw in gas_patterns):
            return f"{prefix}-Gas"
        
        # 3. Alcohol
        alcohol_patterns = ["reagent alcohol", "ethyl alcohol", "methanol", "isopropyl alcohol", "isopropanol"]
        if any(kw in text for kw in alcohol_patterns):
            return f"{prefix}-Alcohol"
        
        # 4. Cleaning/Disinfectant -> Chemical (dashboard only supports Chemical, not Cleaning)
        cleaning_patterns = ["disinfectant", "cleaner and deodorant", "dust mop treatment"]
        if any(kw in text for kw in cleaning_patterns):
            return f"{prefix}-Chemical"
        
        # 5. Chemical (lab reagents, buffers, controls, solutions)
        chemical_patterns = ["calibrator", "control", "buffer", "reagent", "solution",
                            "chemical", "compound", "assay", "hydrochloric", "sulfuric",
                            "nitric", "formaldehyde", "laboratory chemicals"]
        if any(kw in text for kw in chemical_patterns):
            return f"{prefix}-Chemical"
        
        # 6. Oil
        oil_patterns = ["oil", "lubricant", "petroleum", "hydraulic", "fuel", "grease"]
        if any(kw in text for kw in oil_patterns):
            return f"{prefix}-Oil"
        
        # Default
        return "Others"
    except Exception as e:
        print(f"PDF parsing error: {e}")
        return "Others"


def classify_hazard(text: str) -> str:
    """Determine if text describes Hazardous or Non-Hazardous material."""
    import re
    
    # ── Step 1: Check for explicit HAZARDOUS declarations FIRST ──
    # Signal word: Danger (highest priority - overrides any "not classified" boilerplate)
    if "signal word: danger" in text or "signal word - danger" in text:
        return "Hazardous"
    
    # Flammable/corrosive/toxicity category declarations (GHS hazard categories)
    hazard_categories = [
        "flammable liquids, category",
        "skin corrosion, category",
        "serious eye damage, category",
        "acute toxicity, oral, category",
        "acute toxicity, inhalation, category",
        "acute toxicity, dermal, category",
        "corrosive to metals, category",
        "specific target organ toxicity",
        "carcinogenicity, category",
        "mutagenicity, category",
        "reproductive toxicity, category",
        "respiratory sensitization, category",
        "skin sensitization, category",
        "hazardous to the aquatic environment",
    ]
    if any(c in text for c in hazard_categories):
        return "Hazardous"
    
    # H-codes (H200-H399) - GHS hazard statements
    h_codes = re.findall(r'h\d{3}', text)
    if h_codes:
        return "Hazardous"
    
    # GHS pictograms
    ghs_keywords = ["ghs01", "ghs02", "ghs03", "ghs04", "ghs05", "ghs06", "ghs07", "ghs08", "ghs09"]
    if any(kw in text for kw in ghs_keywords):
        return "Hazardous"
    
    # Specific hazard phrases
    hazard_phrases = [
        "causes severe skin burns",
        "highly flammable",
        "extremely flammable",
        "fatal if",
        "may cause cancer",
        "toxic by inhalation",
        "hazardous by the",
        "dangerous goods",
    ]
    if any(p in text for p in hazard_phrases):
        return "Hazardous"
    
    # ── Step 2: Check for explicit NON-HAZARDOUS declarations ──
    non_hazard_phrases = [
        "not classified as hazardous",
        "not considered hazardous",
        "not classified in accordance with",
        "does not meet the criteria for classification",
        "this product is manufactured by streck and does not contain any hazardous",
        "safety data sheet is not required",
    ]
    if any(p in text for p in non_hazard_phrases):
        return "Non-Hazardous"
    
    # ── Step 3: Default ──
    return "Non-Hazardous"
    
    # 2. Explicit HAZARDOUS declarations
    hazard_phrases = [
        "signal word: danger",
        "signal word - danger",
        "flammable liquids, category",
        "skin corrosion, category",
        "serious eye damage, category",
        "acute toxicity, oral, category",
        "causes severe skin burns",
        "highly flammable",
        "extremely flammable",
        "hazardous by the",
    ]
    if any(p in text for p in hazard_phrases):
        return "Hazardous"
    
    # 3. Check for H-codes (H200-H399) - strong hazard indicator
    h_codes = re.findall(r'h\d{3}', text)
    if h_codes:
        return "Hazardous"
    
    # 4. Check for GHS pictograms
    ghs_keywords = ["ghs01", "ghs02", "ghs03", "ghs04", "ghs05", "ghs06", "ghs07", "ghs08", "ghs09"]
    if any(kw in text for kw in ghs_keywords):
        return "Hazardous"
    
    # 5. Check for hazard classification keywords
    hazard_keywords = [
        "hazard statements",
        "hazard warning",
        "fatal if",
        "may cause cancer",
        "causes severe",
        "toxic by inhalation",
        "corrosive to metals",
        "danger of",
        "hazardous to",
    ]
    if any(kw in text for kw in hazard_keywords):
        return "Hazardous"
    
    # 6. Default: no clear hazard signals → Non-Hazardous
    return "Non-Hazardous"

def determine_document_type(filename: str) -> str:
    """Determine document type based on filename patterns with Hazardous/Non-Hazardous prefix."""
    lower = filename.lower()
    hazardous_indicators = ["hazard", "dangerous", "flammable", "corrosive", "explosive", "warning", "toxic"]
    has_hazard = any(hw in lower for hw in hazardous_indicators)
    prefix = "Hazardous" if has_hazard else "Non-Hazardous"
    
    if any(kw in lower for kw in ["gas", "propane", "butane", "hydrogen"]):
        return f"{prefix}-Gas"
    if any(kw in lower for kw in ["oxygen", "oxidizer"]):
        return f"{prefix}-Oxygen"
    if any(kw in lower for kw in ["chemical", "solvent", "acid", "reagent", "lab", "laboratory"]):
        return f"{prefix}-Chemical"
    if any(kw in lower for kw in ["oil", "lubricant", "petroleum", "hydraulic", "fuel"]):
        return f"{prefix}-Oil"
    if any(kw in lower for kw in ["alcohol", "ethanol", "methanol", "isopropyl"]):
        return f"{prefix}-Alcohol"
    return "Others"

def save_doxc_to_airtable_with_file(doxc_name: str, file_content: bytes) -> Optional[Dict]:
    """Upload PDF file to Airtable attachment field via Cloudinary URL."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_DOC_TABLE_ID:
        return None
    
    doc_type = determine_document_type_from_content(file_content)
    
    # Try Cloudinary upload (optional - for attachment field)
    file_url = upload_to_cloudinary(file_content, doxc_name)
    
    encoded_table = urllib.parse.quote(AIRTABLE_DOC_TABLE_ID, safe='')
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Build payload - always include Type, include attachment only if Cloudinary succeeded
    fields = {
        "Date": datetime.datetime.now().isoformat(),
        "Type": doc_type,
    }
    
    if file_url:
        fields["DOXC Name"] = [{
            "url": file_url,
            "filename": doxc_name
        }]
    
    payload = {
        "records": [{
            "fields": fields
        }]
    }
    
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        result = response.json()
        print(f"Airtable Doc upload success: Type={doc_type}, has_attachment={bool(file_url)}")
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
                    return f"Hazardous-{material}"
            return f"Non-Hazardous-{material}"
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
            
            # Normalize type: if old "Standalone" form (e.g., "Gas"), treat as Non-Hazardous
            if doc_type == "Others":
                others_count += 1
            elif doc_type.startswith("Hazardous-"):
                hazardous_count += 1
            elif doc_type.startswith("Non-Hazardous-"):
                others_count += 1
            elif doc_type in ["Hazardous", "Gas", "Chemical", "Oil", "Oxygen", "Alcohol"]:
                hazardous_count += 1
        
        # Simple compliance logic (placeholder):
        compliant_count = counts.get("Others", 0)
        needs_review_count = counts.get("Non-Hazardous-Gas", 0) + counts.get("Non-Hazardous-Oxygen", 0)
        action_required_count = counts.get("Non-Hazardous-Chemical", 0) + counts.get("Non-Hazardous-Oil", 0) + counts.get("Non-Hazardous-Alcohol", 0)
        
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

@app.get("/api/users/{user_id}/password")
def get_user_password(user_id: str):
    try:
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{user_id}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        record = response.json()
        fields = record.get("fields", {})
        return {"password": fields.get("Password", "")}
    except HTTPException:
        raise
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
        sources = result.get("sources", [])
        search_score = sources[0].get("search_score", 0.0) if sources else 0.0
        rank = sources[0].get("rank", 0) if sources else 0
        save_to_airtable(question, result["answer"], material_type, search_score, rank)
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
        airtable_result = save_feedback_to_airtable(request.question, request.answer, request.feedback, score, request.update_only)
        response_payload = {
            "status": "saved",
            "score": score,
            "fetch_more": request.feedback == "up",
            "airtable": airtable_result,
        }
        return response_payload
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
    status = {"status": "ok", "rag": None}
    try:
        status["rag"] = rag_status()
    except Exception:
        status["rag"] = "unavailable"
    return status

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
    except httpx.HTTPStatusError:
        raise
    except HTTPException:
        raise
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
        save_doxc_to_airtable(file.filename, content)
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

class PasswordVerifyRequest(BaseModel):
    user_id: str
    current_password: str

@app.post("/api/users/verify-password")
def verify_password(req: PasswordVerifyRequest):
    try:
        AIRTABLE_USERS_TABLE_ID = os.getenv("AIRTABLE_USER_TABLE_ID", "tbl1E5Pu8DpEAharu")
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_USERS_TABLE_ID:
            raise HTTPException(status_code=400, detail="Airtable not configured")
        encoded_table = urllib.parse.quote(AIRTABLE_USERS_TABLE_ID, safe='')
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{encoded_table}/{req.user_id}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        record = response.json()
        fields = record.get("fields", {})
        stored_password = fields.get("Password", "")
        if stored_password == req.current_password:
            return {"valid": True}
        else:
            raise HTTPException(status_code=401, detail="Current password is incorrect")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc