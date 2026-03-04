"""Parallel tool executor using ThreadPoolExecutor"""
import concurrent.futures
import logging
import time
from typing import Callable, Dict, List, Optional, Tuple

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

    def __init__(self, tool_fn_map: Dict[str, Callable[[Dict], str]], procedural_memory=None):
        self._tools = tool_fn_map
        self._procedural = procedural_memory

    def _classify_error(self, result: str) -> Tuple[str, str]:
        """Classify error type from result string."""
        result_lower = result.lower()
        if "not found" in result_lower or "file not found" in result_lower:
            return "file_not_found", result
        if "permission" in result_lower or "denied" in result_lower:
            return "permission_denied", result
        if "timeout" in result_lower:
            return "timeout", result
        if "invalid" in result_lower or "missing" in result_lower:
            return "parameter_error", result
        if "error" in result_lower:
            return "general_error", result
        return "unknown", result

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
                result = f"Unknown tool: {tool_name}"
                self._record_failure(tool_name, params, "unknown_tool", result)
                return index, result, 0.0
            t0 = time.perf_counter()
            try:
                result = fn(params)
            except Exception as exc:
                result = f"Error in {tool_name}: {exc}"
                error_type, _ = self._classify_error(result)
                self._record_failure(tool_name, params, error_type, result)
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

    def _record_failure(self, tool: str, params: Dict, error_type: str, error_message: str) -> None:
        """Record failure to procedural memory for learning."""
        if self._procedural is not None:
            try:
                self._procedural.record_failure(
                    tool=tool,
                    params=params,
                    error_type=error_type,
                    error_message=error_message,
                    context="parallel_executor",
                )
            except Exception as e:
                logger.debug("Failed to record failure: %s", e)

    def execute_single(self, step: Dict) -> Tuple[str, float]:
        """Convenience wrapper for a single (non-parallel) step."""
        tool_name = step.get("tool", "")
        params = step.get("params", {})
        fn = self._tools.get(tool_name)
        if fn is None:
            result = f"Unknown tool: {tool_name}"
            self._record_failure(tool_name, params, "unknown_tool", result)
            return result, 0.0
        t0 = time.perf_counter()
        try:
            result = fn(params)
        except Exception as exc:
            result = f"Error in {tool_name}: {exc}"
            error_type, _ = self._classify_error(result)
            self._record_failure(tool_name, params, error_type, result)
        return result, time.perf_counter() - t0


__all__ = ["ParallelToolExecutor"]
