"""JARVIS V20 - Explainable AI Layer

XAI layer for transparent reasoning and decision processes.
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("JARVIS.V20.TOOLS.EXPLAINABILITY")


class ExplainableAILayer:
    """
    XAI (Explainable AI) layer for transparent reasoning.

    Provides explanations of:
    - Decision processes
    - Reasoning chains
    - Confidence factors
    - Alternative paths considered
    """

    def __init__(self, bridge: "CzechBridgeClient", metacognition):
        self._bridge = bridge
        self._metacognition = metacognition
        logger.info("ExplainableAILayer initialized")

    def explain_reasoning(self, query: str) -> str:
        """
        Explain reasoning process for a query.

        Args:
            query: User query (Czech)

        Returns:
            Explanation in Czech
        """
        # Get metacognitive analysis
        if self._metacognition:
            analysis = self._metacognition.analyze_self()
        else:
            analysis = {}

        explanation_parts = []

        # Part 1: Overview
        explanation_parts.append(f"## Vysvětlení mojího uvažování pro: '{query}'")
        explanation_parts.append("")

        # Part 2: Metacognitive insights
        if analysis.get("patterns_detected", 0) > 0:
            explanation_parts.append(f"### 🔍 Zjištěné vzorce: {analysis['patterns_detected']}")
            for pattern in analysis.get("patterns", []):
                explanation_parts.append(f"- {pattern['description']}")
        else:
            explanation_parts.append("### 🔍 Zjištěné vzorce: Žádné")

        # Part 3: Biases
        if analysis.get("biases_detected", 0) > 0:
            explanation_parts.append(f"### ⚖️ Detekované zaujatosti: {analysis['biases_detected']}")
            for bias in analysis.get("biases", []):
                explanation_parts.append(f"- {bias['description']}")
        else:
            explanation_parts.append("### ⚖️ Detekované zaujatosti: Žádné")

        # Part 4: Capabilities
        explanation_parts.append("### 💡 Moje schopnosti:")
        explanation_parts.append("- Hierarchical planning s backtracking")
        explanation_parts.append("- Multi-hop reasoning")
        explanation_parts.append("- Metacognitive self-reflection")
        explanation_parts.append("- Smart memory pruning")
        explanation_parts.append("- Confidence calibration")

        explanation_parts.append("")
        explanation_parts.append("---")
        explanation_parts.append("*Toto vysvětlení je generováno automaticky a slouží pro debugování.*")

        full_explanation = "\n".join(explanation_parts)

        return full_explanation

    def answer_why_question(
        self,
        question: str,
        context: Dict,
    ) -> str:
        """
        Answer 'why did you...' questions.

        Args:
            question: User question (e.g., "Why did you choose X?")
            context: Decision context

        Returns:
            Explanation
        """
        # Extract intent
        if "why did" in question.lower():
            explanation = "Volil jsem toto rozhodnutí na základě:"

            if context.get("confidence"):
                explanation += f"\n- Confidence: {context['confidence']:.1%}"

            if context.get("rationale"):
                explanation += f"\n- Zdůvodnění: {context['rationale']}"

            if context.get("alternatives"):
                explanation += f"\n- Zvažované alternativy: {len(context['alternatives'])}"

            return explanation

        return "Nemohu odpovědět na tuto otázku v kontextu." if not context else "Žádný kontext."


__all__ = ["ExplainableAILayer"]
