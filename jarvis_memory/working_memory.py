"""Working memory - session-scoped, limited capacity, not persisted"""
import threading
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from jarvis_config import WORKING_MEMORY_CAPACITY

_SENTINEL = object()


@dataclass
class WorkingMemoryItem:
    key: str
    value: Any
    category: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    importance: float = 0.5


class WorkingMemory:
    def __init__(self, capacity: int = WORKING_MEMORY_CAPACITY):
        self._capacity = capacity
        self._items: deque[WorkingMemoryItem] = deque()
        self._lock = threading.Lock()

    def set(self, key: str, value: Any, category: str = "general", importance: float = 0.5) -> None:
        with self._lock:
            self._items = deque(i for i in self._items if i.key != key)
            self._items.append(WorkingMemoryItem(key=key, value=value, category=category, importance=importance))
            while len(self._items) > self._capacity:
                self._evict()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            for item in self._items:
                if item.key == key:
                    return item.value
        return default

    def remove(self, key: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = deque(i for i in self._items if i.key != key)
            return len(self._items) < before

    def all(self) -> List[WorkingMemoryItem]:
        with self._lock:
            return list(self._items)

    def by_category(self, category: str) -> List[WorkingMemoryItem]:
        with self._lock:
            return [i for i in self._items if i.category == category]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _evict(self) -> None:
        if not self._items:
            return
        min_importance = min(self._items, key=lambda i: i.importance)
        self._items.remove(min_importance)

    def snapshot(self) -> List[Dict]:
        with self._lock:
            return [asdict(i) for i in self._items]

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


__all__ = ["WorkingMemory", "WorkingMemoryItem"]
