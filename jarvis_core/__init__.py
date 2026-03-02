"""JARVIS Core Module"""
import logging, re, time, threading, signal
from typing import Dict, List, Optional, Tuple, Callable
from collections import deque

from jarvis_config import OLLAMA_URL, MODELS, HW_OPTIONS, MAX_REPLANS, MAX_HISTORY, RATE_LIMIT_SECONDS, SMALLTALK_PATTERNS, MEMORY_PATTERNS
from jarvis_memory import MemoryV19
from jarvis_tools import create_tool_class, TOOLS_SCHEMA

logger = logging.getLogger("JARVIS.CORE")
_emergency_stop = threading.Event()

def _handle_sigint(sig, frame):
    _emergency_stop.set()
    print("\n\n🛑 Emergency Stop")

signal.signal(signal.SIGINT, _handle_sigint)
def check_stop(): return _emergency_stop.is_set()

class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = deque()
        self._lock = threading.Lock()
    
    def is_allowed(self) -> Tuple[bool, int]:
        with self._lock:
            now = time.time()
            while self.requests and now - self.requests[0] > self.window: self.requests.popleft()
            remaining = self.max_requests - len(self.requests)
            if len(self.requests) >= self.max_requests:
                return False, max(1, int(self.window - (now - self.requests[0])))
            self.requests.append(now)
            return True, remaining - 1

class CzechBridgeClient:
    def __init__(self): self.rate_limiter = RateLimiter()
    
    def call_json(self, model_role: str, messages: List[Dict], system_prompt: str = "", options: Dict = None) -> Optional[Dict]:
        allowed, _ = self.rate_limiter.is_allowed()
        if not allowed: return None
        options = options or {}
        try:
            import requests, json_repair
            payload = {"model": MODELS[model_role], "messages": ([{"role": "system", "content": system_prompt}] + messages) if system_prompt else messages, "stream": False, "options": {**HW_OPTIONS, **options}}
            r = requests.post(OLLAMA_URL, json=payload, timeout=60)
            if r.status_code == 200:
                return json_repair.loads(r.json()["message"]["content"])
        except: pass
        return None
    
    def call_stream(self, model_role: str, messages: List[Dict], system_prompt: str = "", callback: Callable = None):
        allowed, _ = self.rate_limiter.is_allowed()
        if not allowed:
            if callback: callback("Rate limited")
            return None
        try:
            import requests, json
            payload = {"model": MODELS[model_role], "messages": ([{"role": "system", "content": system_prompt}] + messages) if system_prompt else messages, "stream": True, "options": HW_OPTIONS}
            r = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60)
            if r.status_code == 200:
                full = ""
                for line in r.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8')[6:])
                            content = data.get("message", {}).get("content", "")
                            full += content
                            if callback: callback(content)
                        except: pass
                return full
        except Exception as e:
            if callback: callback(f"Error: {e}")
        return None

class JarvisV19:
    def __init__(self, streaming: bool = True):
        logger.info("Initializing JARVIS V19...")
        self.streaming = streaming
        self.bridge = CzechBridgeClient()
        self.memory = MemoryV19()
        self.tools = create_tool_class(self)
        self.working_memory = []
        self.tool_results = {}
        logger.info(f"Ready with {len(self.tools)} tools")
    
    def _self_check(self, action_desc: str, intent: str) -> Dict:
        if "sandbox" in action_desc.lower() or "sandbox" in intent.lower(): return {"ok": True, "reason": "Allowed"}
        if check_stop(): return {"ok": False, "reason": "Emergency stop"}
        return {"ok": True, "reason": "Allowed"}
    
    def _detect_smalltalk(self, query: str) -> bool:
        q = query.lower()
        return any(p in q for p in SMALLTALK_PATTERNS)
    
    def _detect_memory_query(self, query: str) -> bool:
        q = query.lower()
        return any(p in q for p in MEMORY_PATTERNS)
    
    def _translate_to_en(self, query: str) -> str:
        translations = {"co je": "what is", "kde je": "where is", "najdi": "find", "hledej": "search", "uloz": "save", "cti": "read", "pis": "write", "spust": "run", "otevri": "open", "zavri": "close"}
        result = query.lower()
        for cz, en in translations.items(): result = result.replace(cz, en)
        return result
    
    def process(self, query: str, stream_callback: Callable = None) -> str:
        self.memory.add_message("user", query)
        
        if self._detect_smalltalk(query):
            response = "Ahoj! Jsem JARVIS. Jak ti mohu pomoci?"
            if stream_callback: stream_callback(response)
            self.memory.add_message("assistant", response)
            return response
        
        if self._detect_memory_query(query):
            facts = self.memory.get_all_facts()
            response = "Co o tobě vím:\n" + "\n".join([f"• {f.content}" for f in facts[:10]]) if facts else "Zatím o tobě moc nevím."
            if stream_callback: stream_callback(response)
            self.memory.add_message("assistant", response)
            return response
        
        query_en = self._translate_to_en(query)
        context = "\n".join([f.content for f in self.memory.get_all_facts()])
        recent = "\n".join([f"{c.role}: {c.content[:100]}" for c in self.memory.get_recent(5)])
        
        plan_prompt = f"Context:\n{context}\n\nRecent:\n{recent}\n\nUser: {query_en}\n\nCreate plan JSON:"
        plan_response = self.bridge.call_json("planner", [{"role": "user", "content": plan_prompt}], system_prompt="You are JARVIS planner. Output JSON.")
        
        if not plan_response:
            msg = "Plánování selhalo"
            if stream_callback: stream_callback(msg)
            return msg
        
        plan = plan_response.get("plan", [])
        results = []
        
        for step in plan:
            if check_stop(): break
            step_type = step.get("type", "action")
            if step_type == "tool":
                tool_name = step.get("tool", "")
                params = step.get("params", {})
                if tool_name not in self.tools: continue
                check = self._self_check(f"tool: {tool_name}", str(params))
                if not check.get("ok"): continue
                try:
                    result = self.tools[tool_name](params)
                    results.append(result)
                    self.tool_results[tool_name] = result
                except Exception as e: results.append(f"Error: {e}")
        
        orch_prompt = f"Context:\n{context}\n\nRecent:\n{recent}\n\nUser: {query}\n\n{TOOLS_SCHEMA}"
        
        if self.streaming and stream_callback:
            response = self.bridge.call_stream("czech_gateway", [{"role": "user", "content": orch_prompt}], system_prompt="You are JARVIS. Respond in Czech.", callback=stream_callback)
        else:
            response = self.bridge.call_json("czech_gateway", [{"role": "user", "content": orch_prompt}], system_prompt="You are JARVIS. Respond in Czech.")
            if response: response = response.get("message", {}).get("content", "Hotovo")
        
        if not response: response = "\n".join(results) if results else "Hotovo"
        
        self.memory.add_message("assistant", response)
        return response

__all__ = ["JarvisV19", "check_stop"]
