"""JARVIS V20 - Advanced Code Generation

Enhanced code generation with:
- Multi-language support
- Code review
- Testing generation
- Documentation
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("JARVIS.V20.TOOLS.CODE_GENERATOR")


class AdvancedCodeGenerator:
    """
    Advanced code generator with testing and review.
    """

    def __init__(self, bridge: "CzechBridgeClient"):
        self._bridge = bridge
        logger.info("AdvancedCodeGenerator initialized")

    def generate_code(
        self,
        requirements: str,
        language: str = "python",
        include_tests: bool = True,
    ) -> Dict[str, str]:
        """
        Generate code from requirements.

        Args:
            requirements: Code requirements description
            language: Target programming language
            include_tests: Whether to include unit tests

        Returns:
            Dict with 'code', 'tests', 'documentation' keys
        """
        logger.info("Generating %s code for: %s", language, requirements[:50])

        prompt = f"""Requirements: {requirements}
Language: {language}

Generate clean, well-documented code. Return JSON:
{{
  "code": "main implementation",
  "tests": "unit tests" if include_tests else "",
  "documentation": "README/docstring"
}}"""

        try:
            result = self._bridge.call_json(
                "reasoner",
                [{"role": "user", "content": prompt}],
                system_prompt=f"You are an expert {language} developer. Write clean, tested, documented code.",
            )

            if result:
                return {
                    "code": result.get("code", ""),
                    "tests": result.get("tests", ""),
                    "documentation": result.get("documentation", ""),
                }

        except Exception as e:
            logger.debug("Code generation failed: %s", e)

        # Fallback
        return {
            "code": f"# {language} code for: {requirements}",
            "tests": "",
            "documentation": "",
        }

    def review_code(self, code: str, language: str = "python") -> List[str]:
        """
        Review code for issues.

        Args:
            code: Code to review
            language: Programming language

        Returns:
            List of review comments
        """
        prompt = f"""Review this {language} code:

{code[:2000]}

Identify issues, bugs, and improvements. Return JSON:
{{
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["suggestion 1", "suggestion 2"]
}}"""

        try:
            result = self._bridge.call_json(
                "reasoner",
                [{"role": "user", "content": prompt}],
                system_prompt=f"You are an expert {language} code reviewer.",
            )

            if result:
                return (
                    result.get("issues", []) +
                    result.get("suggestions", [])
                )

        except Exception as e:
            logger.debug("Code review failed: %s", e)

        return []


__all__ = ["AdvancedCodeGenerator"]
