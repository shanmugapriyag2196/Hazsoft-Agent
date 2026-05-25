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

## Troubleshooting

If the chat shows that the Qdrant collection does not exist, the PDFs have not been indexed into the collection configured by `QDRANT_COLLECTION`. Make sure Qdrant is running, then run:

```powershell
python ingest.py
```

The app and ingestion script must use the same `.env` value:

```text
QDRANT_COLLECTION=hazsoft-agent
```

For Vercel, environment variables only configure the deployed app. They do not automatically create the Qdrant collection. Redeploy and check:

```text
https://your-vercel-app.vercel.app/health
```

If `collection_exists` is `false` or `point_count` is `0`, run ingestion from the deployed app:

```powershell
Invoke-RestMethod -Method Post -Uri "https://your-vercel-app.vercel.app/admin/ingest"
```

After ingestion, `/health` should show `collection_exists: true` and `point_count` greater than `0`.

You can also open this URL in the browser:

```text
https://your-vercel-app.vercel.app/admin/ingest
```
