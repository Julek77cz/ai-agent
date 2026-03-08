"""
JARVIS V19 — ULTIMATE VERSION
=============================
Vylepšení:
  - Paralelní kroky (ThreadPoolExecutor)
  - Streaming output
  - Vektorové vyhledávání v paměti
  - Context compression
  - Active learning
  - Tool fallback
  - Confidence scoring
  - Rate limiting
  - Telemetrie (stopky)
  - Incremental Memory (paměť na hotové kroky)
"""
import os
import sys
import json
import logging
import requests
import re
import subprocess
import threading
import signal
import time
import hashlib
import pickle
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict, field
from queue import Queue
from collections import deque

try:
    import json_repair
    _json_loads = json_repair.loads
except ImportError:
    _json_loads = json.loads

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("JARVIS.V19")

# ─────────────────────────────────────────
# KONSTANTY
# ─────────────────────────────────────────
OLLAMA_URL      = "http://localhost:11434/api/chat"
EMBED_URL       = "http://localhost:11434/api/embeddings"
EMBED_MODEL     = "nomic-embed-text"
STATE_FILE      = "C:\\jarvis\\memory\\active_state.json"
UNDO_FILE       = "C:\\jarvis\\memory\\undo_stack.json"
PROMPTS_FILE    = "C:\\jarvis\\orchestrator\\prompts.json"
VECTOR_FILE     = "C:\\jarvis\\memory\\vectors.pkl"
FACTS_FILE      = "C:\\jarvis\\memory\\facts.json"
CONV_FILE       = "C:\\jarvis\\memory\\conversations.json"

MODELS = {
    "czech_gateway": "jobautomation/OpenEuroLLM-Czech:latest",
    "planner":       "qwen2.5:3b-instruct",
    "verifier":      "qwen2.5:3b-instruct",
}

HW_OPTIONS = {
    "num_ctx": 4096, "num_predict": 1024,
    "temperature": 0.5, "num_batch": 256, "num_gpu": 35,
}

DESTRUCTIVE_TOOLS = {"run_command", "write_file"}
SIMPLE_TOOLS = {"get_time", "open_app", "close_app", "read_file", "recall", "list_dir", "system_info"}

_SMALLTALK_PATTERNS = [
    "ahoj", "hello", "hi", "hey", "cau", "zdar",
    "how are you", "what can you do", "who are you",
    "jak se mas", "good morning", "good night",
    "thank you", "thanks", "diky", "dekuji", "super",
]

_MEMORY_PATTERNS = [
    "what do you know about me", "co o me vis", "co vsechno o me",
    "what do you remember", "co si pamatujes", "my preferences",
    "tell me about myself", "co vis o me", "moje preference",
]

MAX_REPLANS = 3
MAX_HISTORY = 30
RATE_LIMIT_SECONDS = 1.0
CONFIDENCE_THRESHOLD = 0.7

# ─────────────────────────────────────────
# EMERGENCY STOP
# ─────────────────────────────────────────
_emergency_stop = threading.Event()

def _handle_sigint(sig, frame):
    _emergency_stop.set()
    print("\n\n🛑 [EMERGENCY STOP] Ctrl+C")
    print("   Napiš 'pokracovat' nebo 'clear'.\n")

signal.signal(signal.SIGINT, _handle_sigint)

def check_stop() -> bool:
    return _emergency_stop.is_set()

# ─────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────
class RateLimiter:
    """Rate limiting pro ochranu proti spamování"""
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests: deque = deque()
        self._lock = threading.Lock()
    
    def is_allowed(self) -> Tuple[bool, int]:
        """Vrátí (povoleno, zbývající_požadavky)"""
        with self._lock:
            now = datetime.now()
            # Odstraň staré požadavky
            while self.requests and now - self.requests[0] > self.window:
                self.requests.popleft()
            
            remaining = self.max_requests - len(self.requests)
            if len(self.requests) >= self.max_requests:
                wait_time = (self.window - (now - self.requests[0])).seconds
                return False, wait_time
            
            self.requests.append(now)
            return True, remaining - 1

# ─────────────────────────────────────────
# VEKTOROVÉ ULOŽIŠTĚ
# ─────────────────────────────────────────
class VectorStore:
    """Sémantické vyhledávání v paměti pomocí embeddingů"""
    
    def __init__(self):
        self.vectors: List[Dict] = []  # [{"id": ..., "text": ..., "embedding": ..., "metadata": ...}]
        self._embed_cache: Dict[str, List[float]] = {}
        self._embed_failures = 0
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        try:
            if Path(VECTOR_FILE).exists():
                with open(VECTOR_FILE, "rb") as f:
                    self.vectors = pickle.load(f)
                logger.info(f"📖 [VECTOR]: Načteno {len(self.vectors)} vektorů")
        except Exception as e:
            logger.warning(f"Vector load error: {e}")
            self.vectors = []
    
    def _save(self):
        try:
            with open(VECTOR_FILE, "wb") as f:
                pickle.dump(self.vectors, f)
        except Exception as e:
            logger.error(f"Vector save error: {e}")
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Získá embedding z Ollama"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Cache check
        if text_hash in self._embed_cache:
            return self._embed_cache[text_hash]
        
        if self._embed_failures >= 5:
            return None
        
        try:
            r = requests.post(EMBED_URL, json={
                "model": EMBED_MODEL,
                "prompt": text[:2000]
            }, timeout=30)
            
            if r.status_code == 200:
                embedding = r.json().get("embedding", [])
                self._embed_cache[text_hash] = embedding
                self._embed_failures = 0
                return embedding
            self._embed_failures += 1
        except Exception as e:
            self._embed_failures += 1
            logger.debug(f"Embedding error: {e}")
        
        return None
    
    def add(self, doc_id: str, text: str, metadata: Dict = None) -> bool:
        """Přidá dokument do vektorového úložiště"""
        with self._lock:
            # Kontrola duplicit
            for v in self.vectors:
                if v["id"] == doc_id:
                    return False
            
            embedding = self._get_embedding(text)
            if embedding is None:
                return False
            
            self.vectors.append({
                "id": doc_id,
                "text": text,
                "embedding": embedding,
                "metadata": metadata or {},
                "created": datetime.now().isoformat()
            })
            self._save()
            return True
    
    def search(self, query: str, k: int = 5, threshold: float = 0.3) -> List[Dict]:
        """Sémantické vyhledávání"""
        if not self.vectors:
            return []
        
        query_emb = self._get_embedding(query)
        if query_emb is None:
            return []
        
        try:
            import numpy as np
            
            similarities = []
            query_vec = np.array(query_emb)
            
            for v in self.vectors:
                vec = np.array(v["embedding"])
                # Cosine similarity
                similarity = np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec))
                if similarity > threshold:
                    similarities.append({
                        **v,
                        "similarity": float(similarity)
                    })
            
            # Seřaď podle podobnosti
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return similarities[:k]
        
        except ImportError:
            logger.warning("numpy nenainstalován, vektorové vyhledávání nedostupné")
            return []
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []
    
    def remove(self, doc_id: str) -> bool:
        """Odstraní dokument"""
        with self._lock:
            for i, v in enumerate(self.vectors):
                if v["id"] == doc_id:
                    self.vectors.pop(i)
                    self._save()
                    return True
        return False
    
    def clear(self):
        """Smaže všechny vektory"""
        with self._lock:
            self.vectors = []
        self._save()

