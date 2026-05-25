from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from openai import OpenAI
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from config import (
    CHAT_MODEL,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
    TOP_K,
)


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    payload: Dict[str, object]


def get_openai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to your .env file.")
    return OpenAI(api_key=OPENAI_API_KEY)


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def ensure_collection(client: QdrantClient) -> None:
    collections = client.get_collections().collections
    if any(collection.name == QDRANT_COLLECTION for collection in collections):
        return

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=Distance.COSINE,
        ),
    )


def extract_pdf_pages(pdf_path: Path) -> Iterable[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        normalized = " ".join(text.split())
        if normalized:
            yield index, normalized


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be greater than or equal to 0 and smaller than chunk_size")

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def stable_chunk_id(pdf_path: Path, page: int, chunk_index: int, text: str) -> str:
    source = f"{pdf_path.name}:{page}:{chunk_index}:{hashlib.sha1(text.encode('utf-8')).hexdigest()}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, source))


def build_chunks(pdf_folder: Path) -> List[Chunk]:
    if not pdf_folder.exists():
        raise FileNotFoundError(f"PDF folder not found: {pdf_folder}")

    chunks: List[Chunk] = []
    for pdf_path in sorted(pdf_folder.glob("*.pdf")):
        for page, page_text in extract_pdf_pages(pdf_path):
            for chunk_index, text in enumerate(split_text(page_text)):
                chunk_id = stable_chunk_id(pdf_path, page, chunk_index, text)
                chunks.append(
                    Chunk(
                        id=chunk_id,
                        text=text,
                        payload={
                            "text": text,
                            "source": pdf_path.name,
                            "path": str(pdf_path),
                            "page": page,
                            "chunk_index": chunk_index,
                        },
                    )
                )
    return chunks


def embed_texts(client: OpenAI, texts: Sequence[str]) -> List[List[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=list(texts))
    return [item.embedding for item in response.data]


def batched(items: Sequence[Chunk], batch_size: int) -> Iterable[Sequence[Chunk]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def index_chunks(pdf_folder: Path, batch_size: int = 64) -> int:
    openai_client = get_openai_client()
    qdrant_client = get_qdrant_client()
    ensure_collection(qdrant_client)

    chunks = build_chunks(pdf_folder)
    for batch in batched(chunks, batch_size):
        vectors = embed_texts(openai_client, [chunk.text for chunk in batch])
        points = [
            PointStruct(id=chunk.id, vector=vector, payload=chunk.payload)
            for chunk, vector in zip(batch, vectors)
        ]
        qdrant_client.upsert(collection_name=QDRANT_COLLECTION, points=points)

    return len(chunks)


def search(question: str, top_k: int = TOP_K) -> List[Dict[str, object]]:
    openai_client = get_openai_client()
    qdrant_client = get_qdrant_client()

    query_vector = embed_texts(openai_client, [question])[0]
    hits = qdrant_client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True,
    )

    results: List[Dict[str, object]] = []
    for hit in hits:
        payload = hit.payload or {}
        results.append(
            {
                "score": hit.score,
                "text": payload.get("text", ""),
                "source": payload.get("source", ""),
                "page": payload.get("page", ""),
                "chunk_index": payload.get("chunk_index", ""),
            }
        )
    return results


def answer_question(question: str) -> Dict[str, object]:
    contexts = search(question)
    context_text = "\n\n".join(
        f"Source: {item['source']} | Page: {item['page']} | Chunk: {item['chunk_index']}\n{item['text']}"
        for item in contexts
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a careful SDS document assistant. Answer only from the provided context. "
                "If the answer is not present in the context, say you do not have enough information "
                "in the indexed SDS files. Include concise source references using PDF filename and page."
            ),
        },
        {
            "role": "user",
            "content": f"Question:\n{question}\n\nRetrieved SDS context:\n{context_text}",
        },
    ]

    openai_client = get_openai_client()
    response = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.1,
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": contexts,
    }
