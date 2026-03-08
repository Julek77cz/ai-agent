"""Multi-Agent Swarm Architecture for JARVIS V19

Implements parallel execution of specialized sub-agents for complex tasks.
Each sub-agent has a specific role with filtered tool access.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from jarvis_config import MODELS, HW_OPTIONS

if TYPE_CHECKING:
    from jarvis_core import CzechBridgeClient
    from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.REASONING.SWARM")


# ============================================================================
# System prompts for Swarm components
# ============================================================================

_SWARM_DECOMPOSER_SYSTEM = (
    "You are a task decomposition specialist. Break down complex tasks into "
    "smaller, independent sub-tasks that can be executed in parallel.\n"
    "RULE 1: Each sub-task should be self-contained and have a clear goal.\n"
    "RULE 2: Identify dependencies between sub-tasks - tasks that must run sequentially.\n"
    "RULE 3: Assign appropriate roles to each sub-task.\n"
    "RULE 4: Output ONLY valid JSON with this structure:\n"
    '{\n'
    '  "subtasks": [\n'
    '    {\n'
    '      "id": "unique_id",\n'
    '      "description": "what this subtask does",\n'
    '      "role": "researcher|developer|analyst|writer",\n'
    '      "priority": 1-10,\n'
    '      "dependencies": ["other_task_id"] // empty if no dependencies\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "Available roles:\n"
    "  - researcher: web_search, recall, read_file, list_dir (information gathering)\n"
    "  - developer: run_command, write_file, read_file, run_python (code/file operations)\n"
    "  - analyst: system_info, list_dir, read_file (system analysis)\n"
    "  - writer: remember, write_file (memory and documentation)"
)

_SWARM_AGGREGATOR_SYSTEM = (
    "You are a result synthesis specialist. Combine results from multiple "
    "specialized agents into a coherent response.\n"
    "RULE 1: Focus on the original user query.\n"
    "RULE 2: Integrate all relevant findings from sub-agents.\n"
    "RULE 3: Resolve any conflicts in the results.\n"
    "RULE 4: Output in Czech language.\n"
    "RULE 5: Output ONLY valid JSON with this structure:\n"
    '{\n'
    '  "synthesis": "combined response in Czech",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "agent_summaries": {\n'
    '    "agent_id": "brief summary of what this agent contributed"\n'
    '  }\n'
    '}'
)


# ============================================================================
# Dataclasses for Swarm components
# ============================================================================

@dataclass
class SubTask:
    """Represents a single sub-task in a swarm execution."""
    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    description: str = ""
    role: str = "researcher"  # researcher, developer, analyst, writer
    priority: int = 5  # 1-10, higher = more important
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def can_execute(self, completed_tasks: Set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep_id in completed_tasks for dep_id in self.dependencies)


@dataclass
class AgentResult:
    """Result from a single sub-agent execution."""
    agent_id: str
    task_id: str
    role: str
    result: str
    success: bool
    duration: float
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class SwarmExecution:
    """Complete execution trace of a swarm."""
    query: str
    subtasks: List[SubTask] = field(default_factory=list)
    agent_results: List[AgentResult] = field(default_factory=list)
    synthesis: str = ""
    confidence: float = 0.0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    total_duration: float = 0.0

    def add_result(self, result: AgentResult):
        """Add an agent result to the execution."""
        self.agent_results.append(result)

    def mark_complete(self, synthesis: str, confidence: float):
        """Mark execution as complete."""
        self.completed_at = time.time()
        self.total_duration = self.completed_at - self.started_at
        self.synthesis = synthesis
        self.confidence = confidence


# ============================================================================
# Role-based tool filtering
# ============================================================================

ROLE_TOOLS: Dict[str, Set[str]] = {
    "researcher": {
        "web_search", "recall", "read_file", "list_dir", "get_time", "system_info"
    },
    "developer": {
        "run_command", "write_file", "read_file", "run_python", "list_dir", "system_info"
    },
    "analyst": {
        "system_info", "list_dir", "read_file", "get_time", "run_command"
    },
    "writer": {
        "remember", "write_file", "read_file", "recall", "list_dir", "system_info", "manage_tasks", "get_time"
    },
}


# ============================================================================
# SubAgent class
# ============================================================================

class SubAgent:
    """
    A specialized sub-agent with role-based tool filtering.
    
    Each sub-agent operates independently with access to only the tools
    relevant to its role.
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        tools: Dict[str, Callable],
    ):
        self.agent_id = agent_id
        self.role = role
        self._bridge = bridge
        self._memory = memory
        self._all_tools = tools
        
        # Filter tools based on role
        allowed_tools = ROLE_TOOLS.get(role, set())
        self._tools = {k: v for k, v in tools.items() if k in allowed_tools}
        
        logger.info(
            "SubAgent %s initialized with role '%s', %d tools available",
            agent_id, role, len(self._tools)
        )

    @property
    def available_tools(self) -> List[str]:
        """Get list of available tools for this agent."""
        return list(self._tools.keys())

    def execute(self, task: SubTask) -> AgentResult:
        """
        Execute a sub-task using this agent.
        
        Args:
            task: The SubTask to execute
            
        Returns:
            AgentResult with execution details
        """
        start_time = time.time()
        logger.info("SubAgent %s executing task %s: %s", 
                    self.agent_id, task.id, task.description[:50])
        
        task.status = "running"
        task.started_at = start_time
        
        try:
            # Use the ReAct loop with filtered tools
            from jarvis_reasoning import ReActLoop
            
            react_loop = ReActLoop(
                bridge=self._bridge,
                memory=self._memory,
                tools=self._tools,
                max_iterations=5,  # Shorter for sub-agents
            )
            
            # Execute with the task description as query
            result = react_loop.run(task.description)
            
            duration = time.time() - start_time
            task.status = "completed"
            task.result = result
            task.duration = duration
            task.completed_at = time.time()
            
            logger.info("SubAgent %s completed task %s in %.2fs", 
                        self.agent_id, task.id, duration)
            
            return AgentResult(
                agent_id=self.agent_id,
                task_id=task.id,
                role=self.role,
                result=result,
                success=True,
                duration=duration,
            )
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            task.status = "failed"
            task.error = error_msg
            task.duration = duration
            task.completed_at = time.time()
            
            logger.error("SubAgent %s failed task %s: %s", 
                         self.agent_id, task.id, error_msg)
            
            return AgentResult(
                agent_id=self.agent_id,
                task_id=task.id,
                role=self.role,
                result="",
                success=False,
                duration=duration,
                error=error_msg,
            )


