"""JARVIS Tools Module"""
import json
import os
import re
import subprocess
import sys
import uuid
import logging
from pathlib import Path
from typing import Dict, Callable, Optional, Any, Tuple
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError

from jarvis_config import TASKS_FILE

logger = logging.getLogger("JARVIS.TOOLS")


class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    USER = CYAN + "👤" + RESET
    JARVIS = GREEN + "🤖" + RESET
    ERROR = RED + "❌" + RESET
    SUCCESS = GREEN + "✅" + RESET
    WARNING = YELLOW + "⚠️" + RESET
    INFO = BLUE + "ℹ️" + RESET


# ============================================================================
# Pydantic BaseModel classes for all tools
# ============================================================================

class GetTimeParams(BaseModel):
    """Parameters for get_time tool - no parameters required."""
    pass


class OpenAppParams(BaseModel):
    """Parameters for open_app tool."""
    app_name: str = Field(..., description="Name of the application to open")
    intent: Optional[str] = Field(default=None, description="Intent description for safety")


class CloseAppParams(BaseModel):
    """Parameters for close_app tool."""
    app_name: str = Field(..., description="Name of the application to close")
    intent: Optional[str] = Field(default=None, description="Intent description for safety")


class RunCommandParams(BaseModel):
    """Parameters for run_command tool."""
    command: str = Field(..., description="Shell command to execute")
    intent: Optional[str] = Field(default=None, description="Intent description for safety")


class WebSearchParams(BaseModel):
    """Parameters for web_search tool."""
    query: str = Field(..., description="Search query string")


class WriteFileParams(BaseModel):
    """Parameters for write_file tool."""
    file_path: str = Field(..., description="Path to the file to write")
    content: str = Field(..., description="Content to write to the file")
    intent: Optional[str] = Field(default=None, description="Intent description for safety")


class ReadFileParams(BaseModel):
    """Parameters for read_file tool."""
    file_path: str = Field(..., description="Path to the file to read")


class RecallParams(BaseModel):
    """Parameters for recall tool."""
    query: str = Field(..., description="Query string to search in memory")


class RememberParams(BaseModel):
    """Parameters for remember tool."""
    content: str = Field(..., description="Content to remember")
    fact_type: str = Field(default="observation", description="Type of fact: preference, fact, event, observation")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0.0-1.0")


class ForgetParams(BaseModel):
    """Parameters for forget tool."""
    fact_id: str = Field(..., description="ID of the fact to forget")


class ListDirParams(BaseModel):
    """Parameters for list_dir tool."""
    path: str = Field(default=".", description="Directory path to list")


class SystemInfoParams(BaseModel):
    """Parameters for system_info tool - no parameters required."""
    pass


class ManageTasksParams(BaseModel):
    """Parameters for manage_tasks tool."""
    action: str = Field(..., description="Action to perform: add, list, remove")
    task_description: Optional[str] = Field(default=None, description="Task description for add action")
    task_id: Optional[str] = Field(default=None, description="Task ID for remove action")


class RunPythonParams(BaseModel):
    """Parameters for run_python tool."""
    code: str = Field(..., description="Python code to execute")
    timeout: int = Field(default=30, ge=1, le=120, description="Execution timeout in seconds (max 120)")


# ============================================================================
# Tool schemas mapping
# ============================================================================

TOOL_SCHEMAS: Dict[str, type[BaseModel]] = {
    "get_time": GetTimeParams,
    "open_app": OpenAppParams,
    "close_app": CloseAppParams,
    "run_command": RunCommandParams,
    "web_search": WebSearchParams,
    "write_file": WriteFileParams,
    "read_file": ReadFileParams,
    "recall": RecallParams,
    "remember": RememberParams,
    "forget": ForgetParams,
    "list_dir": ListDirParams,
    "system_info": SystemInfoParams,
    "manage_tasks": ManageTasksParams,
    "run_python": RunPythonParams,
}


