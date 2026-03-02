"""JARVIS Memory Module"""
import json, pickle, hashlib, logging, threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from jarvis_config import VECTOR_FILE, FACTS_FILE, CONV_FILE, EMBED_URL, EMBED_MODEL, MAX_HISTORY

logger = logging.getLogger("JARVIS.MEMORY")

@dataclass
class Fact: id: str; content: str; fact_type: str; source: str; confidence: float; embedding_id: Optional[str] = None

@dataclass
class ConversationTurn: role: str; content: str; timestamp: str

class VectorStore:
    def __init__(self):
        self.vectors: List[Dict] = []
        self._embed_cache: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        try:
            if Path(VECTOR_FILE).exists():
                with open(VECTOR_FILE, "rb") as f: self.vectors = pickle.load(f)
                logger.info(f"Loaded {len(self.vectors)} vectors")
        except: self.vectors = []
    
    def _save(self):
        try:
            with open(VECTOR_FILE, "wb") as f: pickle.dump(self.vectors, f)
        except: pass
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        if text in self._embed_cache: return self._embed_cache[text]
        try:
            import requests
            r = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=30)
            if r.status_code == 200:
                emb = r.json().get("embedding")
                if emb: self._embed_cache[text] = emb; return emb
        except: pass
        return None
    
    def add(self, id: str, text: str, metadata: Dict = None):
        emb = self._get_embedding(text)
        with self._lock:
            self.vectors.append({"id": id, "text": text, "embedding": emb, "metadata": metadata or {}})
            self._save()
    
    def search(self, query: str, k: int = 5) -> List[Dict]:
        qe = self._get_embedding(query)
        if not qe or not self.vectors: return []
        results = []
        for v in self.vectors:
            if v.get("embedding"):
                sim = self._cosine(qe, v["embedding"])
                results.append({**v, "score": sim})
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:k]
    
    @staticmethod
    def _cosine(a, b):
        dot = sum(x*y for x,y in zip(a,b)); na = sum(x*x for x in a)**0.5; nb = sum(x*x for x in b)**0.5
        return dot/(na*nb) if na*nb else 0

class MemoryV19:
    MAX_HISTORY = MAX_HISTORY
    
    def __init__(self):
        self.facts: Dict[str, Fact] = {}
        self.conversations: List[ConversationTurn] = []
        self.vector_store = VectorStore()
        self._lock = threading.RLock()
        self._load()
        logger.info(f"Memory: {len(self.facts)} facts, {len(self.conversations)} convs")
    
    def _load(self):
        try:
            if Path(FACTS_FILE).exists():
                with open(FACTS_FILE, "r", encoding="utf-8") as f:
                    self.facts = {k: Fact(**v) for k, v in json.load(f).items()}
        except: pass
        try:
            if Path(CONV_FILE).exists():
                with open(CONV_FILE, "r", encoding="utf-8") as f:
                    self.conversations = [ConversationTurn(**c) for c in json.load(f)]
        except: pass
    
    def _save_facts(self):
        try:
            with open(FACTS_FILE, "w", encoding="utf-8") as f:
                json.dump({k: asdict(v) for k, v in self.facts.items()}, f, ensure_ascii=False, indent=2)
        except: pass
    
    def _save_conv(self):
        try:
            with open(CONV_FILE, "w", encoding="utf-8") as f:
                json.dump([asdict(c) for c in self.conversations], f, ensure_ascii=False, indent=2)
        except: pass
    
    def add_fact(self, content: str, fact_type: str = "observation", source: str = "user", confidence: float = 1.0) -> Fact:
        fid = hashlib.md5(content.encode()).hexdigest()[:12]
        with self._lock:
            if fid in self.facts: return self.facts[fid]
            fact = Fact(id=fid, content=content, fact_type=fact_type, source=source, confidence=confidence)
            self.facts[fid] = fact
            self.vector_store.add(fid, content, {"type": fact_type, "source": source})
            fact.embedding_id = fid
        self._save_facts()
        return fact
    
    def get_all_facts(self) -> List[Fact]:
        with self._lock: return list(self.facts.values())
    
    def search_facts_vector(self, query: str, k: int = 5) -> List[Dict]:
        results = self.vector_store.search(query, k)
        enriched = []
        for r in results:
            fact = self.facts.get(r["id"])
            if fact: enriched.append({"content": fact.content, "type": fact.fact_type, "source": fact.source, "score": r.get("score", 0)})
        return enriched
    
    def add_message(self, role: str, content: str):
        with self._lock:
            self.conversations.append(ConversationTurn(role=role, content=content, timestamp=datetime.now().isoformat()))
            if len(self.conversations) > self.MAX_HISTORY * 2: self.conversations = self.conversations[-self.MAX_HISTORY:]
            self._save_conv()
    
    def get_recent(self, n: int = 10) -> List[ConversationTurn]:
        with self._lock: return self.conversations[-n:]

__all__ = ["VectorStore", "MemoryV19", "Fact", "ConversationTurn"]
