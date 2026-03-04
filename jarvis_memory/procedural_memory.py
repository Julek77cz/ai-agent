"""
Procedural Memory for Learning from Mistakes (Immortality)

This module enables JARVIS to learn from its errors and failures,
implementing a form of "immortality" through persistent learning.
When JARVIS makes a mistake, the details are recorded and analyzed
to prevent similar errors in the future.
"""
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict
import re

from jarvis_config import (
    PROCEDURAL_DIR,
    PROCEDURAL_FAILURES_FILE,
    PROCEDURAL_RECOVERIES_FILE,
    PROCEDURAL_PATTERNS_FILE,
    PROCEDURAL_MEMORY_ENABLED,
    PROCEDURAL_MIN_FAILURE_COUNT,
    PROCEDURAL_PATTERN_CONFIDENCE_THRESHOLD,
    PROCEDURAL_MAX_RECOVERIES_STORED,
    PROCEDURAL_ANALYSIS_INTERVAL_MINUTES,
)

logger = logging.getLogger("JARVIS.PROCEDURAL")


@dataclass
class FailureRecord:
    """Record of a failed action or reasoning step."""
    id: str
    timestamp: str
    tool: str
    params: Dict[str, Any]
    error_type: str
    error_message: str
    context: str
    query: str
    resolved: bool = False
    resolution: str = ""
    recovery_id: str = ""


@dataclass
class RecoveryRecord:
    """Record of a successful recovery from a failure."""
    id: str
    timestamp: str
    failure_id: str
    original_error: str
    recovery_strategy: str
    corrected_tool: str
    corrected_params: Dict[str, Any]
    success: bool
    duration_seconds: float
    lessons_learned: List[str] = field(default_factory=list)


@dataclass
class ErrorPattern:
    """Discovered pattern of recurring errors."""
    id: str
    pattern_type: str  # tool_specific, parameter_related, context_dependent
    description: str
    error_signatures: List[str]
    recovery_strategies: List[str]
    occurrence_count: int
    success_rate: float
    last_seen: str
    confidence: float
    avoidance_rules: List[str] = field(default_factory=list)


