"""JARVIS Advanced ReAct Reasoning Engine

Implements iterative ReAct pattern: Thought → Action → Observation → Reflection
with Dynamic Context Compression to prevent token exhaustion.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from jarvis_config import (
    MODELS, HW_OPTIONS, OLLAMA_URL, REACTION_MAX_ITERATIONS,
    CONTEXT_SUMMARIZER_ENABLED, CONTEXT_SOFT_LIMIT_TOKENS,
    CONTEXT_MEDIUM_LIMIT_TOKENS, CONTEXT_HARD_LIMIT_TOKENS,
    CONTEXT_MAX_OBSERVATIONS, CONTEXT_MAX_RECENT_TURNS,
    CONTEXT_ENABLE_LLM_SUMMARIZATION,
)
from jarvis_reasoning.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from jarvis_reasoning.context_summarizer import (
    ContextSummarizer,
    SimpleContextSummarizer,
    ContextSegment,
    CompressionStats,
)

if TYPE_CHECKING:
    from jarvis_core import CzechBridgeClient
    from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.REASONING")


# ANSI color codes for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'


# ============================================================================
# Tool Result Parser
# ============================================================================


class ToolResultParser:
    """Parses tool execution results to extract structured data and detect errors."""

    def parse_error(self, result: str) -> Optional[Dict[str, Any]]:
        """
        Parse tool result to extract error information.

        Args:
            result: Tool execution result string

        Returns:
            Dict with error info if error found, None otherwise
        """
        if not result:
            return {"type": "empty_result", "message": "Tool returned empty result"}

        error_patterns = [
            (r"❌\s*(.+)", "error"),
            (r"Error:\s*(.+)", "error"),
            (r"error:\s*(.+)", "error"),
            (r"⚠️\s*(.+)", "warning"),
            (r"Warning:\s*(.+)", "warning"),
            (r"Missing\s+(\w+)", "missing_param"),
            (r"Not found", "not_found"),
            (r"Blocked", "blocked"),
            (r"Timeout", "timeout"),
        ]

        for pattern, error_type in error_patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                return {
                    "type": error_type,
                    "message": match.group(1).strip() if match.groups() else result.strip(),
                    "raw": result,
                }

        return None

    def extract_data(self, tool_name: str, result: str) -> Dict[str, Any]:
        """
        Extract structured data from tool result based on tool type.

        Args:
            tool_name: Name of the tool that was executed
            result: Tool execution result string

        Returns:
            Dict with extracted data
        """
        data = {"raw": result, "success": self.is_success(result)}

        if tool_name == "get_time":
            lines = result.strip().split("\n")
            if len(lines) >= 2:
                data["time"] = lines[0].strip()
                data["date"] = lines[1].strip()

        elif tool_name == "web_search":
            # Extract URLs and titles from search results
            urls = re.findall(r"https?://[^\s<>\")\]]+", result)
            data["urls"] = urls
            data["result_count"] = len(urls)

        elif tool_name in ["read_file", "write_file"]:
            # Extract file path if present
            path_match = re.search(r"📄\s*(.+?)\n", result)
            if path_match:
                data["filename"] = path_match.group(1).strip()
            line_match = re.search(r"(\d+)\s+lines", result)
            if line_match:
                data["line_count"] = int(line_match.group(1))

        elif tool_name == "recall":
            # Count memory items
            items = re.findall(r"•\s+(.+)", result)
            data["memory_count"] = len(items)

        elif tool_name == "remember":
            # Extract fact ID
            id_match = re.search(r"\[([a-f0-9\-]+)\]", result)
            if id_match:
                data["fact_id"] = id_match.group(1)

        elif tool_name == "list_dir":
            # Count items
            items = re.findall(r"[📁📄]\s+(.+)", result)
            data["item_count"] = len(items)

        elif tool_name == "system_info":
            # Extract percentages
            cpu_match = re.search(r"CPU:\s*(\d+)%", result)
            if cpu_match:
                data["cpu_percent"] = int(cpu_match.group(1))
            ram_match = re.search(r"RAM:\s*(\d+)%", result)
            if ram_match:
                data["ram_percent"] = int(ram_match.group(1))
            disk_match = re.search(r"Disk:\s*(\d+)%", result)
            if disk_match:
                data["disk_percent"] = int(disk_match.group(1))

        return data

    def is_success(self, result: str) -> bool:
        """
        Check if tool result indicates success.

        Args:
            result: Tool execution result string

        Returns:
            True if success, False otherwise
        """
        if not result:
            return False

        # Check for error indicators
        error_indicators = ["❌", "Error:", "error:", "Blocked", "Timeout"]
        return not any(ind in result for ind in error_indicators)


# ============================================================================
# Verifier
# ============================================================================


class Verifier:
    """Verifies if answers correctly address the original query."""

    def __init__(self, bridge: "CzechBridgeClient"):
        self._bridge = bridge

    def verify(self, query: str, answer: str, context: str) -> Tuple[bool, List[str]]:
        """
        Verify if answer correctly addresses the query.

        Args:
            query: Original user query
            answer: Generated answer to verify
            context: Context string with observations

        Returns:
            Tuple of (approved: bool, issues: List[str])
        """
        try:
            feedback = self._generate_feedback(query, answer)

            if not feedback:
                # If verifier unavailable, assume approval
                return True, []

            # Parse feedback
            approved = feedback.get("approved", True)
            issues = feedback.get("issues", [])
            confidence = feedback.get("confidence", 1.0)

            logger.debug(
                "Verification result: approved=%s, confidence=%.2f, issues=%s",
                approved, confidence, issues
            )

            return approved, issues if isinstance(issues, list) else [issues]

        except Exception as e:
            logger.warning("Verification failed: %s", e)
            # STRICT MODE: Fail-closed instead of fail-open
            return False, [f"Verification error: {str(e)}"]

    def _generate_feedback(self, query: str, answer: str) -> Optional[Dict[str, Any]]:
        """
        Generate feedback from LLM about answer quality.

        Args:
            query: Original user query
            answer: Generated answer

        Returns:
            Dict with feedback or None if LLM call fails
        """
        system_prompt = (
            "You are a quality assurance assistant. Review if the answer correctly "
            "addresses the user's query. Return ONLY valid JSON with this structure:\n"
            '{\n'
            '  "approved": true/false,\n'
            '  "confidence": 0.0-1.0,\n'
            '  "issues": ["issue1", "issue2"] // empty if approved\n'
            '}'
        )

        prompt = f"Query: {query}\n\nAnswer: {answer}\n\nDoes this answer correctly address the query?"

        try:
            import requests
            import json_repair

            payload = {
                "model": MODELS.get("verifier", "qwen2.5:3b-instruct"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": HW_OPTIONS,
            }

            response = requests.post(OLLAMA_URL, json=payload, timeout=30)
            if response.status_code == 200:
                content = response.json()["message"]["content"]
                return json_repair.loads(content)

        except Exception as e:
            logger.debug("Verifier LLM call failed: %s", e)

        return None


# ============================================================================
# ReAct Loop
# ============================================================================


@dataclass
class ReActStep:
    """Represents a single ReAct iteration."""
    iteration: int
    thought: str
    action: Dict[str, Any]
    observation: str
    reflection: Optional[Dict[str, Any]] = None
    duration: float = 0.0
    tool_success: bool = True
    timestamp: float = field(default_factory=time.time)


class ReActLoop:
    """
    Implements the iterative ReAct (Reasoning + Acting) pattern.

    The loop follows: Thought → Action → Observation → Reflection
    with support for error recovery, self-correction, and verification.

    Features Dynamic Context Compression to prevent token exhaustion
    during long reasoning chains.
    
    Also integrates with Procedural Memory for learning from mistakes (immortality).
    """

    def __init__(
        self,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        tools: Dict[str, Callable],
        max_iterations: int = REACTION_MAX_ITERATIONS,
    ):
        self._bridge = bridge
        self._memory = memory
        self._tools = tools
        self._max_iterations = max_iterations
        self._result_parser = ToolResultParser()
        self._verifier = Verifier(bridge)
        
        # Create own Circuit Breaker instance (not singleton) for thread safety in swarm
        self._circuit_breaker = CircuitBreaker()
        logger.debug("ReActLoop initialized with dedicated Circuit Breaker instance")
        
        # Procedural Memory for learning from mistakes (Immortality)
        self._procedural = None
        if hasattr(memory, '_procedural'):
            self._procedural = memory._procedural

        # Initialize context summarizer for dynamic compression
        if CONTEXT_SUMMARIZER_ENABLED:
            if CONTEXT_ENABLE_LLM_SUMMARIZATION:
                self._summarizer = ContextSummarizer(
                    bridge=bridge,
                    soft_limit=CONTEXT_SOFT_LIMIT_TOKENS,
                    medium_limit=CONTEXT_MEDIUM_LIMIT_TOKENS,
                    hard_limit=CONTEXT_HARD_LIMIT_TOKENS,
                    max_observations=CONTEXT_MAX_OBSERVATIONS,
                    max_recent_turns=CONTEXT_MAX_RECENT_TURNS,
                    enable_summarization=True,
                )
            else:
                self._summarizer = SimpleContextSummarizer(
                    soft_limit=CONTEXT_SOFT_LIMIT_TOKENS,
                    hard_limit=CONTEXT_HARD_LIMIT_TOKENS,
                    max_observations=CONTEXT_MAX_OBSERVATIONS,
                )
        else:
            self._summarizer = None

    def run(self, query: str, stream_callback: Callable = None) -> str:
        """
        Run the ReAct reasoning loop for the given query.

        Args:
            query: User query to process
            stream_callback: Optional callback for streaming output

        Returns:
            Final answer string
        """
        logger.info("Starting ReAct loop for query: %s", query[:50])

        # Check circuit breaker before starting
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker is OPEN - preventing ReAct execution")
            status = self._circuit_breaker.get_status()
            return (
                f"⚠️ {Colors.RED}ReAct loop blocked by circuit breaker.{Colors.RESET}\n"
                f"State: {status['state']} | Failures: {status['failure_count']} | "
                f"Last failure: {status['time_since_last_failure']:.1f}s ago\n"
                f"Zkoušejte později nebo restartujte JARVIS."
            )

        # Prefetch context from memory
        context = self._prefetch_context(query)

        # Initialize tracking structures
        thoughts: List[str] = []
        observations: List[str] = []
        actions: List[Dict[str, Any]] = []
        steps: List[ReActStep] = []

        final_answer = None

        try:
            for iteration in range(1, self._max_iterations + 1):
                logger.info("ReAct iteration %d/%d", iteration, self._max_iterations)

                # Check circuit breaker at each iteration
                if self._circuit_breaker.is_open:
                    logger.warning("Circuit breaker opened during ReAct loop")
                    break

                # Thought generation with dynamic context compression
                thought = self._generate_thought(query, context, observations, iteration)
                thoughts.append(thought)
                logger.debug("Thought: %s", thought[:100])

                # Action generation
                action = self._generate_action(thought, context)
                actions.append(action)
                logger.info("Action: %s", action.get("tool", "unknown"))

                # Tool execution with validation
                tool_name = action.get("tool", "")
                params = action.get("params", {})

                start_time = time.time()
                observation = self._execute_tool(tool_name, params)
                duration = time.time() - start_time
                observations.append(observation)

                # Parse result
                tool_success = self._result_parser.is_success(observation)
                error_info = self._result_parser.parse_error(observation)

                logger.info("Tool %s: success=%s, duration=%.2fs", tool_name, tool_success, duration)

                # Reflection: should continue or answer?
                reflection = self._generate_reflection(query, observation, tool_success, error_info)

                step = ReActStep(
                    iteration=iteration,
                    thought=thought,
                    action=action,
                    observation=observation,
                    reflection=reflection,
                    duration=duration,
                    tool_success=tool_success,
                )
                steps.append(step)

                # Check if we should stop
                if not self._should_continue(reflection):
                    logger.info("Reflection indicates task complete")
                    final_answer = self._generate_final_answer(query, context, observations, thoughts)
                    break

                # Self-correction if tool failed
                if not tool_success and error_info:
                    correction_thought = self._generate_correction_thought(
                        query, tool_name, params, error_info, observations
                    )
                    thoughts.append(correction_thought)
                    logger.debug("Correction thought: %s", correction_thought[:100])

            if final_answer is None:
                # Max iterations reached - generate answer anyway
                logger.warning("Max iterations reached, generating final answer")
                final_answer = self._generate_final_answer(query, context, observations, thoughts)
                # Record failure for circuit breaker
                self._circuit_breaker.record_failure()

            # Verification
            verified, issues = self._verifier.verify(query, final_answer, "\n".join(observations))

            if not verified:
                logger.info("Verifier rejected answer, issues: %s", issues)
                # Add feedback to observations and retry once
                feedback_observation = f"VERIFICATION_FEEDBACK: {', '.join(issues)}"
                observations.append(feedback_observation)
                final_answer = self._generate_final_answer(query, context, observations, thoughts)
                # Record failure for circuit breaker
                self._circuit_breaker.record_failure()
            else:
                # Record success for circuit breaker
                self._circuit_breaker.record_success()

            # Stream if callback provided
            if stream_callback and final_answer:
                stream_callback(final_answer)

            # Log structured summary
            self._log_summary(query, steps, final_answer, verified)

            return final_answer

        except Exception as e:
            # Record failure for circuit breaker on any exception
            logger.error("ReAct loop error: %s", e)
            self._circuit_breaker.record_failure()
            # Return error message instead of re-raising
            return f"❌ Chyba v ReAct loopu: {str(e)}"

    def _prefetch_context(self, query: str) -> str:
        """Prefetch relevant context from memory including procedural rules."""
        try:
            # Use ContextPrefetcher for comprehensive context including procedural rules
            from jarvis_reasoning.context_prefetch import ContextPrefetcher
            
            prefetcher = ContextPrefetcher(self._memory)
            ctx_full = prefetcher.prefetch(query)
            
            # Log procedural rules if loaded
            procedural_rules = ctx_full.get("procedural_rules", {})
            if procedural_rules:
                total_rules = sum(len(r) for r in procedural_rules.values())
                logger.info("Loaded %d procedural rules for context from tools: %s",
                           total_rules, list(procedural_rules.keys()))
            
            return ctx_full.get("summary", "")
        except Exception as e:
            logger.debug("Context prefetch failed: %s", e)
        
        # Fallback: simple recall
        try:
            results = self._memory.recall(query, k=5)
            if results:
                context_parts = []
                for r in results:
                    content = r.get("content", "")
                    if content:
                        context_parts.append(f"• {content}")
                return "\n".join(context_parts) if context_parts else ""
        except Exception as e:
            logger.debug("Fallback context fetch failed: %s", e)
        return ""

    def _generate_thought(self, query: str, context: str, observations: List[str], iteration: int = 1) -> str:
        """Generate reasoning thought for current state with dynamic context compression."""
        system_prompt = (
            "You are JARVIS, an AI assistant. Think step by step about how to solve "
            "the user's query. Return ONLY your thought as plain text, no JSON."
        )

        # Apply dynamic context compression if enabled
        if self._summarizer is not None:
            if isinstance(self._summarizer, ContextSummarizer):
                # Create segments from context and observations
                segments = self._summarizer.create_react_segments(
                    context_str=context,
                    observations=observations,
                    thoughts=[],  # No previous thoughts for thought generation
                )
                compressed_context, stats = self._summarizer.summarize_for_iteration(
                    query=query,
                    context_segments=segments,
                    current_iteration=iteration,
                )
                if stats.compression_level > 0:
                    logger.debug(
                        "Context compressed for iteration %d: %d -> %d tokens (level %d)",
                        iteration, stats.original_tokens, stats.compressed_tokens, stats.compression_level
                    )
                context = compressed_context
            else:
                # Simple summarizer
                context = self._summarizer.summarize(
                    context_parts=[context] if context else [],
                    observations=observations,
                )

        obs_text = "\n".join(f"- {o[:200]}" for o in observations[-3:]) if observations else "No observations yet."
        recent_thoughts = "\n".join(f"- {t}" for t in thoughts[-2:]) if thoughts else "No previous thoughts."

        prompt = f"""Query: {query}

