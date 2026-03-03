"""JARVIS Cognitive Memory Module"""
from jarvis_memory.embeddings import EmbeddingService, get_embedding_service
from jarvis_memory.vector_store import ChromaCollection
from jarvis_memory.working_memory import WorkingMemory, WorkingMemoryItem
from jarvis_memory.episodic_memory import EpisodicMemory, ConversationTurn, Episode
from jarvis_memory.semantic_memory import SemanticMemory, Fact
from jarvis_memory.knowledge_graph import KnowledgeGraph, Entity, Relation
from jarvis_memory.consolidation import ConsolidationScheduler
from jarvis_memory.memory_manager import CognitiveMemory

MemoryV19 = CognitiveMemory

__all__ = [
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
]
