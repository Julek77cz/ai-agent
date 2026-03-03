"""Semantic memory - facts and concepts with confidence scores, ChromaDB-backed"""
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from jarvis_config import FACTS_FILE, SEMANTIC_COLLECTION, CONFIDENCE_THRESHOLD
from jarvis_memory.vector_store import ChromaCollection

logger = logging.getLogger("JARVIS.MEMORY.SEMANTIC")


@dataclass
class Fact:
    id: str
    content: str
    fact_type: str
    source: str
    confidence: float
    embedding_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SemanticMemory:
    def __init__(self):
        self._facts: Dict[str, Fact] = {}
        self._lock = threading.RLock()
        self._vector = ChromaCollection(SEMANTIC_COLLECTION)
        self._load()

    def _load(self) -> None:
        try:
            if Path(FACTS_FILE).exists():
                with open(FACTS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                with self._lock:
                    for k, v in raw.items():
                        fields = {f: v[f] for f in Fact.__dataclass_fields__ if f in v}
                        self._facts[k] = Fact(**fields)
                logger.info("Loaded %d semantic facts", len(self._facts))
                self._sync_vectors()
        except Exception as e:
            logger.warning("Failed to load facts: %s", e)

    def _sync_vectors(self) -> None:
        with self._lock:
            facts = list(self._facts.values())
        for fact in facts:
            self._vector.add(
                id=fact.id,
                text=fact.content,
                metadata={
                    "type": fact.fact_type,
                    "source": fact.source,
                    "confidence": str(fact.confidence),
                },
            )

    def _save(self) -> None:
        try:
            Path(FACTS_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(FACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {k: asdict(v) for k, v in self._facts.items()},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.warning("Failed to save facts: %s", e)

    def add_fact(
        self,
        content: str,
        fact_type: str = "observation",
        source: str = "user",
        confidence: float = 1.0,
    ) -> Fact:
        fid = hashlib.md5(content.encode()).hexdigest()[:12]
        with self._lock:
            if fid in self._facts:
                existing = self._facts[fid]
                if confidence > existing.confidence:
                    existing.confidence = confidence
                    existing.updated_at = datetime.now().isoformat()
                    self._save()
                return existing
            fact = Fact(
                id=fid,
                content=content,
                fact_type=fact_type,
                source=source,
                confidence=confidence,
                embedding_id=fid,
            )
            self._facts[fid] = fact
        self._vector.add(
            id=fid,
            text=content,
            metadata={"type": fact_type, "source": source, "confidence": str(confidence)},
        )
        self._save()
        return fact

    def get_all(self) -> List[Fact]:
        with self._lock:
            return list(self._facts.values())

    def get_by_id(self, fact_id: str) -> Optional[Fact]:
        with self._lock:
            return self._facts.get(fact_id)

    def search(self, query: str, k: int = 5) -> List[Dict]:
        results = self._vector.search(query, k=k)
        enriched = []
        for r in results:
            fact = self.get_by_id(r["id"])
            if fact and fact.confidence >= CONFIDENCE_THRESHOLD:
                enriched.append(
                    {
                        "content": fact.content,
                        "type": fact.fact_type,
                        "source": fact.source,
                        "confidence": fact.confidence,
                        "score": r.get("score", 0.0),
                    }
                )
        return enriched

    def remove_fact(self, fact_id: str) -> bool:
        with self._lock:
            if fact_id not in self._facts:
                return False
            del self._facts[fact_id]
        self._vector.delete(fact_id)
        self._save()
        return True

    def update_confidence(self, fact_id: str, confidence: float) -> bool:
        with self._lock:
            if fact_id not in self._facts:
                return False
            self._facts[fact_id].confidence = confidence
            self._facts[fact_id].updated_at = datetime.now().isoformat()
        self._save()
        return True

    def deduplicate(self) -> int:
        return self._vector.deduplicate()

    def count(self) -> int:
        with self._lock:
            return len(self._facts)


__all__ = ["SemanticMemory", "Fact"]
