"""Step-level and final-output verifier for the reasoning engine"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

from jarvis_config import MODELS, HW_OPTIONS, OLLAMA_URL, SIMPLE_TOOLS

if TYPE_CHECKING:
    from jarvis_core import CzechBridgeClient

logger = logging.getLogger("JARVIS.REASONING.VERIFIER")

_STEP_VERIFIER_SYSTEM = (
    "You are a verification assistant. "
    "Given a task, a tool name, its output, and execution logs, "
    "decide whether the step succeeded and the output is useful. "
    "Return ONLY valid JSON: "
    '{"success": true, "confidence": 0.85, "reason": "...", "retry": false}'
)

_FINAL_VERIFIER_SYSTEM = (
    "You are a quality-assurance assistant. "
    "Given the original task and the full execution log, "
    "decide whether the task was completed successfully. "
    "Return ONLY valid JSON: "
    '{"success": true, "confidence": 0.9, "reason": "...", "suggest_replan": false}'
)


@dataclass
class VerificationResult:
    success: bool
    confidence: float
    reason: str
    retry: bool = False
    suggest_replan: bool = False
    raw: Dict = field(default_factory=dict)


class StepVerifier:
    """
    Verifies individual ReAct steps and the final execution output.

    For tools in SIMPLE_TOOLS the verification is skipped (returns a
    successful result immediately) to avoid unnecessary LLM round-trips.
    """

    def __init__(self, bridge: "CzechBridgeClient"):
        self._bridge = bridge

    def verify_step(
        self,
        tool_name: str,
        params: Dict,
        result: str,
        logs: List[str],
        query: str,
    ) -> VerificationResult:
        if tool_name in SIMPLE_TOOLS:
            return VerificationResult(success=True, confidence=1.0, reason="simple tool – skipped")

        log_excerpt = "\n".join(logs[-5:]) if logs else ""
        prompt = (
            f"Task: {query}\n"
            f"Tool: {tool_name}\n"
            f"Params: {params}\n"
            f"Output: {result[:500]}\n"
            f"Log: {log_excerpt}\n"
            "Verify this step."
        )
        raw = self._bridge.call_json(
            "verifier",
            [{"role": "user", "content": prompt}],
            system_prompt=_STEP_VERIFIER_SYSTEM,
        )
        if raw is None:
            logger.debug("Step verifier returned None – assuming success")
            return VerificationResult(success=False, confidence=0.0, reason="verifier unavailable", retry=True)

        return VerificationResult(
            success=bool(raw.get("success", True)),
            confidence=float(raw.get("confidence", 70)) / 100.0,
            reason=str(raw.get("reason", "")),
            retry=bool(raw.get("retry", False)),
            raw=raw,
        )

    def verify_final(
        self,
        query: str,
        logs: List[str],
        skip: bool = False,
    ) -> VerificationResult:
        if skip:
            return VerificationResult(success=True, confidence=1.0, reason="skipped")

        log_str = "\n".join(logs)
        prompt = (
            f"Task: {query}\n"
            f"Execution log:\n{log_str[:2000]}\n"
            "Was this task completed successfully?"
        )
        raw = self._bridge.call_json(
            "verifier",
            [{"role": "user", "content": prompt}],
            system_prompt=_FINAL_VERIFIER_SYSTEM,
        )
        if raw is None:
            logger.debug("Final verifier returned None – assuming success")
            return VerificationResult(success=False, confidence=0.0, reason="verifier unavailable", retry=True, suggest_replan=True)

        return VerificationResult(
            success=bool(raw.get("success", True)),
            confidence=float(raw.get("confidence", 70)) / 100.0,
            reason=str(raw.get("reason", "")),
            suggest_replan=bool(raw.get("suggest_replan", False)),
            raw=raw,
        )


__all__ = ["StepVerifier", "VerificationResult"]
