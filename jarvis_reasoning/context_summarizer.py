"""
Dynamic Context Compression (Context Summarizer) for ReAct loop.

Prevents token exhaustion by:
1. Monitoring context size against configurable thresholds
2. Compressing/summarizing older context while preserving recent critical info
3. Prioritizing information by relevance and recency
4. Providing progressive compression levels based on urgency
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from collections import deque

logger = logging.getLogger("JARVIS.REASONING.CONTEXT_SUMMARIZER")


@dataclass
class ContextSegment:
    """A segment of context with metadata for prioritization."""
    content: str
    source: str  # 'facts', 'episodes', 'recent', 'working', 'observation', 'thought'
    timestamp: float = field(default_factory=time.time)
    importance_score: float = 0.5  # 0.0-1.0, higher = more important
    access_count: int = 0  # Track how often this segment is referenced
    compressed_from: Optional[str] = None  # Original content if compressed

    @property
    def token_estimate(self) -> int:
        """Estimate token count (rough approximation: ~4 chars per token)."""
        return len(self.content) // 4

    def touch(self):
        """Mark segment as accessed, increasing its importance."""
        self.access_count += 1
        self.importance_score = min(1.0, self.importance_score + 0.1)


@dataclass
class CompressionStats:
    """Statistics about context compression operations."""
    original_tokens: int = 0
    compressed_tokens: int = 0
    segments_removed: int = 0
    segments_summarized: int = 0
    compression_level: int = 0  # 0=none, 1=light, 2=medium, 3=aggressive
    timestamp: float = field(default_factory=time.time)

    @property
    def reduction_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return (self.original_tokens - self.compressed_tokens) / self.original_tokens


class ContextSummarizer:
    """
    Dynamic context compression system for ReAct reasoning.

    Monitors context size and applies progressive compression strategies
    to prevent token exhaustion while preserving critical information.
    """

    def __init__(
        self,
        bridge: Any,  # CzechBridgeClient
        soft_limit: int = 2048,  # Tokens - start light compression
        medium_limit: int = 3072,  # Tokens - medium compression
        hard_limit: int = 4096,  # Tokens - aggressive compression
        max_observations: int = 10,  # Max observations to keep
        max_recent_turns: int = 5,  # Max recent conversation turns
        enable_summarization: bool = True,
    ):
        self._bridge = bridge
        self._soft_limit = soft_limit
        self._medium_limit = medium_limit
        self._hard_limit = hard_limit
        self._max_observations = max_observations
        self._max_recent_turns = max_recent_turns
        self._enable_summarization = enable_summarization

        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=100)  # Compression history
        self._segment_cache: Dict[str, ContextSegment] = {}

    def summarize_for_iteration(
        self,
        query: str,
        context_segments: List[ContextSegment],
        current_iteration: int,
    ) -> Tuple[str, CompressionStats]:
        """
        Summarize context for a ReAct iteration.

        Args:
            query: Current user query
            context_segments: All available context segments
            current_iteration: Current ReAct iteration number

        Returns:
            Tuple of (compressed_context_string, compression_stats)
        """
        with self._lock:
            return self._summarize(query, context_segments, current_iteration)

    def _summarize(
        self,
        query: str,
        segments: List[ContextSegment],
        iteration: int,
    ) -> Tuple[str, CompressionStats]:
        """Internal summarize implementation."""
        stats = CompressionStats()

        # Calculate total token estimate
        total_tokens = sum(s.token_estimate for s in segments)
        stats.original_tokens = total_tokens

        if total_tokens <= self._soft_limit:
            # No compression needed
            stats.compressed_tokens = total_tokens
            context = self._assemble_context(segments)
            return context, stats

        # Determine compression level
        if total_tokens >= self._hard_limit:
            compression_level = 3  # Aggressive
        elif total_tokens >= self._medium_limit:
            compression_level = 2  # Medium
        else:
            compression_level = 1  # Light

        stats.compression_level = compression_level
        logger.debug(
            "Context compression triggered: %d tokens, level %d",
            total_tokens, compression_level
        )

        # Apply compression strategies based on level
        compressed_segments = self._apply_compression(
            segments, compression_level, iteration
        )

        # Update stats
        stats.compressed_tokens = sum(s.token_estimate for s in compressed_segments)
        stats.segments_removed = len(segments) - len(compressed_segments)
        stats.segments_summarized = sum(
            1 for s in compressed_segments if s.compressed_from is not None
        )

        # Record stats
        self._history.append(stats)

        context = self._assemble_context(compressed_segments)
        return context, stats

    def _apply_compression(
        self,
        segments: List[ContextSegment],
        level: int,
        iteration: int,
    ) -> List[ContextSegment]:
        """Apply compression strategies based on level."""
        segments = list(segments)  # Copy to avoid modifying original

        # Level 1: Remove oldest low-importance segments
        if level >= 1:
            segments = self._filter_by_importance_and_age(segments)

        # Level 2: Summarize older observations and episodes
        if level >= 2:
            segments = self._summarize_old_segments(segments, iteration)

        # Level 3: Aggressive summarization and truncation
        if level >= 3:
            segments = self._aggressive_compression(segments)

        return segments

    def _filter_by_importance_and_age(
        self, segments: List[ContextSegment]
    ) -> List[ContextSegment]:
        """Remove oldest segments with low importance scores."""
        # Sort by importance (high first) then by timestamp (recent first)
        segments.sort(key=lambda s: (s.importance_score, s.timestamp), reverse=True)

        # Keep top segments up to soft limit
        result = []
        token_count = 0

        for segment in segments:
            seg_tokens = segment.token_estimate
            if token_count + seg_tokens <= self._soft_limit:
                result.append(segment)
                token_count += seg_tokens
            else:
                # Check if this is a critical segment we should keep
                if segment.importance_score >= 0.8 or segment.source in ('recent', 'working'):
                    result.append(segment)
                    token_count += seg_tokens

        # Re-sort by source priority for final assembly
        priority_order = {'working': 0, 'recent': 1, 'facts': 2, 'episodes': 3, 'observation': 4, 'thought': 5}
        result.sort(key=lambda s: (priority_order.get(s.source, 99), s.timestamp))

        return result

    def _summarize_old_segments(
        self, segments: List[ContextSegment], current_iteration: int
    ) -> List[ContextSegment]:
        """Summarize older observation segments using LLM."""
        if not self._enable_summarization or self._bridge is None:
            return segments

        # Find old observations to summarize
        observations = [s for s in segments if s.source == 'observation']
        if len(observations) <= 3:
            return segments

        # Group older observations for summarization
        to_summarize = observations[:-3]  # Keep 3 most recent
        keep_recent = observations[-3:]

        if len(to_summarize) < 2:
            return segments

        # Create summary of older observations
        try:
            summary_text = self._create_summary(
                [s.content for s in to_summarize],
                "observations"
            )

            if summary_text:
                # Replace old observations with summary
                summary_segment = ContextSegment(
                    content=f"[Summary of {len(to_summarize)} earlier observations]: {summary_text}",
                    source='observation',
                    timestamp=to_summarize[-1].timestamp,  # Use timestamp of most recent summarized
                    importance_score=0.7,
                    compressed_from="\n".join(s.content for s in to_summarize),
                )

                # Rebuild segment list
                result = [s for s in segments if s.source != 'observation']
                result.append(summary_segment)
                result.extend(keep_recent)

                return result

        except Exception as e:
            logger.warning("LLM summarization failed: %s", e)

        return segments

    def _aggressive_compression(self, segments: List[ContextSegment]) -> List[ContextSegment]:
        """Apply aggressive compression - truncate and aggressively summarize."""
        # Truncate all content to essential info only
        for segment in segments:
            if segment.source == 'observation':
                # Keep only first and last sentence, truncate middle
                content = segment.content
                sentences = content.split('. ')
                if len(sentences) > 2:
                    segment.content = f"{sentences[0]}. [...] {sentences[-1]}"
                    segment.compressed_from = content
            elif segment.source == 'episodes':
                # Truncate episodes to key info
                if len(segment.content) > 200:
                    segment.compressed_from = segment.content
                    segment.content = segment.content[:200] + "..."

        # Limit total observations
        obs = [s for s in segments if s.source == 'observation']
        if len(obs) > self._max_observations:
            # Keep first, last, and most important in between
            sorted_obs = sorted(obs, key=lambda s: (s.importance_score, s.timestamp), reverse=True)
            to_keep = set()
            to_keep.add(id(obs[0]))  # First
            to_keep.add(id(obs[-1]))  # Last
            for s in sorted_obs[:self._max_observations - 2]:
                to_keep.add(id(s))

            segments = [s for s in segments if s.source != 'observation' or id(s) in to_keep]

        return segments

    def _create_summary(self, items: List[str], item_type: str) -> Optional[str]:
        """Use LLM to create a summary of items."""
        if not items or not self._bridge:
            return None

        try:
            system_prompt = (
                "You are a context compression assistant. "
                "Create a brief 1-2 sentence summary of the following information. "
                "Be concise and preserve key facts."
            )

            content = f"{item_type}:\n" + "\n".join(f"- {i[:200]}" for i in items)

            # Try to use the bridge for summarization
            result = self._bridge.call_stream(
                "planner",
                [{"role": "user", "content": content}],
                system_prompt=system_prompt,
            )

            if result:
                return result.strip()[:300]  # Limit summary length

        except Exception as e:
            logger.debug("Summary creation failed: %s", e)

        return None

    def _assemble_context(self, segments: List[ContextSegment]) -> str:
        """Assemble segments into final context string."""
        # Group by source for organized context
        by_source: Dict[str, List[ContextSegment]] = {}
        for segment in segments:
            by_source.setdefault(segment.source, []).append(segment)

        parts = []

        # Order sources by importance
        source_order = ['working', 'facts', 'episodes', 'recent', 'thought', 'observation']

        for source in source_order:
            if source in by_source:
                segs = by_source[source]
                # Sort by timestamp within source
                segs.sort(key=lambda s: s.timestamp)

                if source == 'working':
                    parts.append("Working Memory:\n" + "\n".join(f"• {s.content[:150]}" for s in segs))
                elif source == 'facts':
                    parts.append("Known Facts:\n" + "\n".join(f"• {s.content[:150]}" for s in segs))
                elif source == 'episodes':
                    parts.append("Related Episodes:\n" + "\n".join(f"• {s.content[:200]}" for s in segs))
                elif source == 'recent':
                    parts.append("Recent Conversation:\n" + "\n".join(f"• {s.content[:150]}" for s in segs))
                elif source == 'thought':
                    parts.append("Previous Thoughts:\n" + "\n".join(f"• {s.content[:150]}" for s in segs))
                elif source == 'observation':
                    parts.append("Observations:\n" + "\n".join(f"• {s.content[:250]}" for s in segs))

        return "\n\n".join(parts)

    def create_react_segments(
        self,
        context_str: str,
        observations: List[str],
        thoughts: List[str],
    ) -> List[ContextSegment]:
        """
        Create ContextSegments from ReAct loop data.

        Args:
            context_str: Prefetched context from memory
            observations: List of observation strings
            thoughts: List of thought strings

        Returns:
            List of ContextSegment objects
        """
        segments = []

        # Parse context string into segments
        if context_str:
            lines = context_str.split('\n')
            current_source = None
            current_content = []

            for line in lines:
                if line.startswith('Working Memory:'):
                    current_source = 'working'
                elif line.startswith('Known Facts:'):
                    current_source = 'facts'
                elif line.startswith('Related Episodes:'):
                    current_source = 'episodes'
                elif line.startswith('Recent Conversation:'):
                    current_source = 'recent'
                elif line.startswith('• '):
                    if current_source and current_content:
                        segments.append(ContextSegment(
                            content='\n'.join(current_content),
                            source=current_source,
                            importance_score=0.6 if current_source in ('working', 'facts') else 0.4,
                        ))
                        current_content = []
                    content = line[2:].strip()
                    if content:
                        current_content.append(content)
                elif current_source and line.strip():
                    current_content.append(line.strip())

            # Don't forget the last segment
            if current_source and current_content:
                segments.append(ContextSegment(
                    content='\n'.join(current_content),
                    source=current_source,
                    importance_score=0.6 if current_source in ('working', 'facts') else 0.4,
                ))

        # Add observations as segments
        for i, obs in enumerate(observations):
            # More recent observations are more important
            importance = 0.5 + (i / max(len(observations), 1)) * 0.4
            segments.append(ContextSegment(
                content=obs,
                source='observation',
                importance_score=importance,
            ))

        # Add thoughts as segments
        for i, thought in enumerate(thoughts):
            importance = 0.4 + (i / max(len(thoughts), 1)) * 0.3
            segments.append(ContextSegment(
                content=thought,
                source='thought',
                importance_score=importance,
            ))

        return segments

    def get_stats(self) -> Dict[str, Any]:
        """Get summarizer statistics."""
        if not self._history:
            return {"total_compressions": 0}

        recent = list(self._history)[-10:]
        return {
            "total_compressions": len(self._history),
            "avg_reduction_ratio": sum(s.reduction_ratio for s in recent) / len(recent),
            "last_compression_level": recent[-1].compression_level if recent else 0,
            "last_original_tokens": recent[-1].original_tokens if recent else 0,
            "last_compressed_tokens": recent[-1].compressed_tokens if recent else 0,
        }


class SimpleContextSummarizer:
    """
    Lightweight context summarizer that doesn't require LLM calls.
    Uses rule-based compression for environments where LLM summarization
    would add too much latency.
    """

    def __init__(
        self,
        soft_limit: int = 2048,
        hard_limit: int = 4096,
        max_observations: int = 10,
    ):
        self._soft_limit = soft_limit
        self._hard_limit = hard_limit
        self._max_observations = max_observations
        self._compression_count = 0

    def summarize(self, context_parts: List[str], observations: List[str] = None) -> str:
        """
        Simple rule-based summarization.

        Args:
            context_parts: List of context strings
            observations: Optional list of observations

        Returns:
            Compressed context string
        """
        observations = observations or []

        # Estimate tokens
        all_parts = context_parts + observations
        total_chars = sum(len(p) for p in all_parts)
        estimated_tokens = total_chars // 4

        if estimated_tokens <= self._soft_limit:
            return "\n\n".join(all_parts)

        self._compression_count += 1

        # Progressive compression
        if estimated_tokens > self._hard_limit:
            # Aggressive: keep only last 3 observations, truncate everything
            if len(observations) > 3:
                observations = observations[-3:]
            context_parts = [p[:300] + "..." if len(p) > 300 else p for p in context_parts]
        else:
            # Medium: keep last 5 observations
            if len(observations) > 5:
                observations = observations[-5:]
            context_parts = [p[:500] + "..." if len(p) > 500 else p for p in context_parts]

        result_parts = context_parts + [f"Observation: {o[:400]}" for o in observations]
        return "\n\n".join(result_parts)

    def get_stats(self) -> Dict[str, Any]:
        return {"compression_count": self._compression_count}


__all__ = [
    "ContextSummarizer",
    "SimpleContextSummarizer",
    "ContextSegment",
    "CompressionStats",
]