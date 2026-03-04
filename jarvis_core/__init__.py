"""JARVIS Core Module"""
import logging
import re
import threading
import signal
import time
from typing import Dict, List, Optional, Tuple, Callable
from collections import deque

from jarvis_config import (
    OLLAMA_URL,
    MODELS,
    HW_OPTIONS,
    MAX_HISTORY,
    RATE_LIMIT_SECONDS,
    SMALLTALK_PATTERNS,
    MEMORY_PATTERNS,
    SWARM_ENABLED,
    SWARM_MAX_AGENTS,
    SWARM_TIMEOUT_SECONDS,
    SWARM_COMPLEXITY_THRESHOLD,
    SWARM_COMPLEXITY_INDICATORS,
)
from jarvis_config.dynamic import apply_hardware_scaling
from jarvis_memory import CognitiveMemory
from jarvis_tools import create_tool_class, TOOLS_SCHEMA, validate_tool_params
from jarvis_reasoning import ReActLoop
from jarvis_reasoning.swarm import SwarmManager

logger = logging.getLogger("JARVIS.CORE")
_emergency_stop = threading.Event()


def _handle_sigint(sig, frame):
    _emergency_stop.set()
    print("\n\n🛑 Emergency Stop")


signal.signal(signal.SIGINT, _handle_sigint)


def check_stop():
    return _emergency_stop.is_set()


class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = deque()
        self._lock = threading.Lock()

    def is_allowed(self) -> Tuple[bool, int]:
        with self._lock:
            now = time.time()
            while self.requests and now - self.requests[0] > self.window:
                self.requests.popleft()
            remaining = self.max_requests - len(self.requests)
            if len(self.requests) >= self.max_requests:
                return False, max(1, int(self.window - (now - self.requests[0])))
            self.requests.append(now)
            return True, remaining - 1


class CzechBridgeClient:
    def __init__(self):
        self.rate_limiter = RateLimiter()

    def call_json(
        self, model_role: str, messages: List[Dict], system_prompt: str = "", options: Dict = None
    ) -> Optional[Dict]:
        allowed, _ = self.rate_limiter.is_allowed()
        if not allowed:
            return None
        options = options or {}
        try:
            import requests
            import json_repair

            payload = {
                "model": MODELS[model_role],
                "messages": (
                    [{"role": "system", "content": system_prompt}] + messages
                    if system_prompt
                    else messages
                ),
                "stream": False,
                "options": {**HW_OPTIONS, **options},
            }
            r = requests.post(OLLAMA_URL, json=payload, timeout=60)
            if r.status_code == 200:
                return json_repair.loads(r.json()["message"]["content"])
        except Exception as e:
            logger.debug("call_json failed: %s", e)
        return None

    def call_stream(
        self, model_role: str, messages: List[Dict], system_prompt: str = "", callback: Callable = None
    ):
        allowed, _ = self.rate_limiter.is_allowed()
        if not allowed:
            if callback:
                callback("Rate limited")
            return None
        try:
            import requests
            import json

            payload = {
                "model": MODELS[model_role],
                "messages": (
                    [{"role": "system", "content": system_prompt}] + messages
                    if system_prompt
                    else messages
                ),
                "stream": True,
                "options": HW_OPTIONS,
            }
            r = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60)
            if r.status_code == 200:
                full = ""
                for line in r.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode("utf-8"))
                            if not data.get("done"):
                                content = data.get("message", {}).get("content", "")
                                full += content
                                if callback:
                                    callback(content)
                        except Exception:
                            pass
                return full
        except Exception as e:
            if callback:
                callback(f"Error: {e}")
        return None


