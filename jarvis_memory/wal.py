"""
Write-Ahead Log (WAL) for JARVIS State Persistence

Provides crash-recovery capability by logging all state changes before applying them.
This ensures that if JARVIS crashes, it can recover its state from the WAL.
"""
import gzip
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from jarvis_config import (
    WAL_DIR,
    WAL_FILE,
    WAL_SNAPSHOT_FILE,
    WAL_ENABLED,
    WAL_FLUSH_INTERVAL_SECONDS,
    WAL_MAX_SIZE_MB,
    WAL_COMPRESSION,
)

logger = logging.getLogger("JARVIS.WAL")


class WALEntryType(Enum):
    SNAPSHOT = "snapshot"
    FACT_ADD = "fact_add"
    FACT_REMOVE = "fact_remove"
    FACT_UPDATE = "fact_update"
    CONVERSATION_ADD = "conversation_add"
    ENTITY_ADD = "entity_add"
    RELATION_ADD = "relation_add"
    ENTITY_REMOVE = "entity_remove"
    WORKING_SET = "working_set"
    WORKING_REMOVE = "working_remove"
    STATE_CHANGE = "state_change"
    CHECKPOINT = "checkpoint"


@dataclass
class WALEntry:
    """Single entry in the WAL journal."""
    entry_id: str
    entry_type: str
    timestamp: str
    data: Dict[str, Any]
    checksum: str = ""
    
    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()
    
    def _compute_checksum(self) -> str:
        content = f"{self.entry_id}:{self.entry_type}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def verify(self) -> bool:
        return self.checksum == self._compute_checksum()
    
    def to_json(self) -> str:
        return json.dumps({
            "entry_id": self.entry_id,
            "entry_type": self.entry_type,
            "timestamp": self.timestamp,
            "data": self.data,
            "checksum": self.checksum,
        }, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, line: str) -> Optional["WALEntry"]:
        try:
            obj = json.loads(line)
            return cls(
                entry_id=obj["entry_id"],
                entry_type=obj["entry_type"],
                timestamp=obj["timestamp"],
                data=obj["data"],
                checksum=obj.get("checksum", ""),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse WAL entry: %s", e)
            return None


@dataclass
class WALState:
    """Current state snapshot for recovery."""
    facts_count: int
    conversations_count: int
    entities_count: int
    relations_count: int
    working_items_count: int
    last_entry_id: str
    last_checkpoint: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class WriteAheadLog:
    """
    Write-Ahead Log for state persistence.
    
    All state modifications are logged to the WAL before being applied.
    This enables crash recovery and provides audit trail.
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._enabled = WAL_ENABLED
        self._flush_interval = WAL_FLUSH_INTERVAL_SECONDS
        self._max_size_mb = WAL_MAX_SIZE_MB
        self._compression = WAL_COMPRESSION
        
        self._entries: List[WALEntry] = []
        self._current_state: Dict[str, Any] = {}
        self._last_flush = time.time()
        self._entry_counter = 0
        self._lock = threading.RLock()
        self._shutdown = False
        
        # Ensure WAL directory exists
        WAL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Initialize WAL
        if self._enabled:
            self._load_wal()
            self._start_flush_thread()
        
        self._initialized = True
        logger.info("WAL initialized: enabled=%s, entries=%d", self._enabled, len(self._entries))
    
    def _load_wal(self) -> None:
        """Load existing WAL entries on startup."""
        if not Path(WAL_FILE).exists():
            return
        
        try:
            with open(WAL_FILE, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    entry = WALEntry.from_json(line)
                    if entry and entry.verify():
                        self._entries.append(entry)
                        self._entry_counter = max(
                            self._entry_counter,
                            int(entry.entry_id.split("-")[-1]) if "-" in entry.entry_id else 0
                        )
                    else:
                        logger.warning("Invalid WAL entry at line %d, skipping", line_num + 1)
            
            logger.info("Loaded %d valid WAL entries", len(self._entries))
            
            # Apply state from WAL to reconstruct current state
            self._reconstruct_state()
            
        except Exception as e:
            logger.error("Failed to load WAL: %s", e)
    
    def _reconstruct_state(self) -> None:
        """Reconstruct current state from WAL entries."""
        self._current_state = {
            "facts": {},
            "conversations": [],
            "entities": {},
            "relations": [],
            "working": {},
        }
        
        for entry in self._entries:
            self._apply_entry_to_state(entry)
        
        logger.debug("Reconstructed state: %d facts, %d conversations, %d entities",
                    len(self._current_state["facts"]),
                    len(self._current_state["conversations"]),
                    len(self._current_state["entities"]))
    
    def _apply_entry_to_state(self, entry: WALEntry) -> None:
        """Apply a single WAL entry to reconstruct state."""
        data = entry.data
        
        if entry.entry_type == WALEntryType.FACT_ADD.value:
            self._current_state["facts"][data.get("id", "")] = data
        elif entry.entry_type == WALEntryType.FACT_REMOVE.value:
            self._current_state["facts"].pop(data.get("id", ""), None)
        elif entry.entry_type == WALEntryType.FACT_UPDATE.value:
            fid = data.get("id", "")
            if fid in self._current_state["facts"]:
                self._current_state["facts"][fid].update(data)
        elif entry.entry_type == WALEntryType.CONVERSATION_ADD.value:
            self._current_state["conversations"].append(data)
        elif entry.entry_type == WALEntryType.ENTITY_ADD.value:
            self._current_state["entities"][data.get("id", "")] = data
        elif entry.entry_type == WALEntryType.ENTITY_REMOVE.value:
            self._current_state["entities"].pop(data.get("id", ""), None)
        elif entry.entry_type == WALEntryType.RELATION_ADD.value:
            self._current_state["relations"].append(data)
        elif entry.entry_type == WALEntryType.WORKING_SET.value:
            self._current_state["working"][data.get("key", "")] = data.get("value")
        elif entry.entry_type == WALEntryType.WORKING_REMOVE.value:
            self._current_state["working"].pop(data.get("key", ""), None)
    
    def _start_flush_thread(self) -> None:
        """Start background thread for periodic WAL flushing."""
        def flush_loop():
            while not self._shutdown:
                time.sleep(self._flush_interval)
                if self._shutdown:
                    break
                if time.time() - self._last_flush >= self._flush_interval:
                    self.flush()
        
        thread = threading.Thread(target=flush_loop, daemon=True, name="jarvis-wal-flush")
        thread.start()
        logger.info("WAL flush thread started (interval=%ds)", self._flush_interval)
    
    def write(self, entry_type: WALEntryType, data: Dict[str, Any]) -> str:
        """
        Write an entry to the WAL.
        
        Args:
            entry_type: Type of the entry
            data: Data to log
            
        Returns:
            Entry ID
        """
        if not self._enabled:
            return ""
        
        with self._lock:
            self._entry_counter += 1
            entry_id = f"wal-{self._entry_counter:08d}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            entry = WALEntry(
                entry_id=entry_id,
                entry_type=entry_type.value,
                timestamp=datetime.now().isoformat(),
                data=data,
            )
            
            self._entries.append(entry)
            self._apply_entry_to_state(entry)
            
            # Check if we need to rotate WAL
            self._maybe_rotate()
            
            return entry_id
    
    def _maybe_rotate(self) -> None:
        """Rotate WAL file if it exceeds max size."""
        if not Path(WAL_FILE).exists():
            return
        
        size_mb = Path(WAL_FILE).stat().st_size / (1024 * 1024)
        if size_mb >= self._max_size_mb:
            self._rotate_wal()
    
    def _rotate_wal(self) -> None:
        """Rotate the WAL file, compressing old entries."""
        if not self._entries:
            return
        
        try:
            # Create compressed archive of old entries
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = WAL_DIR / f"wal_archive_{timestamp}.jsonl.gz"
            
            with gzip.open(archive_path, "wt", encoding="utf-8") as f:
                for entry in self._entries[:-100]:  # Keep last 100 entries
                    f.write(entry.to_json() + "\n")
            
            # Keep only recent entries
            self._entries = self._entries[-100:]
            
            # Write remaining to new file
            with open(WAL_FILE, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(entry.to_json() + "\n")
            
            logger.info("WAL rotated, archived to %s", archive_path.name)
            
        except Exception as e:
            logger.error("WAL rotation failed: %s", e)
    
    def flush(self) -> int:
        """
        Flush WAL entries to disk.
        
        Returns:
            Number of entries flushed
        """
        if not self._enabled or not self._entries:
            return 0
        
        with self._lock:
            try:
                with open(WAL_FILE, "a", encoding="utf-8") as f:
                    for entry in self._entries[-50:]:  # Flush last 50 entries
                        f.write(entry.to_json() + "\n")
                
                self._last_flush = time.time()
                count = len(self._entries)
                logger.debug("WAL flushed: %d entries", count)
                return count
                
            except Exception as e:
                logger.error("WAL flush failed: %s", e)
                return 0
    
    def create_checkpoint(self, state: Dict[str, Any]) -> str:
        """
        Create a full state checkpoint.
        
        Args:
            state: Current system state to checkpoint
            
        Returns:
            Checkpoint ID
        """
        checkpoint_id = f"checkpoint-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Write checkpoint entry to WAL
        self.write(WALEntryType.CHECKPOINT, {
            "checkpoint_id": checkpoint_id,
            "state": state,
            "facts_count": len(state.get("facts", {})),
            "conversations_count": len(state.get("conversations", [])),
        })
        
        # Save snapshot file
        try:
            snapshot = {
                "checkpoint_id": checkpoint_id,
                "timestamp": datetime.now().isoformat(),
                "state": state,
            }
            with open(WAL_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            logger.info("Created checkpoint: %s", checkpoint_id)
        except Exception as e:
            logger.error("Failed to create snapshot: %s", e)
        
        return checkpoint_id
    
    def recover_from_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Recover state from the latest snapshot.
        
        Returns:
            Recovered state or None if no snapshot exists
        """
        if not Path(WAL_SNAPSHOT_FILE).exists():
            logger.info("No snapshot found for recovery")
            return None
        
        try:
            with open(WAL_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
            
            logger.info("Recovered from snapshot: %s", snapshot.get("checkpoint_id"))
            return snapshot.get("state", {})
            
        except Exception as e:
            logger.error("Failed to recover from snapshot: %s", e)
            return None
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current reconstructed state."""
        return self._current_state.copy()
    
    def get_recent_entries(self, n: int = 10) -> List[WALEntry]:
        """Get the n most recent WAL entries."""
        with self._lock:
            return list(self._entries[-n:])
    
    def get_entry_count(self) -> int:
        """Get total number of WAL entries."""
        with self._lock:
            return len(self._entries)
    
    def shutdown(self) -> None:
        """Shutdown WAL, flushing all pending entries."""
        self._shutdown = True
        self.flush()
        logger.info("WAL shutdown: %d entries", len(self._entries))


# Global WAL instance
_wal_instance: Optional[WriteAheadLog] = None


def get_wal() -> WriteAheadLog:
    """Get the global WAL instance."""
    global _wal_instance
    if _wal_instance is None:
        _wal_instance = WriteAheadLog()
    return _wal_instance


def init_wal() -> WriteAheadLog:
    """Initialize and return WAL instance."""
    return get_wal()


def shutdown_wal() -> None:
    """Shutdown the WAL."""
    global _wal_instance
    if _wal_instance:
        _wal_instance.shutdown()
        _wal_instance = None


__all__ = [
    "WriteAheadLog",
    "WALEntry",
    "WALEntryType",
    "WALState",
    "get_wal",
    "init_wal",
    "shutdown_wal",
]
