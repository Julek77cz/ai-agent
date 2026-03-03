"""Embedding service with LRU caching"""
import logging
import threading
from collections import OrderedDict
from typing import List, Optional

import requests

from jarvis_config import EMBED_URL, EMBED_MODEL

logger = logging.getLogger("JARVIS.MEMORY.EMBEDDINGS")

_CACHE_MAX = 512


class EmbeddingService:
    def __init__(self):
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, text: str) -> Optional[List[float]]:
        with self._lock:
            if text in self._cache:
                self._cache.move_to_end(text)
                return self._cache[text]

        embedding = self._fetch(text)
        if embedding:
            with self._lock:
                self._cache[text] = embedding
                self._cache.move_to_end(text)
                if len(self._cache) > _CACHE_MAX:
                    self._cache.popitem(last=False)
        return embedding

    def get_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        return [self.get(t) for t in texts]

    def _fetch(self, text: str) -> Optional[List[float]]:
        try:
            r = requests.post(
                EMBED_URL,
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            if r.status_code == 200:
                return r.json().get("embedding")
        except Exception as e:
            logger.debug("Embedding fetch failed: %s", e)
        return None

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


_service: Optional[EmbeddingService] = None
_service_lock = threading.Lock()


def get_embedding_service() -> EmbeddingService:
    global _service
    with _service_lock:
        if _service is None:
            _service = EmbeddingService()
    return _service


__all__ = ["EmbeddingService", "get_embedding_service"]
