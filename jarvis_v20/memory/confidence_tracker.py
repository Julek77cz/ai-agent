"""JARVIS V20 - Confidence Calibration Tracker

Track and calibrate confidence scores based on historical accuracy.
"""
import logging
from typing import Dict, List, Tuple
from collections import defaultdict
import numpy as np

logger = logging.getLogger("JARVIS.V20.MEMORY.CONFIDENCE")


class ConfidenceTracker:
    """
    Track and calibrate confidence scores based on historical accuracy.
    """

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self._calibration_data: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        logger.info("ConfidenceTracker initialized")

    def record(
        self,
        decision_type: str,
        predicted_confidence: float,
        actual_outcome: float,
    ):
        """Record a prediction with outcome."""
        self._calibration_data[decision_type].append((predicted_confidence, actual_outcome))

        # Trim history
        if len(self._calibration_data[decision_type]) > self.max_history:
            self._calibration_data[decision_type] = self._calibration_data[decision_type][-self.max_history:]

        logger.debug("Recorded confidence: type=%s, predicted=%.2f, actual=%.2f",
                   decision_type, predicted_confidence, actual_outcome)

    def get_calibrated_confidence(
        self,
        decision_type: str,
        raw_confidence: float,
    ) -> float:
        """Get calibrated confidence based on history."""
        if decision_type not in self._calibration_data:
            return raw_confidence

        data = self._calibration_data[decision_type]
        if len(data) < 10:
            return raw_confidence

        # Calculate bias
        predicted = np.array([p for p, a in data])
        actual = np.array([a for p, a in data])
        bias = np.mean(predicted - actual)

        # Remove bias
        calibrated = raw_confidence - bias

        # Clamp to [0, 1]
        return max(0.0, min(1.0, calibrated))

    def get_statistics(self) -> Dict:
        """Get calibration statistics."""
        stats = {}

        for decision_type, data in self._calibration_data.items():
            if len(data) < 5:
                continue

            predictions = np.array([p for p, a in data])
            outcomes = np.array([a for p, a in data])

            stats[decision_type] = {
                "record_count": len(data),
                "avg_predicted": float(np.mean(predictions)),
                "avg_actual": float(np.mean(outcomes)),
                "bias": float(np.mean(predictions - outcomes)),
                "mae": float(np.mean(np.abs(predictions - outcomes))),
            }

        return stats


__all__ = ["ConfidenceTracker"]
