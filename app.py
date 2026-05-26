from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import datetime
from typing import Optional, Dict, List

from config import PDF_FOLDER
from config import AIRTABLE_API_KEY
from config import AIRTABLE_BASE_ID
from config import AIRTABLE_TABLE_NAME

from rag import answer_question, index_chunks, rag_status


app = FastAPI(title="Hazsoft SDS RAG Chatbot")


class ChatRequest(BaseModel):
    question: str


class ChatHistoryItem(BaseModel):
    question: str
    answer: str
    type: str = ""  # Gas, Chemicals, etc.


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
    except Exception:
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
    except Exception:
        return []


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hazsoft Agent Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f0f4f9;
      --panel: #ffffff;
      --panel-glass: rgba(255, 255, 255, 0.88);
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --nav: #0b1f33;
      --nav-soft: #143553;
      --green: #059669;
      --amber: #d97706;
      --red: #dc2626;
      --blue: #2563eb;
      --teal: #0d9488;
      --purple: #7c3aed;
      --sky: #0ea5e9;
      --indigo: #4f46e5;
      --shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
      --shadow-lg: 0 25px 60px rgba(15, 23, 42, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background:
        radial-gradient(circle at 15% 25%, rgba(5, 150, 105, 0.06) 0%, transparent 40%),
        radial-gradient(circle at 85% 75%, rgba(37, 99, 235, 0.06) 0%, transparent 40%),
        var(--bg);
      color: var(--ink);
      -webkit-font-smoothing: antialiased;
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 20px;
      padding: 20px;
    }
