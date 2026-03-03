"""Nightly consolidation background task"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Optional

from jarvis_config import CONSOLIDATION_IDLE_MINUTES, CONSOLIDATION_HOUR, OLLAMA_URL, MODELS, HW_OPTIONS

if TYPE_CHECKING:
    from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.MEMORY.CONSOLIDATION")

_FACT_EXTRACT_SYSTEM = (
    "You are a memory consolidation assistant. "
    "Extract important facts about the user from a conversation. "
    "Return ONLY valid JSON: "
    '{\"facts\": [{\"content\": \"...\", \"confidence\": 0.0, \"type\": \"preference|fact|event\"}]}'
)


def _call_llm(prompt: str) -> Optional[dict]:
    try:
        import requests, json_repair
        payload = {
            "model": MODELS["planner"],
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {**HW_OPTIONS, "temperature": 0.2},
        }
        r = requests.post(OLLAMA_URL, json=payload, timeout=90)
        if r.status_code == 200:
            return json_repair.loads(r.json()["message"]["content"])
    except Exception as e:
        logger.debug("LLM call failed during consolidation: %s", e)
    return None


def _extract_facts_from_turns(turns: list) -> List[dict]:
    if not turns:
        return []
    conversation_text = "\n".join(
        f"{t.role}: {t.content[:300]}" for t in turns[-30:]
    )
    prompt = (
        f"Conversation:\n{conversation_text}\n\n"
        "Extract important facts about the user. "
        "Return JSON: {\"facts\": [{\"content\": \"...\", \"confidence\": 0.5, \"type\": \"preference\"}]}"
    )
    result = _call_llm(prompt)
    if result and isinstance(result.get("facts"), list):
        return result["facts"]
    return []


def _summarize_turns(turns: list) -> Optional[str]:
    if not turns:
        return None
    conversation_text = "\n".join(
        f"{t.role}: {t.content[:200]}" for t in turns
    )
    prompt = (
        f"Summarize this conversation in 2-3 sentences:\n{conversation_text}\n\n"
        "Return JSON: {\"summary\": \"...\"}"
    )
    result = _call_llm(prompt)
    if result and isinstance(result.get("summary"), str):
        return result["summary"]
    return None


class ConsolidationScheduler:
    def __init__(self, memory: "CognitiveMemory"):
        self._memory = memory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_activity: float = time.time()
        self._running = False

    def record_activity(self) -> None:
        self._last_activity = time.time()

    def _idle_seconds(self) -> float:
        return time.time() - self._last_activity

    def _should_run_now(self) -> bool:
        now = datetime.now()
        hour_match = now.hour == CONSOLIDATION_HOUR and now.minute < 10
        idle_match = self._idle_seconds() >= CONSOLIDATION_IDLE_MINUTES * 60
        return hour_match or idle_match

    def _run_loop(self) -> None:
        logger.info("Consolidation scheduler started")
        last_consolidated = 0.0
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=60)
            if self._stop_event.is_set():
                break
            now = time.time()
            if now - last_consolidated < 3600:
                continue
            if self._should_run_now():
                logger.info("Starting memory consolidation...")
                try:
                    self.run_consolidation()
                    last_consolidated = now
                except Exception as e:
                    logger.error("Consolidation failed: %s", e)

    def run_consolidation(self) -> dict:
        stats = {
            "facts_extracted": 0,
            "duplicates_removed": 0,
            "episodes_created": 0,
            "kg_entities_added": 0,
            "started_at": datetime.now().isoformat(),
        }
        try:
            stats.update(self._consolidate_episodic_to_semantic())
        except Exception as e:
            logger.warning("Episodic→semantic consolidation error: %s", e)
        try:
            removed = self._memory.semantic.deduplicate()
            stats["duplicates_removed"] = removed
            logger.info("Deduplication removed %d entries", removed)
        except Exception as e:
            logger.warning("Deduplication error: %s", e)
        try:
            stats["kg_entities_added"] += self._promote_facts_to_kg()
        except Exception as e:
            logger.warning("KG promotion error: %s", e)
        stats["finished_at"] = datetime.now().isoformat()
        logger.info("Consolidation complete: %s", stats)
        return stats

    def _consolidate_episodic_to_semantic(self) -> dict:
        from jarvis_memory.episodic_memory import Episode
        import hashlib

        turns = self._memory.episodic.get_all_turns()
        if not turns:
            return {"facts_extracted": 0, "episodes_created": 0}

        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        recent_turns = [t for t in turns if t.timestamp >= cutoff]
        if not recent_turns:
            return {"facts_extracted": 0, "episodes_created": 0}

        facts = _extract_facts_from_turns(recent_turns)
        added = 0
        for fact_data in facts:
            content = fact_data.get("content", "").strip()
            if not content:
                continue
            confidence = float(fact_data.get("confidence", 0.7))
            fact_type = fact_data.get("type", "observation")
            self._memory.semantic.add_fact(
                content=content,
                fact_type=fact_type,
                source="consolidation",
                confidence=confidence,
            )
            added += 1

        summary = _summarize_turns(recent_turns)
        episodes_created = 0
        if summary:
            episode_id = hashlib.md5(summary.encode()).hexdigest()[:12]
            episode = Episode(
                id=episode_id,
                summary=summary,
                start_time=recent_turns[0].timestamp,
                end_time=recent_turns[-1].timestamp,
                turn_count=len(recent_turns),
            )
            self._memory.episodic.store_episode(episode)
            episodes_created = 1

        return {"facts_extracted": added, "episodes_created": episodes_created}

    def _promote_facts_to_kg(self) -> int:
        added = 0
        for fact in self._memory.semantic.get_all():
            if fact.confidence < 0.85:
                continue
            words = fact.content.split()
            if len(words) < 3:
                continue
            try:
                self._memory.kg.add_entity(
                    name=fact.content[:80],
                    entity_type="concept",
                    attributes={"source": fact.source, "confidence": fact.confidence},
                )
                added += 1
            except Exception:
                pass
        return added

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="jarvis-consolidation")
        self._thread.start()
        logger.info("Consolidation scheduler running (idle threshold: %dm, nightly hour: %d)",
                    CONSOLIDATION_IDLE_MINUTES, CONSOLIDATION_HOUR)

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Consolidation scheduler stopped")


__all__ = ["ConsolidationScheduler"]
