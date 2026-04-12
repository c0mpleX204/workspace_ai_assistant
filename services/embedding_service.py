import json
import logging
import math
from typing import Dict, List

import requests

from config.config import settings


def embed_text(text: str) -> List[float]:
    if not settings.embedding_api_key:
        raise ValueError("EMBEDDING_API_KEY is empty")
    url = f"{settings.embedding_api_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.embedding_model,
        "input": [text],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=settings.embedding_timeout_sec)
    resp.raise_for_status()
    data = resp.json()
    return data["data"][0]["embedding"]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def rank_chunks(query_vec: List[float], chunks: List[Dict], top_k: int = 5) -> List[Dict]:
    scored = []
    for c in chunks:
        emb = c["embedding"]
        if isinstance(emb, str):
            emb = json.loads(emb)
        score = cosine_similarity(query_vec, emb)
        scored.append(
            {
                "chunk_id": c["chunk_id"],
                "content": c["content"],
                "score": score,
                "document_id": c["document_id"],
                "document_title": c["document_title"],
                "page_no": c["page_no"],
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def embed_document_chunks(document_id: int, batch_size: int = 32) -> None:
    from infra.db import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            while True:
                cur.execute(
                    "select id, content from chunks where document_id = %s and embedding is null limit %s",
                    (document_id, batch_size),
                )
                rows = cur.fetchall()
                if not rows:
                    logging.info(f"All chunks of document {document_id} have been embedded.")
                    break
                texts = [row[1] for row in rows]
                try:
                    embeddings = [embed_text(text) for text in texts]
                except Exception as exc:
                    logging.warning(
                        f"Failed to embed a batch of chunks for document {document_id}: {exc}"
                    )
                    break
                for (chunk_id, _), emb in zip(rows, embeddings):
                    cur.execute(
                        "update chunks set embedding = %s where id = %s",
                        (json.dumps(emb), chunk_id),
                    )
                conn.commit()
