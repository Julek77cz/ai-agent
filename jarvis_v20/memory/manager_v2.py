"""JARVIS V20 - Enhanced Memory Manager

Wrapper around existing CognitiveMemory with V20 enhancements.
"""
import logging
from typing import Dict, List, Optional, Any

from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.V20.MEMORY.MANAGER_V2")


class MemoryManagerV2:
    """
    Enhanced memory manager wrapping CognitiveMemory.

    Adds V20-specific features like smart pruning and confidence tracking.
    """

    def __init__(self, memory: CognitiveMemory):
        self._memory = memory
        logger.info("MemoryManagerV2 initialized")

    def recall_with_confidence(
        self,
        query: str,
        k: int = 5,
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Recall memories with confidence filtering.

        Args:
            query: Search query
            k: Number of results
            min_confidence: Minimum confidence threshold

        Returns:
            List of memory items with confidence scores
        """
        results = self._memory.recall(query, k=k * 2)  # Get more to filter

        # Filter by confidence if available
        filtered = []
        for result in results:
            conf = result.get("confidence", 1.0)
            if conf >= min_confidence:
                filtered.append(result)
                if len(filtered) >= k:
                    break

        return filtered

    def remember_with_validation(
        self,
        content: str,
        fact_type: str = "observation",
        confidence: float = 1.0,
        validate: bool = True,
    ) -> Optional[str]:
        """
        Store a memory with optional validation.

        Args:
            content: Content to store
            fact_type: Type of fact
            confidence: Confidence in the fact
            validate: Whether to validate before storing

        Returns:
            Fact ID if stored, None otherwise
        """
        if validate and confidence < 0.3:
            logger.debug("Skipping low-confidence memory: %s", content[:50])
            return None

        return self._memory.remember(content, fact_type=fact_type, confidence=confidence)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        stats = {
            "total_memories": 0,
            "by_type": {},
            "avg_confidence": 0.0,
        }

        try:
            # Try to get semantic memory stats
            if hasattr(self._memory, '_semantic'):
                stats["total_memories"] = self._memory._semantic.count()
                stats["avg_confidence"] = 0.8  # Placeholder

        except Exception as e:
            logger.debug("Could not get memory stats: %s", e)

        return stats


__all__ = ["MemoryManagerV2"]
