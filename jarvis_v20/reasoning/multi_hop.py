"""JARVIS V20 - Multi-Hop Reasoning Chain

Implements multi-hop reasoning for complex queries that require
multiple steps of reasoning with intermediate conclusions.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

logger = logging.getLogger("JARVIS.V20.REASONING.MULTI_HOP")


@dataclass
class Hop:
    """Represents a single hop in multi-hop reasoning."""
    hop_number: int
    query: str
    intermediate_conclusion: str
    evidence: List[str]
    confidence: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class MultiHopChain:
    """Represents a complete multi-hop reasoning chain."""
    hops: List[Hop] = field(default_factory=list)
    final_answer: str = ""
    total_confidence: float = 0.0

    def add_hop(self, hop: Hop):
        """Add a hop to the chain."""
        self.hops.append(hop)

    def get_chain_length(self) -> int:
        """Get number of hops in chain."""
        return len(self.hops)


class MultiHopReasoner:
    """
    Multi-hop reasoner for complex queries.

    Breaks down complex queries into multiple reasoning steps,
    each building on the previous conclusions.
    """

    def __init__(self, bridge: "CzechBridgeClient"):
        self._bridge = bridge
        logger.info("MultiHopReasoner initialized")

    def reason(self, query: str, max_hops: int = 3) -> MultiHopChain:
        """
        Perform multi-hop reasoning.

        Args:
            query: Original query
            max_hops: Maximum number of hops

        Returns:
            MultiHopChain object
        """
        logger.info("Starting multi-hop reasoning for: %s", query[:50])

        chain = MultiHopChain()
        current_query = query

        for hop_num in range(1, max_hops + 1):
            logger.debug("Multi-hop step %d/%d", hop_num, max_hops)

            hop = self._perform_hop(current_query, hop_num)
            chain.add_hop(hop)

            # Check if we've reached a conclusion
            if hop.confidence > 0.9 or "final" in hop.intermediate_conclusion.lower():
                logger.info("Reached high confidence conclusion at hop %d", hop_num)
                break

            # Update query for next hop
            current_query = f"Based on: {hop.intermediate_conclusion}. Next: {query}"

        # Generate final answer
        chain.final_answer = self._synthesize_final_answer(chain)
        chain.total_confidence = chain.hops[-1].confidence if chain.hops else 0.0

        return chain

    def _perform_hop(self, query: str, hop_number: int) -> Hop:
        """Perform a single reasoning hop."""
        prompt = f"""Step {hop_number}: {query}

Analyze this query carefully. Provide:
1. Your reasoning process
2. Intermediate conclusion
3. Evidence supporting your conclusion
4. Your confidence in this conclusion (0.0-1.0)

Return ONLY valid JSON:
{{
  "reasoning": "your reasoning process",
  "conclusion": "intermediate conclusion",
  "evidence": ["evidence 1", "evidence 2"],
  "confidence": 0.8
}}"""

        try:
            result = self._bridge.call_json(
                "reasoner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are a multi-hop reasoning specialist. Break down complex queries into clear reasoning steps.",
            )

            if result:
                return Hop(
                    hop_number=hop_number,
                    query=query,
                    intermediate_conclusion=result.get("conclusion", ""),
                    evidence=result.get("evidence", []),
                    confidence=result.get("confidence", 0.7),
                )

        except Exception as e:
            logger.debug("Hop %d failed: %s", hop_number, e)

        # Fallback
        return Hop(
            hop_number=hop_number,
            query=query,
            intermediate_conclusion=f"Analysis of: {query}",
            evidence=[],
            confidence=0.5,
        )

    def _synthesize_final_answer(self, chain: MultiHopChain) -> str:
        """Synthesize final answer from chain."""
        if not chain.hops:
            return ""

        # Combine all intermediate conclusions
        conclusions = "\n".join(
            f"Step {h.hop_number}: {h.intermediate_conclusion}"
            for h in chain.hops
        )

        prompt = f"""Based on the following reasoning steps:

{conclusions}

Provide a final, comprehensive answer."""

        try:
            result = self._bridge.call_stream(
                "reasoner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are JARVIS V20. Synthesize comprehensive answers from reasoning chains.",
            )
            if result:
                return result.strip()
        except Exception as e:
            logger.debug("Final answer synthesis failed: %s", e)

        # Fallback: return last conclusion
        return chain.hops[-1].intermediate_conclusion


__all__ = ["MultiHopReasoner", "MultiHopChain", "Hop"]
