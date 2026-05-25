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
      --bg: #eef3f8;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d6dee8;
      --nav: #0b1f33;
      --nav-soft: #143553;
      --green: #08745f;
      --amber: #b54708;
      --red: #b42318;
      --blue: #246bfd;
      --teal: #0e9384;
      --purple: #6941c6;
      --shadow: 0 18px 40px rgba(16, 42, 67, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Arial, Helvetica, sans-serif;
      background:
        linear-gradient(135deg, rgba(8, 116, 95, 0.08), transparent 34%),
        linear-gradient(315deg, rgba(36, 107, 253, 0.08), transparent 38%),
        var(--bg);
      color: var(--ink);
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 264px minmax(0, 1fr) 380px;
      gap: 18px;
      padding: 18px;
    }
    aside {
      background:
        linear-gradient(180deg, rgba(20, 53, 83, 0.96), rgba(11, 31, 51, 1));
      color: #ffffff;
      border-radius: 18px;
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      gap: 26px;
      box-shadow: var(--shadow);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 23px;
      font-weight: 800;
      letter-spacing: 0;
      padding: 0 6px;
    }
    .brand-mark {
      width: 38px;
      height: 38px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      background: #f9fafb;
      color: var(--nav);
      font-weight: 900;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.4);
    }
    nav {
      display: flex;
      flex-direction: column;
      gap: 9px;
    }
    .nav-item {
      border: 0;
      border-radius: 12px;
      background: transparent;
      color: #d9e6f2;
      min-height: 46px;
      padding: 0 14px;
      display: flex;
      align-items: center;
      justify-content: flex-start;
      gap: 10px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }
    .nav-item::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.35);
    }
    .nav-item.active,
    .nav-item:hover {
      background: rgba(255, 255, 255, 0.12);
      color: #ffffff;
    }
    .nav-item.active::before {
      background: #34d399;
    }
    .sidebar-foot {
      margin-top: auto;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 14px;
      padding: 14px;
      color: #cbdced;
      font-size: 13px;
      line-height: 1.45;
      background: rgba(255, 255, 255, 0.07);
    }
    .sidebar-foot strong {
      display: block;
      color: #ffffff;
      margin-bottom: 4px;
    }
    .main {
      min-width: 0;
      padding: 4px 0 4px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 24px;
      border: 1px solid rgba(214, 222, 232, 0.9);
      border-radius: 18px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(241, 248, 247, 0.96));
      box-shadow: var(--shadow);
    }
    h1 {
      margin: 0;
      font-size: 30px;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
    }
    .sync {
      color: #ffffff;
      font-size: 13px;
      font-weight: 800;
      white-space: nowrap;
      background: var(--green);
      border-radius: 999px;
      padding: 10px 14px;
      box-shadow: 0 10px 24px rgba(8, 116, 95, 0.18);
    }
    .quick-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }
    .quick-pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 10px;
      color: var(--muted);
      background: #ffffff;
      font-size: 12px;
      font-weight: 800;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid rgba(214, 222, 232, 0.9);
      border-radius: 16px;
      padding: 18px;
      min-height: 128px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 12px 28px rgba(16, 42, 67, 0.07);
      position: relative;
      overflow: hidden;
    }
    .metric::after {
      content: "";
      position: absolute;
      right: -24px;
      top: -24px;
      width: 80px;
      height: 80px;
      border-radius: 50%;
      background: rgba(8, 116, 95, 0.10);
    }
    .metric-label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      position: relative;
    }
    .metric-value {
      font-size: 38px;
      font-weight: 800;
      line-height: 1;
      position: relative;
    }
    .metric-note {
      color: var(--muted);
      font-size: 12px;
      position: relative;
    }
    .dashboard-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 18px;
      align-items: stretch;
    }
    .panel {
      background: var(--panel);
      border: 1px solid rgba(214, 222, 232, 0.9);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 14px 30px rgba(16, 42, 67, 0.08);
    }
    .panel h2 {
      margin: 0 0 4px;
      font-size: 18px;
      letter-spacing: 0;
    }
    .panel-subtitle {
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 13px;
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
      height: 14px;
      border-radius: 999px;
      background: #edf1f6;
      overflow: hidden;
      box-shadow: inset 0 0 0 1px rgba(16, 42, 67, 0.04);
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
      width: 168px;
      aspect-ratio: 1;
      border-radius: 50%;
      background:
        radial-gradient(circle at center, #ffffff 0 47%, transparent 48%),
        conic-gradient(var(--green) 0 62%, var(--amber) 62% 85%, var(--red) 85% 100%);
      border: 1px solid var(--line);
      position: relative;
      box-shadow: 0 18px 30px rgba(16, 42, 67, 0.12);
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
      border: 1px solid rgba(214, 222, 232, 0.9);
      border-radius: 18px;
      background: rgba(251, 252, 254, 0.96);
      display: grid;
      grid-template-rows: auto 1fr auto;
      padding: 20px 16px;
      gap: 14px;
      box-shadow: var(--shadow);
    }
    .agent-head {
      padding: 16px;
      border-bottom: 1px solid var(--line);
      border-radius: 14px;
      background: #ffffff;
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
      border-radius: 14px;
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
      border-radius: 12px;
      padding: 0 12px;
      font-size: 14px;
      color: var(--ink);
      background: var(--panel);
    }
    button {
      min-height: 44px;
      border: 0;
      border-radius: 12px;
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
        min-height: 520px;
      }
    }
    @media (max-width: 820px) {
      .shell {
        grid-template-columns: 1fr;
      }
      aside {
        padding: 18px;
        border-radius: 0;
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
      <div class="brand"><span class="brand-mark">H</span><span>Hazsoft Agent</span></div>
      <nav aria-label="SDS navigation">
        <button class="nav-item active" type="button">All SDS</button>
        <button class="nav-item" type="button">My Documents</button>
        <button class="nav-item" type="button">Categories</button>
        <button class="nav-item" type="button">Hazard</button>
        <button class="nav-item" type="button">Settings</button>
      </nav>
      <div class="sidebar-foot">
        <strong>SDS Intelligence</strong>
        15 source documents indexed with Qdrant and OpenAI embeddings.
      </div>
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
