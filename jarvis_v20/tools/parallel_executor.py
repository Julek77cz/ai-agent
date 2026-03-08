"""JARVIS V20 - Parallel Tool Executor

Execute multiple tools in parallel with streaming results.
"""
import logging
from typing import List, Dict, Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = logging.getLogger("JARVIS.V20.TOOLS.PARALLEL")


class ParallelToolExecutor:
    """
    Parallel execution of tools with streaming results.
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        logger.info("ParallelToolExecutor initialized (workers=%d)", max_workers)

    def execute_parallel(
        self,
        actions: List[Dict],
        tools: Dict[str, Callable],
        stream_callback: Callable = None,
    ) -> Dict[str, Any]:
        """
        Execute multiple tools in parallel.

        Args:
            actions: List of action dicts with "tool" and "params"
            tools: Tool registry
            stream_callback: Optional callback for streaming

        Returns:
            Dict mapping tool names to results
        """
        results = {}
        completed = 0
        total = len(actions)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all actions
            future_to_action = {
                executor.submit(self._execute_single, a, tools): a
                for a in actions
            }

            # Collect results as they complete
            for future in as_completed(future_to_action.keys()):
                action = future_to_action[future]
                tool_name = action.get("tool", "unknown")

                try:
                    result = future.result()
                    results[tool_name] = result
                    completed += 1

                    if stream_callback:
                        progress = completed / total
                        stream_callback(f"[{completed}/{total}] {tool_name}: {str(result)[:50]}...")

                    logger.debug("Parallel execution: %s completed", tool_name)

                except Exception as e:
                    results[tool_name] = f"Error: {str(e)}"
                    completed += 1

                    if stream_callback:
                        progress = completed / total
                        stream_callback(f"[{completed}/{total}] {tool_name}: ERROR - {str(e)[:30]}...")

                    logger.error("Parallel execution error for %s: %s", tool_name, e)

        logger.info("Parallel execution complete: %d/%d succeeded",
                   sum(1 for r in results.values() if "Error" not in str(r)), total)

        return results

    def _execute_single(self, action: Dict, tools: Dict[str, Callable]) -> Any:
        """Execute a single tool."""
        tool_name = action.get("tool", "")
        params = action.get("params", {})

        tool_fn = tools.get(tool_name)
        if not tool_fn:
            return f"Unknown tool: {tool_name}"

        try:
            return tool_fn(params)
        except Exception as e:
            return f"Error: {str(e)}"


__all__ = ["ParallelToolExecutor"]