# ============================================================================
# SwarmManager class
# ============================================================================

class SwarmManager:
    """
    Manages the execution of multiple sub-agents in parallel.
    
    Handles task decomposition, role assignment, parallel execution,
    and result aggregation.
    """

    def __init__(
        self,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        tools: Dict[str, Callable],
        max_agents: int = 4,
        timeout_seconds: int = 120,
    ):
        self._bridge = bridge
        self._memory = memory
        self._all_tools = tools
        self._max_agents = max_agents
        self._timeout_seconds = timeout_seconds
        
        logger.info(
            "SwarmManager initialized: max_agents=%d, timeout=%ds",
            max_agents, timeout_seconds
        )

    def is_complex_task(self, query: str) -> bool:
        """
        Determine if a task is complex enough to warrant swarm execution.
        
        Args:
            query: User query to evaluate
            
        Returns:
            True if task should use swarm execution
        """
        # Check for multi-part queries (AND, multiple questions)
        conjunctions = [" a zároveň ", " a pak ", " and then ", " simultaneously "]
        if any(c.lower() in query.lower() for c in conjunctions):
            return True
        
        # Check for multiple question marks
        if query.count("?") > 1:
            return True
        
        # Check for length and complexity indicators
        complex_indicators = [
            "research", "hledej", "najdi", "analyzuj", "compare",
            "porovnej", "vytvoř", "implementuj", "build", "create",
            "multiple", "several", "více", "několik"
        ]
        word_count = len(query.split())
        
        if word_count > 50 and any(ind in query.lower() for ind in complex_indicators):
            return True
        
        # Check for explicit parallel indicators
        parallel_indicators = ["parallel", "simultaneously", "současně", "paralelně"]
        if any(ind in query.lower() for ind in parallel_indicators):
            return True
        
        return False

    def decompose_task(self, query: str) -> List[SubTask]:
        """
        Decompose a complex task into smaller sub-tasks.
        
        Args:
            query: Original user query
            
        Returns:
            List of SubTask objects
        """
        logger.info("Decomposing task: %s", query[:100])
        
        prompt = f"Task: {query}\n\nBreak this task into independent sub-tasks that can be executed in parallel."
        
        try:
            result = self._bridge.call_json(
                "planner",
                [{"role": "user", "content": prompt}],
                system_prompt=_SWARM_DECOMPOSER_SYSTEM,
            )
            
            if result and "subtasks" in result and isinstance(result["subtasks"], list):
                subtasks = []
                # Limit to max 6 subtasks for stability
                for st in result["subtasks"][:6]:
                    subtask = SubTask(
                        id=st.get("id", f"task_{uuid.uuid4().hex[:8]}"),
                        description=st.get("description", ""),
                        role=st.get("role", "researcher"),
                        priority=st.get("priority", 5),
                        dependencies=st.get("dependencies", []),
                    )
                    if subtask.description:  # Only add valid tasks
                        subtasks.append(subtask)
                
                if subtasks:
                    logger.info("Decomposed into %d subtasks", len(subtasks))
                    return subtasks
                
        except Exception as e:
            logger.error("Task decomposition failed: %s", e)
        
        # Fallback: create a single task
        return [SubTask(description=query)]

    def assign_roles(self, subtasks: List[SubTask]) -> Dict[str, str]:
        """
        Assign agents to subtasks based on their roles.
        
        Args:
            subtasks: List of subtasks to assign
            
        Returns:
            Dict mapping task_id to agent_id
        """
        assignments = {}
        
        # Create agents for each unique role
        role_agents: Dict[str, SubAgent] = {}
        
        for task in subtasks:
            role = task.role
            
            if role not in role_agents:
                agent_id = f"agent_{role}_{uuid.uuid4().hex[:6]}"
                agent = SubAgent(
                    agent_id=agent_id,
                    role=role,
                    bridge=self._bridge,
                    memory=self._memory,
                    tools=self._all_tools,
                )
                role_agents[role] = agent
            
            assignments[task.id] = role_agents[role].agent_id
        
        logger.info("Assigned %d tasks to %d agents", 
                    len(subtasks), len(role_agents))
        
        return assignments

    def execute_swarm(
        self,
        query: str,
        subtasks: List[SubTask],
        role_assignments: Dict[str, str],
    ) -> SwarmExecution:
        """
        Execute all subtasks in parallel using sub-agents.
        
        Args:
            query: Original user query
            subtasks: List of subtasks to execute
            role_assignments: Task ID to agent ID mapping
            
        Returns:
            SwarmExecution with all results
        """
        execution = SwarmExecution(query=query, subtasks=subtasks)
        
        logger.info("Starting swarm execution with %d subtasks", len(subtasks))
        
        # Create agents
        agents: Dict[str, SubAgent] = {}
        for task in subtasks:
            agent_id = role_assignments.get(task.id)
            if agent_id and agent_id not in agents:
                agent = SubAgent(
                    agent_id=agent_id,
                    role=task.role,
                    bridge=self._bridge,
                    memory=self._memory,
                    tools=self._all_tools,
                )
                agents[agent_id] = agent
        
        # Execute tasks respecting dependencies
        completed_tasks: Set[str] = set()
        
        while len(completed_tasks) < len(subtasks):
            # Find tasks ready to execute
            ready_tasks = [
                task for task in subtasks
                if task.id not in completed_tasks and task.can_execute(completed_tasks)
            ]
            
            if not ready_tasks:
                # Deadlock - no tasks can proceed
                logger.warning("Swarm execution deadlock - no tasks can proceed")
                break
            
            # Execute ready tasks in parallel using threading
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(ready_tasks), self._max_agents)) as pool:
                futures = {}
                
                for task in ready_tasks:
                    agent_id = role_assignments.get(task.id)
                    agent = agents.get(agent_id)
                    if agent:
                        future = pool.submit(agent.execute, task)
                        futures[future] = task.id
                
                # Wait for all to complete
                for future in concurrent.futures.as_completed(futures):
                    task_id = futures[future]
                    try:
                        result = future.result(timeout=self._timeout_seconds)
                        execution.add_result(result)
                        completed_tasks.add(task_id)
                    except concurrent.futures.TimeoutError:
                        logger.error("Task %s timed out", task_id)
                        # Mark as failed
                        task = next(t for t in subtasks if t.id == task_id)
                        task.status = "failed"
                        task.error = f"Timeout after {self._timeout_seconds}s"
                        completed_tasks.add(task_id)
                    except Exception as e:
                        logger.error("Task %s failed: %s", task_id, e)
                        task = next(t for t in subtasks if t.id == task_id)
                        task.status = "failed"
                        task.error = str(e)
                        completed_tasks.add(task_id)
        
        logger.info("Swarm execution complete: %d/%d tasks successful", 
                    len([t for t in subtasks if t.status == "completed"]), 
                    len(subtasks))
        
        return execution

    def aggregate_results(self, execution: SwarmExecution) -> SwarmExecution:
        """
        Aggregate results from all sub-agents into a final response.
        
        Args:
            execution: The swarm execution with all results
            
        Returns:
            Updated execution with synthesis
        """
        logger.info("Aggregating results from %d agents", len(execution.agent_results))
        
        # Build summary of all results
        results_summary = []
        for result in execution.agent_results:
            results_summary.append(
                f"Agent {result.agent_id} ({result.role}):\n{result.result[:500]}\n"
            )
        
        results_text = "\n---\n".join(results_summary)
        
        prompt = (
            f"Original query: {execution.query}\n\n"
            f"Agent results:\n{results_text}\n\n"
            "Synthesize these results into a coherent response in Czech."
        )
        
        try:
            json_result = self._bridge.call_json(
                "czech_gateway",
                [{"role": "user", "content": prompt}],
                system_prompt=_SWARM_AGGREGATOR_SYSTEM,
            )
            
            if json_result:
                synthesis = json_result.get("synthesis", "")
                confidence = float(json_result.get("confidence", 0.7))
                
                execution.mark_complete(synthesis, confidence)
                logger.info("Aggregation complete: confidence=%.2f", confidence)
                return execution
                
        except Exception as e:
            logger.error("Result aggregation failed: %s", e)
        
        # Fallback: concatenate all results
        fallback = "\n\n".join(r.result for r in execution.agent_results if r.success)
        execution.mark_complete(fallback, 0.5)
        
        return execution


