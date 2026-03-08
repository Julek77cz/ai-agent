"""JARVIS V20 - Smart Memory Pruning

Intelligent memory pruning based on:
- Recency
- Confidence
- Redundancy
- Relevance
"""
import logging
from typing import Dict, List, Optional
import time

logger = logging.getLogger("JARVIS.V20.MEMORY.SEMANTIC_PRUNER")


class SemanticMemoryPruner:
    """
    Smart memory pruner for semantic memory.

    Intelligently removes low-value memories to maintain
    memory efficiency and relevance.
    """

    def __init__(
        self,
        max_age_days: int = 30,
        min_confidence: float = 0.3,
        redundancy_threshold: float = 0.9,
    ):
        self.max_age_days = max_age_days
        self.min_confidence = min_confidence
        self.redundancy_threshold = redundancy_threshold

        logger.info(
            "SemanticMemoryPruner initialized: max_age=%d, min_conf=%.2f",
            max_age_days, min_confidence
        )

    def should_prune(self, memory: Dict) -> bool:
        """
        Determine if a memory should be pruned.

        Args:
            memory: Memory object with metadata

        Returns:
            True if memory should be pruned
        """
        # Check confidence
        confidence = memory.get("confidence", 1.0)
        if confidence < self.min_confidence:
            logger.debug("Pruning low-confidence memory: %.2f", confidence)
            return True

        # Check age
        timestamp = memory.get("timestamp", time.time())
        age_days = (time.time() - timestamp) / (24 * 3600)
        if age_days > self.max_age_days:
            logger.debug("Pruning old memory: %.1f days", age_days)
            return True

        return False

    def prune_memories(
        self,
        memories: List[Dict],
        max_memories: int = 1000,
    ) -> List[Dict]:
        """
        Prune a list of memories to fit within limits.

        Args:
            memories: List of memory objects
            max_memories: Maximum number of memories to keep

        Returns:
            Pruned list of memories
        """
        if len(memories) <= max_memories:
            return memories

        # Sort by confidence and recency
        sorted_memories = sorted(
            memories,
            key=lambda m: (
                m.get("confidence", 0.0),
                m.get("timestamp", 0.0),
            ),
            reverse=True,
        )

        # Keep top memories
        pruned = sorted_memories[:max_memories]

        logger.info("Pruned %d → %d memories", len(memories), len(pruned))

        return pruned

    def deduplicate_memories(
        self,
        memories: List[Dict],
        similarity_threshold: float = None,
    ) -> List[Dict]:
        """
        Remove duplicate or very similar memories.

        Args:
            memories: List of memory objects
            similarity_threshold: Threshold for considering duplicates

        Returns:
            Deduplicated list
        """
        if similarity_threshold is None:
            similarity_threshold = self.redundancy_threshold

        # Simple deduplication by content
        seen_contents = set()
        deduplicated = []

        for memory in memories:
            content = memory.get("content", "")
            if content and content not in seen_contents:
                seen_contents.add(content)
                deduplicated.append(memory)

        if len(deduplicated) < len(memories):
            logger.info("Deduplicated %d → %d memories", len(memories), len(deduplicated))

        return deduplicated


__all__ = ["SemanticMemoryPruner"]
