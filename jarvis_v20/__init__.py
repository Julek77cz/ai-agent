"""JARVIS V20 - State-of-the-Art AI Agent

Complete rewrite with:
- Hierarchical Planning Engine
- Metacognitive Layer
- Advanced Code Generation
- Self-Testing Framework
- Explainable AI
- Streaming Result Aggregation
- Smart Memory Pruning
- Multi-Hop Reasoning
- Confidence Calibration
"""
import logging
from typing import Optional, Callable

from jarvis_v20.orchestrator import JarvisV20

logger = logging.getLogger("JARVIS.V20")


__all__ = ["JarvisV20"]


def get_version() -> str:
    """Get JARVIS V20 version."""
    return "20.0.0"


def initialize() -> JarvisV20:
    """
    Initialize JARVIS V20 with all advanced features.

    Returns:
        Initialized JarvisV20 instance
    """
    logger.info("Initializing JARVIS V20 - State-of-the-Art AI Agent")
    return JarvisV20()
