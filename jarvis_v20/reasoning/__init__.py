"""JARVIS V20 - Reasoning Module

Enhanced reasoning with:
- Multi-hop ReAct loop
- Metacognitive layer
- Self-reflection
"""
from jarvis_v20.reasoning.react_v2 import ReActLoopV2, ReasoningStep
from jarvis_v20.reasoning.metacognition import MetacognitiveLayer
from jarvis_v20.reasoning.multi_hop import MultiHopReasoner

__all__ = ["ReActLoopV2", "ReasoningStep", "MetacognitiveLayer", "MultiHopReasoner"]
