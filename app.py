from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import PDF_FOLDER
from rag import answer_question, index_chunks, rag_status


app = FastAPI(title="Hazsoft SDS RAG Chatbot")


class ChatRequest(BaseModel):
    question: str


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hazsoft SDS Chatbot</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --ink: #182230;
      --muted: #667085;
      --line: #d0d5dd;
      --accent: #126b68;
      --accent-2: #b54708;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    main {
      max-width: 1040px;
      min-height: 100vh;
      margin: 0 auto;
      display: grid;
      grid-template-rows: auto 1fr auto;
      padding: 24px;
      gap: 16px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 14px;
    }
    h1 {
      font-size: 24px;
      margin: 0 0 4px;
      letter-spacing: 0;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .status {
      color: var(--accent);
      font-size: 13px;
      white-space: nowrap;
    }
    #chat {
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 4px 0;
    }
    .message {
      max-width: 82%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
      line-height: 1.48;
      background: var(--panel);
      white-space: pre-wrap;
    }
    .user {
      align-self: flex-end;
      border-color: #87b9b6;
      background: #e8f4f3;
    }
    .assistant {
      align-self: flex-start;
    }
    .sources {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      white-space: normal;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }
    input {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 12px;
      font-size: 15px;
      color: var(--ink);
      background: var(--panel);
    }
    button {
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      padding: 0 18px;
      background: var(--accent);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.65;
      cursor: wait;
    }
    @media (max-width: 640px) {
      main { padding: 16px; }
      header { align-items: start; flex-direction: column; }
      .message { max-width: 100%; }
      form { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Hazsoft SDS Chatbot</h1>
        <p>Ask questions grounded in your indexed SDS PDF files.</p>
      </div>
      <div class="status">Qdrant + OpenAI RAG</div>
    </header>

    <section id="chat" aria-live="polite">
      <div class="message assistant">Ready. Ask about hazards, PPE, storage, first aid, spill response, disposal, or product details.</div>
    </section>

    <form id="form">
      <input id="question" autocomplete="off" placeholder="Ask a question about the SDS files..." />
      <button id="send" type="submit">Ask</button>
    </form>
  </main>

  <script>
    const chat = document.querySelector("#chat");
    const form = document.querySelector("#form");
    const input = document.querySelector("#question");
    const send = document.querySelector("#send");

    function addMessage(text, role, sources) {
      const node = document.createElement("div");
      node.className = `message ${role}`;
      node.textContent = text;
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
        pending.textContent = `Error: ${error.message}`;
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
        return answer_question(question)
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
