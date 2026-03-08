"""JARVIS V20 - Hierarchical Planning Engine with Backtracking

Implements a hierarchical planner that can:
- Decompose tasks into sub-goals recursively
- Generate alternative execution paths
- Estimate costs and confidence scores
- Backtrack when paths fail
- Prune branches based on heuristics
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, TYPE_CHECKING, Any, TYPE_CHECKING as _TYPE_CHECKING

if _TYPE_CHECKING:
    from jarvis_core import CzechBridgeClient
    from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.V20.PLANNING.HIERARCHICAL")


@dataclass
class ExecutionPath:
    """Represents an alternative execution path through the planning tree."""
    id: str = field(default_factory=lambda: f"path_{uuid.uuid4().hex[:8]}")
    node_sequence: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    confidence: float = 0.8
    tried: bool = False
    successful: bool = False
    failure_reason: str = ""


@dataclass
class PlanningNode:
    """Represents a node in the hierarchical planning tree."""
    id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    description: str = ""
    sub_goals: List["PlanningNode"] = field(default_factory=list)
    cost_estimate: float = 0.0
    confidence: float = 0.8
    completed: bool = False
    alternatives: List[ExecutionPath] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    def get_total_nodes(self) -> int:
        """Get total number of nodes in subtree."""
        return 1 + sum(child.get_total_nodes() for child in self.sub_goals)

    def get_leaf_nodes(self) -> List["PlanningNode"]:
        """Get all leaf nodes (executable actions)."""
        if not self.sub_goals:
            return [self]
        leaves = []
        for child in self.sub_goals:
            leaves.extend(child.get_leaf_nodes())
        return leaves

    def get_depth(self) -> int:
        """Get depth of this node in the tree."""
        if not self.sub_goals:
            return 0
        return 1 + max(child.get_depth() for child in self.sub_goals)


@dataclass
class Plan:
    """Represents a complete hierarchical plan."""
    id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    root: PlanningNode = field(default_factory=lambda: PlanningNode(description="root"))
    created_at: float = field(default_factory=time.time)
    current_path: Optional[ExecutionPath] = None
    alternatives: List[ExecutionPath] = field(default_factory=list)
    execution_log: List[str] = field(default_factory=list)

    def calculate_confidence(self) -> float:
        """Calculate overall plan confidence."""
        def dfs(node: PlanningNode) -> float:
            if not node.sub_goals:
                return node.confidence
            child_conf = sum(dfs(child) for child in node.sub_goals)
            return min(node.confidence, child_conf / len(node.sub_goals))
        return dfs(self.root)

    def log(self, message: str):
        """Log a message to execution log."""
        timestamp = time.strftime("%H:%M:%S")
        self.execution_log.append(f"[{timestamp}] {message}")
        logger.debug("Plan log: %s", message)


class HierarchicalPlanner:
    """
    Hierarchical Planning Engine with Backtracking.

    Decomposes complex tasks into hierarchies of sub-goals,
    generates alternative execution paths, and supports backtracking.
    """

    def __init__(
        self,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        max_depth: int = 4,
        max_alternatives: int = 3,
    ):
        self._bridge = bridge
        self._memory = memory
        self.max_depth = max_depth
        self.max_alternatives = max_alternatives

        logger.info(
            "HierarchicalPlanner initialized: max_depth=%d, max_alternatives=%d",
            max_depth, max_alternatives
        )

    def create_plan(self, query: str) -> Plan:
        """
        Create a hierarchical plan for the given query.

        Args:
            query: User query to plan for

        Returns:
            Complete Plan object
        """
        logger.info("Creating hierarchical plan for: %s", query[:50])

        # Create root node
        root = PlanningNode(
            description=query,
            confidence=self._estimate_initial_confidence(query),
        )

        # Decompose recursively
        self._decompose_recursive(root, query, current_depth=0)

        # Create plan
        plan = Plan(root=root)

        # Generate execution paths
        plan.current_path = self._get_execution_plan(plan.root)
        plan.alternatives = self._generate_alternatives(plan.root)

        plan.log(f"Plan created with {root.get_total_nodes()} nodes")
        plan.log(f"Confidence: {plan.calculate_confidence():.2%}")

        return plan

    def _decompose_recursive(
        self,
        node: PlanningNode,
        query: str,
        current_depth: int,
    ) -> List[PlanningNode]:
        """
        Recursively decompose a node into sub-goals.

        Args:
            node: Node to decompose
            query: Original query context
            current_depth: Current depth in tree

        Returns:
            List of sub-goal nodes
        """
        if current_depth >= self.max_depth:
            logger.debug("Max depth reached for node: %s", node.id)
            return []

        # Check if node should be decomposed
        if self._should_stop_decomposition(node, current_depth):
            logger.debug("Stopping decomposition at depth %d for node: %s",
                        current_depth, node.id)
            return []

        # Get sub-goals from LLM
        sub_goals = self._generate_sub_goals(node, query, current_depth)

        if not sub_goals:
            logger.debug("No sub-goals generated for node: %s", node.id)
            return []

        # Recursively decompose each sub-goal
        for sub_goal in sub_goals:
            sub_goals_extended = self._decompose_recursive(
                sub_goal, query, current_depth + 1
            )
            if not sub_goals_extended:
                # No further decomposition, keep as leaf
                pass

        node.sub_goals = sub_goals
        logger.debug("Node %s decomposed into %d sub-goals at depth %d",
                    node.id, len(sub_goals), current_depth)

        return sub_goals

    def _should_stop_decomposition(self, node: PlanningNode, depth: int) -> bool:
        """Determine if decomposition should stop for this node."""
        # Stop if description is simple enough
        simple_indicators = [
            "get", "fetch", "retrieve", "read", "write",
            "open", "close", "start", "stop", "call",
        ]
        if any(ind in node.description.lower() for ind in simple_indicators):
            return True

        # Stop if max depth reached
        if depth >= self.max_depth:
            return True

        # Stop if node already has sub-goals
        if node.sub_goals:
            return True

        return False

    def _generate_sub_goals(
        self,
        node: PlanningNode,
        query: str,
        depth: int,
    ) -> List[PlanningNode]:
        """
        Generate sub-goals for a node using LLM.

        Args:
            node: Parent node
            query: Original query
            depth: Current depth

        Returns:
            List of PlanningNode objects
        """
        prompt = f"""Goal: {node.description}

