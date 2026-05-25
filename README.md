# Hazsoft SDS RAG Chatbot

Local RAG chatbot for the PDF files in `Hazsoft Sample SDS Files`.

## What It Uses

- PDF folder: `C:\Users\priyag\Documents\Hazsoft Agent\Hazsoft Sample SDS Files`
- Chunk size: `500`
- Chunk overlap: `75`
- Embedding model: `text-embedding-3-small`
- Vector database: Qdrant
- Chat API/UI: FastAPI

## Setup

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Create `.env` from the example:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Edit `.env` and set your OpenAI API key:

   ```text
   OPENAI_API_KEY=sk-...
   ```

5. Start Qdrant:

   ```powershell
   docker compose up -d
   ```

6. Ingest the PDFs into Qdrant:

   ```powershell
   python ingest.py
   ```

7. Run the chatbot:

   ```powershell
   uvicorn app:app --reload
   ```

8. Open the app:

   ```text
   http://127.0.0.1:8000
   ```

## Ask Questions

Ask about SDS details such as hazards, first aid, handling, storage, PPE, spill response, disposal, and product information. Answers include source PDF names and page numbers used for retrieval.
