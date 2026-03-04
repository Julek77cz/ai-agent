"""Context pre-fetching: proactively loads memory context before reasoning begins"""
import logging
import threading
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from jarvis_memory.memory_manager import CognitiveMemory

logger = logging.getLogger("JARVIS.REASONING.PREFETCH")

# Keywords to likely tools mapping for procedural rule fetching
_KEYWORDS_TO_TOOLS: Dict[str, str] = {
    "vyhledej": "web_search",
    "najdi": "web_search",
    "hledej": "web_search",
    "search": "web_search",
    "soubor": "read_file",
    "file": "read_file",
    "zapiš": "write_file",
    "write": "write_file",
    "kód": "run_python",
    "python": "run_python",
    "code": "run_python",
    "spusť": "run_command",
    "run": "run_command",
    "příkaz": "run_command",
    "command": "run_command",
    "čas": "get_time",
    "time": "get_time",
    "adresář": "list_dir",
    "directory": "list_dir",
    "folder": "list_dir",
    "pamatovat": "remember",
    "zapamatovat": "remember",
    "remember": "remember",
    "pamatuj": "remember",
    "vzpomeň": "recall",
    "recall": "recall",
    "pamatujš": "recall",
}


class ContextPrefetcher:
    """
    Proactively fetches and assembles context from all memory layers
    before the reasoning loop starts, reducing latency during ReAct steps.
    """

    def __init__(self, memory: "CognitiveMemory"):
        self._memory = memory
        self._cache: Dict[str, object] = {}
        self._lock = threading.Lock()
    
    def _extract_tools_from_query(self, query: str) -> List[str]:
        """Extract likely tools from query based on keywords."""
        if not query:
            return []
        
        query_lower = query.lower()
        likely_tools = []
        
        for keyword, tool in _KEYWORDS_TO_TOOLS.items():
            if keyword in query_lower and tool not in likely_tools:
                likely_tools.append(tool)
        
        return likely_tools

    def prefetch(self, query: str, k_semantic: int = 5, k_episodic: int = 3) -> Dict:
        """
        Fetch relevant context for *query* from all memory layers in parallel.

        Returns a dict with keys:
          - ``facts``       : list of str from semantic memory
          - ``episodes``    : list of str from episodic memory
          - ``recent``      : list of ConversationTurn objects (last turns)
          - ``working``     : list of WorkingMemoryItem objects
          - ``summary``     : a single pre-assembled context string
        """
        results: Dict[str, object] = {}
        errors: List[str] = []

        def _fetch_semantic():
            try:
                hits = self._memory.recall(query, k=k_semantic)
                results["facts"] = [h.get("content", "") for h in hits if h.get("content")]
            except Exception as exc:
                errors.append(f"semantic: {exc}")
                results["facts"] = []

        def _fetch_episodic():
            try:
                hits = self._memory.episodic.search_semantic(query, k=k_episodic)
                results["episodes"] = [h.get("text", "") for h in hits if h.get("text")]
            except Exception as exc:
                errors.append(f"episodic: {exc}")
                results["episodes"] = []

        def _fetch_recent():
            try:
                results["recent"] = self._memory.get_recent(5)
            except Exception as exc:
                errors.append(f"recent: {exc}")
                results["recent"] = []

        def _fetch_working():
            try:
                results["working"] = self._memory.working.all()
            except Exception as exc:
                errors.append(f"working: {exc}")
                results["working"] = []
        
        def _fetch_procedural():
            """Fetch procedural memory rules (avoidance rules from past failures)."""
            try:
                # Extract likely tools from query
                likely_tools = self._extract_tools_from_query(query)
                
                # Load avoidance rules for each likely tool
                all_rules = {}
                for tool in likely_tools:
                    if hasattr(self._memory, 'get_avoidance_rules'):
                        rules = self._memory.get_avoidance_rules(tool=tool)
                        if rules:
                            all_rules[tool] = rules
                
                results["procedural_rules"] = all_rules
                logger.debug("Fetched procedural rules for tools %s: %d rules total",
                           likely_tools, sum(len(r) for r in all_rules.values()))
            except Exception as exc:
                errors.append(f"procedural: {exc}")
                results["procedural_rules"] = {}

        threads = [
            threading.Thread(target=_fetch_semantic, daemon=True),
            threading.Thread(target=_fetch_episodic, daemon=True),
            threading.Thread(target=_fetch_recent, daemon=True),
            threading.Thread(target=_fetch_working, daemon=True),
            threading.Thread(target=_fetch_procedural, daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        if errors:
            logger.debug("Prefetch errors: %s", "; ".join(errors))

        facts: List[str] = results.get("facts", [])
        episodes: List[str] = results.get("episodes", [])
        recent = results.get("recent", [])
        working = results.get("working", [])

        parts: List[str] = []
        if facts:
            parts.append("Known facts:\n" + "\n".join(f"• {f}" for f in facts))
        if episodes:
            parts.append("Related episodes:\n" + "\n".join(f"• {e}" for e in episodes))
        if recent:
            recent_lines = [f"{t.role}: {t.content[:120]}" for t in recent]
            parts.append("Recent conversation:\n" + "\n".join(recent_lines))
        if working:
            wm_lines = [f"{item.key}: {str(item.value)[:100]}" for item in working]
            parts.append("Working memory:\n" + "\n".join(wm_lines))
        
        # Add procedural memory rules (lessons learned from past failures)
        procedural_rules = results.get("procedural_rules", {})
        if procedural_rules:
            rules_parts = []
            for tool, rules in procedural_rules.items():
                if rules:
                    # Take up to 3 rules per tool to avoid overwhelming context
                    selected_rules = rules[:3]
                    rules_parts.append(f"For tool '{tool}': " + "; ".join(selected_rules))
            
            if rules_parts:
                parts.append(
                    "Procedural Memory (learned from past failures):\n" +
                    "\n".join(f"• {rp}" for rp in rules_parts)
                )

        summary = "\n\n".join(parts) if parts else ""

        ctx = {
            "facts": facts,
            "episodes": episodes,
            "recent": recent,
            "working": working,
            "procedural_rules": procedural_rules,
            "summary": summary,
        }

        with self._lock:
            self._cache[query] = ctx

        logger.debug(
            "Prefetched context for query=%r: facts=%d, episodes=%d, recent=%d, procedural_rules=%d",
            query[:60],
            len(facts),
            len(episodes),
            len(recent),
            sum(len(r) for r in procedural_rules.values()) if procedural_rules else 0,
        )
        return ctx

    def get_cached(self, query: str) -> Optional[Dict]:
        with self._lock:
            return self._cache.get(query)

    def invalidate(self, query: Optional[str] = None) -> None:
        with self._lock:
            if query is None:
                self._cache.clear()
            else:
                self._cache.pop(query, None)


__all__ = ["ContextPrefetcher"]