# ─────────────────────────────────────────
# MEMORY V19 S VEKTORY
# ─────────────────────────────────────────
@dataclass
class Fact:
    id: str
    content: str
    fact_type: str
    source: str = "user"
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence: float = 1.0
    embedding_id: str = ""

@dataclass
class ConversationTurn:
    id: str
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    summary: str = ""

class MemoryV19:
    """Rozšířená paměť s vektory a kompresí kontextu"""
    
    MAX_HISTORY = MAX_HISTORY
    
    def __init__(self):
        self.facts: Dict[str, Fact] = {}
        self.conversations: List[ConversationTurn] = []
        self.vector_store = VectorStore()
        self._lock = threading.RLock()
        self._load()
        logger.info(f"🧠 [MEMORY]: {len(self.facts)} faktů, {len(self.conversations)} konverzací")
    
    def _load(self):
        try:
            if Path(FACTS_FILE).exists():
                with open(FACTS_FILE, "r", encoding="utf-8") as f:
                    self.facts = {k: Fact(**v) for k, v in json.load(f).items()}
        except: pass
        
        try:
            if Path(CONV_FILE).exists():
                with open(CONV_FILE, "r", encoding="utf-8") as f:
                    self.conversations = [ConversationTurn(**c) for c in json.load(f)]
        except: pass
    
    def _save_facts(self):
        try:
            with open(FACTS_FILE, "w", encoding="utf-8") as f:
                json.dump({k: asdict(v) for k, v in self.facts.items()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Facts save error: {e}")
    
    def _save_conv(self):
        try:
            with open(CONV_FILE, "w", encoding="utf-8") as f:
                json.dump([asdict(c) for c in self.conversations], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Conv save error: {e}")
    
    def add_fact(self, content: str, fact_type: str = "observation", 
                 source: str = "user", confidence: float = 1.0) -> Fact:
        """Přidá fakt s vektorovým indexováním"""
        fid = hashlib.md5(content.encode()).hexdigest()[:12]
        
        with self._lock:
            if fid in self.facts:
                return self.facts[fid]
            
            fact = Fact(
                id=fid, 
                content=content, 
                fact_type=fact_type,
                source=source,
                confidence=confidence
            )
            self.facts[fid] = fact
            
            # Přidat do vektorového úložiště
            self.vector_store.add(fid, content, {"type": fact_type, "source": source})
            fact.embedding_id = fid
        
        self._save_facts()
        return fact
    
    def get_all_facts(self) -> List[Fact]:
        with self._lock:
            return list(self.facts.values())
    
    def search_facts_vector(self, query: str, k: int = 5) -> List[Dict]:
        """Sémantické vyhledávání ve faktech"""
        results = self.vector_store.search(query, k)
        
        # Obohať o původní fakty
        enriched = []
        for r in results:
            fact = self.facts.get(r["id"])
            if fact:
                enriched.append({
                    "content": fact.content,
                    "type": fact.fact_type,
                    "confidence": fact.confidence,
                    "similarity": r["similarity"]
                })
        
        return enriched
    
    def add_conversation(self, role: str, content: str):
        cid = hashlib.md5(f"{role}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        with self._lock:
            turn = ConversationTurn(id=cid, role=role, content=content)
            self.conversations.append(turn)
            
            # Oříznout historii
            if len(self.conversations) > self.MAX_HISTORY:
                self.conversations = self.conversations[-self.MAX_HISTORY:]
        
        self._save_conv()
    
    def get_history_for_llm(self, compress: bool = False) -> List[Dict]:
        """Vrátí historii, volitelně komprimovanou"""
        with self._lock:
            if not compress or len(self.conversations) <= 10:
                return [{"role": c.role, "content": c.content} for c in self.conversations]
            
            # Komprese: posledních 5 + shrnutí starších
            recent = self.conversations[-5:]
            older = self.conversations[:-5]
            
            # Vrátí s markerem pro kompresi
            return [
                {"role": "system", "content": f"[Komprimovaná historie: {len(older)} starších zpráv]"},
                *[{"role": c.role, "content": c.content} for c in recent]
            ]
    
    def get_context_string(self, limit: int = 5) -> str:
        """Vrátí fakty jako string pro kontext"""
        facts = self.get_all_facts()[:limit]
        if not facts:
            return ""
        return "\n".join(f"- {f.content} (confidence: {f.confidence:.0%})" for f in facts)
    
    def clear_conversations(self):
        with self._lock:
            self.conversations = []
        self._save_conv()
    
    def clear_all(self):
        with self._lock:
            self.facts = {}
            self.conversations = []
        self._save_facts()
        self._save_conv()
        self.vector_store.clear()

# ─────────────────────────────────────────
# PROMPTY
# ─────────────────────────────────────────
DEFAULT_PROMPTS = {
    "planner_sys": (
        "You are a task planner for Windows. Output ONLY valid JSON.\n"
        "RULE 1: Mark steps with 'parallel': true if they can run simultaneously. NEVER use parallel for 'ask_user'!\n"
        "RULE 2: Use absolute paths for files (e.g., C:\\Sandbox\\...).\n"
        "RULE 3: For memory queries → use recall tool.\n"
        "RULE 4: Use ask_user only when critical info is missing.\n"
        "RULE 5: Keep the plan strictly minimal. MAXIMUM 6 steps!"
    ),
    "planner_usr": (
        "--- CONTEXT ---\n"
        "USER FACTS: {context}\n"
        "RECENT: {recent_context}\n"
        "----------------\n\n"
        "TASK: \"{query_en}\"\n"
        "SCHEMA: {schema}\n\n"
        "Output JSON with plan. For parallel steps, add \"parallel\": true.\n"
        "Include \"confidence\": 0-100 for the plan.\n\n"
        "Examples:\n"
        "Task: \"find BTC and ETH prices and save to file\"\n"
        "JSON: {\"plan\": [{\"step\": 1, \"type\": \"tool\", \"tool\": \"web_search\", \"params\": {\"query\": \"BTC price\"}, \"parallel\": true}, {\"step\": 2, \"type\": \"tool\", \"tool\": \"web_search\", \"params\": {\"query\": \"ETH price\"}, \"parallel\": true}, {\"step\": 3, \"type\": \"tool\", \"tool\": \"write_file\", \"params\": {\"file_path\": \"prices.txt\", \"content\": \"\"}}], \"confidence\": 85}\n\n"
        "Now generate JSON for: \"{query_en}\""
    ),
    "verifier_sys": "Verify task execution. Return JSON: {\"success\": true/false, \"confidence\": 0-100, \"reason\": \"...\"}",
    "verifier_usr": "Task: \"{query_en}\"\nLogs:\n{log_str}\nReturn JSON.",
    "confidence_sys": "Rate your confidence in this response. Return JSON: {\"confidence\": 0-100, \"uncertainty\": \"what you're unsure about\", \"need_clarification\": true/false}",
    "active_learning_sys": "Determine if user's statement reveals a preference or fact worth remembering. Return JSON: {\"should_remember\": true/false, \"fact\": \"...\", \"confidence\": 0-100}",
    "active_learning_usr": "User said: \"{text}\"\nDoes this reveal a long-term preference or fact about the user?",
}

class PromptManager:
    def __init__(self):
        Path(PROMPTS_FILE).parent.mkdir(parents=True, exist_ok=True)
        if not Path(PROMPTS_FILE).exists():
            with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_PROMPTS, f, indent=4, ensure_ascii=False)
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            self.prompts = json.load(f)

    def get(self, key: str, **kwargs) -> str:
        text = self.prompts.get(key, "")
        for k, v in kwargs.items():
            text = text.replace("{" + k + "}", str(v))
        return text

pm = PromptManager()

# ─────────────────────────────────────────
# CZECH BRIDGE CLIENT S STREAMING
# ─────────────────────────────────────────
class CzechBridgeClient:
    def __init__(self):
        self.request_count = 0
    
    def call(self, model_key: str, messages: List[Dict],
             timeout: int = 120, system_prompt: str = "") -> str:
        """Normální volání"""
        if check_stop():
            return "[STOP]"
        
        model = MODELS.get(model_key, MODELS["czech_gateway"])
        msgs = ([{"role": "system", "content": system_prompt}] + messages 
                if system_prompt else messages)
        
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": model, "messages": msgs,
                "stream": False, "options": HW_OPTIONS,
            }, timeout=timeout)
            
            if r.status_code == 200:
                self.request_count += 1
                return r.json()["message"]["content"]
            return f"HTTP Error: {r.status_code}"
        except Exception as e:
            return f"Error: {e}"
    
    def call_stream(self, model_key: str, messages: List[Dict],
                    callback: Callable[[str], None],
                    timeout: int = 120, system_prompt: str = "") -> str:
        """Streaming volání - postupný výstup"""
        if check_stop():
            return "[STOP]"
        
        model = MODELS.get(model_key, MODELS["czech_gateway"])
        msgs = ([{"role": "system", "content": system_prompt}] + messages 
                if system_prompt else messages)
        
        full_content = ""
        
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": model, "messages": msgs,
                "stream": True, "options": HW_OPTIONS,
            }, timeout=timeout, stream=True)
            
            for line in r.iter_lines():
                if check_stop():
                    break
                if line:
                    chunk = json.loads(line)
                    if not chunk.get("done"):
                        content = chunk["message"]["content"]
                        full_content += content
                        if callback:
                            callback(content)
            
            self.request_count += 1
            return full_content
        
        except Exception as e:
            return f"Error: {e}"
    
    def call_json(self, model_key: str, messages: List[Dict],
                  system_prompt: str = "") -> Optional[Dict]:
        """JSON volání s vynuceným formátem"""
        if check_stop():
            return None
        
        model = MODELS.get(model_key, MODELS["czech_gateway"])
        strict_opts = {**HW_OPTIONS, "temperature": 0.0}
        msgs = ([{"role": "system", "content": system_prompt}] + messages 
                if system_prompt else messages)
        
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": model, "messages": msgs,
                "stream": False, "options": strict_opts, "format": "json",
            }, timeout=120)
            
            if r.status_code == 200:
                raw = r.json()["message"]["content"]
                self.request_count += 1
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    return _json_loads(match.group())
        except: pass
        
        return None
    
    def evaluate_confidence(self, response: str, context: str) -> Tuple[float, str, bool]:
        """Vyhodnotí confidence odpovědi"""
        prompt = f"Response: {response}\nContext: {context}\nRate confidence."
        
        res = self.call_json("verifier", [{"role": "user", "content": prompt}],
                            system_prompt=pm.get("confidence_sys"))
        
        if res:
            confidence = res.get("confidence", 70) / 100.0
            uncertainty = res.get("uncertainty", "")
            need_clarification = res.get("need_clarification", False)
            return confidence, uncertainty, need_clarification
        
        return 0.7, "", False
    
    def _translate_cz_to_en(self, text: str) -> str:
        if check_stop():
            return text
        
        prompt = f"Translate to English:\n'{text}'\nReturn ONLY translation."
        
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": MODELS["czech_gateway"],
                "messages": [{"role": "user", "content": prompt}],
                "stream": False, "options": HW_OPTIONS,
            }, timeout=40)
            
            if r.status_code == 200:
                return r.json()["message"]["content"].strip()
        except: pass
        
        return text

