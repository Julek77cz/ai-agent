"""JARVIS V20 - Metacognitive Layer

Implements self-reflection, pattern recognition, bias detection,
and confidence calibration.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

logger = logging.getLogger("JARVIS.V20.REASONING.METACOGNITION")


@dataclass
class MetacognitiveEvent:
    """Represents a metacognitive event."""
    event_id: str
    event_type: str
    timestamp: float
    decision_context: Dict[str, Any]
    confidence: float
    rationale: str
    outcome: Optional[str] = None
    outcome_quality: float = 0.0
    execution_time: float = 0.0


@dataclass
class MetacognitiveInsight:
    """Represents an insight from metacognitive analysis."""
    insight_type: str  # pattern, bias, limitation, improvement
    description: str
    evidence: List[str]
    suggestion: Optional[str] = None
    confidence: float = 0.8


class MetacognitiveLayer:
    """
    Metacognitive Layer for self-reflection and pattern recognition.

    Tracks decisions, detects patterns and biases, calibrates confidence,
    and provides suggestions for improvement.
    """

    def __init__(
        self,
        history_size: int = 1000,
        pattern_threshold: int = 5,
        bias_detection_window: int = 50,
    ):
        self.history_size = history_size
        self.pattern_threshold = pattern_threshold
        self.bias_detection_window = bias_detection_window

        # Decision history
        self._events: List[MetacognitiveEvent] = []
        self._events_by_type: Dict[str, List[MetacognitiveEvent]] = defaultdict(list)

        # Calibration data
        self._calibration_data: Dict[str, List[tuple]] = defaultdict(list)

        # Insights cache
        self._insights: List[MetacognitiveInsight] = []
        self._insight_cache_time = 0.0

        logger.info(
            "MetacognitiveLayer initialized: history=%d, threshold=%d",
            history_size, pattern_threshold
        )

    def monitor_decision(
        self,
        decision_type: str,
        decision_context: Dict[str, Any],
        decision_confidence: float,
        decision_rationale: str,
    ) -> str:
        """
        Monitor a decision and record it for metacognitive analysis.

        Args:
            decision_type: Type of decision (e.g., "tool_selection", "task_planning")
            decision_context: Context surrounding the decision
            decision_confidence: Confidence in the decision (0.0-1.0)
            decision_rationale: Rationale for the decision

        Returns:
            Event ID for later outcome recording
        """
        event_id = f"event_{int(time.time() * 1000)}"

        event = MetacognitiveEvent(
            event_id=event_id,
            event_type=decision_type,
            timestamp=time.time(),
            decision_context=decision_context,
            confidence=decision_confidence,
            rationale=decision_rationale,
        )

        self._events.append(event)
        self._events_by_type[decision_type].append(event)

        # Trim history
        if len(self._events) > self.history_size:
            self._events = self._events[-self.history_size:]
        if len(self._events_by_type[decision_type]) > self.history_size:
            self._events_by_type[decision_type] = self._events_by_type[decision_type][-self.history_size:]

        logger.debug(
            "Recorded decision %s: type=%s, confidence=%.2f",
            event_id, decision_type, decision_confidence
        )

        return event_id

    def record_outcome(
        self,
        decision_id: str,
        outcome: str,
        outcome_quality: float,
        execution_time: float,
    ):
        """
        Record the outcome of a monitored decision.

        Args:
            decision_id: Event ID from monitor_decision
            outcome: "success" or "failure"
            outcome_quality: Quality of outcome (0.0-1.0)
            execution_time: Time taken (seconds)
        """
        event = None
        for e in self._events:
            if e.event_id == decision_id:
                event = e
                break

        if event:
            event.outcome = outcome
            event.outcome_quality = outcome_quality
            event.execution_time = execution_time

            # Update calibration data
            self._calibration_data[event.event_type].append(
                (event.confidence, outcome_quality)
            )

            logger.debug(
                "Recorded outcome for %s: %s, quality=%.2f",
                decision_id, outcome, outcome_quality
            )

            # Clear insight cache
            self._insight_cache_time = 0

    def get_calibrated_confidence(
        self,
        decision_type: str,
        raw_confidence: float,
    ) -> float:
        """
        Get calibrated confidence based on historical accuracy.

        Args:
            decision_type: Type of decision
            raw_confidence: Raw confidence from model

        Returns:
            Calibrated confidence (0.0-1.0)
        """
        if decision_type not in self._calibration_data:
            return raw_confidence

        data = self._calibration_data[decision_type]
        if len(data) < 10:
            return raw_confidence

        # Calculate bias
        predicted = [p for p, a in data]
        actual = [a for p, a in data]
        bias = sum(p - a for p, a in data) / len(data)

        # Remove bias
        calibrated = raw_confidence - bias

        # Clamp to [0, 1]
        return max(0.0, min(1.0, calibrated))

    def detect_patterns(self) -> List[MetacognitiveInsight]:
        """Detect patterns in decision history."""
        patterns = []

        # Group by decision type
        for decision_type, events in self._events_by_type.items():
            if len(events) < self.pattern_threshold:
                continue

            # Check for overconfidence
            predicted = [e.confidence for e in events[-self.bias_detection_window:]]
            actual = [e.outcome_quality for e in events[-self.bias_detection_window:]]

            if len(predicted) >= 10 and len(actual) >= 10:
                avg_pred = sum(predicted) / len(predicted)
                avg_actual = sum(actual) / len(actual)

                if avg_pred > avg_actual + 0.2:
                    patterns.append(MetacognitiveInsight(
                        insight_type="pattern",
                        description=f"Overconfidence detected in {decision_type}",
                        evidence=[f"Predicted: {avg_pred:.2%}, Actual: {avg_actual:.2%}"],
                        suggestion="Reduce confidence estimates by 20%",
                        confidence=0.7,
                    ))

        return patterns

    def detect_biases(self) -> List[MetacognitiveInsight]:
        """Detect biases in decision-making."""
        biases = []

        # Check for tool preference bias
        tool_usage = defaultdict(int)
        for event in self._events:
            if event.event_type == "tool_selection":
                tool = event.decision_context.get("tool", "unknown")
                tool_usage[tool] += 1

        if tool_usage:
            total = sum(tool_usage.values())
            for tool, count in tool_usage.items():
                if count / total > 0.7 and count > 10:
                    biases.append(MetacognitiveInsight(
                        insight_type="bias",
                        description=f"Strong preference for tool: {tool}",
                        evidence=[f"Used in {count}/{total} decisions ({count/total:.1%})"],
                        suggestion="Consider alternative tools more often",
                        confidence=0.8,
                    ))

        return biases

    def detect_limitations(self) -> List[MetacognitiveInsight]:
        """Detect limitations in capabilities."""
        limitations = []

        # Check for high failure rates
        for decision_type, events in self._events_by_type.items():
            recent_failures = [
                e for e in events[-self.bias_detection_window:]
                if e.outcome == "failure"
            ]

            if len(recent_failures) > len(events[-self.bias_detection_window:]) * 0.5:
                limitations.append(MetacognitiveInsight(
                    insight_type="limitation",
                    description=f"High failure rate in {decision_type}",
                    evidence=[
                        f"{len(recent_failures)} failures in recent {self.bias_detection_window} decisions"
                    ],
                    suggestion="Consider alternative approaches or fallback strategies",
                    confidence=0.8,
                ))

        return limitations

    def get_suggestion(
        self,
        decision_type: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """
        Get a suggestion for a decision based on metacognitive analysis.

        Args:
            decision_type: Type of decision
            context: Decision context

        Returns:
            Suggestion string or None
        """
        # Check recent outcomes for this decision type
        if decision_type in self._events_by_type:
            recent = self._events_by_type[decision_type][-10:]
            failures = [e for e in recent if e.outcome == "failure"]

            if len(failures) > 5:
                return f"Caution: High failure rate for {decision_type} decisions. Consider alternative approach."

        return None

    def analyze_self(self) -> Dict[str, Any]:
        """
        Perform comprehensive self-analysis.

        Returns:
            Dict with analysis results
        """
        # Update insights cache
        if time.time() - self._insight_cache_time > 300:  # Cache for 5 minutes
            self._insights = (
                self.detect_patterns() +
                self.detect_biases() +
                self.detect_limitations()
            )
            self._insight_cache_time = time.time()

        return {
            "total_decisions": len(self._events),
            "patterns_detected": len(self._insights),
            "patterns": [
                {"description": i.description, "type": i.insight_type}
                for i in self._insights
            ],
            "biases_detected": len([i for i in self._insights if i.insight_type == "bias"]),
            "biases": [
                {"description": i.description}
                for i in self._insights if i.insight_type == "bias"
            ],
            "decision_types": list(self._events_by_type.keys()),
        }


__all__ = ["MetacognitiveLayer", "MetacognitiveEvent", "MetacognitiveInsight"]
