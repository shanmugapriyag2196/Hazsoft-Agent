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
  <title>Hazsoft Agent Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d8dee8;
      --nav: #102a43;
      --nav-soft: #1b3d5f;
      --green: #08745f;
      --amber: #b54708;
      --red: #b42318;
      --blue: #246bfd;
      --teal: #0e9384;
      --purple: #6941c6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 250px minmax(0, 1fr) 360px;
    }
    aside {
      background: var(--nav);
      color: #ffffff;
      padding: 24px 18px;
      display: flex;
      flex-direction: column;
      gap: 28px;
    }
    .brand {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: 0;
    }
    nav {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .nav-item {
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: #d9e6f2;
      min-height: 42px;
      padding: 0 12px;
      display: flex;
      align-items: center;
      justify-content: flex-start;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }
    .nav-item.active,
    .nav-item:hover {
      background: var(--nav-soft);
      color: #ffffff;
    }
    .main {
      min-width: 0;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0;
      font-size: 26px;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
    }
    .sync {
      color: var(--green);
      font-size: 13px;
      font-weight: 800;
      white-space: nowrap;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-height: 112px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .metric-label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .metric-value {
      font-size: 34px;
      font-weight: 800;
      line-height: 1;
    }
    .metric-note {
      color: var(--muted);
      font-size: 12px;
    }
    .dashboard-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 16px;
      align-items: stretch;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 18px;
      letter-spacing: 0;
    }
    .bar-chart {
      display: grid;
      gap: 15px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 150px 1fr 42px;
      gap: 10px;
      align-items: center;
      min-height: 34px;
    }
    .bar-label {
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
    }
    .bar-track {
      height: 12px;
      border-radius: 999px;
      background: #edf1f6;
      overflow: hidden;
    }
    .bar-fill {
      height: 100%;
      border-radius: 999px;
    }
    .bar-value {
      color: var(--muted);
      font-size: 13px;
      text-align: right;
      font-weight: 800;
    }
    .donut-layout {
      display: grid;
      grid-template-columns: 170px 1fr;
      gap: 18px;
      align-items: center;
    }
    .donut {
      width: 160px;
      aspect-ratio: 1;
      border-radius: 50%;
      background:
        radial-gradient(circle at center, #ffffff 0 47%, transparent 48%),
        conic-gradient(var(--green) 0 62%, var(--amber) 62% 85%, var(--red) 85% 100%);
      border: 1px solid var(--line);
      position: relative;
    }
    .donut-center {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-direction: column;
      font-weight: 800;
      font-size: 24px;
    }
    .donut-center span {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .legend {
      display: grid;
      gap: 10px;
    }
    .legend-item {
      display: grid;
      grid-template-columns: 12px 1fr auto;
      gap: 8px;
      align-items: center;
      font-size: 13px;
      color: var(--muted);
    }
    .dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }
    .agent {
      min-width: 0;
      border-left: 1px solid var(--line);
      background: #fbfcfe;
      display: grid;
      grid-template-rows: auto 1fr auto;
      padding: 22px 18px;
      gap: 14px;
    }
    .agent-head {
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }
    .agent-head h2 {
      margin: 0;
      font-size: 20px;
    }
    .agent-head p {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }
    #chat {
      min-height: 0;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding-right: 4px;
    }
    #chat::-webkit-scrollbar,
    .message-text.expanded::-webkit-scrollbar {
      width: 10px;
    }
    #chat::-webkit-scrollbar-track,
    .message-text.expanded::-webkit-scrollbar-track {
      background: #edf1f6;
      border-radius: 8px;
    }
    #chat::-webkit-scrollbar-thumb,
    .message-text.expanded::-webkit-scrollbar-thumb {
      background: #98a2b3;
      border-radius: 8px;
      border: 2px solid #edf1f6;
    }
    .message {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      line-height: 1.48;
      background: var(--panel);
      overflow-wrap: anywhere;
      font-size: 14px;
    }
    .user {
      border-color: #9ccbc5;
      background: #e9f6f4;
    }
    .assistant {
      background: #ffffff;
    }
    .message-text {
      white-space: pre-wrap;
    }
    .assistant .message-text.collapsed {
      max-height: 190px;
      overflow: hidden;
    }
    .assistant .message-text.expanded {
      max-height: 360px;
      overflow-y: auto;
      padding-right: 10px;
    }
    .sources {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      white-space: normal;
    }
    .more-button {
      min-height: 32px;
      margin-top: 10px;
      padding: 0 12px;
      border-radius: 8px;
      background: transparent;
      color: var(--green);
      border: 1px solid #8bc6bd;
      font-weight: 800;
      cursor: pointer;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }
    input {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 12px;
      font-size: 14px;
      color: var(--ink);
      background: var(--panel);
    }
    button {
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      padding: 0 16px;
      background: var(--green);
      color: white;
      font-weight: 800;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.65;
      cursor: wait;
    }
    @media (max-width: 1120px) {
      .shell {
        grid-template-columns: 220px minmax(0, 1fr);
      }
      .agent {
        grid-column: 1 / -1;
        border-left: 0;
        border-top: 1px solid var(--line);
        min-height: 520px;
      }
    }
    @media (max-width: 820px) {
      .shell {
        grid-template-columns: 1fr;
      }
      aside {
        padding: 18px;
      }
      nav {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .main {
        padding: 18px;
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
      <div class="brand">Hazsoft Agent</div>
      <nav aria-label="SDS navigation">
        <button class="nav-item active" type="button">All SDS</button>
        <button class="nav-item" type="button">My Documents</button>
        <button class="nav-item" type="button">Categories</button>
        <button class="nav-item" type="button">Hazard</button>
        <button class="nav-item" type="button">Settings</button>
      </nav>
    </aside>

    <main class="main">
      <section class="topbar">
        <div>
          <h1>SDS Dashboard</h1>
          <p class="subtitle">Monitor indexed safety documents, hazard levels, categories, and compliance readiness.</p>
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

    <section class="agent" aria-label="Hazsoft SDS assistant">
      <div class="agent-head">
        <h2>Ask Hazsoft Agent</h2>
        <p>Ask about hazards, PPE, storage, first aid, spill response, disposal, or product details.</p>
      </div>

      <div id="chat" aria-live="polite">
        <div class="message assistant">
          <div class="message-text">Ready. Ask a question about the indexed SDS files.</div>
        </div>
      </div>

      <form id="form">
        <input id="question" autocomplete="off" placeholder="Ask about an SDS material..." />
        <button id="send" type="submit">Ask</button>
      </form>
    </section>
  </div>

  <script>
    const chat = document.querySelector("#chat");
    const form = document.querySelector("#form");
    const input = document.querySelector("#question");
    const send = document.querySelector("#send");

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
