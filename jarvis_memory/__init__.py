"""JARVIS Cognitive Memory Module"""
from jarvis_memory.embeddings import EmbeddingService, get_embedding_service
from jarvis_memory.vector_store import ChromaCollection
from jarvis_memory.working_memory import WorkingMemory, WorkingMemoryItem
from jarvis_memory.episodic_memory import EpisodicMemory, ConversationTurn, Episode
from jarvis_memory.semantic_memory import SemanticMemory, Fact
from jarvis_memory.knowledge_graph import KnowledgeGraph, Entity, Relation
from jarvis_memory.consolidation import ConsolidationScheduler
from jarvis_memory.memory_manager import CognitiveMemory

# New modules for State Persistence (WAL) and Procedural Memory (Immortality)
from jarvis_memory.wal import (
    WriteAheadLog,
    WALEntry,
    WALEntryType,
    WALState,
    get_wal,
    init_wal,
    shutdown_wal,
)
from jarvis_memory.procedural_memory import (
    ProceduralMemory,
    FailureRecord,
    RecoveryRecord,
    ErrorPattern,
    get_procedural_memory,
    init_procedural_memory,
)

MemoryV19 = CognitiveMemory

__all__ = [
    # Core memory components
    "EmbeddingService",
    "get_embedding_service",
    "ChromaCollection",
    "WorkingMemory",
    "WorkingMemoryItem",
    "EpisodicMemory",
    "ConversationTurn",
    "Episode",
    "SemanticMemory",
    "Fact",
    "KnowledgeGraph",
    "Entity",
    "Relation",
    "ConsolidationScheduler",
    "CognitiveMemory",
    "MemoryV19",
    # WAL (Write-Ahead Log) - State Persistence
    "WriteAheadLog",
    "WALEntry",
    "WALEntryType",
    "WALState",
    "get_wal",
    "init_wal",
    "shutdown_wal",
    # Procedural Memory - Learning from Mistakes (Immortality)
    "ProceduralMemory",
    "FailureRecord",
    "RecoveryRecord",
    "ErrorPattern",
    "get_procedural_memory",
    "init_procedural_memory",
]