class ProceduralMemory:
    """
    Procedural memory system that learns from mistakes.
    
    This implements the "immortality" feature - JARVIS learns from
    every failure to avoid repeating the same mistakes.
    
    Features:
    - Record all failures with full context
    - Track recovery attempts and strategies
    - Discover patterns in recurring errors
    - Generate avoidance rules for known failure patterns
    - Integrate with reasoning engine to avoid known pitfalls
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._enabled = PROCEDURAL_MEMORY_ENABLED
        
        self._failures: List[FailureRecord] = []
        self._recoveries: List[RecoveryRecord] = []
        self._patterns: Dict[str, ErrorPattern] = {}
        
        self._lock = threading.RLock()
        self._analysis_lock = threading.Lock()
        self._last_analysis = datetime.now()
        
        # Ensure procedural directory exists
        PROCEDURAL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        if self._enabled:
            self._load_data()
        
        # Start background analysis thread
        if self._enabled:
            self._start_analysis_thread()
        
        self._initialized = True
        logger.info(
            "ProceduralMemory initialized: enabled=%s, failures=%d, patterns=%d",
            self._enabled, len(self._failures), len(self._patterns)
        )
    
    def _load_data(self) -> None:
        """Load existing failure and recovery records."""
        # Load failures
        if PROCEDURAL_FAILURES_FILE.exists():
            try:
                with open(PROCEDURAL_FAILURES_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                with self._lock:
                    for fdata in raw:
                        self._failures.append(FailureRecord(**fdata))
                logger.info("Loaded %d failure records", len(self._failures))
            except Exception as e:
                logger.warning("Failed to load failures: %s", e)
        
        # Load recoveries
        if PROCEDURAL_RECOVERIES_FILE.exists():
            try:
                with open(PROCEDURAL_RECOVERIES_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                with self._lock:
                    for rdata in raw:
                        self._recoveries.append(RecoveryRecord(**rdata))
                logger.info("Loaded %d recovery records", len(self._recoveries))
            except Exception as e:
                logger.warning("Failed to load recoveries: %s", e)
        
        # Load patterns
        if PROCEDURAL_PATTERNS_FILE.exists():
            try:
                with open(PROCEDURAL_PATTERNS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                with self._lock:
                    for pid, pdata in raw.items():
                        self._patterns[pid] = ErrorPattern(**pdata)
                logger.info("Loaded %d error patterns", len(self._patterns))
            except Exception as e:
                logger.warning("Failed to load patterns: %s", e)
    
    def _save_failures(self) -> None:
        """Save failures to disk."""
        try:
            with self._lock:
                data = [asdict(f) for f in self._failures]
            with open(PROCEDURAL_FAILURES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save failures: %s", e)
    
    def _save_recoveries(self) -> None:
        """Save recoveries to disk."""
        try:
            with self._lock:
                data = [asdict(r) for r in self._recoveries]
            # Keep only recent recoveries
            data = data[-PROCEDURAL_MAX_RECOVERIES_STORED:]
            with open(PROCEDURAL_RECOVERIES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save recoveries: %s", e)
    
    def _save_patterns(self) -> None:
        """Save error patterns to disk."""
        try:
            with self._lock:
                data = {pid: asdict(p) for pid, p in self._patterns.items()}
            with open(PROCEDURAL_PATTERNS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save patterns: %s", e)
    
    def _start_analysis_thread(self) -> None:
        """Start background thread for pattern analysis."""
        def analysis_loop():
            while True:
                threading.Event().wait(timeout=PROCEDURAL_ANALYSIS_INTERVAL_MINUTES * 60)
                if not self._enabled:
                    break
                try:
                    self.analyze_patterns()
                except Exception as e:
                    logger.error("Pattern analysis failed: %s", e)
        
        thread = threading.Thread(target=analysis_loop, daemon=True, name="jarvis-procedural-analysis")
        thread.start()
        logger.info("Procedural memory analysis thread started")
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    def record_failure(
        self,
        tool: str,
        params: Dict[str, Any],
        error_type: str,
        error_message: str,
        context: str = "",
        query: str = "",
    ) -> FailureRecord:
        """
        Record a failure event.
        
        Args:
            tool: Name of the tool that failed
            params: Parameters passed to the tool
            error_type: Type/category of the error
            error_message: Error message
            context: Additional context (observations, thoughts)
            query: Original user query
            
        Returns:
            The created FailureRecord
        """
        if not self._enabled:
            return None
        
        with self._lock:
            record_id = hashlib.md5(
                f"{tool}{datetime.now().isoformat()}{error_type}".encode()
            ).hexdigest()[:12]
            
            record = FailureRecord(
                id=record_id,
                timestamp=datetime.now().isoformat(),
                tool=tool,
                params=params,
                error_type=error_type,
                error_message=error_message,
                context=context,
                query=query,
            )
            
            self._failures.append(record)
            
            # Keep only recent failures
            if len(self._failures) > 1000:
                self._failures = self._failures[-500:]
            
            self._save_failures()
            
            logger.info(
                "Recorded failure: tool=%s, type=%s, id=%s",
                tool, error_type, record_id
            )
            
            return record
    
    def record_recovery(
        self,
        failure_id: str,
        original_error: str,
        recovery_strategy: str,
        corrected_tool: str,
        corrected_params: Dict[str, Any],
        success: bool,
        duration_seconds: float,
        lessons_learned: List[str] = None,
    ) -> RecoveryRecord:
        """
        Record a successful or attempted recovery from a failure.
        
        Args:
            failure_id: ID of the original failure
            original_error: The original error message
            recovery_strategy: Strategy used to recover
            corrected_tool: Tool used after correction
            corrected_params: Corrected parameters
            success: Whether recovery was successful
            duration_seconds: Time taken to recover
            lessons_learned: List of lessons learned
            
        Returns:
            The created RecoveryRecord
        """
        if not self._enabled:
            return None
        
        with self._lock:
            record_id = hashlib.md5(
                f"recovery-{failure_id}-{datetime.now().isoformat()}".encode()
            ).hexdigest()[:12]
            
            record = RecoveryRecord(
                id=record_id,
                timestamp=datetime.now().isoformat(),
                failure_id=failure_id,
                original_error=original_error,
                recovery_strategy=recovery_strategy,
                corrected_tool=corrected_tool,
                corrected_params=corrected_params,
                success=success,
                duration_seconds=duration_seconds,
                lessons_learned=lessons_learned or [],
            )
            
            self._recoveries.append(record)
            
            # Update failure record if found
            for failure in self._failures:
                if failure.id == failure_id:
                    failure.resolved = True
                    failure.resolution = recovery_strategy
                    failure.recovery_id = record_id
                    break
            
            # Keep only recent recoveries
            if len(self._recoveries) > PROCEDURAL_MAX_RECOVERIES_STORED:
                self._recoveries = self._recoveries[-PROCEDURAL_MAX_RECOVERIES_STORED:]
            
            self._save_recoveries()
            self._save_failures()
            
            logger.info(
                "Recorded recovery: failure=%s, success=%s, strategy=%s",
                failure_id, success, recovery_strategy
            )
            
            # Trigger pattern analysis after recovery
            self._maybe_analyze()
            
            return record
    
    def analyze_patterns(self) -> List[ErrorPattern]:
        """
        Analyze recorded failures and recoveries to discover patterns.
        
        Returns:
            List of discovered error patterns
        """
        if not self._enabled:
            return []
        
        with self._analysis_lock:
            logger.info("Starting pattern analysis...")
            
            # Group failures by tool and error type
            tool_errors: Dict[str, List[FailureRecord]] = defaultdict(list)
            error_similarities: Dict[str, Set[str]] = defaultdict(set)
            
            with self._lock:
                for failure in self._failures:
                    if failure.resolved:
                        continue
                    tool_errors[failure.tool].append(failure)
                    
                    # Calculate error signature
                    sig = self._compute_error_signature(failure)
                    error_similarities[sig].add(failure.id)
            
            # Find recurring patterns
            new_patterns = []
            
            for sig, failure_ids in error_similarities.items():
                if len(failure_ids) < PROCEDURAL_MIN_FAILURE_COUNT:
                    continue
                
                # Get all failures in this pattern
                pattern_failures = [f for f in self._failures if f.id in failure_ids]
                if not pattern_failures:
                    continue
                
                # Get recoveries for these failures
                pattern_recoveries = [
                    r for r in self._recoveries
                    if r.failure_id in failure_ids
                ]
                
                success_rate = 0.0
                if pattern_recoveries:
                    success_count = sum(1 for r in pattern_recoveries if r.success)
                    success_rate = success_count / len(pattern_recoveries)
                
                # Determine pattern type
                params_sample = pattern_failures[0].params if pattern_failures else {}
                if params_sample and any(pattern_failures):
                    pattern_type = "parameter_related"
                elif pattern_failures[0].context if pattern_failures else "":
                    pattern_type = "context_dependent"
                else:
                    pattern_type = "tool_specific"
                
                # Generate avoidance rules
                avoidance_rules = self._generate_avoidance_rules(
                    pattern_failures, pattern_recoveries
                )
                
                pattern_id = hashlib.md5(sig.encode()).hexdigest()[:12]
                
                pattern = ErrorPattern(
                    id=pattern_id,
                    pattern_type=pattern_type,
                    description=self._describe_pattern(pattern_failures),
                    error_signatures=list(failure_ids),
                    recovery_strategies=list(set(r.recovery_strategy for r in pattern_recoveries)),
                    occurrence_count=len(failure_ids),
                    success_rate=success_rate,
                    last_seen=max(f.timestamp for f in pattern_failures),
                    confidence=min(1.0, len(failure_ids) * 0.2),
                    avoidance_rules=avoidance_rules,
                )
                
                self._patterns[pattern_id] = pattern
                new_patterns.append(pattern)
                
                logger.info(
                    "Discovered pattern: type=%s, occurrences=%d, confidence=%.2f",
                    pattern_type, len(failure_ids), pattern.confidence
                )
            
            if new_patterns:
                self._save_patterns()
            
            self._last_analysis = datetime.now()
            logger.info("Pattern analysis complete: found %d new patterns", len(new_patterns))
            
            return new_patterns
    
    def _maybe_analyze(self) -> None:
        """Trigger analysis if enough new data has accumulated."""
        time_since_analysis = (datetime.now() - self._last_analysis).total_seconds()
        if time_since_analysis > PROCEDURAL_ANALYSIS_INTERVAL_MINUTES * 60:
            self.analyze_patterns()
    
    def _compute_error_signature(self, failure: FailureRecord) -> str:
        """Compute a signature for error clustering."""
        # Normalize error message
        normalized_msg = re.sub(r'\d+', 'N', failure.error_message.lower())
        normalized_msg = re.sub(r'[^\w\s]', '', normalized_msg)
        
        # Create signature based on tool and error pattern
        return f"{failure.tool}:{failure.error_type}:{normalized_msg[:50]}"
    
    def _describe_pattern(self, failures: List[FailureRecord]) -> str:
        """Generate a human-readable description of an error pattern."""
        if not failures:
            return "Unknown pattern"
        
        tool = failures[0].tool
        error_type = failures[0].error_type
        
        descriptions = {
            "file_not_found": f"Tool '{tool}' repeatedly fails with file not found errors",
            "parameter_error": f"Tool '{tool}' has issues with parameter validation",
            "timeout": f"Tool '{tool}' repeatedly times out",
            "permission_denied": f"Tool '{tool}' has permission issues",
        }
        
        return descriptions.get(error_type, f"Tool '{tool}' fails with '{error_type}' errors")
    
    def _generate_avoidance_rules(
        self,
        failures: List[FailureRecord],
        recoveries: List[RecoveryRecord],
    ) -> List[str]:
        """Generate avoidance rules based on failure and recovery analysis."""
        rules = []
        
        if not failures or not recoveries:
            return rules
        
        # Analyze successful recoveries
        successful_recoveries = [r for r in recoveries if r.success]
        
        if successful_recoveries:
            # Extract common successful strategies
            strategies = defaultdict(int)
            for recovery in successful_recoveries:
                strategies[recovery.recovery_strategy] += 1
            
            # Generate rules from most common successful strategies
            for strategy, count in sorted(strategies.items(), key=lambda x: -x[1]):
                if count >= 2:
                    rules.append(
                        f"When {failures[0].tool} fails, try: {strategy}"
                    )
        
        # Add parameter-based rules
        if failures[0].params:
            rules.append(
                f"Verify parameters for {failures[0].tool}: {list(failures[0].params.keys())}"
            )
        
        return rules[:5]  # Limit to 5 rules per pattern
    
    def get_avoidance_rules(self, tool: str = None, context: str = None) -> List[str]:
        """
        Get applicable avoidance rules for a given tool and context.
        
        Args:
            tool: Tool name to get rules for (optional)
            context: Current context (optional)
            
        Returns:
            List of applicable avoidance rules
        """
        rules = []
        
        with self._lock:
            for pattern in self._patterns.values():
                if pattern.confidence < PROCEDURAL_PATTERN_CONFIDENCE_THRESHOLD:
                    continue
                
                if tool and pattern.error_signatures:
                    # Check if any signature matches this tool
                    matching_failures = [
                        f for f in self._failures
                        if f.id in pattern.error_signatures and f.tool == tool
                    ]
                    if matching_failures or not tool:
                        rules.extend(pattern.avoidance_rules)
                elif not tool:
                    rules.extend(pattern.avoidance_rules)
        
        return list(set(rules))[:10]  # Dedupe and limit
    
    def check_for_known_failure(
        self,
        tool: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Check if this tool/params combination has failed before.
        
        Args:
            tool: Tool name
            params: Tool parameters
            
        Returns:
            Dict with warning and alternative approach, or None if no known issues
        """
        with self._lock:
            # Find recent failures for this tool
            recent_failures = [
                f for f in self._failures[-50:]
                if f.tool == tool and not f.resolved
            ]
            
            if not recent_failures:
                return None
            
            # Check for similar parameter issues
            for failure in recent_failures:
                # Check if params are similar (have overlap)
                param_overlap = set(params.keys()) & set(failure.params.keys())
                if param_overlap:
                    # Check if there was a successful recovery
                    for recovery in self._recoveries:
                        if recovery.failure_id == failure.id and recovery.success:
                            return {
                                "warning": f"Similar failure was resolved with: {recovery.recovery_strategy}",
                                "suggested_approach": recovery.corrected_params,
                                "lesson": recovery.lessons_learned[0] if recovery.lessons_learned else "",
                                "pattern_id": self._find_pattern_for_failure(failure.id),
                            }
            
            return None
    
    def _find_pattern_for_failure(self, failure_id: str) -> Optional[str]:
        """Find pattern ID that contains this failure."""
        with self._lock:
            for pid, pattern in self._patterns.items():
                if failure_id in pattern.error_signatures:
                    return pid
        return None
    
    def get_failure_stats(self) -> Dict[str, Any]:
        """Get statistics about failures and recoveries."""
        with self._lock:
            total_failures = len(self._failures)
            resolved_failures = sum(1 for f in self._failures if f.resolved)
            
            # Tool-specific stats
            tool_failures: Dict[str, int] = defaultdict(int)
            for f in self._failures:
                tool_failures[f.tool] += 1
            
            # Recovery stats
            successful_recoveries = sum(1 for r in self._recoveries if r.success)
            
            return {
                "total_failures": total_failures,
                "resolved_failures": resolved_failures,
                "unresolved_failures": total_failures - resolved_failures,
                "total_recoveries": len(self._recoveries),
                "successful_recoveries": successful_recoveries,
                "recovery_success_rate": (
                    successful_recoveries / len(self._recoveries)
                    if self._recoveries else 0.0
                ),
                "patterns_discovered": len(self._patterns),
                "tool_failures": dict(tool_failures),
            }
    
    def get_recent_failures(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get the n most recent failures."""
        with self._lock:
            recent = sorted(
                self._failures,
                key=lambda f: f.timestamp,
                reverse=True
            )[:n]
            return [
                {
                    "id": f.id,
                    "timestamp": f.timestamp,
                    "tool": f.tool,
                    "error_type": f.error_type,
                    "error_message": f.error_message,
                    "resolved": f.resolved,
                }
                for f in recent
            ]
    
    def get_lessons_learned(self) -> List[str]:
        """Get all lessons learned from recoveries."""
        lessons = []
        with self._lock:
            for recovery in self._recoveries:
                if recovery.success and recovery.lessons_learned:
                    lessons.extend(recovery.lessons_learned)
        return list(set(lessons))[:20]  # Dedupe and limit
    
    def clear_old_records(self, days: int = 30) -> int:
        """Clear records older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._lock:
            before = len(self._failures)
            self._failures = [
                f for f in self._failures
                if f.timestamp >= cutoff or not f.resolved
            ]
            self._recoveries = [
                r for r in self._recoveries
                if r.timestamp >= cutoff
            ]
            removed = before - len(self._failures)
            
            if removed > 0:
                self._save_failures()
                self._save_recoveries()
        
        return removed


# Global ProceduralMemory instance
_procedural_instance: Optional[ProceduralMemory] = None


def get_procedural_memory() -> ProceduralMemory:
    """Get the global ProceduralMemory instance."""
    global _procedural_instance
    if _procedural_instance is None:
        _procedural_instance = ProceduralMemory()
    return _procedural_instance


def init_procedural_memory() -> ProceduralMemory:
    """Initialize and return ProceduralMemory instance."""
    return get_procedural_memory()


__all__ = [
    "ProceduralMemory",
    "FailureRecord",
    "RecoveryRecord",
    "ErrorPattern",
    "get_procedural_memory",
    "init_procedural_memory",
]
