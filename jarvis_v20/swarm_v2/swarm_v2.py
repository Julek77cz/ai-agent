"""JARVIS V20 - Deterministic Swarm V2

Improved swarm with:
- Strict limits on agents and subtasks
- Better coordination
- Deterministic behavior
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable

logger = logging.getLogger("JARVIS.V20.SWARM_V2")


@dataclass
class SubTaskV2:
    """Represents a single sub-task in swarm execution."""
    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    description: str = ""
    role: str = "researcher"
    priority: int = 5
    status: str = "pending"
    result: Optional[str] = None
    duration: float = 0.0


class SwarmManagerV2:
    """
    Deterministic Swarm Manager V2.

    Improved swarm with strict limits and better coordination.
    """

    def __init__(
        self,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        tools: Dict[str, Callable],
        max_agents: int = 4,
        timeout_seconds: int = 120,
        planner=None,
    ):
        self._bridge = bridge
        self._memory = memory
        self._tools = tools
        self.max_agents = max_agents
        self.timeout_seconds = timeout_seconds
        self.planner = planner

        logger.info(
            "SwarmManagerV2 initialized: max_agents=%d, timeout=%ds",
            max_agents, timeout_seconds
        )

    def execute_plan(self, plan) -> str:
        """
        Execute a plan using swarm.

        Args:
            plan: Plan object from hierarchical planner

        Returns:
            Aggregated result
        """
        logger.info("Executing plan with swarm V2")

        # Get leaf nodes as subtasks
        leaves = plan.root.get_leaf_nodes()

        # Limit to max_agents
        subtasks = []
        for i, leaf in enumerate(leaves[:self.max_agents]):
            subtask = SubTaskV2(
                description=leaf.description,
                role="researcher",
                priority=i,
            )
            subtasks.append(subtask)

        if not subtasks:
            return "No subtasks to execute"

        logger.info("Executing %d subtasks with swarm", len(subtasks))

        # Execute subtasks
        results = []
        for subtask in subtasks:
            result = self._execute_subtask(subtask)
            results.append(result)

        # Aggregate results
        return self._aggregate_results(results)

    def _execute_subtask(self, subtask: SubTaskV2) -> str:
        """Execute a single subtask."""
        subtask.status = "running"
        start_time = time.time()

        try:
            # Use ReAct loop for subtask execution
            from jarvis_reasoning import ReActLoop

            react_loop = ReActLoop(
                bridge=self._bridge,
                memory=self._memory,
                tools=self._tools,
                max_iterations=5,
            )

            result = react_loop.run(subtask.description)
            duration = time.time() - start_time

            subtask.status = "completed"
            subtask.result = result
            subtask.duration = duration

            logger.info(
                "Subtask %s completed in %.2fs",
                subtask.id, duration
            )

            return result

        except Exception as e:
            duration = time.time() - start_time
            subtask.status = "failed"
            subtask.duration = duration

            logger.error("Subtask %s failed: %s", subtask.id, e)
            return f"Error: {str(e)}"

    def _aggregate_results(self, results: List[str]) -> str:
        """Aggregate results from multiple subtasks."""
        # Simple aggregation: join results
        aggregated = "\n\n".join(
            f"Result {i+1}:\n{result}"
            for i, result in enumerate(results)
        )

        return aggregated


__all__ = ["SwarmManagerV2", "SubTaskV2"]
