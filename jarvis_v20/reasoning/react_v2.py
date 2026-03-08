"""JARVIS V20 - Enhanced ReAct Loop with Multi-Hop Reasoning"""
import logging
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
import time

from jarvis_reasoning.circuit_breaker import CircuitBreaker
from jarvis_config import (
    MODELS, HW_OPTIONS, REACTION_MAX_ITERATIONS,
    CONTEXT_SUMMARIZER_ENABLED, CONTEXT_SOFT_LIMIT_TOKENS,
    CONTEXT_MEDIUM_LIMIT_TOKENS, CONTEXT_HARD_LIMIT_TOKENS,
)

logger = logging.getLogger("JARVIS.V20.REASONING.REACT_V2")


@dataclass
class ReasoningStep:
    """Single reasoning step in multi-hop chain."""
    hop: int
    thought: str
    action: Dict[str, Any]
    observation: str
    sub_goal: Optional[str] = None
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


class ReActLoopV2:
    """
    Enhanced ReAct Loop with Multi-Hop Reasoning.

    Features:
    - Multi-hop reasoning chains
    - Sub-goal tracking
    - Dynamic context compression
    - Circuit breaker
    - Metacognitive integration
    """

    def __init__(
        self,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        tools: Dict[str, Callable],
        metacognition: Optional["MetacognitiveLayer"] = None,
        max_iterations: int = REACTION_MAX_ITERATIONS,
        enable_multi_hop: bool = True,
    ):
        self._bridge = bridge
        self._memory = memory
        self._tools = tools
        self._metacognition = metacognition
        self._max_iterations = max_iterations
        self._enable_multi_hop = enable_multi_hop

        self._circuit_breaker = CircuitBreaker()
        self._reasoning_chain: List[ReasoningStep] = []

        logger.info("ReActLoopV2 initialized with multi-hop=%s", enable_multi_hop)

    def run(
        self,
        query: str,
        plan,
        stream_callback: Callable = None,
    ) -> str:
        """
        Run enhanced ReAct loop with multi-hop reasoning.

        Args:
            query: User query (already translated to EN)
            plan: Hierarchical plan from planner
            stream_callback: Optional streaming callback

        Returns:
            Final answer
        """
        logger.info("Starting V2 ReAct loop with multi-hop")

        # Check circuit breaker
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker is OPEN")
            return self._generate_fallback_response(query, "circuit_breaker_open")

        thoughts: List[str] = []
        observations: List[str] = []
        final_answer = None

        try:
            for iteration in range(1, self._max_iterations + 1):
                logger.info("V2 ReAct iteration %d/%d", iteration, self._max_iterations)

                # Check circuit breaker
                if self._circuit_breaker.is_open:
                    break

                # Generate thought with multi-hop awareness
                thought = self._generate_thought_v2(
                    query,
                    plan,
                    observations,
                    thoughts,
                    iteration,
                )
                thoughts.append(thought)

                # Multi-hop: Identify sub-goals
                sub_goal = self._extract_sub_goal(thought, observations)

                # Generate action
                action = self._generate_action_v2(thought, observations)

                # Monitor decision
                if self._metacognition:
                    decision_id = self._metacognition.monitor_decision(
                        decision_type="reasoning_step",
                        decision_context={
                            "iteration": iteration,
                            "thought": thought[:100],
                            "action": action.get("tool", ""),
                            "sub_goal": sub_goal,
                        },
                        decision_confidence=action.get("confidence", 0.7),
                    )

                # Execute tool
                tool_name = action.get("tool", "")
                params = action.get("params", {})

                # Check for parallel execution
                if action.get("parallel", False):
                    results = self._execute_parallel([action])
                    observation = "\n".join(results.values())
                else:
                    observation = self._execute_tool(tool_name, params)

                observations.append(observation)

                # Record outcome
                if self._metacognition:
                    self._metacognition.record_outcome(
                        decision_id=decision_id,
                        outcome="success" if "error" not in observation.lower() else "failure",
                        outcome_quality=0.8 if len(observation) > 50 else 0.3,
                        execution_time=0.0,
                    )

                # Check if done
                if self._should_stop(observation, iteration):
                    final_answer = self._generate_final_answer_v2(
                        query,
                        plan,
                        observations,
                        thoughts,
                    )
                    break

                # Circuit breaker update
                if "error" in observation.lower():
                    self._circuit_breaker.record_failure()
                else:
                    self._circuit_breaker.record_success()

            if not final_answer:
                final_answer = self._generate_fallback_response(query, "max_iterations")

            return final_answer

        except Exception as e:
            logger.error("V2 ReAct loop error: %s", e)
            return self._generate_fallback_response(query, str(e))

    def _generate_thought_v2(
        self,
        query: str,
        plan,
        observations: List[str],
        thoughts: List[str],
        iteration: int,
    ) -> str:
        """Generate thought with multi-hop awareness."""
        # Rolling buffer for recent thoughts
        recent_thoughts = "\n".join(f"- {t}" for t in thoughts[-2:])

        # Plan context
        plan_context = ""
        if plan:
            plan_context = f"Plan: {plan.root.description[:100]} (depth={plan.root.get_total_nodes()})"

        # Observations
        obs_text = "\n".join(f"- {o[:200]}" for o in observations[-3:])

        prompt = f"""Query: {query}
{plan_context}
Recent thoughts (DO NOT REPEAT): {recent_thoughts}
Previous observations: {obs_text}
Current iteration: {iteration}

Think step-by-step. Consider:
1. What sub-goal should I focus on now?
2. What's the best reasoning path (multi-hop)?
3. What evidence do I need?
4. Am I repeating a previous thought? If yes, STOP and think differently."""

        try:
            result = self._bridge.call_stream(
                "reasoner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are a reasoning agent. Think step-by-step.",
            )
            if result:
                return result.strip()
        except Exception as e:
            logger.debug("Thought generation failed: %s", e)

        return f"Thinking step {iteration}..."

    def _extract_sub_goal(self, thought: str, observations: List[str]) -> Optional[str]:
        """Extract sub-goal from thought."""
        # Simple pattern matching
        patterns = [
            "need to", "should", "must", "first", "then", "next", "sub-goal",
        ]
        for pattern in patterns:
            if pattern in thought.lower():
                # Extract sentence after pattern
                parts = thought.lower().split(pattern)
                if len(parts) > 1:
                    return parts[1][:100]
        return None

    def _generate_action_v2(self, thought: str, observations: List[str]) -> Dict[str, Any]:
        """Generate action with metacognitive suggestions."""
        # Get calibrated confidence
        calibrated_confidence = self._metacognition.get_calibrated_confidence(
            "tool_selection", 0.7
        ) if self._metacognition else 0.7

        # Get suggestion from metacognition
        suggestion = self._metacognition.get_suggestion(
            "tool_selection",
            {"thought": thought, "observations": observations},
        ) if self._metacognition else None

        prompt = f"""Thought: {thought}
Observations: {observations[-1][:200] if observations else "None"}
{'Suggestion from metacognition: ' + suggestion if suggestion else 'None'}

Select the best tool. Return JSON: {{"tool": "...", "params": {...}, "parallel": true/false, "confidence": 0.0-1.0}}"""

        try:
            result = self._bridge.call_json(
                "planner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are JARVIS V20. Select tools with metacognitive awareness.",
            )
            if result:
                return result
        except Exception as e:
            logger.debug("Action generation failed: %s", e)

        # Fallback
        return {"tool": "recall", "params": {"query": thought[:50]}, "parallel": False, "confidence": 0.5}

    def _execute_parallel(self, actions: List[Dict]) -> Dict[str, str]:
        """Execute multiple tools in parallel."""
        results = {}

        for action in actions:
            tool_name = action.get("tool", "")
            params = action.get("params", {})
            result = self._execute_tool(tool_name, params)
            results[tool_name] = result

        return results

    def _execute_tool(self, tool_name: str, params: Dict) -> str:
        """Execute a single tool."""
        tool_fn = self._tools.get(tool_name)
        if not tool_fn:
            return f"❌ Unknown tool: {tool_name}"

        try:
            result = tool_fn(params)
            return result if result else "⚠️ No output"
        except Exception as e:
            return f"❌ Error in {tool_name}: {str(e)}"

    def _should_stop(self, observation: str, iteration: int) -> bool:
        """Determine if reasoning should stop."""
        # Stop conditions
        stop_indicators = ["✅", "success", "done", "complete", "answer:", "final:"]
        return any(ind in observation.lower() for ind in stop_indicators)

    def _generate_final_answer_v2(
        self,
        query: str,
        plan,
        observations: List[str],
        thoughts: List[str],
    ) -> str:
        """Generate final answer with multi-hop synthesis."""
        prompt = f"""Original query: {query}
Plan: {plan.root.description if plan else 'N/A'}
Reasoning chain: {len(thoughts)} steps
Observations: {len(observations)}

Synthesize a clear, helpful answer in English. Include reasoning from the chain."""

        try:
            result = self._bridge.call_stream(
                "reasoner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are JARVIS V20. Synthesize answers.",
            )
            if result:
                return result.strip()
        except Exception as e:
            logger.debug("Final answer generation failed: %s", e)

        return "\n".join(o for o in observations[-3:] if o)

    def _generate_fallback_response(self, query: str, reason: str) -> str:
        """Generate fallback response."""
        return f"I apologize, but I encountered an issue: {reason}. Please try again."


__all__ = ["ReActLoopV2", "ReasoningStep"]