Context from memory:
{context[:1500] if context else "None"}

Recent thoughts (DO NOT REPEAT THESE):
{recent_thoughts}

Previous observations:
{obs_text}

What should I do next? Think about the best approach."""

        try:
            result = self._bridge.call_stream(
                "planner",
                [{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
            )
            if result:
                return result.strip()
        except Exception as e:
            logger.debug("Thought generation failed: %s", e)

        return f"Analyzing query: {query}"

    def _generate_action(self, thought: str, context: str) -> Dict[str, Any]:
        """Generate action based on thought."""

        system_prompt = (
            "CRITICAL INSTRUCTION FOR MEMORY TOOLS:\n"
            "IF THE USER ASKS A QUESTION about themselves or past events -> MUST USE 'recall' tool.\n"
            "IF THE USER TELLS YOU A NEW FACT to save (e.g. 'my favorite food is...', 'I live in...') -> MUST USE 'remember' tool.\n"
            "NEVER use 'web_search' for personal queries!\n\n"
            "You are JARVIS, an AI assistant. Based on your thought, select the best tool action.\n\n"
            "CRITICAL PRIORITY: If the user asks about their personal data, past instructions, passwords, names, or any context from the current or previous sessions, you MUST ALWAYS use the 'recall' tool first to check your memory. DO NOT use 'web_search' for personal or session-related questions!\n\n"
            "CRITICAL INSTRUCTION FOR TOOL USAGE: When outputting an Action, you MUST output the "
            "parameters as a valid JSON object immediately following the action name, like this:\n"
            'Action: tool_name {\\"param1\\": \\"value1\\", \\"param2\\": \\"value2\\"}\n\n'
            "DO NOT output the action name without the JSON parameters if the tool requires them!\n\n"
            "Return ONLY valid JSON with this structure:\n"
            '{\n'
            '  "tool": "tool_name",\n'
            '  "params": {"param1": "value1", "param2": "value2"},\n'
            '  "parallel": false\n'
            '}\n\n'
            "=== TOOL EXAMPLES ===\n"
            "1. RECALL (search memory):\n"
            '   {\"tool\": \"recall\", \"params\": {\"query\": \"user preferences\"}, \"parallel\": false}\n\n'
            "2. REMEMBER (store fact):\n"
            '   {\"tool\": \"remember\", \"params\": {\"content\": \"User likes coffee\", \"fact_type\": \"preference\", \"confidence\": 1.0}, \"parallel\": false}\n\n'
            "3. FORGET (remove memory):\n"
            '   {\"tool\": \"forget\", \"params\": {\"fact_id\": \"abc123\"}, \"parallel\": false}\n\n'
            "4. WEB_SEARCH (online search):\n"
            '   {\"tool\": \"web_search\", \"params\": {\"query\": \"weather in Prague\"}, \"parallel\": false}\n\n'
            "5. READ_FILE (read file):\n"
            '   {\"tool\": \"read_file\", \"params\": {\"file_path\": \"document.txt\"}, \"parallel\": false}\n\n'
            "6. WRITE_FILE (write file):\n"
            '   {\"tool\": \"write_file\", \"params\": {\"file_path\": \"output.txt\", \"content\": \"Hello World\"}, \"parallel\": false}\n\n'
            "7. RUN_PYTHON (execute code):\n"
            '   {\"tool\": \"run_python\", \"params\": {\"code\": \"print(2+2)\"}, \"parallel\": false}\n\n'
            "8. MANAGE_TASKS (task management):\n"
            '   {\"tool\": \"manage_tasks\", \"params\": {\"action\": \"add\", \"task_description\": \"Buy milk\"}, \"parallel\": false}\n\n'
            "9. GET_TIME (current time):\n"
            '   {\"tool\": \"get_time\", \"params\": {}, \"parallel\": false}\n\n'
            "10. SYSTEM_INFO (system status):\n"
            '    {\"tool\": \"system_info\", \"params\": {}, \"parallel\": false}\n\n'
            "=== PARAMETER RULES ===\n"
            "- Required params MUST be included in the JSON\n"
            "- Optional params can be omitted\n"
            "- fact_type: 'preference', 'fact', 'event', or 'observation'\n"
            "- action: 'add', 'list', or 'remove'\n"
            "- confidence: 0.0 to 1.0\n\n"
            "Available tools: get_time, open_app, close_app, run_command, web_search, "
            "write_file, read_file, recall, remember, forget, list_dir, system_info, manage_tasks, run_python"
        )

        prompt = f"""Thought: {thought}

