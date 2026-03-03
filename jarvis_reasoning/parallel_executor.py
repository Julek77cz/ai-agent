"""Parallel tool executor using ThreadPoolExecutor"""
import concurrent.futures
import logging
import time
from typing import Callable, Dict, List, Tuple

logger = logging.getLogger("JARVIS.REASONING.PARALLEL")

_MAX_WORKERS = 4
_STEP_TIMEOUT = 60


class ParallelToolExecutor:
    """
    Executes a batch of tool steps concurrently when they are marked
    ``"parallel": true`` in the plan.

    Each callable in *tool_fn_map* is expected to accept ``(params: dict)``
    and return a string result.
    """

    def __init__(self, tool_fn_map: Dict[str, Callable[[Dict], str]]):
        self._tools = tool_fn_map

    def execute_batch(
        self, steps: List[Dict]
    ) -> List[Tuple[Dict, str, float]]:
        """
        Execute *steps* in parallel.

        Returns a list of ``(step, result, duration_seconds)`` tuples in
        the same order as the input steps.
        """
        if not steps:
            return []

        ordered: List[Tuple[Dict, str, float]] = [None] * len(steps)  # type: ignore[list-item]

        def _run(index: int, step: Dict) -> Tuple[int, str, float]:
            tool_name = step.get("tool", "")
            params = step.get("params", {})
            fn = self._tools.get(tool_name)
            if fn is None:
                return index, f"Unknown tool: {tool_name}", 0.0
            t0 = time.perf_counter()
            try:
                result = fn(params)
            except Exception as exc:
                result = f"Error in {tool_name}: {exc}"
            duration = time.perf_counter() - t0
            return index, result, duration

        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_run, idx, step): idx
                for idx, step in enumerate(steps)
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, result, duration = future.result(timeout=_STEP_TIMEOUT)
                    ordered[idx] = (steps[idx], result, duration)
                    logger.debug(
                        "Parallel step %d (%s) finished in %.2fs",
                        idx,
                        steps[idx].get("tool", "?"),
                        duration,
                    )
                except concurrent.futures.TimeoutError:
                    idx = futures[future]
                    ordered[idx] = (steps[idx], f"Timeout after {_STEP_TIMEOUT}s", float(_STEP_TIMEOUT))
                except Exception as exc:
                    idx = futures[future]
                    ordered[idx] = (steps[idx], f"Execution error: {exc}", 0.0)

        return ordered

    def execute_single(self, step: Dict) -> Tuple[str, float]:
        """Convenience wrapper for a single (non-parallel) step."""
        tool_name = step.get("tool", "")
        params = step.get("params", {})
        fn = self._tools.get(tool_name)
        if fn is None:
            return f"Unknown tool: {tool_name}", 0.0
        t0 = time.perf_counter()
        try:
            result = fn(params)
        except Exception as exc:
            result = f"Error in {tool_name}: {exc}"
        return result, time.perf_counter() - t0


__all__ = ["ParallelToolExecutor"]
