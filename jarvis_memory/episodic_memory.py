"""Episodic memory - conversation history, time-indexed, ChromaDB-backed"""
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from jarvis_config import CONV_FILE, MAX_HISTORY, EPISODIC_COLLECTION
from jarvis_memory.vector_store import ChromaCollection

logger = logging.getLogger("JARVIS.MEMORY.EPISODIC")


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        if not self.turn_id:
            self.turn_id = hashlib.md5(
                f"{self.role}{self.content}{self.timestamp}".encode()
            ).hexdigest()[:12]


@dataclass
class Episode:
    id: str
    summary: str
    start_time: str
    end_time: str
    turn_count: int
    session_id: str = ""


class EpisodicMemory:
    def __init__(self):
        self._conversations: List[ConversationTurn] = []
        self._episodes: List[Episode] = []
        self._lock = threading.RLock()
        self._vector = ChromaCollection(EPISODIC_COLLECTION)
        self._load()

    def _load(self) -> None:
        try:
            if Path(CONV_FILE).exists():
                with open(CONV_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                with self._lock:
                    self._conversations = [
                        ConversationTurn(**{k: v for k, v in c.items() if k in ConversationTurn.__dataclass_fields__})
                        for c in raw
                    ]
                logger.info("Loaded %d conversation turns", len(self._conversations))
        except Exception as e:
            logger.warning("Failed to load conversations: %s", e)

    def _save(self) -> None:
        try:
            Path(CONV_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(CONV_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    [asdict(c) for c in self._conversations],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.warning("Failed to save conversations: %s", e)

    def add_turn(self, role: str, content: str, session_id: str = "") -> ConversationTurn:
        turn = ConversationTurn(role=role, content=content, session_id=session_id)
        with self._lock:
            self._conversations.append(turn)
            if len(self._conversations) > MAX_HISTORY * 4:
                self._conversations = self._conversations[-MAX_HISTORY * 2:]
            self._save()
        self._vector.add(
            id=turn.turn_id,
            text=f"{role}: {content}",
            metadata={"role": role, "timestamp": turn.timestamp, "session_id": session_id},
        )
        return turn

    def get_recent(self, n: int = 10) -> List[ConversationTurn]:
        with self._lock:
            return self._conversations[-n:]

    def search_semantic(self, query: str, k: int = 5) -> List[Dict]:
        return self._vector.search(query, k=k)

    def search_by_role(self, query: str, role: str, k: int = 5) -> List[Dict]:
        return self._vector.search(query, k=k, where={"role": role})

    def get_turns_since(self, iso_timestamp: str) -> List[ConversationTurn]:
        with self._lock:
            return [t for t in self._conversations if t.timestamp >= iso_timestamp]

    def get_all_turns(self) -> List[ConversationTurn]:
        with self._lock:
            return list(self._conversations)

    def store_episode(self, episode: Episode) -> None:
        with self._lock:
            self._episodes.append(episode)
        self._vector.add(
            id=episode.id,
            text=episode.summary,
            metadata={
                "type": "episode",
                "start_time": episode.start_time,
                "end_time": episode.end_time,
                "turn_count": str(episode.turn_count),
            },
        )

    def count(self) -> int:
        with self._lock:
            return len(self._conversations)


__all__ = ["EpisodicMemory", "ConversationTurn", "Episode"]
