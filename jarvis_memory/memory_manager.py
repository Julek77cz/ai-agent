"""Unified cognitive memory interface - working, episodic, semantic layers + WAL + Procedural"""
import logging
import threading
from typing import Any, Dict, List, Optional

from jarvis_memory.working_memory import WorkingMemory
from jarvis_memory.episodic_memory import EpisodicMemory, ConversationTurn
from jarvis_memory.semantic_memory import SemanticMemory, Fact
from jarvis_memory.knowledge_graph import KnowledgeGraph
from jarvis_memory.consolidation import ConsolidationScheduler

# Import new modules
from jarvis_memory.wal import get_wal, WALEntryType, shutdown_wal
from jarvis_memory.procedural_memory import (
    get_procedural_memory,
    ProceduralMemory,
    FailureRecord,
    RecoveryRecord,
    ErrorPattern,
)

logger = logging.getLogger("JARVIS.MEMORY.MANAGER")


class CognitiveMemory:
    def __init__(self, start_consolidation: bool = True):
        logger.info("Initializing CognitiveMemory...")
        
        # Initialize WAL for state persistence
        self._wal = get_wal()
        
        # Initialize Procedural Memory for learning from mistakes
        self._procedural = get_procedural_memory()
        
        # Core memory layers
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.kg = KnowledgeGraph()
        
        # Session tracking
        self._session_id = _new_session_id()
        
        # Consolidation scheduler
        self._consolidator = ConsolidationScheduler(self)
        if start_consolidation:
            self._consolidator.start()
        
        # Try to recover state from WAL if needed
        self._check_recovery()
        
        logger.info(
            "CognitiveMemory ready: facts=%d, turns=%d, kg_entities=%d, wal_entries=%d",
            self.semantic.count(),
            self.episodic.count(),
            self.kg.entity_count(),
            self._wal.get_entry_count(),
        )
    
    def _check_recovery(self) -> None:
        """Check if recovery is needed from WAL snapshot."""
        recovered_state = self._wal.recover_from_snapshot()
        if recovered_state:
            logger.info("Recovered state from WAL snapshot")
            
            # Restore working memory if present in recovered state
            working_data = recovered_state.get("working", {})
            if working_data:
                for key, value in working_data.items():
                    self.working.set(key, value)
                logger.info("Restored %d items to working memory", len(working_data))

    def remember(
        self,
        content: str,
        fact_type: str = "observation",
        source: str = "user",
        confidence: float = 1.0,
    ) -> Fact:
        # Log to WAL before modifying state
        self._wal.write(WALEntryType.STATE_CHANGE, {
            "operation": "remember_start",
            "content": content,
            "fact_type": fact_type,
        })
        
        fact = self.semantic.add_fact(content, fact_type=fact_type, source=source, confidence=confidence)
        
        # Log successful operation to WAL
        self._wal.write(WALEntryType.FACT_ADD, {
            "id": fact.id,
            "content": fact.content,
            "fact_type": fact.fact_type,
            "source": fact.source,
            "confidence": fact.confidence,
        })
        
        self.working.set(
            key=f"recent_fact_{fact.id}",
            value=content,
            category="recent_facts",
            importance=confidence,
        )
        
        # Also log to working memory in WAL
        self._wal.write(WALEntryType.WORKING_SET, {
            "key": f"recent_fact_{fact.id}",
            "value": content,
        })
        
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
        # Log to WAL before removing
        self._wal.write(WALEntryType.FACT_REMOVE, {
            "id": fact_id,
        })
        
        removed = self.semantic.remove_fact(fact_id)
        self.working.remove(f"recent_fact_{fact_id}")
        
        # Log working memory removal
        self._wal.write(WALEntryType.WORKING_REMOVE, {
            "key": f"recent_fact_{fact_id}",
        })
        
        return removed

    def consolidate(self) -> dict:
        return self._consolidator.run_consolidation()

    def add_message(self, role: str, content: str) -> ConversationTurn:
        self._consolidator.record_activity()
        turn = self.episodic.add_turn(role, content, session_id=self._session_id)
        
        # Log conversation to WAL
        self._wal.write(WALEntryType.CONVERSATION_ADD, {
            "role": turn.role,
            "content": turn.content[:500],  # Truncate for WAL
            "timestamp": turn.timestamp,
            "session_id": turn.session_id,
            "turn_id": turn.turn_id,
        })
        
        self.working.set(
            key=f"last_{role}",
            value=content[:200],
            category="recent_messages",
            importance=0.8,
        )
        
        # Log working memory set
        self._wal.write(WALEntryType.WORKING_SET, {
            "key": f"last_{role}",
            "value": content[:200],
        })
        
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
        
        # Log to WAL
        self._wal.write(WALEntryType.WORKING_SET, {
            "key": key,
            "value": str(value)[:500],
        })

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.working.get(key, default)
    
    # ========================================================================
    # Procedural Memory API - Learning from Mistakes (Immortality)
    # ========================================================================
    
    def record_failure(
        self,
        tool: str,
        params: Dict[str, Any],
        error_type: str,
        error_message: str,
        context: str = "",
        query: str = "",
    ) -> Optional[FailureRecord]:
        """
        Record a failure for learning purposes.
        
        This is part of the "immortality" feature - JARVIS learns from
        every mistake to avoid repeating it.
        """
        return self._procedural.record_failure(
            tool=tool,
            params=params,
            error_type=error_type,
            error_message=error_message,
            context=context,
            query=query,
        )
    
    def record_recovery(
        self,
        failure_id: str,
        original_error: str,
        recovery_strategy: str,
        corrected_tool: str,
        corrected_params: Dict[str, Any],
        success: bool,
        duration_seconds: float,
        lessons_learned: List[str] = None,
    ) -> Optional[RecoveryRecord]:
        """Record a recovery from a failure."""
        return self._procedural.record_recovery(
            failure_id=failure_id,
            original_error=original_error,
            recovery_strategy=recovery_strategy,
            corrected_tool=corrected_tool,
            corrected_params=corrected_params,
            success=success,
            duration_seconds=duration_seconds,
            lessons_learned=lessons_learned,
        )
    
    def check_for_known_failure(
        self,
        tool: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Check if this tool/params combination has failed before."""
        return self._procedural.check_for_known_failure(tool, params)
    
    def get_avoidance_rules(self, tool: str = None, context: str = None) -> List[str]:
        """Get applicable avoidance rules."""
        return self._procedural.get_avoidance_rules(tool, context)
    
    def get_failure_stats(self) -> Dict[str, Any]:
        """Get failure statistics."""
        return self._procedural.get_failure_stats()
    
    def get_recent_failures(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent failures."""
        return self._procedural.get_recent_failures(n)
    
    def get_lessons_learned(self) -> List[str]:
        """Get all lessons learned from past failures."""
        return self._procedural.get_lessons_learned()
    
    # ========================================================================
    # WAL API
    # ========================================================================
    
    def create_checkpoint(self) -> str:
        """Create a full state checkpoint."""
        state = {
            "facts": {f.id: f.content for f in self.semantic.get_all()},
            "conversations": [
                {"role": t.role, "content": t.content}
                for t in self.episodic.get_all_turns()
            ],
            "entities": {e.id: e.name for e in self.kg.all_entities()},
        }
        return self._wal.create_checkpoint(state)
    
    def get_wal_status(self) -> Dict[str, Any]:
        """Get WAL status."""
        return {
            "entry_count": self._wal.get_entry_count(),
            "recent_entries": len(self._wal.get_recent_entries(5)),
        }

    def shutdown(self) -> None:
        # Create checkpoint before shutdown
        self.create_checkpoint()
        
        # Stop consolidator
        self._consolidator.stop()
        
        # Flush and shutdown WAL
        shutdown_wal()
        
        logger.info("CognitiveMemory shut down")


def _new_session_id() -> str:
    import hashlib, time
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]


__all__ = ["CognitiveMemory"]
