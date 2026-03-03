"""JARVIS Configuration Module"""
from pathlib import Path
from typing import Dict, Any

JARVIS_DATA_DIR = Path.cwd() / "jarvis_data"

STATE_FILE = JARVIS_DATA_DIR / "memory" / "active_state.json"
UNDO_FILE = JARVIS_DATA_DIR / "memory" / "undo_stack.json"
PROMPTS_FILE = JARVIS_DATA_DIR / "orchestrator" / "prompts.json"
VECTOR_FILE = JARVIS_DATA_DIR / "memory" / "vectors.pkl"
FACTS_FILE = JARVIS_DATA_DIR / "memory" / "facts.json"
CONV_FILE = JARVIS_DATA_DIR / "memory" / "conversations.json"
TASKS_FILE = JARVIS_DATA_DIR / "tasks.json"

CHROMA_DIR = JARVIS_DATA_DIR / "chromadb"
KG_FILE = JARVIS_DATA_DIR / "knowledge_graph" / "graph.json"

SEMANTIC_COLLECTION = "jarvis_semantic"
EPISODIC_COLLECTION = "jarvis_episodic"
WORKING_MEMORY_CAPACITY = 7

CONSOLIDATION_IDLE_MINUTES = 60
CONSOLIDATION_HOUR = 2

OLLAMA_URL = "http://localhost:11434/api/chat"
EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

MODELS: Dict[str, str] = {
    "czech_gateway": "jobautomation/OpenEuroLLM-Czech:latest",
    "planner": "qwen2.5:3b-instruct",
    "verifier": "qwen2.5:3b-instruct",
    "reasoner": "qwen2.5:3b-instruct",
}

HW_OPTIONS: Dict[str, Any] = {
    "num_ctx": 4096, "num_predict": 1024,
    "temperature": 0.5, "num_batch": 256, "num_gpu": 35,
}

MAX_REPLANS = 3
MAX_HISTORY = 30
RATE_LIMIT_SECONDS = 1.0
CONFIDENCE_THRESHOLD = 0.7

DESTRUCTIVE_TOOLS = {"run_command", "write_file"}
SIMPLE_TOOLS = {"get_time", "open_app", "close_app", "read_file", "recall", "list_dir", "system_info"}

# ReAct Reasoning Configuration
REACTION_MAX_ITERATIONS = 10
VERIFIER_ENABLED = True
VERIFIER_THRESHOLD = 0.7

SMALLTALK_PATTERNS = ["ahoj", "hello", "hi", "hey", "cau", "zdar", "how are you", "what can you do", "who are you", "jak se mas", "good morning", "good night", "thank you", "thanks", "diky", "dekuji", "super"]

MEMORY_PATTERNS = ["what do you know about me", "co o me vis", "co vsechno o me", "what do you remember", "co si pamatujes", "my preferences", "tell me about myself", "co vis o me", "moje preference"]

def ensure_data_dirs() -> None:
    for subdir in ["memory", "orchestrator", "chromadb", "knowledge_graph"]:
        (JARVIS_DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)

ensure_data_dirs()