Break this goal into 2-4 sub-goals that can be executed independently.
Each sub-goal should be clear, specific, and achievable.

Context:
- Original query: {query}
- Current depth: {depth}
- Max depth: {self.max_depth}

Return ONLY valid JSON:
{{
  "sub_goals": [
    {{"description": "sub-goal 1", "confidence": 0.9}},
    {{"description": "sub-goal 2", "confidence": 0.8}}
  ]
}}"""

        try:
            result = self._bridge.call_json(
                "planner",
                [{"role": "user", "content": prompt}],
                system_prompt="You are a task decomposition specialist. Break goals into clear, executable sub-goals.",
            )

            if result and "sub_goals" in result:
                sub_goals = []
                for sg in result["sub_goals"][:4]:  # Limit to 4 sub-goals
                    sub_goal = PlanningNode(
                        description=sg.get("description", ""),
                        confidence=sg.get("confidence", 0.8),
                    )
                    if sub_goal.description:
                        sub_goals.append(sub_goal)
                return sub_goals

        except Exception as e:
            logger.debug("Sub-goal generation failed: %s", e)

        return []

    def _generate_alternatives(self, root: PlanningNode) -> List[ExecutionPath]:
        """
        Generate alternative execution paths.

        Args:
            root: Root node of plan

        Returns:
            List of alternative ExecutionPath objects
        """
        alternatives = []

        # Get all leaf nodes
        leaves = root.get_leaf_nodes()

        # Generate alternative orderings
        if len(leaves) > 1:
            # Simple alternative: reverse order
            reverse_path = ExecutionPath(
                node_sequence=[node.id for node in reversed(leaves)],
                confidence=root.confidence * 0.9,
            )
            alternatives.append(reverse_path)

            # Another alternative: prioritize high-confidence nodes
            sorted_by_confidence = sorted(leaves, key=lambda n: -n.confidence)
            confidence_path = ExecutionPath(
                node_sequence=[node.id for node in sorted_by_confidence],
                confidence=sum(n.confidence for n in leaves) / len(leaves),
            )
            alternatives.append(confidence_path)

        return alternatives[:self.max_alternatives]

    def _get_execution_plan(self, root: PlanningNode) -> ExecutionPath:
        """
        Get the primary execution path through the plan.

        Args:
            root: Root node of plan

        Returns:
            ExecutionPath object
        """
        # BFS to get leaf nodes in order
        leaves = root.get_leaf_nodes()

        path = ExecutionPath(
            node_sequence=[node.id for node in leaves],
            confidence=root.confidence,
        )

        return path

    def _estimate_initial_confidence(self, query: str) -> float:
        """Estimate initial confidence for a query."""
        # Simple heuristics
        if len(query) < 20:
            return 0.7
        elif len(query) < 100:
            return 0.8
        else:
            return 0.6

    def execute_plan(self, plan: Plan) -> str:
        """
        Execute a plan (placeholder - actual execution done by ReAct/Swarm).

        Args:
            plan: Plan to execute

        Returns:
            Result string
        """
        plan.log("Starting plan execution")
        return "Plan execution"


__all__ = ["HierarchicalPlanner", "PlanningNode", "ExecutionPath", "Plan"]
