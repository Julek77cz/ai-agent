"""JARVIS V20 - Enhanced Task Decomposer

Improved task decomposition with:
- Better sub-goal identification
- Dependency detection
- Priority assignment
- Complexity estimation
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from jarvis_core import CzechBridgeClient

logger = logging.getLogger("JARVIS.V20.PLANNING.DECOMPOSER")


@dataclass
class SubTask:
    """Enhanced sub-task representation."""
    id: str = field(default_factory=lambda: f"subtask_{uuid.uuid4().hex[:8]}")
    description: str = ""
    priority: int = 5  # 1-10, higher = more important
    complexity: int = 5  # 1-10, higher = more complex
    dependencies: List[str] = field(default_factory=list)
    estimated_time: float = 60.0  # seconds
    tool_suggestions: List[str] = field(default_factory=list)


class EnhancedTaskDecomposer:
    """
    Enhanced task decomposer with improved analysis.
    """

    def __init__(self, bridge: "CzechBridgeClient"):
        self._bridge = bridge
        logger.info("EnhancedTaskDecomposer initialized")

    def decompose(self, task: str) -> List[SubTask]:
        """
        Decompose a task into sub-tasks.

        Args:
            task: Task description

        Returns:
            List of SubTask objects
        """
        logger.info("Decomposing task: %s", task[:100])

        prompt = f"""Task: {task}

Break this task into 3-6 sub-tasks. For each sub-task, provide:
- Description: clear, actionable description
- Priority: 1-10 (10 = highest priority)
- Complexity: 1-10 (10 = most complex)
- Dependencies: list of sub-task IDs this depends on (empty if none)
- Estimated time: seconds to complete
- Tool suggestions: likely tools needed (e.g., web_search, recall, write_file)

Return ONLY valid JSON:
{{
  "subtasks": [
    {{
      "description": "sub-task description",
      "priority": 8,
      "complexity": 5,
      "dependencies": [],
      "estimated_time": 30,
      "tool_suggestions": ["web_search"]
    }}
  ]
}}"""

        try:
            result = self._bridge.call_json(
                "planner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are a task decomposition expert. Break tasks into well-structured, executable sub-tasks.",
            )

            if result and "subtasks" in result:
                subtasks = []
                for st in result["subtasks"][:6]:  # Limit to 6
                    subtask = SubTask(
                        description=st.get("description", ""),
                        priority=st.get("priority", 5),
                        complexity=st.get("complexity", 5),
                        dependencies=st.get("dependencies", []),
                        estimated_time=st.get("estimated_time", 60),
                        tool_suggestions=st.get("tool_suggestions", []),
                    )
                    if subtask.description:
                        subtasks.append(subtask)

                logger.info("Decomposed into %d sub-tasks", len(subtasks))
                return subtasks

        except Exception as e:
            logger.debug("Task decomposition failed: %s", e)

        # Fallback
        return [SubTask(description=task)]


__all__ = ["EnhancedTaskDecomposer", "SubTask"]