Context: {context[:300] if context else "None"}

What action should I take? Return JSON with tool name and parameters."""

        try:
            result = self._bridge.call_json(
                "planner",
                [{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
            )
            logger.debug("Raw action result from planner: %s", result)

            # Handle case where LLM returns a list of actions instead of a single dict
            if isinstance(result, list) and len(result) > 0:
                logger.info("Planner returned a list of actions. Taking the first one for now.")
                result = result[0]

            if result and isinstance(result, dict) and "tool" in result:
                tool_name = result.get("tool", "")
                params = result.get("params", {})

                # Check if parameters are missing or incomplete
                has_required = self._has_required_params(tool_name, params)
                
                if not has_required:
                    # Use enhanced fallback to extract missing parameters from thought
                    enhanced = self._enhance_action_with_fallback(result, thought)
                    logger.warning(
                        "Planner returned incomplete params for %s, enhanced from thought. "
                        "Original: %s, Enhanced: %s",
                        tool_name, params, enhanced.get("params", {})
                    )
                    return enhanced

                return {
                    "tool": tool_name,
                    "params": params,
                    "parallel": result.get("parallel", False),
                }
        except Exception as e:
            logger.debug("Action generation failed: %s", e)

        # Fallback: try to extract tool from thought or use recall
        fallback_tool = self._extract_tool_from_thought(thought)
        if fallback_tool:
            params = self._extract_params_from_thought(fallback_tool, thought)
            # Validate that we have required params
            if self._has_required_params(fallback_tool, params):
                logger.info("Using fallback tool extraction: %s with params: %s", fallback_tool, params)
                return {"tool": fallback_tool, "params": params, "parallel": False}
            else:
                logger.warning("Fallback extraction missing required params for %s: %s", fallback_tool, params)

        # Ultimate fallback: recall with thought as query
        logger.info("Using ultimate fallback: recall with thought as query")
        return {"tool": "recall", "params": {"query": thought[:100]}, "parallel": False}

    def _extract_params_from_thought(self, tool_name: str, thought: str) -> Dict[str, Any]:
        """
        Extract parameters from thought text when model fails to provide them.
        Uses regex patterns to intelligently infer parameters from the thought content.
        """
        thought_lower = thought.lower()
        
        if tool_name == "recall":
            # Look for quoted strings (likely the search query)
            quoted_match = re.search(r'["\']([^"\']+)["\']', thought)
            if quoted_match:
                return {"query": quoted_match.group(1)}
            # Look for question patterns
            question_match = re.search(r'(?:about|regarding|on|concerning)\s+(.+?)(?:\?|$|\.)', thought_lower)
            if question_match:
                return {"query": question_match.group(1).strip()}
            # Look for keywords indicating memory search
            memory_keywords = ["remember", "recall", "memory", "know", "stored"]
            for keyword in memory_keywords:
                if keyword in thought_lower:
                    # Extract words after the keyword
                    after_keyword = thought_lower.split(keyword, 1)[-1].strip()
                    if after_keyword and len(after_keyword) > 3:
                        return {"query": after_keyword[:100]}
            # Default: use entire thought
            return {"query": thought[:100]}
            
        elif tool_name == "remember":
            content = None
            fact_type = "observation"
            
            # Try to extract content after "remember" or similar
            remember_patterns = [
                r'["\']([^"\']+)["\']',  # Quoted content
                r'(?:remember|store|save|note)\s+(?:that\s+)?(.+?)(?:\.|$)',  # After action verbs
            ]
            for pattern in remember_patterns:
                match = re.search(pattern, thought, re.IGNORECASE)
                if match:
                    content = match.group(1).strip()
                    break
            
            if not content:
                content = thought[:500]
            
            # Detect fact_type from keywords
            if any(kw in thought_lower for kw in ["like", "prefer", "favorite", "enjoy", "mám rád", "rád", "oblíbené"]):
                fact_type = "preference"
            elif any(kw in thought_lower for kw in ["event", "happened", "occurred", "meeting", "appointment", "událost"]):
                fact_type = "event"
            elif any(kw in thought_lower for kw in ["is", "are", "was", "were", "fact", "skutečnost"]):
                fact_type = "fact"
            
            return {"content": content, "fact_type": fact_type, "confidence": 1.0}
            
        elif tool_name == "forget":
            # Try to extract fact_id from various patterns
            id_patterns = [
                r'fact_id["\']?\s*[=:]\s*["\']?([a-f0-9\-]+)',
                r'["\']?([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})["\']?',
                r'["\']?([a-f0-9]{8,32})["\']?',
                r'id["\']?\s*[=:]\s*["\']?([a-zA-Z0-9\-]+)',
            ]
            for pattern in id_patterns:
                match = re.search(pattern, thought)
                if match:
                    return {"fact_id": match.group(1)}
            # If we can't extract ID, return empty to trigger validation error
            return {"fact_id": ""}
            
        elif tool_name == "web_search":
            # Look for quoted strings (likely search terms)
            quoted_match = re.search(r'["\']([^"\']+)["\']', thought)
            if quoted_match:
                return {"query": quoted_match.group(1)}
            # Look for "search for" or "look up" patterns
            search_patterns = [
                r'(?:search for|look up|find|vyhledej|hledej)\s+(.+?)(?:\?|$|\.|on the|using)',
            ]
            for pattern in search_patterns:
                match = re.search(pattern, thought, re.IGNORECASE)
                if match:
                    return {"query": match.group(1).strip()}
            # Default: use entire thought
            return {"query": thought[:100]}
            
        elif tool_name in ["read_file", "write_file"]:
            # Try multiple patterns for file paths
            path_patterns = [
                r'["\']([^"\']+\.(?:txt|md|json|py|csv|yaml|yml|log))["\']',
                r'(?:file|soubor)\s+["\']?([^"\']+\.(?:txt|md|json|py|csv))["\']?',
                r'["\']([^"\']+/[^"\']+)["\']',
            ]
            for pattern in path_patterns:
                match = re.search(pattern, thought)
                if match:
                    return {"file_path": match.group(1)}
            # Default fallback
            return {"file_path": "output.txt"}
            
        elif tool_name == "manage_tasks":
            action = "list"
            task_description = None
            task_id = None
            
            # Detect action
            if any(kw in thought_lower for kw in ["add", "create", "new", "přidej", "vytvoř"]):
                action = "add"
            elif any(kw in thought_lower for kw in ["remove", "delete", "complete", "smazat", "odstraň"]):
                action = "remove"
            elif any(kw in thought_lower for kw in ["list", "show", "display", "zobraz", "ukaž"]):
                action = "list"
            
            # Extract task description
            desc_patterns = [
                r'["\']([^"\']+)["\']',
                r'(?:task|úkol|todo)\s*:?\s*(.+?)(?:\.|$|\n)',
                r'(?:add|přidej)\s+(.+?)(?:\.|$|\n)',
            ]
            for pattern in desc_patterns:
                match = re.search(pattern, thought, re.IGNORECASE)
                if match:
                    task_description = match.group(1).strip()
                    break
            
            # Extract task ID for removal
            id_match = re.search(r'task[_\-]?id["\']?\s*[=:]?\s*["\']?([a-zA-Z0-9\-]+)', thought_lower)
            if id_match:
                task_id = id_match.group(1)
            
            result = {"action": action}
            if task_description:
                result["task_description"] = task_description
            if task_id:
                result["task_id"] = task_id
            return result
            
        elif tool_name == "run_python":
            # Try to extract code between backticks or quotes
            code_patterns = [
                r'```python\s*\n(.*?)\n```',
                r'```\s*\n(.*?)\n```',
                r'`([^`]+)`',
            ]
            for pattern in code_patterns:
                match = re.search(pattern, thought, re.DOTALL)
                if match:
                    return {"code": match.group(1).strip()}
            # If no code block found, return empty
            return {"code": ""}
            
        elif tool_name == "open_app":
            # Extract app name
            app_patterns = [
                r'["\']([^"\']+)["\']',
                r'(?:open|spusť|otevři)\s+(.+?)(?:\.|$|\n)',
            ]
            for pattern in app_patterns:
                match = re.search(pattern, thought, re.IGNORECASE)
                if match:
                    return {"app_name": match.group(1).strip()}
            return {"app_name": ""}
            
        elif tool_name == "run_command":
            # Extract command
            cmd_patterns = [
                r'`([^`]+)`',
                r'["\']([^"\']+)["\']',
                r'(?:command|příkaz)\s*:?\s*(.+?)(?:\.|$|\n)',
            ]
            for pattern in cmd_patterns:
                match = re.search(pattern, thought, re.IGNORECASE)
                if match:
                    return {"command": match.group(1).strip()}
            return {"command": ""}
            
        elif tool_name == "list_dir":
            # Try to extract path
            path_match = re.search(r'["\']([^"\']+)["\']', thought)
            if path_match:
                return {"path": path_match.group(1)}
            return {"path": "."}
            
        return {}

    def _extract_tool_from_thought(self, thought: str) -> Optional[str]:
        """Extract tool name from thought text based on keywords."""
        thought_lower = thought.lower()
        # Order matters: more specific/longer patterns should come first
        tool_keywords = [
            ("remember", ["remember that", "zapamatuj si", "store this"]),
            ("recall", ["what do i recall", "i recall", "recall ", "what do you recall", "what do i remember about", "what do you remember about"]),
            ("web_search", ["search for", "look up", "find online", "google", "internet", "vyhledej", "hledej"]),
            ("read_file", ["read file", "open file", "load file", "file content", "přečti soubor"]),
            ("write_file", ["write file", "save file", "create file", "store file", "vytvoř soubor", "zapiš", "write this", "save this", "to a file"]),
            ("get_time", ["current time", "what time", "time is it", "clock", "kolik je hodin", "čas"]),
            ("system_info", ["system info", "system resources", "cpu usage", "memory usage", "stav systému"]),
            ("list_dir", ["list directory", "show files", "folder contents", "directory contents", "zobraz soubory"]),
            ("manage_tasks", ["task list", "todo list", "úkol", "přidej úkol"]),
            ("run_python", ["run python", "execute python", "python code", "spusť kód"]),
            # Fallback patterns (shorter/more general)
            ("recall", ["remember", "memory", "past", "previous", "know about", "what do you know"]),
            ("get_time", ["time"]),
            ("system_info", ["system", "cpu", "memory", "resources"]),
            ("manage_tasks", ["task", "todo"]),
            ("run_python", ["python", "code", "execute"]),
        ]
        for tool, keywords in tool_keywords:
            if any(keyword in thought_lower for keyword in keywords):
                return tool
        return None

    def _enhance_action_with_fallback(self, action: Dict[str, Any], thought: str) -> Dict[str, Any]:
        """
        Enhance an action with fallback parameter extraction.
        Called when LLM returns incomplete or missing parameters.
        """
        tool_name = action.get("tool", "")
        params = action.get("params", {})
        
        if not tool_name:
            return action
        
        # Check if params are missing or empty for tools that require them
        extracted_params = self._extract_params_from_thought(tool_name, thought)
        
        # Merge: LLM params take precedence, but fill in missing ones
        merged_params = {**extracted_params, **params}
        
        # If merged_params is still empty but tool requires params, log warning
        if not merged_params and tool_name not in ["get_time", "system_info"]:
            logger.warning("Could not extract params for tool %s from thought: %s", tool_name, thought[:100])
        
        return {
            "tool": tool_name,
            "params": merged_params,
            "parallel": action.get("parallel", False),
        }

    def _get_tool_required_params(self, tool_name: str) -> List[str]:
        """Get list of required parameters for a tool."""
        required_params = {
            "recall": ["query"],
            "remember": ["content"],
            "forget": ["fact_id"],
            "web_search": ["query"],
            "read_file": ["file_path"],
            "write_file": ["file_path", "content"],
            "open_app": ["app_name"],
            "close_app": ["app_name"],
            "run_command": ["command"],
            "run_python": ["code"],
            "manage_tasks": ["action"],
            "list_dir": [],  # path has default
            "get_time": [],
            "system_info": [],
        }
        return required_params.get(tool_name, [])

    def _has_required_params(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """Check if action has all required parameters."""
        required = self._get_tool_required_params(tool_name)
        if not required:
            return True
        return all(param in params and params[param] for param in required)

    def _execute_tool(self, tool_name: str, params: Dict) -> str:
        """Execute a tool with parameter validation and error tracking."""
        from jarvis_tools import validate_tool_params

        # Check for known failures from procedural memory (immortality feature)
        if self._procedural:
            known_issue = self._procedural.check_for_known_failure(tool_name, params)
            if known_issue:
                logger.info("Known failure detected for %s: %s", tool_name, known_issue.get("warning", ""))

        # Validate parameters
        success, validated = validate_tool_params(tool_name, params)
        if not success:
            error_msg = f"❌ {validated}"
            self._record_failure(tool_name, params, "parameter_error", validated)
            # Record to circuit breaker with full context
            self._circuit_breaker.record_failure(
                tool=tool_name,
                params=params,
                error_message=f"parameter_error: {validated}",
            )
            return error_msg

        # Get tool function
        tool_fn = self._tools.get(tool_name)
        if not tool_fn:
            error_msg = f"❌ Unknown tool: {tool_name}"
            self._record_failure(tool_name, params, "unknown_tool", error_msg)
            # Record to circuit breaker with full context
            self._circuit_breaker.record_failure(
                tool=tool_name,
                params=params,
                error_message=f"unknown_tool: {tool_name}",
            )
            return error_msg

        # Execute tool
        try:
            result = tool_fn(validated)
            
            # Parse error from result
            error_info = self._result_parser.parse_error(result)
            if error_info:
                # Record failure with full context (including error message)
                self._circuit_breaker.record_failure(
                    tool=tool_name,
                    params=validated,
                    error_message=error_info.get("message", result[:200]),
                )
            
            return result if result else "⚠️ No output"
        except Exception as e:
            logger.exception("Tool execution failed: %s", tool_name)
            error_msg = f"❌ Error in {tool_name}: {str(e)}"
            self._record_failure(tool_name, params, "execution_error", str(e))
            # Record to circuit breaker with full context
            self._circuit_breaker.record_failure(
                tool=tool_name,
                params=params,
                error_message=f"execution_error: {str(e)}",
            )
            return error_msg
    
    def _record_failure(self, tool: str, params: Dict, error_type: str, error_message: str) -> None:
        """Record failure to procedural memory for learning."""
        if self._procedural is not None:
            try:
                self._procedural.record_failure(
                    tool=tool,
                    params=params,
                    error_type=error_type,
                    error_message=error_message,
                    context="react_loop",
                )
            except Exception as e:
                logger.debug("Failed to record failure: %s", e)

    def _generate_reflection(
        self, query: str, observation: str, tool_success: bool, error_info: Optional[Dict]
    ) -> Dict[str, Any]:
        """Generate reflection on observation."""
        reflection = {
            "continue": True,
            "reason": "",
            "sufficient": False,
        }

        if not tool_success:
            reflection["reason"] = f"Tool failed: {error_info.get('message', 'Unknown error') if error_info else 'Unknown error'}"
            reflection["continue"] = True  # Continue to try recovery
            return reflection

        # Check for empty or warning results from memory
        obs_lower = observation.lower()
        if "no results" in obs_lower or "no memories" in obs_lower or "empty" in obs_lower:
            reflection["reason"] = "No results found, may need to try different approach"
            # We still stop, because we shouldn't infinitely search memory if it's empty
            reflection["sufficient"] = True
            reflection["continue"] = False
            return reflection

        # If the tool succeeded and returned some data (and wasn't just empty), it is sufficient to answer!
        reflection["sufficient"] = True
        reflection["continue"] = False
        reflection["reason"] = "Information gathered successfully."
        return reflection

    def _should_continue(self, reflection: Dict[str, Any]) -> bool:
        """Determine if ReAct loop should continue."""
        return reflection.get("continue", True) and not reflection.get("sufficient", False)

    def _generate_correction_thought(
        self, query: str, failed_tool: str, params: Dict, error_info: Dict, observations: List[str]
    ) -> str:
        """Generate a correction thought after tool failure."""
        error_msg = error_info.get("message", "Unknown error")
        error_type = error_info.get("type", "error")

        return (
            f"The previous attempt using '{failed_tool}' failed with {error_type}: {error_msg}. "
            f"I need to try a different approach or correct the parameters. "
            f"Original query: {query}"
        )

    def _generate_final_answer(self, query: str, context: str, observations: List[str], thoughts: List[str] = None) -> str:
        """Generate final answer from observations with dynamic context compression."""
        system_prompt = (
            "You are JARVIS, a helpful AI assistant. Synthesize a clear, concise answer "
            "in ENGLISH based on the execution results. Be direct and helpful."
        )

        thoughts = thoughts or []

        # Apply dynamic context compression if enabled
        if self._summarizer is not None:
            if isinstance(self._summarizer, ContextSummarizer):
                segments = self._summarizer.create_react_segments(
                    context_str=context,
                    observations=observations,
                    thoughts=thoughts,
                )
                compressed_context, stats = self._summarizer.summarize_for_iteration(
                    query=query,
                    context_segments=segments,
                    current_iteration=self._max_iterations,
                )
                if stats.compression_level > 0:
                    logger.debug(
                        "Final context compressed: %d -> %d tokens (level %d)",
                        stats.original_tokens, stats.compressed_tokens, stats.compression_level
                    )
                context = compressed_context
            else:
                context = self._summarizer.summarize(
                    context_parts=[context] if context else [],
                    observations=observations,
                )

        obs_summary = "\n\n".join(f"Step {i+1}: {o[:300]}" for i, o in enumerate(observations[-5:]))

        prompt = f"""Original query: {query}

