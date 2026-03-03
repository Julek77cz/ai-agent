"""Unified cognitive memory interface - working, episodic, and semantic layers"""
import logging
import threading
from typing import Any, Dict, List, Optional

from jarvis_memory.working_memory import WorkingMemory
from jarvis_memory.episodic_memory import EpisodicMemory, ConversationTurn
from jarvis_memory.semantic_memory import SemanticMemory, Fact
from jarvis_memory.knowledge_graph import KnowledgeGraph
from jarvis_memory.consolidation import ConsolidationScheduler

logger = logging.getLogger("JARVIS.MEMORY.MANAGER")


class CognitiveMemory:
    def __init__(self, start_consolidation: bool = True):
        logger.info("Initializing CognitiveMemory...")
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.kg = KnowledgeGraph()
        self._session_id = _new_session_id()
        self._consolidator = ConsolidationScheduler(self)
        if start_consolidation:
            self._consolidator.start()
        logger.info(
            "CognitiveMemory ready: facts=%d, turns=%d, kg_entities=%d",
            self.semantic.count(),
            self.episodic.count(),
            self.kg.entity_count(),
        )

    def remember(
        self,
        content: str,
        fact_type: str = "observation",
        source: str = "user",
        confidence: float = 1.0,
    ) -> Fact:
        fact = self.semantic.add_fact(content, fact_type=fact_type, source=source, confidence=confidence)
        self.working.set(
            key=f"recent_fact_{fact.id}",
            value=content,
            category="recent_facts",
            importance=confidence,
        )
        return fact

    def recall(self, query: str, k: int = 5) -> List[Dict]:
        semantic_results = self.semantic.search(query, k=k)
        episodic_results = self.episodic.search_semantic(query, k=3)
        working_items = self.working.all()
        combined = list(semantic_results)
        seen_contents = {r["content"] for r in combined}
        for ep in episodic_results:
            text = ep.get("text", "")
            if text and text not in seen_contents:
                combined.append(
                    {
                        "content": text,
                        "type": "episodic",
                        "source": "episodic",
                        "score": ep.get("score", 0.0),
                        "confidence": 1.0,
                    }
                )
                seen_contents.add(text)
        for item in working_items:
            val = str(item.value)
            if val not in seen_contents:
                combined.append(
                    {
                        "content": val,
                        "type": "working",
                        "source": "working",
                        "score": item.importance,
                        "confidence": 1.0,
                    }
                )
                seen_contents.add(val)
        combined.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return combined[:k]

    def forget(self, fact_id: str) -> bool:
        removed = self.semantic.remove_fact(fact_id)
        self.working.remove(f"recent_fact_{fact_id}")
        return removed

    def consolidate(self) -> dict:
        return self._consolidator.run_consolidation()

    def add_message(self, role: str, content: str) -> ConversationTurn:
        self._consolidator.record_activity()
        turn = self.episodic.add_turn(role, content, session_id=self._session_id)
        self.working.set(
            key=f"last_{role}",
            value=content[:200],
            category="recent_messages",
            importance=0.8,
        )
        return turn

    def get_recent(self, n: int = 10) -> List[ConversationTurn]:
        return self.episodic.get_recent(n)

    def add_fact(
        self,
        content: str,
        fact_type: str = "observation",
        source: str = "user",
        confidence: float = 1.0,
    ) -> Fact:
        return self.remember(content, fact_type=fact_type, source=source, confidence=confidence)

    def get_all_facts(self) -> List[Fact]:
        return self.semantic.get_all()

    def search_facts_vector(self, query: str, k: int = 5) -> List[Dict]:
        return self.semantic.search(query, k=k)

    def set_context(self, key: str, value: Any, importance: float = 0.7) -> None:
        self.working.set(key=key, value=value, category="context", importance=importance)

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.working.get(key, default)

    def shutdown(self) -> None:
        self._consolidator.stop()
        logger.info("CognitiveMemory shut down")


def _new_session_id() -> str:
    import hashlib, time
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]


__all__ = ["CognitiveMemory"]
