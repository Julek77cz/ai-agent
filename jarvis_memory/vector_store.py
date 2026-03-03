"""ChromaDB-backed vector store"""
import logging
import threading
from typing import Any, Dict, List, Optional

from jarvis_config import CHROMA_DIR
from jarvis_memory.embeddings import get_embedding_service

logger = logging.getLogger("JARVIS.MEMORY.VECTORSTORE")

_DEDUP_THRESHOLD = 0.95


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na * nb else 0.0


class ChromaCollection:
    def __init__(self, name: str):
        self._name = name
        self._lock = threading.Lock()
        self._client = None
        self._collection = None
        self._embeddings = get_embedding_service()
        self._init()

    def _init(self) -> None:
        try:
            import chromadb

            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._collection = self._client.get_or_create_collection(
                name=self._name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB collection '%s' ready (%d items)", self._name, self._collection.count())
        except Exception as e:
            logger.warning("ChromaDB init failed for '%s': %s", self._name, e)
            self._collection = None

    def _available(self) -> bool:
        return self._collection is not None

    def add(self, id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        embedding = self._embeddings.get(text)
        if embedding is None:
            return False
        if not self._available():
            return False
        try:
            with self._lock:
                self._collection.upsert(
                    ids=[id],
                    documents=[text],
                    embeddings=[embedding],
                    metadatas=[metadata or {}],
                )
            return True
        except Exception as e:
            logger.warning("ChromaDB add failed: %s", e)
            return False

    def search(self, query: str, k: int = 5, where: Optional[Dict] = None) -> List[Dict]:
        embedding = self._embeddings.get(query)
        if embedding is None or not self._available():
            return []
        try:
            kwargs: Dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": min(k, max(1, self._collection.count())),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            result = self._collection.query(**kwargs)
            out = []
            for idx, doc_id in enumerate(result["ids"][0]):
                distance = result["distances"][0][idx]
                score = 1.0 - distance
                out.append(
                    {
                        "id": doc_id,
                        "text": result["documents"][0][idx],
                        "metadata": result["metadatas"][0][idx],
                        "score": score,
                    }
                )
            return out
        except Exception as e:
            logger.warning("ChromaDB search failed: %s", e)
            return []

    def delete(self, id: str) -> bool:
        if not self._available():
            return False
        try:
            with self._lock:
                self._collection.delete(ids=[id])
            return True
        except Exception as e:
            logger.warning("ChromaDB delete failed: %s", e)
            return False

    def get_all(self) -> List[Dict]:
        if not self._available():
            return []
        try:
            result = self._collection.get(include=["documents", "metadatas", "embeddings"])
            out = []
            for idx, doc_id in enumerate(result["ids"]):
                out.append(
                    {
                        "id": doc_id,
                        "text": result["documents"][idx],
                        "metadata": result["metadatas"][idx],
                        "embedding": result["embeddings"][idx] if result.get("embeddings") else None,
                    }
                )
            return out
        except Exception as e:
            logger.warning("ChromaDB get_all failed: %s", e)
            return []

    def count(self) -> int:
        if not self._available():
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def deduplicate(self, threshold: float = _DEDUP_THRESHOLD) -> int:
        if not self._available():
            return 0
        items = self.get_all()
        if len(items) < 2:
            return 0

        items_with_emb = [i for i in items if i.get("embedding")]
        removed = 0
        seen_ids: set = set()

        for i in range(len(items_with_emb)):
            if items_with_emb[i]["id"] in seen_ids:
                continue
            for j in range(i + 1, len(items_with_emb)):
                if items_with_emb[j]["id"] in seen_ids:
                    continue
                sim = _cosine(items_with_emb[i]["embedding"], items_with_emb[j]["embedding"])
                if sim >= threshold:
                    seen_ids.add(items_with_emb[j]["id"])
                    self.delete(items_with_emb[j]["id"])
                    removed += 1

        return removed


__all__ = ["ChromaCollection"]