def validate_tool_params(tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Any]:
    """
    Validate tool parameters using Pydantic schemas.

    Args:
        tool_name: Name of the tool to validate
        params: Dictionary of parameters to validate

    Returns:
        Tuple of (success: bool, result: Any)
        - On success: (True, validated_params_dict)
        - On failure: (False, error_message: str)
    """
    if tool_name not in TOOL_SCHEMAS:
        return False, f"Unknown tool: {tool_name}"

    schema_class = TOOL_SCHEMAS[tool_name]

    try:
        validated = schema_class(**params)
        # Convert to dict for use with tool functions
        validated_dict = validated.model_dump(exclude_none=True)
        return True, validated_dict
    except ValidationError as e:
        # Extract clear error messages from validation errors
        errors = []
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            msg = error["msg"]
            errors.append(f"  - {field}: {msg}")
        error_msg = f"Parameter validation failed for '{tool_name}':\n" + "\n".join(errors)
        logger.warning(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error validating '{tool_name}': {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def get_tool_required_params(tool_name: str) -> list:
    """Get list of required parameter names for a tool."""
    required_map = {
        "get_time": [],
        "open_app": ["app_name"],
        "close_app": ["app_name"],
        "run_command": ["command"],
        "web_search": ["query"],
        "write_file": ["file_path", "content"],
        "read_file": ["file_path"],
        "recall": ["query"],
        "remember": ["content"],
        "forget": ["fact_id"],
        "list_dir": [],
        "system_info": [],
        "manage_tasks": ["action"],
        "run_python": ["code"],
    }
    return required_map.get(tool_name, [])


def get_tool_param_examples(tool_name: str) -> Dict[str, Any]:
    """Get example parameters for a tool."""
    examples = {
        "get_time": {},
        "open_app": {"app_name": "firefox", "intent": "Open web browser"},
        "close_app": {"app_name": "firefox", "intent": "Close web browser"},
        "run_command": {"command": "ls -la", "intent": "List files"},
        "web_search": {"query": "weather in Prague"},
        "write_file": {"file_path": "output.txt", "content": "Hello World", "intent": "Save greeting"},
        "read_file": {"file_path": "document.txt"},
        "recall": {"query": "user preferences"},
        "remember": {"content": "User likes coffee", "fact_type": "preference", "confidence": 1.0},
        "forget": {"fact_id": "abc123"},
        "list_dir": {"path": "."},
        "system_info": {},
        "manage_tasks": {"action": "add", "task_description": "Buy milk"},
        "run_python": {"code": "print(2+2)", "timeout": 30},
    }
    return examples.get(tool_name, {})


def create_tool_class(jarvis_instance):
    def _tool_get_time(params):
        now = datetime.now()
        return f"{now.strftime('%H:%M:%S')}\n{now.strftime('%d.%m.%Y')}"

    def _tool_open_app(params):
        app = params.get("app_name", "")
        if not app:
            return f"{Colors.ERROR} Missing app_name"
        try:
            subprocess.Popen([app] if os.name != "nt" else ["start", "", app], shell=os.name == "nt")
            return f"{Colors.SUCCESS} Opened: {app}"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_close_app(params):
        app = params.get("app_name", "")
        if not app:
            return f"{Colors.ERROR} Missing app_name"
        try:
            subprocess.run(
                ["pkill", "-f", app] if os.name != "nt" else ["taskkill", "/F", "/IM", f"{app}.exe"],
                capture_output=True,
            )
            return f"{Colors.SUCCESS} Closed: {app}"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_run_command(params):
        cmd = params.get("command", "")
        if not cmd:
            return f"{Colors.ERROR} Missing command"
        dangerous = ["rm -rf", "del /", "format", "shutdown"]
        if any(d in cmd.lower() for d in dangerous):
            return f"{Colors.ERROR} Blocked"
        try:
            r = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            return r.stdout or r.stderr or f"{Colors.WARNING} No output"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_web_search(params):
        q = params.get("query", "")
        if not q:
            return f"{Colors.ERROR} Missing query"
        try:
            from ddgs import DDGS

            results = DDGS().text(q, max_results=3)
            if not results:
                return f"{Colors.WARNING} No results"
            out = [f"{Colors.INFO} Results: {q}\n"]
            for r in results:
                out.extend([f"• {r.get('title', '')}", f"  {r.get('href', '')}", ""])
            return "\n".join(out)
        except ImportError:
            return f"{Colors.ERROR} ddgs not installed"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_write_file(params):
        fp, content = params.get("file_path", ""), params.get("content", "")
        if not fp:
            return f"{Colors.ERROR} Missing file_path"
        try:
            path = Path(fp).resolve()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"{Colors.SUCCESS} Written {len(content.splitlines())} lines"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_read_file(params):
        fp = params.get("file_path", "")
        if not fp:
            return f"{Colors.ERROR} Missing file_path"
        try:
            path = Path(fp).resolve()
            if not path.exists():
                return f"{Colors.ERROR} Not found"
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(5000)
            return f"{Colors.INFO} {path.name}\n{'-'*40}\n{content}"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_recall(params):
        q = params.get("query", "")
        if not q:
            return f"{Colors.ERROR} Missing query parameter"
        
        # Validate query length
        if len(q.strip()) < 2:
            return f"{Colors.WARNING} Query too short (min 2 characters)"
        
        try:
            # Check if jarvis_instance has memory
            if not hasattr(jarvis_instance, 'memory') or jarvis_instance.memory is None:
                return f"{Colors.ERROR} Memory not initialized"
            
            results = jarvis_instance.memory.recall(q, k=5)
            
            if not results:
                return f"{Colors.WARNING} No memories found for '{q}'. Try a different query or the memory is empty."
            
            out = [f"{Colors.INFO} Recall: '{q}'\n"]
            for r in results:
                content = r.get('content', '')
                score = r.get('score', 0)
                mem_type = r.get('type', '?')
                # Truncate long content for display
                if len(content) > 200:
                    content = content[:200] + "..."
                out.extend(
                    [
                        f"• {content}",
                        f"  Score: {score:.2f} | Type: {mem_type}",
                        "",
                    ]
                )
            return "\n".join(out)
            
        except Exception as e:
            logger.exception("Recall tool failed")
            return f"{Colors.ERROR} Failed to recall: {str(e)}"

    def _tool_remember(params):
        content = params.get("content", "")
        if not content:
            return f"{Colors.ERROR} Missing content parameter"
        
        fact_type = params.get("fact_type", "observation")
        confidence = float(params.get("confidence", 1.0))
        
        # Validate fact_type
        valid_fact_types = ["preference", "fact", "event", "observation"]
        if fact_type not in valid_fact_types:
            logger.warning("Invalid fact_type '%s', defaulting to 'observation'", fact_type)
            fact_type = "observation"
        
        # Validate confidence range
        if not (0.0 <= confidence <= 1.0):
            logger.warning("Confidence %s out of range, clamping to [0, 1]", confidence)
            confidence = max(0.0, min(1.0, confidence))
        
        try:
            # Check if jarvis_instance has memory
            if not hasattr(jarvis_instance, 'memory') or jarvis_instance.memory is None:
                return f"{Colors.ERROR} Memory not initialized"
            
            fact = jarvis_instance.memory.remember(
                content=content,
                fact_type=fact_type,
                source="user",
                confidence=confidence,
            )
            
            if fact and hasattr(fact, 'id'):
                return f"{Colors.SUCCESS} Remembered [{fact.id}]: {content[:100]}{'...' if len(content) > 100 else ''}"
            else:
                return f"{Colors.SUCCESS} Remembered: {content[:100]}{'...' if len(content) > 100 else ''}"
                
        except Exception as e:
            logger.exception("Remember tool failed")
            return f"{Colors.ERROR} Failed to remember: {str(e)}"

    def _tool_forget(params):
        fact_id = params.get("fact_id", "")
        if not fact_id:
            return f"{Colors.ERROR} Missing fact_id parameter. Usage: forget with fact_id='<id>'"
        
        # Validate fact_id format (basic UUID validation)
        if not re.match(r'^[a-f0-9\-]+$', fact_id, re.IGNORECASE):
            return f"{Colors.WARNING} Invalid fact_id format: '{fact_id}'. Expected UUID format."
        
        try:
            # Check if jarvis_instance has memory
            if not hasattr(jarvis_instance, 'memory') or jarvis_instance.memory is None:
                return f"{Colors.ERROR} Memory not initialized"
            
            removed = jarvis_instance.memory.forget(fact_id)
            
            if removed:
                return f"{Colors.SUCCESS} Forgotten [{fact_id}]"
            else:
                return f"{Colors.WARNING} Memory [{fact_id}] not found. It may have already been deleted or the ID is incorrect."
                
        except Exception as e:
            logger.exception("Forget tool failed")
            return f"{Colors.ERROR} Failed to forget: {str(e)}"

    def _tool_list_dir(params):
        p = params.get("path", ".")
        try:
            target = Path(p).resolve()
            if not target.exists():
                return f"{Colors.ERROR} Not found"
            items = [
                f"{'📁' if i.is_dir() else '📄'} {i.name}{'' if i.is_dir() else f' ({i.stat().st_size}B)'}"
                for i in target.iterdir()
            ]
            return f"{Colors.INFO} {target}\n" + "\n".join(items) if items else f"{Colors.WARNING} Empty"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_system_info(params):
        try:
            import psutil

            disk = psutil.disk_usage("/" if os.name != "nt" else "C:\\")
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            return f"{Colors.INFO} System\n{'─'*30}\n🖥️ CPU: {cpu}%\n💾 RAM: {mem.percent}%\n💿 Disk: {disk.percent}%"
        except ImportError:
            return f"{Colors.ERROR} psutil not installed"
        except Exception as e:
            return f"{Colors.ERROR} {e}"

    def _tool_manage_tasks(params):
        action = params.get("action", "list")
        try:
            tasks = json.load(open(TASKS_FILE)) if Path(TASKS_FILE).exists() else []
        except:
            tasks = []

        if action == "add":
            desc = params.get("task_description", "")
            if not desc:
                return f"{Colors.ERROR} Missing task_description"
            task = {
                "id": str(uuid.uuid4())[:8],
                "description": desc,
                "created_at": datetime.now().isoformat(),
                "completed": False,
            }
            tasks.append(task)
            try:
                with open(TASKS_FILE, "w") as f:
                    json.dump(tasks, f, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"{Colors.ERROR} Save failed: {e}"
            return f"{Colors.SUCCESS} Task added [{task['id']}]: {desc}"

        elif action == "list":
            open_tasks = [t for t in tasks if not t.get("completed")]
            if not open_tasks:
                return f"{Colors.WARNING} No open tasks"
            result = [f"{Colors.MAGENTA}📋 Open Tasks:"]
            for t in open_tasks:
                result.append(f"  [{t['id']}] {t['description']}")
            return "\n".join(result)

        elif action == "remove":
            tid = params.get("task_id", "")
            if not tid:
                return f"{Colors.ERROR} Missing task_id"
            original = len(tasks)
            tasks = [t for t in tasks if t.get("id") != tid]
            if len(tasks) < original:
                try:
                    with open(TASKS_FILE, "w") as f:
                        json.dump(tasks, f, ensure_ascii=False, indent=2)
                except:
                    pass
                return f"{Colors.SUCCESS} Task [{tid}] removed"
            return f"{Colors.ERROR} Task [{tid}] not found"

        return f"{Colors.ERROR} Unknown action: {action}"

    def _tool_run_python(params):
        """Execute Python code in a sandboxed subprocess environment."""
        code = params.get("code", "")
        timeout = int(params.get("timeout", 30))

        if not code:
            return f"{Colors.ERROR} Missing code"

        # Security: block dangerous imports and operations
        dangerous_patterns = [
            r"import\s+os",
            r"import\s+sys",
            r"import\s+subprocess",
            r"import\s+socket",
            r"import\s+requests",
            r"import\s+httpx",
            r"import\s+urllib",
            r"import\s+importlib",
            r"__import__",
            r"eval\s*\(",
            r"exec\s*\(",
            r"compile\s*\(",
            r"os\.[a-zA-Z_]+",
            r"sys\.[a-zA-Z_]+",
            r"subprocess\.[a-zA-Z_]+",
            r"socket\.[a-zA-Z_]+",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                logger.warning("Code interpreter blocked dangerous pattern: %s", pattern)
                return f"{Colors.ERROR} Blocked: dangerous imports or operations not allowed (pattern: {pattern})"

        # Create workspace directory if it doesn't exist
        workspace_dir = Path("jarvis_data/workspace")
        try:
            workspace_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"{Colors.ERROR} Failed to create workspace: {e}"

        # Generate unique script filename
        script_id = uuid.uuid4().hex[:12]
        script_path = workspace_dir / f"script_{script_id}.py"

        # Write code to temporary file
        try:
            script_path.write_text(code, encoding="utf-8")
        except Exception as e:
            return f"{Colors.ERROR} Failed to write script: {e}"

        logger.info("Code interpreter: executing script %s with timeout %ds", script_path.name, timeout)

        # Prepare limited environment variables
        limited_env = {
            "PYTHONPATH": "",
            "HOME": str(workspace_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }

        # Execute in isolated subprocess
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=min(timeout, 120),  # Max 120 seconds
                env=limited_env,
                cwd=str(workspace_dir),
            )

            stdout = result.stdout
            stderr = result.stderr

            # Clean up script file
            try:
                script_path.unlink()
            except Exception as e:
                logger.debug("Failed to cleanup script file: %s", e)

            if result.returncode != 0:
                error_msg = stderr[:500] if stderr else f"Exit code: {result.returncode}"
                return f"{Colors.ERROR} Execution error:\n{error_msg}"

            if stderr:
                return f"{Colors.WARNING} Output:\n{stdout}\n{Colors.ERROR} Stderr:\n{stderr}"
            if not stdout:
                return f"{Colors.WARNING} No output"
            return f"{Colors.INFO} Output:\n{stdout}"

        except subprocess.TimeoutExpired:
            # Cleanup on timeout
            try:
                script_path.unlink()
            except Exception:
                pass
            logger.warning("Code interpreter: script %s timed out after %ds", script_path.name, timeout)
            return f"{Colors.ERROR} Execution timeout after {timeout} seconds"
        except Exception as e:
            # Cleanup on error
            try:
                script_path.unlink()
            except Exception:
                pass
            logger.exception("Code interpreter: execution failed")
            return f"{Colors.ERROR} Execution failed: {e}"

    return {
        "get_time": _tool_get_time,
        "open_app": _tool_open_app,
        "close_app": _tool_close_app,
        "run_command": _tool_run_command,
        "web_search": _tool_web_search,
        "write_file": _tool_write_file,
        "read_file": _tool_read_file,
        "recall": _tool_recall,
        "remember": _tool_remember,
        "forget": _tool_forget,
        "list_dir": _tool_list_dir,
        "system_info": _tool_system_info,
        "manage_tasks": _tool_manage_tasks,
        "run_python": _tool_run_python,
    }


TOOLS_SCHEMA = """
RULE: Mark parallel steps with "parallel": true
RULE: For memory queries → recall tool
RULE: For storing facts → remember tool
RULE: For removing memories → forget tool
RULE: For task management → manage_tasks tool
RULE: For Python code execution → run_python tool

Tools:
  get_time
  open_app        (app_name, intent)
  close_app       (app_name, intent)
  run_command     (command, intent)
  web_search      (query)
  write_file      (file_path, content, intent)
  read_file       (file_path)
  recall          (query)
  remember        (content, fact_type, confidence)
    fact_type: "preference" | "fact" | "event" | "observation"
  forget          (fact_id)
  list_dir        (path)
  system_info
  manage_tasks    (action, task_description, task_id)
    action: "add" | "list" | "remove"
  run_python      (code, timeout)
"""

__all__ = [
    "create_tool_class",
    "TOOLS_SCHEMA",
    "Colors",
    "validate_tool_params",
    "TOOL_SCHEMAS",
    "GetTimeParams",
    "OpenAppParams",
    "CloseAppParams",
    "RunCommandParams",
    "WebSearchParams",
    "WriteFileParams",
    "ReadFileParams",
    "RecallParams",
    "RememberParams",
    "ForgetParams",
    "ListDirParams",
    "SystemInfoParams",
    "ManageTasksParams",
    "RunPythonParams",
    "get_tool_required_params",
    "get_tool_param_examples",
]
