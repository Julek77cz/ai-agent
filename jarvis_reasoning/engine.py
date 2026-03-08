"""
Advanced Reasoning Engine – iterative ReAct (Reason + Act) loop.

Architecture:
  1. ContextPrefetcher loads all relevant memory before reasoning starts.
  2. The planner produces an initial plan (list of steps).
  3. The ReAct loop iterates: Thought → Action → Observation → Thought …
     • Parallel steps (``"parallel": true``) are dispatched to ParallelToolExecutor.
     • Each step result is optionally verified by StepVerifier.
     • If a step fails and ``retry`` is requested, the step is retried once.
     • If the verifier suggests a replan, a new plan is requested from the LLM.
  4. After all steps, a final verification is run.
  5. The final answer is synthesised by the LLM using the full execution trace.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from jarvis_config import MAX_REPLANS, SIMPLE_TOOLS
from jarvis_reasoning.context_prefetch import ContextPrefetcher
from jarvis_reasoning.verifier import StepVerifier, VerificationResult
from jarvis_reasoning.parallel_executor import ParallelToolExecutor

if TYPE_CHECKING:
    from jarvis_core import CzechBridgeClient, check_stop
    from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.REASONING.ENGINE")

try:
    from jarvis_tools import TOOLS_SCHEMA as _TOOLS_SCHEMA
except ImportError:
    _TOOLS_SCHEMA = ""

_PLANNER_SYSTEM = (
    "You are a task planner. Output ONLY valid JSON.\n"
    "RULE 1: Mark steps with 'parallel': true if they can run simultaneously.\n"
    "RULE 2: For memory queries -> use recall tool.\n"
    "RULE 3: For storing facts -> use remember tool.\n"
    "RULE 4: Keep plan minimal. MAXIMUM 6 steps.\n"
    "RULE 5: Include 'confidence': 0-100 for the whole plan.\n"
    "RULE 6: When writing files (write_file), ALWAYS use just the filename (e.g. 'file.txt') and save it to the current directory. DO NOT use absolute paths like /home/user or C:\\!\n"
    f"{_TOOLS_SCHEMA}"
)

_REPLAN_SYSTEM = (
    "You are a task replanner. The previous plan had failures. "
    "Output ONLY valid JSON with a revised plan.\n"
    "RULE: Mark parallel steps with 'parallel': true.\n"
    "RULE: Include 'confidence': 0-100.\n"
    "RULE: When writing files, ALWAYS use just the filename (e.g. 'file.txt') without absolute paths.\n"
    f"{_TOOLS_SCHEMA}"
)

_SYNTHESIS_SYSTEM = (
    "You are JARVIS. Synthesise a helpful response in Czech based on the "
    "execution trace. Be concise and direct."
)


@dataclass
class ReActStep:
    """A single step in the ReAct trace."""
    step_number: int
    thought: str
    tool: str
    params: Dict
    observation: str = ""
    duration: float = 0.0
    success: bool = True
    verification: Optional[VerificationResult] = None
    parallel: bool = False


@dataclass
class ReasoningTrace:
    """Complete trace of a reasoning session."""
    query: str
    query_en: str
    steps: List[ReActStep] = field(default_factory=list)
    replan_count: int = 0
    final_success: bool = True
    final_confidence: float = 1.0
    final_reason: str = ""
    context_summary: str = ""
    started_at: float = field(default_factory=time.time)

    def log_lines(self) -> List[str]:
        lines: List[str] = []
        for s in self.steps:
            line = f"[{s.tool}] ({s.duration:.2f}s) → {s.observation[:300]}"
            lines.append(line)
        return lines

    def elapsed(self) -> float:
        return time.time() - self.started_at


class ReasoningEngine:
    """
    Iterative ReAct reasoning engine for JARVIS V19.

    Parameters
    ----------
    bridge:
        CzechBridgeClient instance for LLM calls.
    memory:
        CognitiveMemory instance.
    tools:
        Mapping of tool_name → callable(params) → str.
    check_stop_fn:
        Zero-argument callable that returns True when an emergency stop
        has been requested.
    streaming:
        Whether the engine should stream the final synthesis.
    """

    def __init__(
        self,
        bridge: "CzechBridgeClient",
        memory: "CognitiveMemory",
        tools: Dict[str, Callable],
        check_stop_fn: Callable[[], bool],
        streaming: bool = True,
    ):
        self._bridge = bridge
        self._memory = memory
        self._tools = tools
        self._check_stop = check_stop_fn
        self._streaming = streaming

        self._prefetcher = ContextPrefetcher(memory)
        self._verifier = StepVerifier(bridge)
        self._executor = ParallelToolExecutor(tools)

    def reason(
        self,
        query: str,
        query_en: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Run the full ReAct reasoning loop for *query* and return the final
        Czech response string.
        """
        trace = ReasoningTrace(query=query, query_en=query_en)

        ctx = self._prefetcher.prefetch(query_en)
        trace.context_summary = ctx.get("summary", "")

        plan, confidence = self._create_plan(query_en, ctx)

        if not plan:
            logger.info("No plan produced – falling back to direct chat")
            return self._direct_chat(query, ctx, stream_callback)

        logger.info("Initial plan: %d steps, confidence=%.0f%%", len(plan), confidence * 100)

        replan_count = 0
        while replan_count <= MAX_REPLANS:
            if self._check_stop():
                return "🛑 Zastaveno."

            plan = self._execute_plan(plan, trace, query_en)

            needs_replan = any(
                s.verification is not None and s.verification.suggest_replan
                for s in trace.steps
            )

            if needs_replan and replan_count < MAX_REPLANS:
                replan_count += 1
                trace.replan_count = replan_count
                logger.info("Replanning (%d/%d)…", replan_count, MAX_REPLANS)
                plan, _ = self._replan(query_en, trace, ctx)
                if not plan:
                    break
            else:
                break

        all_tools = {s.tool for s in trace.steps}
        skip_final_verify = all_tools.issubset(SIMPLE_TOOLS)
        final_result = self._verifier.verify_final(
            query_en,
            trace.log_lines(),
            skip=skip_final_verify,
        )
        trace.final_success = final_result.success
        trace.final_confidence = final_result.confidence
        trace.final_reason = final_result.reason

        logger.info(
            "Reasoning complete in %.2fs – %d steps, success=%s",
            trace.elapsed(),
            len(trace.steps),
            trace.final_success,
        )

        return self._synthesise(query, trace, stream_callback)

    def _create_plan(self, query_en: str, ctx: Dict) -> tuple:
        prompt = (
            f"Context:\n{ctx.get('summary', '')}\n\n"
            f"Task: {query_en}\n\n"
            "Create an execution plan."
        )
        raw = self._bridge.call_json(
            "planner",
            [{"role": "user", "content": prompt}],
            system_prompt=_PLANNER_SYSTEM,
        )
        if raw is None:
            return [], 0.0
        plan = raw.get("plan", [])
        confidence = float(raw.get("confidence", 70)) / 100.0
        return plan, confidence

    def _replan(self, query_en: str, trace: ReasoningTrace, ctx: Dict) -> tuple:
        failures = [
            f"Step {s.step_number} ({s.tool}): {s.observation[:200]}"
            for s in trace.steps
            if not s.success
        ]
        prompt = (
            f"Original task: {query_en}\n"
            f"Context:\n{ctx.get('summary', '')}\n\n"
            f"Failed steps:\n" + "\n".join(failures) + "\n\n"
            "Create a revised plan to complete the task."
        )
        raw = self._bridge.call_json(
            "planner",
            [{"role": "user", "content": prompt}],
            system_prompt=_REPLAN_SYSTEM,
        )
        if raw is None:
            return [], 0.0
        plan = raw.get("plan", [])
        confidence = float(raw.get("confidence", 60)) / 100.0
        return plan, confidence

    def _execute_plan(
        self, plan: List[Dict], trace: ReasoningTrace, query_en: str
    ) -> List[Dict]:
        """Execute the plan, grouping consecutive parallel steps."""
        i = 0
        remaining_plan: List[Dict] = []

        while i < len(plan):
            if self._check_stop():
                remaining_plan = plan[i:]
                break

            step = plan[i]

            if step.get("parallel"):
                batch = [step]
                j = i + 1
                while j < len(plan) and plan[j].get("parallel"):
                    batch.append(plan[j])
                    j += 1

                logger.info("Executing %d parallel steps", len(batch))
                batch_results = self._executor.execute_batch(batch)

                for b_step, b_result, b_duration in batch_results:
                    step_num = len(trace.steps) + 1
                    react_step = ReActStep(
                        step_number=step_num,
                        thought=f"Running {b_step.get('tool', '?')} in parallel",
                        tool=b_step.get("tool", ""),
                        params=b_step.get("params", {}),
                        observation=b_result,
                        duration=b_duration,
                        parallel=True,
                    )
                    react_step.success = not (
                        "Error" in b_result or "Unknown tool" in b_result
                    )
                    if not b_step.get("tool", "") in SIMPLE_TOOLS:
                        react_step.verification = self._verifier.verify_step(
                            b_step.get("tool", ""),
                            b_step.get("params", {}),
                            b_result,
                            trace.log_lines(),
                            query_en,
                        )
                        if not react_step.verification.success and react_step.verification.retry:
                            logger.info("Retrying step %d (%s)", step_num, b_step.get("tool"))
                            retry_result, retry_dur = self._executor.execute_single(b_step)
                            react_step.observation = retry_result
                            react_step.duration = b_duration + retry_dur
                            react_step.success = "Error" not in retry_result
                    trace.steps.append(react_step)

                i = j
            else:
                tool_name = step.get("tool", "")
                params = step.get("params", {})
                step_num = len(trace.steps) + 1

                thought = f"Running {tool_name}"
                logger.info("Step %d: %s", step_num, tool_name)

                result, duration = self._executor.execute_single(step)

                react_step = ReActStep(
                    step_number=step_num,
                    thought=thought,
                    tool=tool_name,
                    params=params,
                    observation=result,
                    duration=duration,
                    parallel=False,
                )
                react_step.success = not ("Error" in result or "Unknown tool" in result)

                if tool_name not in SIMPLE_TOOLS:
                    react_step.verification = self._verifier.verify_step(
                        tool_name,
                        params,
                        result,
                        trace.log_lines(),
                        query_en,
                    )
                    if (
                        react_step.verification is not None
                        and not react_step.verification.success
                        and react_step.verification.retry
                    ):
                        logger.info("Retrying step %d (%s)", step_num, tool_name)
                        retry_result, retry_dur = self._executor.execute_single(step)
                        react_step.observation = retry_result
                        react_step.duration = duration + retry_dur
                        react_step.success = "Error" not in retry_result

                trace.steps.append(react_step)
                i += 1

        return remaining_plan

    def _synthesise(
        self,
        query: str,
        trace: ReasoningTrace,
        stream_callback: Optional[Callable[[str], None]],
    ) -> str:
        log_str = "\n".join(trace.log_lines())

        if trace.final_success:
            prompt = (
                f"Task: '{query}'\n"
                f"Results:\n{log_str}\n\n"
                "Summarise the results for the user."
            )
        else:
            prompt = (
                f"Task: '{query}'\n"
                f"Results:\n{log_str}\n"
                f"Failure reason: {trace.final_reason}\n\n"
                "Apologise and explain what went wrong."
            )

        if self._streaming and stream_callback:
            return self._bridge.call_stream(
                "czech_gateway",
                [{"role": "user", "content": prompt}],
                system_prompt=_SYNTHESIS_SYSTEM,
                callback=stream_callback,
            ) or ""

        raw = self._bridge.call_json(
            "czech_gateway",
            [{"role": "user", "content": prompt}],
            system_prompt=_SYNTHESIS_SYSTEM,
        )
        if raw:
            return raw.get("message", {}).get("content", "") or "\n".join(
                s.observation for s in trace.steps if s.observation
            )
        return "\n".join(s.observation for s in trace.steps if s.observation)

    def _direct_chat(
        self,
        query: str,
        ctx: Dict,
        stream_callback: Optional[Callable[[str], None]],
    ) -> str:
        recent = ctx.get("recent", [])
        history = [{"role": t.role, "content": t.content} for t in recent]
        system = f"Jsi JARVIS.\nKontext:\n{ctx.get('summary', '')}"

        if self._streaming and stream_callback:
            return self._bridge.call_stream(
                "czech_gateway",
                history + [{"role": "user", "content": query}],
                system_prompt=system,
                callback=stream_callback,
            ) or ""

        raw = self._bridge.call_json(
            "czech_gateway",
            history + [{"role": "user", "content": query}],
            system_prompt=system,
        )
        if raw:
            return raw.get("message", {}).get("content", "") or ""
        return ""


__all__ = ["ReasoningEngine", "ReActStep", "ReasoningTrace"]