Context from memory:
{context[:1500] if context else "None"}

Execution results:
{obs_summary}

Provide a clear, helpful response in ENGLISH based on these results."""

        try:
            result = self._bridge.call_stream(
                "czech_gateway",
                [{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
            )
            if result:
                return result.strip()
        except Exception as e:
            logger.debug("Final answer generation failed: %s", e)

        # Fallback: return summary of observations
        return "\n".join(o for o in observations if o)

    def _log_summary(self, query: str, steps: List[ReActStep], answer: str, verified: bool):
        """Log structured summary of ReAct execution."""
        logger.info(
            "ReAct Summary: query='%s...' steps=%d verified=%s",
            query[:50], len(steps), verified
        )
        for step in steps:
            logger.debug(
                "  Step %d: tool=%s success=%s duration=%.2fs",
                step.iteration,
                step.action.get("tool", "?"),
                step.tool_success,
                step.duration,
            )


# ============================================================================
# Re-export existing components for backward compatibility
# ============================================================================

# Import and re-export existing components
from jarvis_reasoning.engine import ReasoningEngine, ReActStep as EngineReActStep, ReasoningTrace
from jarvis_reasoning.context_prefetch import ContextPrefetcher
from jarvis_reasoning.verifier import StepVerifier, VerificationResult
from jarvis_reasoning.parallel_executor import ParallelToolExecutor
from jarvis_reasoning.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    FailureRecord,
)

# Import Swarm components
from jarvis_reasoning.swarm import (
    SubTask,
    AgentResult,
    SwarmExecution,
    SubAgent,
    SwarmManager,
    ROLE_TOOLS,
    execute_swarm_task,
)
from jarvis_reasoning.swarm_executor import (
    AsyncTaskResult,
    AsyncSwarmExecutor,
    SharedContext,
    ContextAwareSwarmExecutor,
    BatchSwarmExecutor,
)

__all__ = [
    # New ReAct components
    "ToolResultParser",
    "Verifier",
    "ReActLoop",
    "ReActStep",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "FailureRecord",
    # Context Summarizer (Dynamic Context Compression)
    "ContextSummarizer",
    "SimpleContextSummarizer",
    "ContextSegment",
    "CompressionStats",
    # Existing components (backward compatibility)
    "ReasoningEngine",
    "EngineReActStep",
    "ReasoningTrace",
    "ContextPrefetcher",
    "StepVerifier",
    "VerificationResult",
    "ParallelToolExecutor",
    # Swarm Architecture
    "SubTask",
    "AgentResult",
    "SwarmExecution",
    "SubAgent",
    "SwarmManager",
    "ROLE_TOOLS",
    "execute_swarm_task",
    # Async Swarm Executor
    "AsyncTaskResult",
    "AsyncSwarmExecutor",
    "SharedContext",
    "ContextAwareSwarmExecutor",
    "BatchSwarmExecutor",
]
