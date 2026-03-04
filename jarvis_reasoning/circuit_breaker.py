"""Circuit Breaker for ReAct Loop

Protects against infinite loops in the ReAct reasoning loop by tracking
failures and opening the circuit when too many consecutive failures occur.
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any, Dict, List

from jarvis_config import (
    CIRCUIT_BREAKER_ENABLED,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    CIRCUIT_BREAKER_TIMEOUT_SECONDS,
)

logger = logging.getLogger("JARVIS.CIRCUIT_BREAKER")


@dataclass
class FailureRecord:
    """Record of a failure for pattern detection."""
    tool: str
    params_hash: str
    error_hash: str
    timestamp: float = field(default_factory=time.time)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker to prevent infinite loops in ReAct reasoning.

    The circuit breaker tracks consecutive failures and opens when a threshold
    is reached. After a timeout, it enters half-open state to test if the
    system has recovered.
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        success_threshold: int = CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
        timeout_seconds: int = CIRCUIT_BREAKER_TIMEOUT_SECONDS,
        enabled: bool = CIRCUIT_BREAKER_ENABLED,
    ):
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._timeout = timeout_seconds
        self._enabled = enabled

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        
        # Failure history for detecting repeated failures (immortality feature)
        self._failure_history: List[FailureRecord] = []
        self._max_history_size = 50  # Keep last 50 failures

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        if not self._enabled:
            return CircuitState.CLOSED
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking)."""
        if not self._enabled:
            return False

        if self._state == CircuitState.OPEN:
            # Check if timeout has passed to transition to half-open
            if self._last_failure_time and (time.time() - self._last_failure_time) >= self._timeout:
                logger.info("Circuit breaker transitioning to HALF_OPEN after timeout")
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                return False
            return True
        return False

    def record_success(self) -> None:
        """Record a successful execution."""
        if not self._enabled:
            return

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                logger.info("Circuit breaker transitioning to CLOSED after recovery")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    def record_failure(
        self,
        tool: Optional[str] = None,
        params: Optional[Dict] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a failed execution.
        
        Args:
            tool: Name of the tool that failed (optional)
            params: Parameters passed to the tool (optional)
            error_message: Error message from the failure (optional)
        """
        if not self._enabled:
            return

        self._failure_count += 1
        self._last_failure_time = time.time()
        
        # Track failure history for pattern detection
        if tool and params and error_message:
            params_hash = hashlib.md5(
                json.dumps(params, sort_keys=True, default=str).encode()
            ).hexdigest()[:12]
            error_hash = hashlib.md5(error_message.encode()).hexdigest()[:12]
            
            record = FailureRecord(
                tool=tool,
                params_hash=params_hash,
                error_hash=error_hash,
            )
            self._failure_history.append(record)
            
            # Trim history if needed
            if len(self._failure_history) > self._max_history_size:
                self._failure_history = self._failure_history[-self._max_history_size:]
            
            # Check for repeated failures (same tool + params + error)
            self._check_repeated_failures(tool, params_hash, error_hash, error_message)

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens the circuit
            logger.warning("Circuit breaker reopening after failure in HALF_OPEN state")
            self._state = CircuitState.OPEN
            self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                logger.warning(
                    "Circuit breaker opening after %d consecutive failures",
                    self._failure_count
                )
                self._state = CircuitState.OPEN
    
    def _check_repeated_failures(
        self,
        tool: str,
        params_hash: str,
        error_hash: str,
        error_message: str,
    ) -> None:
        """Check if the same failure has occurred multiple times."""
        # Look at recent failures (last 10)
        recent = self._failure_history[-10:]
        repeats = [
            f for f in recent
            if f.tool == tool
            and f.params_hash == params_hash
            and f.error_hash == error_hash
        ]
        
        # If we've seen this exact failure 2+ times before (3+ total including current)
        if len(repeats) >= 3:
            logger.warning(
                "Circuit breaker triggered by repeated failure: "
                "tool=%s, repeats=%d, error=%s...",
                tool, len(repeats), error_message[:50]
            )
            self._state = CircuitState.OPEN
            self._last_failure_time = time.time()

    def execute(self, func: Callable[[], Any]) -> Any:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Function to execute

        Returns:
            Result of the function

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        if self.is_open:
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN. "
                f"State: {self._state.value}, "
                f"Failures: {self._failure_count}, "
                f"Last failure: {self._get_time_since_last_failure():.1f}s ago"
            )

        try:
            result = func()
            self.record_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception as e:
            # Simple record_failure without context (backward compatibility)
            self.record_failure()
            raise

    def _get_time_since_last_failure(self) -> float:
        """Get seconds since last failure."""
        if self._last_failure_time:
            return time.time() - self._last_failure_time
        return 0.0

    def get_status(self) -> dict:
        """Get circuit breaker status for debugging."""
        return {
            "enabled": self._enabled,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self._failure_threshold,
            "success_threshold": self._success_threshold,
            "timeout_seconds": self._timeout,
            "time_since_last_failure": self._get_time_since_last_failure(),
            "failure_history_size": len(self._failure_history),
        }

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    @property
    def success_count(self) -> int:
        """Get current success count."""
        return self._success_count

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        logger.info("Circuit breaker manually reset to CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "FailureRecord",
]