# ============================================================================
# Convenience function for quick swarm execution
# ============================================================================

def execute_swarm_task(
    query: str,
    bridge: "CzechBridgeClient",
    memory: "CognitiveMemory",
    tools: Dict[str, Callable],
) -> str:
    """
    Convenience function to execute a task using the swarm architecture.
    
    Args:
        query: User query
        bridge: LLM bridge client
        memory: Cognitive memory
        tools: Available tools
        
    Returns:
        Final synthesized response
    """
    manager = SwarmManager(
        bridge=bridge,
        memory=memory,
        tools=tools,
        max_agents=4,
        timeout_seconds=120,
    )
    
    # Check if task is complex enough
    if not manager.is_complex_task(query):
        # Not complex - use standard ReAct loop
        from jarvis_reasoning import ReActLoop
        react = ReActLoop(bridge=bridge, memory=memory, tools=tools)
        return react.run(query)
    
    # Decompose task
    subtasks = manager.decompose_task(query)
    
    # Assign roles
    assignments = manager.assign_roles(subtasks)
    
    # Execute swarm
    execution = manager.execute_swarm(query, subtasks, assignments)
    
    # Aggregate results
    execution = manager.aggregate_results(execution)
    
    return execution.synthesis


__all__ = [
    "SubTask",
    "AgentResult",
    "SwarmExecution",
    "SubAgent",
    "SwarmManager",
    "ROLE_TOOLS",
    "execute_swarm_task",
]