# ─────────────────────────────────────────
# UNDO MANAGER
# ─────────────────────────────────────────
class UndoManager:
    def __init__(self):
        self.stack: List[Dict] = []
        self._load()
    
    def _load(self):
        try:
            if Path(UNDO_FILE).exists():
                with open(UNDO_FILE, "r", encoding="utf-8") as f:
                    self.stack = json.load(f)
        except: pass
    
    def _save(self):
        try:
            with open(UNDO_FILE, "w", encoding="utf-8") as f:
                json.dump(self.stack, f, ensure_ascii=False, indent=2)
        except: pass
    
    def push(self, action_type: str, revert_params: Dict, description: str):
        self.stack.append({
            "type": action_type, "params": revert_params, "desc": description,
        })
        self._save()
    
    def pop_and_revert(self) -> str:
        if not self.stack:
            return "Není co vrátit zpět."
        
        action = self.stack.pop()
        self._save()
        logger.info(f"⏪ [UNDO]: {action['desc']}")
        
        try:
            if action["type"] == "delete_file":
                p = Path(action["params"]["file_path"])
                if p.exists():
                    p.unlink()
                return f"Revertováno: smazán soubor {p.name}"
            return f"Revertováno: {action['desc']}"
        except Exception as e:
            return f"Chyba UNDO: {e}"