class JarvisV19:
    def __init__(self, streaming: bool = True):
        logger.info("Initializing JARVIS V19...")
        hw_profile, swarm_agents, context_limit = apply_hardware_scaling()
        logger.info(
            "Hardware detekován: %s. Konfiguruji Swarm na %d agenty a Context limit na %d tokenů.",
            hw_profile, swarm_agents, context_limit,
        )
        self.streaming = streaming
        self.bridge = CzechBridgeClient()
        self.memory = CognitiveMemory(start_consolidation=True)
        self.tools = create_tool_class(self)
        self.tool_results = {}

        # Initialize ReAct reasoning loop
        self.reasoning = ReActLoop(
            bridge=self.bridge,
            memory=self.memory,
            tools=self.tools,
            max_iterations=10,
        )

        # Initialize Swarm Manager for complex tasks
        self._swarm_manager = None
        if SWARM_ENABLED:
            self._swarm_manager = SwarmManager(
                bridge=self.bridge,
                memory=self.memory,
                tools=self.tools,
                max_agents=swarm_agents,
                timeout_seconds=SWARM_TIMEOUT_SECONDS,
            )
            logger.info("Swarm Manager initialized: max_agents=%d", swarm_agents)

        logger.info(f"Ready with {len(self.tools)} tools")

    def _is_complex_task(self, query: str) -> bool:
        """Determine if query is complex enough for swarm execution."""
        if not self._swarm_manager:
            return False
        return self._swarm_manager.is_complex_task(query)

    def _detect_smalltalk(self, query: str) -> bool:
        q = query.lower()
        return any(p in q for p in SMALLTALK_PATTERNS)

    def _detect_memory_query(self, query: str) -> bool:
        q = query.lower()
        return any(p in q for p in MEMORY_PATTERNS)

    def _translate_to_en(self, query: str) -> str:
        translations = {
            "co je": "what is",
            "kde je": "where is",
            "najdi": "find",
            "hledej": "search",
            "uloz": "save",
            "cti": "read",
            "pis": "write",
            "spust": "run",
            "otevri": "open",
            "zavri": "close",
        }
        result = query.lower()
        for cz, en in translations.items():
            result = result.replace(cz, en)
        return result

    def process(self, query: str, stream_callback: Callable = None) -> str:
        """
        Process a user query using ReAct reasoning loop or Swarm architecture.

        Smalltalk and memory queries are handled directly.
        Complex tasks use the Swarm architecture for parallel sub-agent execution.
        All other queries go through the standard ReAct reasoning loop.
        """
        self.memory.add_message("user", query)

        # Handle smalltalk directly
        if self._detect_smalltalk(query):
            response = "Ahoj! Jsem JARVIS. Jak ti mohu pomoci?"
            if stream_callback:
                stream_callback(response)
            self.memory.add_message("assistant", response)
            return response

        # Handle memory queries directly
        if self._detect_memory_query(query):
            facts = self.memory.get_all_facts()
            if facts:
                response = "Co o tobě vím:\n" + "\n".join([f"• {f.content}" for f in facts[:10]])
            else:
                response = "Zatím o tobě moc nevím."
            if stream_callback:
                stream_callback(response)
            self.memory.add_message("assistant", response)
            return response

        # Check if task is complex enough for swarm execution
        if self._swarm_manager and self._is_complex_task(query):
            logger.info("Using Swarm architecture for complex task")
            response = self._execute_swarm(query, stream_callback)
        else:
            # Use standard ReAct reasoning loop
            response = self.reasoning.run(query, stream_callback=stream_callback)

        if not response:
            response = "Hotovo"

        self.memory.add_message("assistant", response)
        return response

    def _execute_swarm(self, query: str, stream_callback: Callable = None) -> str:
        """Execute complex task using Swarm architecture."""
        if not self._swarm_manager:
            return self.reasoning.run(query, stream_callback=stream_callback)

        try:
            # Decompose task into subtasks
            subtasks = self._swarm_manager.decompose_task(query)

            if len(subtasks) <= 1:
                # Not actually complex - use standard loop
                return self.reasoning.run(query, stream_callback=stream_callback)

            # Assign roles to subtasks
            assignments = self._swarm_manager.assign_roles(subtasks)

            # Execute swarm
            execution = self._swarm_manager.execute_swarm(query, subtasks, assignments)

            # Aggregate results
            execution = self._swarm_manager.aggregate_results(execution)

            logger.info(
                "Swarm execution complete: %d agents, %.2fs total",
                len(execution.agent_results), execution.total_duration
            )

            if stream_callback:
                stream_callback(execution.synthesis)

            return execution.synthesis

        except Exception as e:
            logger.error("Swarm execution failed: %s", e)
            # Fallback to standard ReAct loop
            return self.reasoning.run(query, stream_callback=stream_callback)

    def shutdown(self) -> None:
        self.memory.shutdown()


__all__ = ["JarvisV19", "CzechBridgeClient", "check_stop"]
