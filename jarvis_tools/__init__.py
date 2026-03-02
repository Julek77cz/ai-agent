"""JARVIS Tools Module"""
import json, os, subprocess, uuid, logging
from pathlib import Path
from typing import Dict, Callable
from datetime import datetime
from jarvis_config import TASKS_FILE

logger = logging.getLogger("JARVIS.TOOLS")

class Colors:
    RESET = "\033[0m"; RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
    BLUE = "\033[94m"; MAGENTA = "\033[95m"; CYAN = "\033[96m"; BOLD = "\033[1m"
    USER = CYAN + "👤" + RESET; JARVIS = GREEN + "🤖" + RESET
    ERROR = RED + "❌" + RESET; SUCCESS = GREEN + "✅" + RESET
    WARNING = YELLOW + "⚠️" + RESET; INFO = BLUE + "ℹ️" + RESET

def create_tool_class(jarvis_instance):
    def _tool_get_time(params): now = datetime.now(); return f"{now.strftime('%H:%M:%S')}\n{now.strftime('%d.%m.%Y')}"
    
    def _tool_open_app(params):
        app = params.get("app_name", "")
        if not app: return f"{Colors.ERROR} Missing app_name"
        try:
            subprocess.Popen([app] if os.name != "nt" else ["start", "", app], shell=os.name=="nt")
            return f"{Colors.SUCCESS} Opened: {app}"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_close_app(params):
        app = params.get("app_name", "")
        if not app: return f"{Colors.ERROR} Missing app_name"
        try:
            subprocess.run(["pkill", "-f", app] if os.name != "nt" else ["taskkill", "/F", "/IM", f"{app}.exe"], capture_output=True)
            return f"{Colors.SUCCESS} Closed: {app}"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_run_command(params):
        cmd = params.get("command", "")
        if not cmd: return f"{Colors.ERROR} Missing command"
        dangerous = ["rm -rf", "del /", "format", "shutdown"]
        if any(d in cmd.lower() for d in dangerous): return f"{Colors.ERROR} Blocked"
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return r.stdout or r.stderr or f"{Colors.WARNING} No output"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_web_search(params):
        q = params.get("query", "")
        if not q: return f"{Colors.ERROR} Missing query"
        try:
            from ddgs import DDGS
            results = DDGS().text(q, max_results=3)
            if not results: return f"{Colors.WARNING} No results"
            out = [f"{Colors.SEARCH} Results: {q}\n"]
            for r in results: out.extend([f"• {r.get('title','')}", f"  {r.get('href','')}", ""])
            return "\n".join(out)
        except ImportError: return f"{Colors.ERROR} ddgs not installed"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_write_file(params):
        fp, content = params.get("file_path", ""), params.get("content", "")
        if not fp: return f"{Colors.ERROR} Missing file_path"
        try:
            path = Path(fp).resolve()
            with open(path, "w", encoding="utf-8") as f: f.write(content)
            return f"{Colors.SUCCESS} Written {len(content.splitlines())} lines"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_read_file(params):
        fp = params.get("file_path", "")
        if not fp: return f"{Colors.ERROR} Missing file_path"
        try:
            path = Path(fp).resolve()
            if not path.exists(): return f"{Colors.ERROR} Not found"
            with open(path, "r", encoding="utf-8") as f: content = f.read(5000)
            return f"{Colors.FILE} {path.name}\n{'-'*40}\n{content}"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_recall(params):
        q = params.get("query", "")
        if not q: return f"{Colors.ERROR} Missing query"
        try:
            results = jarvis_instance.memory.search_facts_vector(q, k=5)
            if not results: return f"{Colors.WARNING} No memories"
            out = [f"{Colors.INFO} Recall: {q}\n"]
            for r in results: out.extend([f"• {r.get('content','')}", f"  Score: {r.get('score',0):.2f}", ""])
            return "\n".join(out)
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_list_dir(params):
        p = params.get("path", ".")
        try:
            target = Path(p).resolve()
            if not target.exists(): return f"{Colors.ERROR} Not found"
            items = [f"{'📁' if i.is_dir() else '📄'} {i.name}{'' if i.is_dir() else f' ({i.stat().st_size}B)'}" for i in target.iterdir()]
            return f"{Colors.FILE} {target}\n" + "\n".join(items) if items else f"{Colors.WARNING} Empty"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_system_info(params):
        try:
            import psutil
            disk = psutil.disk_usage("/" if os.name != "nt" else "C:\\")
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            return f"{Colors.INFO} System\n{'─'*30}\n🖥️ CPU: {cpu}%\n💾 RAM: {mem.percent}%\n💿 Disk: {disk.percent}%"
        except ImportError: return f"{Colors.ERROR} psutil not installed"
        except Exception as e: return f"{Colors.ERROR} {e}"
    
    def _tool_manage_tasks(params):
        action = params.get("action", "list")
        try: tasks = json.load(open(TASKS_FILE)) if Path(TASKS_FILE).exists() else []
        except: tasks = []
        
        if action == "add":
            desc = params.get("task_description", "")
            if not desc: return f"{Colors.ERROR} Missing task_description"
            task = {"id": str(uuid.uuid4())[:8], "description": desc, "created_at": datetime.now().isoformat(), "completed": False}
            tasks.append(task)
            try:
                with open(TASKS_FILE, "w") as f: json.dump(tasks, f, ensure_ascii=False, indent=2)
            except Exception as e: return f"{Colors.ERROR} Save failed: {e}"
            return f"{Colors.SUCCESS} Task added [{task['id']}]: {desc}"
        
        elif action == "list":
            open_tasks = [t for t in tasks if not t.get("completed")]
            if not open_tasks: return f"{Colors.WARNING} No open tasks"
            result = [f"{Colors.MAGENTA}📋 Open Tasks:"]
            for t in open_tasks: result.append(f"  [{t['id']}] {t['description']}")
            return "\n".join(result)
        
        elif action == "remove":
            tid = params.get("task_id", "")
            if not tid: return f"{Colors.ERROR} Missing task_id"
            original = len(tasks)
            tasks = [t for t in tasks if t.get("id") != tid]
            if len(tasks) < original:
                try:
                    with open(TASKS_FILE, "w") as f: json.dump(tasks, f, ensure_ascii=False, indent=2)
                except: pass
                return f"{Colors.SUCCESS} Task [{tid}] removed"
            return f"{Colors.ERROR} Task [{tid}] not found"
        
        return f"{Colors.ERROR} Unknown action: {action}"
    
    return {"get_time": _tool_get_time, "open_app": _tool_open_app, "close_app": _tool_close_app,
            "run_command": _tool_run_command, "web_search": _tool_web_search, "write_file": _tool_write_file,
            "read_file": _tool_read_file, "recall": _tool_recall, "list_dir": _tool_list_dir,
            "system_info": _tool_system_info, "manage_tasks": _tool_manage_tasks}

TOOLS_SCHEMA = """
RULE: Mark parallel steps with "parallel": true
RULE: For memory queries → recall tool
RULE: For task management → manage_tasks tool

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
  manage_tasks    (action, task_description, task_id)
    action: "add" | "list" | "remove"
"""

__all__ = ["create_tool_class", "TOOLS_SCHEMA", "Colors"]
