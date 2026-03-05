"""JARVIS Configuration Module"""
from pathlib import Path
from typing import Dict, Any
import sys

JARVIS_DATA_DIR = Path.cwd() / "jarvis_data"

STATE_FILE = JARVIS_DATA_DIR / "memory" / "active_state.json"
UNDO_FILE = JARVIS_DATA_DIR / "memory" / "undo_stack.json"
PROMPTS_FILE = JARVIS_DATA_DIR / "orchestrator" / "prompts.json"
VECTOR_FILE = JARVIS_DATA_DIR / "memory" / "vectors.pkl"
FACTS_FILE = JARVIS_DATA_DIR / "memory" / "facts.json"
CONV_FILE = JARVIS_DATA_DIR / "memory" / "conversations.json"
TASKS_FILE = JARVIS_DATA_DIR / "tasks.json"

# Write-Ahead Log (WAL) persistence
WAL_DIR = JARVIS_DATA_DIR / "wal"
WAL_FILE = WAL_DIR / "journal.jsonl"
WAL_SNAPSHOT_FILE = WAL_DIR / "snapshot.json"

# Procedural memory for learning from mistakes (Immortality)
PROCEDURAL_DIR = JARVIS_DATA_DIR / "procedural"
PROCEDURAL_FAILURES_FILE = PROCEDURAL_DIR / "failures.json"
PROCEDURAL_RECOVERIES_FILE = PROCEDURAL_DIR / "recoveries.json"
PROCEDURAL_PATTERNS_FILE = PROCEDURAL_DIR / "patterns.json"

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

# Default models - can be overridden by user_config.py
MODELS: Dict[str, str] = {
    "czech_gateway": "jobautomation/OpenEuroLLM-Czech:latest",
    "planner": "qwen2.5:3b-instruct",
    "verifier": "qwen2.5:3b-instruct",
    "reasoner": "qwen2.5:3b-instruct",
}

# Load user configuration override if exists
try:
    from jarvis_config.user_config import apply_user_config
    apply_user_config()
except ImportError:
    pass
except Exception as e:
    pass

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

# Circuit Breaker Configuration
CIRCUIT_BREAKER_ENABLED = True
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 3
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60

# Context Summarizer Configuration (Dynamic Context Compression)
CONTEXT_SUMMARIZER_ENABLED = True
CONTEXT_SOFT_LIMIT_TOKENS = 2048  # Start light compression
CONTEXT_MEDIUM_LIMIT_TOKENS = 3072  # Medium compression
CONTEXT_HARD_LIMIT_TOKENS = 4096  # Aggressive compression
CONTEXT_MAX_OBSERVATIONS = 10  # Max observations to keep
CONTEXT_MAX_RECENT_TURNS = 5  # Max recent conversation turns
CONTEXT_ENABLE_LLM_SUMMARIZATION = True  # Use LLM for summarization

# WAL (Write-Ahead Log) Configuration
WAL_ENABLED = True
WAL_FLUSH_INTERVAL_SECONDS = 5  # How often to flush to disk
WAL_MAX_SIZE_MB = 50  # Max WAL size before rotation
WAL_COMPRESSION = True  # Compress old WAL segments

# Procedural Memory Configuration (Immortality - Learning from Mistakes)
PROCEDURAL_MEMORY_ENABLED = True
PROCEDURAL_MIN_FAILURE_COUNT = 2  # Minimum failures before pattern is recognized
PROCEDURAL_PATTERN_CONFIDENCE_THRESHOLD = 0.7
PROCEDURAL_MAX_RECOVERIES_STORED = 100
PROCEDURAL_ANALYSIS_INTERVAL_MINUTES = 30

# Multi-Agent Swarm Architecture Configuration
SWARM_ENABLED = True  # Enable swarm for complex tasks
SWARM_COMPLEXITY_THRESHOLD = 50  # Word count threshold for complexity detection
SWARM_MAX_AGENTS = 4  # Maximum parallel sub-agents
SWARM_TIMEOUT_SECONDS = 120  # Timeout per sub-agent task
SWARM_RETRY_FAILED = False  # Retry failed sub-tasks
SWARM_MAX_RETRIES = 2  # Maximum retry attempts
SWARM_MIN_DEPENDENCIES = 1  # Min dependencies to use swarm

# Agent Roles and Tool Permissions
AGENT_ROLES: Dict[str, Dict[str, Any]] = {
    "researcher": {
        "description": "Information gathering and research",
        "tools": ["web_search", "recall", "read_file", "list_dir", "get_time", "system_info"],
        "max_iterations": 5,
    },
    "developer": {
        "description": "Code and file operations",
        "tools": ["run_command", "write_file", "read_file", "run_python", "list_dir"],
        "max_iterations": 5,
    },
    "analyst": {
        "description": "System analysis and monitoring",
        "tools": ["system_info", "list_dir", "read_file", "get_time", "run_command"],
        "max_iterations": 5,
    },
    "writer": {
        "description": "Documentation and memory storage",
        "tools": ["remember", "write_file", "read_file", "recall", "list_dir"],
        "max_iterations": 5,
    },
}

# Task complexity indicators for automatic swarm detection
SWARM_COMPLEXITY_INDICATORS = [
    "research", "hledej", "najdi", "analyzuj", "compare",
    "porovnej", "vytvoř", "implementuj", "build", "create",
    "multiple", "several", "více", "několik", "parallel", "simultaneously"
]

SMALLTALK_PATTERNS = ["ahoj", "hello", "hi", "hey", "cau", "zdar", "how are you", "what can you do", "who are you", "jak se mas", "good morning", "good night", "thank you", "thanks", "diky", "dekuji", "super"]

MEMORY_PATTERNS = ["what do you know about me", "co o me vis", "co vsechno o me", "what do you remember", "co si pamatujes", "my preferences", "tell me about myself", "co vis o me", "moje preference"]

def ensure_data_dirs() -> None:
    for subdir in ["memory", "orchestrator", "chromadb", "knowledge_graph", "wal", "procedural"]:
        (JARVIS_DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)

ensure_data_dirs()