.shell.has-agent {
  grid-template-columns: 280px minmax(0, 1fr) 1fr;
}
    aside {
      background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(10, 15, 25, 1));
      color: #ffffff;
      border-radius: 20px;
      padding: 28px 20px;
      display: flex;
      flex-direction: column;
      gap: 28px;
      box-shadow: var(--shadow-lg);
      position: relative;
      overflow: hidden;
    }
    aside::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
      padding: 0 4px;
    }
    .brand-mark {
      width: 42px;
      height: 42px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, #ffffff, #e2e8f0);
      color: var(--nav);
      font-weight: 900;
      font-size: 18px;
      box-shadow: 
        0 4px 12px rgba(0, 0, 0, 0.15),
        inset 0 0 0 1px rgba(255, 255, 255, 0.3);
    }
    nav {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .nav-item {
      border: 0;
      border-radius: 14px;
      background: transparent;
      color: #cbd5e1;
      min-height: 48px;
      padding: 0 16px;
      display: flex;
      align-items: center;
      justify-content: flex-start;
      gap: 12px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }
    .nav-item::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.3);
      transition: background 0.2s ease;
    }
    .nav-item.active,
    .nav-item:hover {
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
      transform: translateX(4px);
    }
    .nav-item.active::before {
      background: #34d399;
      box-shadow: 0 0 0 2px rgba(52, 211, 153, 0.3);
    }
    .nav-item svg {
      width: 20px;
      height: 20px;
      opacity: 0.7;
    }
    .sidebar-foot {
      margin-top: auto;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 18px;
      color: #cbd5e1;
      font-size: 13px;
      line-height: 1.5;
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(10px);
    }
    .sidebar-foot strong {
      display: block;
      color: #ffffff;
      margin-bottom: 6px;
      font-weight: 700;
    }
    .main {
      min-width: 0;
      padding: 4px 0 4px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 28px;
      border: 1px solid rgba(226, 232, 240, 0.8);
      border-radius: 20px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.92));
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    h1 {
      margin: 0;
      font-size: 32px;
      letter-spacing: -0.02em;
      font-weight: 800;
      background: linear-gradient(135deg, var(--ink), var(--nav));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .subtitle {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 15px;
      font-weight: 500;
    }
    .sync {
      color: #ffffff;
      font-size: 14px;
      font-weight: 700;
      white-space: nowrap;
      background: linear-gradient(135deg, var(--green), #047857);
      border-radius: 999px;
      padding: 10px 18px;
      box-shadow: 0 12px 28px rgba(5, 150, 105, 0.25);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sync::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #34d399;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .quick-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }
    .quick-pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 14px;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.7);
      font-size: 12px;
      font-weight: 600;
      box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 20px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid rgba(226, 232, 240, 0.9);
      border-radius: 18px;
      padding: 24px;
      min-height: 140px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow-lg);
    }
    .metric::after {
      content: "";
      position: absolute;
      right: -40px;
      top: -40px;
      width: 120px;
      height: 120px;
      border-radius: 50%;
      background: rgba(5, 150, 105, 0.08);
      transition: background 0.3s ease;
    }
    .metric:hover::after {
      background: rgba(5, 150, 105, 0.12);
    }
    .metric-label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      position: relative;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .metric-value {
      font-size: 42px;
      font-weight: 800;
      line-height: 1;
      position: relative;
      letter-spacing: -0.03em;
    }
    .metric-note {
      color: var(--muted);
      font-size: 13px;
      position: relative;
      font-weight: 500;
    }
    .dashboard-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
      gap: 20px;
      align-items: stretch;
    }
    .panel {
      background: var(--panel);
      border: 1px solid rgba(226, 232, 240, 0.9);
      border-radius: 20px;
      padding: 28px;
      box-shadow: var(--shadow);
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .panel:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-lg);
    }
    .panel h2 {
      margin: 0 0 6px;
      font-size: 20px;
      letter-spacing: -0.01em;
      font-weight: 700;
    }
    .panel-subtitle {
      margin: 0 0 22px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
    }
    .bar-chart {
      display: grid;
      gap: 18px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 150px 1fr 46px;
      gap: 14px;
      align-items: center;
      min-height: 36px;
    }
    .bar-label {
      color: var(--ink);
      font-size: 14px;
      font-weight: 600;
    }
    .bar-track {
      height: 16px;
      border-radius: 999px;
      background: #f1f5f9;
      overflow: hidden;
      box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.04);
    }
    .bar-fill {
      height: 100%;
      border-radius: 999px;
      transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .bar-value {
      color: var(--muted);
      font-size: 14px;
      text-align: right;
      font-weight: 700;
    }
    .donut-layout {
      display: grid;
      grid-template-columns: 180px 1fr;
      gap: 22px;
      align-items: center;
    }
    .donut {
      width: 176px;
      aspect-ratio: 1;
      border-radius: 50%;
      background:
        radial-gradient(circle at center, #ffffff 0 47%, transparent 48%),
        conic-gradient(var(--green) 0 62%, var(--amber) 62% 85%, var(--red) 85% 100%);
      border: 2px solid var(--line);
      position: relative;
      box-shadow: 0 20px 35px rgba(15, 23, 42, 0.12);
    }
    .donut-center {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-direction: column;
      font-weight: 800;
      font-size: 28px;
      letter-spacing: -0.02em;
    }
    .donut-center span {
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      margin-top: 4px;
    }
    .legend {
      display: grid;
      gap: 12px;
    }
    .legend-item {
      display: grid;
      grid-template-columns: 14px 1fr auto;
      gap: 10px;
      align-items: center;
      font-size: 14px;
      color: var(--muted);
    }
    .dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
     .agent {
       min-width: 0;
       border: 1px solid rgba(226, 232, 240, 0.9);
       border-radius: 20px;
       background: rgba(251, 252, 254, 0.96);
       display: grid;
       grid-template-rows: auto 1fr auto;
       padding: 24px 20px;
       gap: 18px;
       box-shadow: var(--shadow-lg);
       backdrop-filter: blur(10px);
     }
     
     /* AI Agent Dashboard Specific Styles */
     .agent-container {
       display: grid;
       grid-template-columns: 1fr 320px;
       gap: 20px;
       height: 100%;
     }
     
     .agent-header {
       text-align: center;
       padding-bottom: 20px;
       border-bottom: 1px solid var(--line);
       margin-bottom: 20px;
     }
     
     .agent-header h2 {
       margin: 0 0 8px 0;
       font-size: 22px;
       font-weight: 700;
       color: var(--ink);
     }
     
     .agent-subtitle {
       margin: 0;
       color: var(--muted);
       font-size: 14px;
       line-height: 1.5;
     }
     
     .agent-content {
       display: grid;
       grid-template-rows: 1fr auto;
       height: 100%;
     }
     
     .chat-wrapper {
       display: flex;
       flex-direction: column;
       gap: 16px;
       margin-bottom: 20px;
     }
     
     #chat {
       min-height: 0;
       overflow-y: auto;
       display: flex;
       flex-direction: column;
       gap: 14px;
       padding-right: 8px;
       padding-bottom: 20px;
     }
     
     .history-wrapper {
       border: 1px solid var(--line);
       border-radius: 16px;
       padding: 16px;
       background: var(--panel);
       overflow-y: auto;
       height: fit-content;
       max-height: 80vh;
     }
     
     .history-wrapper h3 {
       margin: 0 0 12px 0;
       font-size: 16px;
       font-weight: 600;
       color: var(--ink);
       display: flex;
       align-items: center;
       gap: 8px;
     }
     
     .history-wrapper h3::before {
       content: "";
       width: 8px;
       height: 8px;
       border-radius: 50%;
       background: var(--green);
     }
     
     .history-list {
       display: flex;
       flex-direction: column;
       gap: 10px;
     }
     
     .history-item {
       padding: 12px 16px;
       border-radius: 10px;
       background: #f8fafc;
       font-size: 13px;
       line-height: 1.5;
       border-left: 3px solid var(--green);
       transition: all 0.2s ease;
     }
     
     .history-item:hover {
       background: #f1f5f9;
       transform: translateX(4px);
       box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
     }
     
     .history-item strong {
       color: var(--green);
       font-weight: 600;
     }
     
     .history-item em {
       display: block;
       color: var(--muted);
       font-size: 11px;
       margin-top: 6px;
       font-style: normal;
     }
    .page {
      min-width: 0;
      border: 1px solid rgba(226, 232, 240, 0.9);
      border-radius: 20px;
      background: rgba(251, 252, 254, 0.96);
      display: grid;
      grid-template-rows: auto 1fr auto;
      padding: 24px 20px;
      gap: 18px;
      box-shadow: var(--shadow-lg);
      backdrop-filter: blur(10px);
      margin-left: 20px;
    }
    .agent-layout {
      display: grid;
      grid-template-columns: 1fr 320px;
      gap: 20px;
      min-height: 500px;
    }
    .chat-container {
      display: grid;
      grid-template-rows: 1fr auto;
      min-height: 0;
    }
    .history-sidebar {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      background: var(--panel);
      overflow-y: auto;
    }
    .history-sidebar h3 {
      margin: 0 0 12px;
      font-size: 16px;
      font-weight: 600;
    }
    .history-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .history-item {
      padding: 10px;
      border-radius: 8px;
      background: #f8fafc;
      font-size: 13px;
      line-height: 1.4;
    }
    .history-item strong {
      color: var(--green);
      font-weight: 600;
    }
    .history-item em {
      display: block;
      color: var(--muted);
      font-size: 11px;
      margin-top: 4px;
    }
    .agent-head {
      padding: 20px;
      border-bottom: 1px solid var(--line);
      border-radius: 16px;
      background: #ffffff;
    }
    .agent-head h2 {
      margin: 0;
      font-size: 22px;
      font-weight: 700;
    }
    .agent-head p {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
      font-weight: 500;
    }
    #chat {
      min-height: 0;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 14px;
      padding-right: 6px;
    }
    #chat::-webkit-scrollbar,
    .message-text.expanded::-webkit-scrollbar {
      width: 10px;
    }
    #chat::-webkit-scrollbar-track,
    .message-text.expanded::-webkit-scrollbar-track {
      background: #e2e8f0;
      border-radius: 8px;
    }
    #chat::-webkit-scrollbar-thumb,
    .message-text.expanded::-webkit-scrollbar-thumb {
      background: #94a3b8;
      border-radius: 8px;
      border: 2px solid #e2e8f0;
    }
    .message {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      line-height: 1.55;
      background: var(--panel);
      overflow-wrap: anywhere;
      font-size: 15px;
      transition: transform 0.1s ease;
    }
    .message:hover {
      transform: translateX(2px);
    }
    .user {
      border-color: #9ccbc5;
      background: linear-gradient(135deg, #e9f6f4, #d1ece6);
    }
    .assistant {
      background: #ffffff;
    }
    .message-text {
      white-space: pre-wrap;
    }
    .assistant .message-text.collapsed {
      max-height: 200px;
      overflow: hidden;
    }
    .assistant .message-text.expanded {
      max-height: 380px;
      overflow-y: auto;
      padding-right: 12px;
    }
    .sources {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      white-space: normal;
    }
    .more-button {
      min-height: 36px;
      margin-top: 12px;
      padding: 0 16px;
      border-radius: 10px;
      background: transparent;
      color: var(--green);
      border: 1px solid #86c9b8;
      font-weight: 700;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s ease;
    }
    .more-button:hover {
      background: rgba(5, 150, 105, 0.08);
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
    }
    input {
      width: 100%;
      min-height: 48px;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 0 16px;
      font-size: 15px;
      color: var(--ink);
      background: var(--panel);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    input:focus {
      outline: none;
      border-color: var(--green);
      box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.15);
    }
    button {
      min-height: 48px;
      border: 0;
      border-radius: 14px;
      padding: 0 20px;
      background: linear-gradient(135deg, var(--green), #047857);
      color: white;
      font-weight: 700;
      cursor: pointer;
      font-size: 15px;
      transition: transform 0.1s ease, box-shadow 0.2s ease;
    }
button:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 20px rgba(5, 150, 105, 0.25);
    }
    button:disabled {
      opacity: 0.65;
      cursor: wait;
      transform: none;
    }
    @media (max-width: 1120px) {
      .shell {
        grid-template-columns: 220px minmax(0, 1fr);
      }
      .topbar {
        flex-direction: column;
        align-items: flex-start;
        gap: 16px;
      }
      .sync {
        align-self: flex-start;
      }
    }
    @media (max-width: 820px) {
      .shell {
        grid-template-columns: 1fr;
      }
      aside {
        padding: 20px;
        border-radius: 0;
      }
      .main {
        padding: 20px;
      }
      nav {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .metrics,
      .dashboard-grid,
      .donut-layout {
        grid-template-columns: 1fr;
      }
      .bar-row {
        grid-template-columns: 118px 1fr 36px;
      }
      form {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand"><span class="brand-mark">H</span><span>Hazsoft Agent</span></div>
      <nav aria-label="SDS navigation">
        <button class="nav-item active" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><path d="M9 22V12h6v10"></path></svg>
          All SDS
        </button>
        <button class="nav-item" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 0-7.18 17.62l.19.18H9l3 3 3-3h4.01l.19-.18A10 10 0 0 0 12 2z"></path><path d="M12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8z"></path></svg>
          AI Agent
        </button>
        <button class="nav-item" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path><path d="M16 13H8"></path><path d="M16 17H8"></path><path d="M10 9H8"></path></svg>
          My Documents
        </button>
        <button class="nav-item" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          Categories
        </button>
        <button class="nav-item" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          Hazard
        </button>
        <button class="nav-item" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
          Users
        </button>
        <button class="nav-item" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
          Settings
        </button>
       </nav>
    </aside>

    <main class="main">
      <section class="topbar">
        <div>
          <h1>SDS Dashboard</h1>
          <p class="subtitle">Monitor indexed safety documents, hazard levels, categories, and compliance readiness.</p>
          <div class="quick-row">
            <span class="quick-pill">Qdrant connected</span>
            <span class="quick-pill">15 PDFs</span>
            <span class="quick-pill">500 chunk size</span>
            <span class="quick-pill">75 overlap</span>
          </div>
        </div>
        <div class="sync">547 chunks indexed</div>
      </section>

      <section class="metrics" aria-label="SDS summary">
        <article class="metric">
          <div class="metric-label">Total SDS Documents</div>
          <div class="metric-value">15</div>
          <div class="metric-note">Available in Qdrant collection</div>
        </article>
        <article class="metric">
          <div class="metric-label">Hazardous Material</div>
          <div class="metric-value">9</div>
          <div class="metric-note">Requires handling controls</div>
        </article>
        <article class="metric">
          <div class="metric-label">Non-Hazardous Material</div>
          <div class="metric-value">6</div>
          <div class="metric-note">General SDS references</div>
        </article>
        <article class="metric">
          <div class="metric-label">Categories</div>
          <div class="metric-value">4</div>
          <div class="metric-note">Gas, chemicals, cleaning, lab</div>
        </article>
      </section>

      <section class="dashboard-grid">
        <article class="panel">
          <h2>SDS Category Bar Chart</h2>
          <p class="panel-subtitle">Distribution of indexed SDS materials by operational category.</p>
          <div class="bar-chart">
            <div class="bar-row">
              <div class="bar-label">Gas</div>
              <div class="bar-track"><div class="bar-fill" style="width: 27%; background: var(--blue);"></div></div>
              <div class="bar-value">4</div>
            </div>
            <div class="bar-row">
              <div class="bar-label">Chemicals</div>
              <div class="bar-track"><div class="bar-fill" style="width: 47%; background: var(--red);"></div></div>
              <div class="bar-value">7</div>
            </div>
            <div class="bar-row">
              <div class="bar-label">Cleaning Products</div>
              <div class="bar-track"><div class="bar-fill" style="width: 33%; background: var(--teal);"></div></div>
              <div class="bar-value">5</div>
            </div>
            <div class="bar-row">
              <div class="bar-label">Laboratory Chemicals</div>
              <div class="bar-track"><div class="bar-fill" style="width: 20%; background: var(--purple);"></div></div>
              <div class="bar-value">3</div>
            </div>
          </div>
        </article>

        <article class="panel">
          <h2>Regulatory Compliance</h2>
          <p class="panel-subtitle">Current SDS readiness view across the indexed document set.</p>
          <div class="donut-layout">
            <div class="donut" role="img" aria-label="Regulatory compliance donut chart">
              <div class="donut-center">62%<span>Compliant</span></div>
            </div>
            <div class="legend">
              <div class="legend-item"><span class="dot" style="background: var(--green);"></span><span>GHS aligned</span><strong>62%</strong></div>
              <div class="legend-item"><span class="dot" style="background: var(--amber);"></span><span>Needs review</span><strong>23%</strong></div>
              <div class="legend-item"><span class="dot" style="background: var(--red);"></span><span>Action required</span><strong>15%</strong></div>
</div>
          </div>
        </article>
      </section>
    </main>

     <section class="page" id="agent-page" style="display: none;">
       <div class="agent-container">
         <div class="agent-header">
           <h2>AI Agent Dashboard</h2>
           <p class="agent-subtitle">AI Agent ready. Ask about hazards, PPE, storage, first aid, spill response, disposal, or product details.</p>
         </div>
         <div class="agent-content">
           <div class="chat-wrapper">
             <div id="chat" aria-live="polite"></div>
             <form id="form">
               <input id="question" autocomplete="off" placeholder="Ask about an SDS material..." />
               <button id="send" type="submit">Ask</button>
             </form>
           </div>
           <div class="history-wrapper">
             <h3>RECENT HISTORY</h3>
             <div id="history-list" class="history-list">
               <div class="history-item">Loading history...</div>
             </div>
           </div>
         </div>
       </div>
     </section>

    <script>
    const chat = document.querySelector("#chat");
    const form = document.querySelector("#form");
    const input = document.querySelector("#question");
    const send = document.querySelector("#send");
    const agentPage = document.querySelector("#agent-page");
    const historyList = document.querySelector("#history-list");

    async function loadHistory() {
      try {
        const response = await fetch("/history");
        const data = await response.json();
        historyList.innerHTML = "";
        if (data.history && data.history.length > 0) {
          data.history.forEach(item => {
            const fields = item.fields || {};
            const div = document.createElement("div");
            div.className = "history-item";
            div.innerHTML = `<strong>${fields.Type || "General"}</strong>: ${fields.Question || ""} <em>${new Date(fields.Date).toLocaleString()}</em>`;
            historyList.appendChild(div);
          });
        } else {
          historyList.innerHTML = '<div class="history-item">No history yet</div>';
        }
      } catch {
        historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
      }
    }

    function showAgentPage() {
      document.querySelector("main").style.display = "none";
      agentPage.style.display = "grid";
      document.querySelector(".shell").classList.add("has-agent");
      loadHistory();
    }

    function showMainPage() {
      agentPage.style.display = "none";
      document.querySelector("main").style.display = "block";
      document.querySelector(".shell").classList.remove("has-agent");
    }

    document.querySelectorAll(".nav-item")[1].addEventListener("click", showAgentPage);
    document.querySelectorAll(".nav-item")[0].addEventListener("click", showMainPage);

    function addMessage(text, role, sources) {
      const node = document.createElement("div");
      node.className = `message ${role}`;

      const textNode = document.createElement("div");
      textNode.className = "message-text";
      textNode.textContent = text;
      node.appendChild(textNode);

      if (sources && sources.length) {
        const sourceNode = document.createElement("div");
        sourceNode.className = "sources";
        sourceNode.textContent = "Sources: " + sources
          .map(item => `${item.source} p.${item.page}`)
          .filter(Boolean)
          .join("; ");
        node.appendChild(sourceNode);
      }

      chat.appendChild(node);

      if (role === "assistant" && text.length > 700) {
        textNode.classList.add("collapsed");
        const moreButton = document.createElement("button");
        moreButton.type = "button";
        moreButton.className = "more-button";
        moreButton.textContent = "More";
        moreButton.addEventListener("click", () => {
          const isExpanded = textNode.classList.toggle("expanded");
          textNode.classList.toggle("collapsed", !isExpanded);
          moreButton.textContent = isExpanded ? "Less" : "More";
          chat.scrollTop = chat.scrollHeight;
        });
        node.appendChild(moreButton);
      }

      chat.scrollTop = chat.scrollHeight;
      return node;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;

      addMessage(question, "user");
      input.value = "";
      send.disabled = true;
      const pending = addMessage("Searching indexed SDS files...", "assistant");

      try {
        const response = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Request failed");
        pending.remove();
        addMessage(data.answer, "assistant", data.sources);
      } catch (error) {
        pending.querySelector(".message-text").textContent = `Error: ${error.message}`;
      } finally {
        send.disabled = false;
        input.focus();
      }
    });
  </script>
</body>
</html>
"""


@app.post("/chat")
def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    try:
        result = answer_question(question)
        # Save to Airtable
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