# ─────────────────────────────────────────
# TOOL EXECUTOR S FALLBACK
# ─────────────────────────────────────────
class ToolExecutor:
    """Executor s fallback nástroji"""
    
    HARD_BLOCKED = [
        r"format\s+[a-z]:",
        r"del\s+.*?\\windows",
        r"(rmdir|rd)\s+/s.*?c:\\windows",
    ]
    
    # Fallback nástroje
    TOOL_FALLBACKS = {
        "web_search": ["read_file"],  # Pokud web selže, zkus přečíst lokální soubor
        "open_app": ["run_command"],  # Pokud open_app selže, zkus přes příkaz
    }
    
    def __init__(self, undo: UndoManager, bridge: CzechBridgeClient, memory: MemoryV19):
        self.undo = undo
        self.bridge = bridge
        self.memory = memory
        self.working_memory: List[str] = []
        self.tool_results: Dict[str, str] = {}  # Pro paralelní kroky
        
        self.tools = {
            "get_time":    self._tool_get_time,
            "open_app":    self._tool_open_app,
            "close_app":   self._tool_close_app,
            "run_command": self._tool_run_command,
            "web_search":  self._tool_web_search,
            "write_file":  self._tool_write_file,
            "read_file":   self._tool_read_file,
            "recall":      self._tool_recall,
            "list_dir":    self._tool_list_dir,
            "system_info": self._tool_system_info,
        }
    
    def _self_check(self, action_desc: str, intent: str) -> Dict:
        if "sandbox" in action_desc.lower() or "sandbox" in intent.lower():
            return {"ok": True, "reason": "Sandbox plně povolen."}
        if check_stop():
            return {"ok": False, "reason": "Emergency stop."}
        
        prompt = (
            f"Cíl: '{intent}'\n"
            f"Akce: '{action_desc}'\n"
            f"Je to bezpečné a v souladu? JSON: {{\"ok\": true/false, \"reason\": \"...\"}}"
        )
        
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": MODELS["czech_gateway"],
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {**HW_OPTIONS, "temperature": 0.0},
                "format": "json",
            }, timeout=20)
            
            if r.status_code == 200:
                raw = r.json()["message"]["content"]
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    return _json_loads(match.group())
        except: pass
        
        return {"ok": True, "reason": "check nedostupný"}
    
    def execute(self, tool_name: str, params: Dict, step_id: str = None) -> str:
        """Vykoná nástroj s možným fallbackem"""
        if check_stop():
            return "[STOP]"
        
        if tool_name not in self.tools:
            return f"Neznámý nástroj: {tool_name}"
        
        try:
            result = self.tools[tool_name](params)
            
            # Pokud selhal a má fallback
            if "[STOP]" not in result and "Error" in result and tool_name in self.TOOL_FALLBACKS:
                for fallback in self.TOOL_FALLBACKS[tool_name]:
                    if fallback in self.tools:
                        logger.info(f"🔄 [FALLBACK]: {tool_name} → {fallback}")
                        fallback_result = self.tools[fallback](params)
                        if "Error" not in fallback_result:
                            result = fallback_result
                            break
            
            # Uložit do working memory
            if tool_name in ["web_search", "read_file", "run_command", "recall"]:
                if "[STOP]" not in result:
                    self.working_memory.append(f"[{tool_name}]: {result[:500]}")
            
            # Uložit pro paralelní kroky
            if step_id:
                self.tool_results[step_id] = result
            
            return result
            
        except Exception as e:
            return f"Kritická chyba '{tool_name}': {e}"
    
    def execute_parallel(self, steps: List[Dict]) -> Dict[str, str]:
        """Vykoná více kroků paralelně"""
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for step in steps:
                step_id = f"step_{step.get('step', len(futures))}"
                future = executor.submit(
                    self.execute, 
                    step["tool"], 
                    step.get("params", {}),
                    step_id
                )
                futures[future] = step_id
            
            for future in concurrent.futures.as_completed(futures):
                step_id = futures[future]
                try:
                    results[step_id] = future.result(timeout=60)
                except Exception as e:
                    results[step_id] = f"Error: {e}"
        
        return results
    
    # --- IMPLEMENTACE NÁSTROJŮ ---
    
    def _tool_get_time(self, params: Dict) -> str:
        return datetime.now().strftime("%H:%M:%S")
    
    def _tool_open_app(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        raw_app = params.get("app_name", "")
        apps = raw_app if isinstance(raw_app, list) else [str(raw_app)]
        results = []
        
        for app in apps:
            app = app.strip()
            if not app:
                continue
            
            try:
                subprocess.Popen(f"start {app}", shell=True)
                results.append(f"Otevřeno: {app}")
            except Exception as e:
                results.append(f"Chyba {app}: {e}")
        
        return " | ".join(results) if results else "Chyba: prázdný název."
    
    def _tool_close_app(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        raw_app = params.get("app_name", "")
        apps = raw_app if isinstance(raw_app, list) else [str(raw_app)]
        results = []
        
        for app in apps:
            app = app.strip()
            if not app:
                continue
            
            process = app if app.endswith(".exe") else app + ".exe"
            result = subprocess.run(
                f"taskkill /IM {process} /F",
                shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            
            output = (result.stdout or result.stderr or "").strip()
            if result.returncode == 0 or "SUCCESS" in output.upper():
                results.append(f"Zavřeno: {app}")
            else:
                results.append(f"Nelze zavřít {app}: {output}")
        
        return " | ".join(results) if results else "Chyba: prázdný název."
    
    def _tool_run_command(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        cmd = params.get("command", "").strip()
        intent = params.get("_intent", cmd)
        
        if not cmd:
            return "Prázdný příkaz."
        
        # Hard guard
        if any(re.search(p, cmd, re.IGNORECASE) for p in self.HARD_BLOCKED):
            logger.warning(f"⛔ [HARD-GUARD]: {cmd}")
            return "Zablokováno Hard Guard."
        
        # Self check
        check = self._self_check(cmd, intent)
        if not check.get("ok", True):
            return f"Odmítnuto: {check['reason']}"
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            return (result.stdout or result.stderr or "OK").strip()[:1500]
        except subprocess.TimeoutExpired:
            return "Timeout (30s)."
    
    def _tool_web_search(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        query = params.get("query", "")
        if not query:
            return "Prázdný dotaz."
        
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            
            if not results:
                return "Nic nenalezeno."
            
            raw_data = "\n".join(f"- {r.get('title','')}: {r.get('body','')}" for r in results)
            
            # AI syntéza
            prompt = (
                f"Data pro '{query}':\n{raw_data[:2000]}\n\n"
                "Extrahuj fakta, odpověz česky, stručně."
            )
            return self.bridge.call("czech_gateway", [{"role": "user", "content": prompt}])
        
        except ImportError:
            return "Chybí: pip install ddgs"
        except Exception as e:
            return f"Chyba: {e}"
    
    def _tool_write_file(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        file_path = params.get("file_path", "").strip()
        intent = params.get("_intent", "zápis")
        
        if not file_path:
            return "Chybí cesta."
        
        if file_path.upper() in ["C:\\", "C:/"]:
            return "Zápis do kořene C:\\ zablokován."
        
        # Získat content
        if self.working_memory:
            memory_str = "\n\n".join(self.working_memory)
            prompt = f"Cíl: '{intent}'\nData:\n{memory_str}\n\nVytvoř finální text."
            content = self.bridge.call("czech_gateway", [{"role": "user", "content": prompt}])
            self.working_memory.clear()
        else:
            content = params.get("content", "").strip()
            if not content and intent:
                content = self.bridge.call(
                    "czech_gateway",
                    [{"role": "user", "content": f"Text pro zápis: '{intent}'"}],
                )
        
        # Self check
        check = self._self_check(f"write to {file_path}", intent)
        if not check.get("ok", True):
            return f"Zápis odmítnut: {check['reason']}"
        
        p = Path(file_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            self.undo.push("delete_file", {"file_path": str(p)}, f"Smazat {p.name}")
            return f"Uloženo: {p}"
        except PermissionError:
            return f"Přístup odepřen: '{p}'."
    
    def _tool_read_file(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        file_path = params.get("file_path", "").strip()
        if not file_path:
            return "Chybí cesta."
        
        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Soubor neexistuje: {p}"
        
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read(2000)
        except Exception as e:
            return f"Chyba: {e}"
    
    def _tool_recall(self, params: Dict) -> str:
        """Vektorové vyhledávání v paměti"""
        if check_stop():
            return "[STOP]"
        
        query = params.get("query", "")
        
        # Zkusit vektorové vyhledávání
        vector_results = self.memory.search_facts_vector(query, k=5)
        
        if vector_results:
            results = []
            for r in vector_results:
                results.append(f"• {r['content']} (sim: {r['similarity']:.0%})")
            return "Nalezeno v paměti:\n" + "\n".join(results)
        
        # Fallback na klasické
        facts = self.memory.get_all_facts()
        if not facts:
            return "Zatím o tobě nic nevím."
        
        return "O tobě vím:\n" + "\n".join(f"• {f.content}" for f in facts[:10])
    
    def _tool_list_dir(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        path = params.get("path", ".")
        p = Path(path).expanduser()
        
        if not p.exists():
            return f"Adresář neexistuje: {path}"
        
        if not p.is_dir():
            return f"Není adresář: {path}"
        
        items = list(p.iterdir())[:50]
        result = []
        
        for item in items:
            prefix = "📁" if item.is_dir() else "📄"
            result.append(f"{prefix} {item.name}")
        
        return "\n".join(result) if result else "(prázdný)"
    
    def _tool_system_info(self, params: Dict) -> str:
        if check_stop():
            return "[STOP]"
        
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")
            return f"CPU: {cpu}%\nRAM: {mem.percent}%\nDisk: {disk.percent}%"
        except ImportError:
            return "pip install psutil"

# ─────────────────────────────────────────
# TOOLS SCHEMA
# ─────────────────────────────────────────
TOOLS_SCHEMA = """
RULE: Mark parallel steps with "parallel": true
RULE: Include confidence 0-100
RULE: For memory queries → recall tool

Tools:
  get_time
  open_app        (app_name, _intent)
  close_app       (app_name, _intent)
  run_command     (command, _intent)
  web_search      (query)
  write_file      (file_path, content, _intent)
  read_file       (file_path)
  recall          (query)
  list_dir        (path)
  system_info

Special:
  ask_user        (question)

Example parallel:
{"plan": [
  {"step": 1, "type": "tool", "tool": "web_search", "params": {"query": "BTC"}, "parallel": true},
  {"step": 2, "type": "tool", "tool": "web_search", "params": {"query": "ETH"}, "parallel": true},
  {"step": 3, "type": "tool", "tool": "write_file", "params": {"file_path": "prices.txt", "content": ""}}
], "confidence": 85}
"""

# ─────────────────────────────────────────
# PLANNER
# ─────────────────────────────────────────
class AgentPlanner:
    def __init__(self, bridge: CzechBridgeClient):
        self.bridge = bridge
    
    def create_plan(self, query_en: str, context: str,
                    recent_context: str) -> Tuple[List[Dict], float]:
        """Vrátí (plan, confidence)"""
        if check_stop():
            return [], 0.0
        
        prompt = pm.get("planner_usr",
                        query_en=query_en, context=context,
                        recent_context=recent_context, schema=TOOLS_SCHEMA)
        
        res = self.bridge.call_json(
            "planner",
            [{"role": "user", "content": prompt}],
            system_prompt=pm.get("planner_sys"),
        )
        
        if res:
            plan = res.get("plan", [])
            confidence = res.get("confidence", 70) / 100.0
            
            logger.info(f"🧠 [PLANNER]: {len(plan)} kroků, confidence: {confidence:.0%}")
            logger.info(f"🧠 [PLANNER JSON]:\n{json.dumps(res, indent=2, ensure_ascii=False)}")
            
            return plan, confidence
        
        return [], 0.0

# ─────────────────────────────────────────
# VERIFIER
# ─────────────────────────────────────────
class OutputVerifier:
    def __init__(self, bridge: CzechBridgeClient):
        self.bridge = bridge
    
    def verify(self, query_en: str, logs: List[str],
               skip: bool = False) -> Tuple[bool, str, float]:
        if skip or check_stop():
            return True, "Přeskočeno", 1.0
        
        log_str = "\n".join(logs)
        prompt = pm.get("verifier_usr", query_en=query_en, log_str=log_str)
        
        res = self.bridge.call_json(
            "verifier",
            [{"role": "user", "content": prompt}],
            system_prompt=pm.get("verifier_sys"),
        )
        
        if res:
            success = res.get("success", True)
            reason = res.get("reason", "")
            confidence = res.get("confidence", 100) / 100.0
            logger.info(f"⚖️ [VERIFIER]: {'OK' if success else 'FAIL'} ({confidence:.0%})")
            return success, reason, confidence
        
        return True, "Nelze ověřit", 0.5

# ─────────────────────────────────────────
# ACTIVE LEARNING
# ─────────────────────────────────────────
class ActiveLearning:
    """Detekuje preference a ptá se na nejasnosti"""
    
    def __init__(self, bridge: CzechBridgeClient, memory: MemoryV19):
        self.bridge = bridge
        self.memory = memory
    
    def analyze(self, text: str) -> Optional[Tuple[bool, str]]:
        """Vrátí (should_remember, fact) nebo None"""
        if len(text.split()) < 5:
            return None
        
        prompt = pm.get("active_learning_usr", text=text)
        
        res = self.bridge.call_json(
            "verifier",  # Reuse model
            [{"role": "user", "content": prompt}],
            system_prompt=pm.get("active_learning_sys"),
        )
        
        if res and res.get("should_remember"):
            fact = res.get("fact", "")
            confidence = res.get("confidence", 50) / 100.0
            return True, fact
        
        return None
    
    def should_ask_clarification(self, query: str, confidence: float) -> Optional[str]:
        """Vrátí otázku pokud je třeba upřesnění"""
        if confidence > CONFIDENCE_THRESHOLD:
            return None
        
        # Generuj upřesňující otázku
        prompt = f"Uživatel se ptá: '{query}'\nGeneruj krátkou upřesňující otázku v češtině."
        question = self.bridge.call("czech_gateway", [{"role": "user", "content": prompt}])
        
        return question[:200] if question else None

# ─────────────────────────────────────────
# ORCHESTRÁTOR V19
# ─────────────────────────────────────────
class JarvisV19:
    def __init__(self, streaming: bool = True):
        logger.info("Inicializace JARVIS V19 Ultimate...")
        
        self.streaming = streaming
        self.memory = MemoryV19()
        self.undo = UndoManager()
        self.bridge = CzechBridgeClient()
        self.planner = AgentPlanner(self.bridge)
        self.executor = ToolExecutor(self.undo, self.bridge, self.memory)
        self.verifier = OutputVerifier(self.bridge)
        self.active_learning = ActiveLearning(self.bridge, self.memory)
        self.rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
        
        self.active_state = None
        self.recent_context = ""
        self._load_state()
        
        if not self.active_state:
            self.memory.clear_conversations()
        
        self._print_banner()
    
    def _print_banner(self):
        print("\n╔══════════════════════════════════════════════╗")
        print("║      JARVIS V19 — ULTIMATE                   ║")
        print("║  ✓ Paralelní kroky  ✓ Vektorové vyhledávání  ║")
        print("║  ✓ Streaming        ✓ Active learning        ║")
        print("║  ✓ Tool fallback    ✓ Rate limiting          ║")
        print("║  ✓ Telemetrie       ✓ Paměť na kroky         ║")
        print("╚══════════════════════════════════════════════╝\n")
    
    def _save_state(self):
        try:
            if self.active_state:
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.active_state, f, ensure_ascii=False, indent=2)
            elif Path(STATE_FILE).exists():
                Path(STATE_FILE).unlink()
        except: pass
    
    def _load_state(self):
        try:
            if Path(STATE_FILE).exists():
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    self.active_state = json.load(f)
                logger.info("⚠️ Nalezen rozpracovaný úkol!")
        except: pass
    
    def process(self, query: str, stream_callback: Callable[[str], None] = None) -> str:
        """Hlavní vstupní bod"""
        
        # Rate limiting
        allowed, remaining = self.rate_limiter.is_allowed()
        if not allowed:
            return f"⏳ Rate limit - počkej {remaining}s"
        
        # Systémové příkazy
        query_lower = query.lower().strip()
        
        if query_lower == "pokracovat":
            if _emergency_stop.is_set():
                _emergency_stop.clear()
            if self.active_state:
                return self._execute_state(stream_callback)
            return "Žádný rozpracovaný úkol."
        
        if query_lower in ["undo", "zpet"]:
            return self.undo.pop_and_revert()
        
        if query_lower == "clear":
            self.memory.clear_conversations()
            self.active_state = None
            self.executor.working_memory.clear()
            self.executor.tool_results.clear()
            _emergency_stop.clear()
            self._save_state()
            return "✅ Vymazáno."
        
        if query_lower in ["stats", "statistiky"]:
            return self._get_stats()
        
        self.memory.add_conversation("user", query)
        
        # Re-planning
        if self.active_state and self.active_state.get("status") == "waiting_for_user":
            return self._handle_replan(query, stream_callback)
        
        if check_stop():
            return "🛑 Pozastaveno. Napiš 'pokracovat'."
        
        # Překlad
        logger.info(f"🌐 [BRIDGE]: '{query}'")
        query_en = self.bridge._translate_cz_to_en(query)
        
        # Kontext
        facts_str = self.memory.get_context_string(5)
        
        # Detekce typu dotazu
        is_smalltalk = any(p in query_lower for p in _SMALLTALK_PATTERNS)
        is_memory_query = any(p in query_lower for p in _MEMORY_PATTERNS)
        
        if is_smalltalk:
            logger.info("💬 [CHAT]: Smalltalk")
            plan, confidence = [], 1.0
        elif is_memory_query:
            logger.info("📖 [RECALL]: Memory query")
            plan = [{"step": 1, "type": "tool", "tool": "recall", "params": {"query": query_en}}]
            confidence = 0.9
        else:
            plan, confidence = self.planner.create_plan(query_en, facts_str, self.recent_context)
        
        if check_stop():
            return "🛑 Pozastaveno."
        
        # Active learning - check if need clarification
        if confidence < CONFIDENCE_THRESHOLD and not plan:
            question = self.active_learning.should_ask_clarification(query, confidence)
            if question:
                return f"❓ {question}"
        
        # Proaktivní učení
        learning = self.active_learning.analyze(query)
        if learning:
            should_remember, fact = learning
            if should_remember and fact:
                self.memory.add_fact(fact, "proactive", source="auto")
                logger.info(f"💾 [LEARNING]: '{fact}'")
        
        if not plan:
            # Přímý chat
            history = self.memory.get_history_for_llm(compress=True)
            system = f"Jsi JARVIS.\nFakta:\n{facts_str}"
            
            if self.streaming and stream_callback:
                response = self.bridge.call_stream(
                    "czech_gateway",
                    history + [{"role": "user", "content": query}],
                    stream_callback,
                    system_prompt=system
                )
            else:
                response = self.bridge.call(
                    "czech_gateway",
                    history + [{"role": "user", "content": query}],
                    system_prompt=system
                )
            
            self.memory.add_conversation("assistant", response)
            return response
        
        # Spustit plán
        logger.info(f"⚙️ [EXEC]: {len(plan)} kroků")
        self.executor.working_memory.clear()
        self.executor.tool_results.clear()
        
        self.active_state = {
            "original_cz": query,
            "original_en": query_en,
            "current_step": 1,
            "total_steps": len(plan),
            "steps": plan,
            "execution_log": [],
            "completed_steps": [],
            "status": "running",
            "plan_confidence": confidence,
        }
        self._save_state()
        
        return self._execute_state(stream_callback)
    
    def _execute_state(self, stream_callback: Callable = None) -> str:
        """Vykonání plánu s paralelními kroky a stopkami"""
        
        while self.active_state["current_step"] <= self.active_state["total_steps"]:
            
            if check_stop():
                self.active_state["status"] = "paused"
                self._save_state()
                return "🛑 Pozastaveno. Napiš 'pokracovat'."
            
            current_idx = self.active_state["current_step"] - 1
            steps = self.active_state["steps"]
            
            parallel_steps = []
            for i in range(current_idx, len(steps)):
                step = steps[i]
                is_ask = (step.get("tool") == "ask_user" or step.get("type") == "ask_user")
                
                # Zabrání zařazení ask_user do paralelního bloku, ať už LLM vymyslí cokoliv
                if is_ask:
                    if not parallel_steps:
                        parallel_steps = [step]
                    break
                    
                if step.get("parallel") and i == current_idx + len(parallel_steps):
                    parallel_steps.append(step)
                elif not step.get("parallel") and not parallel_steps:
                    parallel_steps = [step]
                    break
                else:
                    break
            
            if not parallel_steps:
                parallel_steps = [steps[current_idx]]
            
            if len(parallel_steps) > 1:
                logger.info(f"⚡ [PARALLEL]: {len(parallel_steps)} kroků najednou")
                
                t0 = time.perf_counter()
                results = self.executor.execute_parallel(parallel_steps)
                duration = time.perf_counter() - t0
                logger.info(f"⏱️ [TIMER]: Paralelní blok dokončen za {duration:.2f}s")
                
                for step_id, result in results.items():
                    step_num = int(step_id.split("_")[1])
                    self.active_state["execution_log"].append(f"[Step {step_num}] ({duration:.2f}s) → {result[:200]}")
                    if "Error" not in result and "Chyba" not in result and "[STOP]" not in result:
                        if "completed_steps" not in self.active_state: self.active_state["completed_steps"] = []
                        self.active_state["completed_steps"].append({"step": step_num, "tool": "parallel_task"})
                
                self.active_state["current_step"] += len(parallel_steps)
            
            else:
                step = parallel_steps[0]
                stype = step.get("type", "tool")
                tool_name = step.get("tool", "")
                
                logger.info(f"➡️ [KROK {self.active_state['current_step']}/{self.active_state['total_steps']}]: {tool_name or stype}")
                
                if stype == "ask_user" or tool_name == "ask_user":
                    self.active_state["status"] = "waiting_for_user"
                    self._save_state()
                    q_en = step.get("params", {}).get("question", "I need more information.")
                    
                    logger.info(f"🗣️ [PŘEKLAD OTÁZKY]: {q_en}")
                    q_cz = self.bridge.call("czech_gateway", [{"role": "user", "content": f"Přelož do přirozené češtiny (pouze překlad): '{q_en}'"}])
                    
                    out_msg = f"❓ {q_cz.strip()}"
                    if stream_callback:
                        stream_callback(out_msg)
                    return out_msg
                
                elif stype == "tool" or tool_name:
                    params = step.get("params", {})
                    
                    t0 = time.perf_counter()
                    result = self.executor.execute(tool_name, params)
                    duration = time.perf_counter() - t0
                    
                    logger.info(f"✅ [RESULT] ({duration:.2f}s): {result[:100]}")
                    self.active_state["execution_log"].append(f"[{tool_name}] ({duration:.2f}s) → {result}")
                    
                    if "Error" not in result and "Chyba" not in result and "[STOP]" not in result:
                        if "completed_steps" not in self.active_state: self.active_state["completed_steps"] = []
                        self.active_state["completed_steps"].append({"step": self.active_state["current_step"], "tool": tool_name})
                
                self.active_state["current_step"] += 1
            
            self._save_state()
        
        return self._finalize_execution(stream_callback)
    
    def _finalize_execution(self, stream_callback: Callable = None) -> str:
        """Finalizace a vygenerování odpovědi"""
        
        if check_stop():
            return "🛑 Pozastaveno před finalizací."
        
        # Verifikace
        all_tools = {s.get("tool", "") for s in self.active_state["steps"]}
        skip_verif = all_tools.issubset(SIMPLE_TOOLS)
        
        success, reason, conf = self.verifier.verify(
            self.active_state["original_en"],
            self.active_state["execution_log"],
            skip=skip_verif
        )
        
        log_str = "\n".join(self.active_state["execution_log"])
        
        if not success and conf > 0.5:
            prompt = f"Úkol selhal: {self.active_state['original_cz']}\nLogy: {log_str}\nOmluv se a vysvětli."
        else:
            prompt = f"Shrň výsledek: '{self.active_state['original_cz']}'\nLogy:\n{log_str}"
        
        # Streaming nebo normální výstup
        if self.streaming and stream_callback:
            final = self.bridge.call_stream(
                "czech_gateway",
                [{"role": "user", "content": prompt}],
                stream_callback,
                system_prompt="Jsi JARVIS. Odpovídej česky."
            )
        else:
            final = self.bridge.call(
                "czech_gateway",
                [{"role": "user", "content": prompt}],
                system_prompt="Jsi JARVIS. Odpovídej česky."
            )
        
        # Proaktivní učení z interakce
        learning = self.active_learning.analyze(
            f"{self.active_state['original_en']}\n{log_str}"
        )
        if learning:
            _, fact = learning
            if fact:
                self.memory.add_fact(fact, "interaction", source="auto")
        
        # Cleanup
        self.active_state = None
        self.recent_context = ""
        self._save_state()
        self.memory.add_conversation("assistant", final)
        
        logger.info("🏁 [HOTOVO]")
        return final

    def _handle_replan(self, query: str, stream_callback: Callable = None) -> str:
        """Zpracování re-plan s tvrdým vynucením pokračování"""
        replan_count = self.active_state.get("replan_count", 0) + 1
        
        if replan_count > MAX_REPLANS:
            self.active_state = None
            self._save_state()
            return "Příliš mnoho pokusů. Operace byla zrušena."
        
        logger.info(f"🔄 [RE-PLAN #{replan_count}]")
        query_en_ans = self.bridge._translate_cz_to_en(query).lower()
        
        # Obejdeme hloupého Plánovače!
        skip_words = ["no", "skip", "cancel", "don't", "dont", "ne", "přeskoč", "preskoc"]
        
        if any(w in query_en_ans for w in skip_words):
            logger.info("⏩ [ENFORCER]: Uživatel zrušil akci. Přeskakuji ask_user a pokračuji ve stejném plánu!")
            self.active_state["execution_log"].append("[ask_user] → Uživatel odmítl/přeskočil akci.")
            self.active_state["status"] = "running"
            self.active_state["replan_count"] = replan_count
            
            # MAGIE JE ZDE: Upravíme plán natvrdo, vyhodíme z něj aktuální krok, 
            # na kterém stojíme, aby se k němu smyčka v _execute_state už nevracela!
            del self.active_state["steps"][self.active_state["current_step"] - 1]
            self.active_state["total_steps"] -= 1
            
            self._save_state()
            return self._execute_state(stream_callback)
            
        # Uživatel neodmítl, jen dodal info
        logger.info("▶️ [ENFORCER]: Uživatel dodal info. Pokračuji ve stejném plánu!")
        self.active_state["execution_log"].append(f"[ask_user] → Uživatel odpověděl: {query}")
        self.active_state["status"] = "running"
        self.active_state["replan_count"] = replan_count
        
        del self.active_state["steps"][self.active_state["current_step"] - 1]
        self.active_state["total_steps"] -= 1
        
        self._save_state()
        return self._execute_state(stream_callback)

    def _get_stats(self) -> str:
        stats = {
            "facts": len(self.memory.facts),
            "vectors": len(self.memory.vector_store.vectors),
            "conversations": len(self.memory.conversations),
            "llm_requests": self.bridge.request_count,
            "undo_stack": len(self.undo.stack),
            "rate_remaining": self.rate_limiter.is_allowed()[1],
        }
        
        lines = ["📊 JARVIS V19 Statistiky:"]
        for k, v in stats.items():
            lines.append(f"  {k}: {v}")
        
        return "\n".join(lines)

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    jarvis = JarvisV19(streaming=True)
    
    def print_stream(text: str):
        print(text, end="", flush=True)
    
    while True:
        try:
            query = input("\nTy: ").strip()
            if not query:
                continue
            
            if query.lower() == "exit":
                print("👋 Na shledanou!")
                break
            
            print("\nJARVIS: ", end="", flush=True)
            response = jarvis.process(query, stream_callback=print_stream)
            print()  # Newline after streaming
            
        except KeyboardInterrupt:
            print("\n   (Napiš 'pokracovat' nebo 'clear')")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            print(f"\n❌ Chyba: {e}")
