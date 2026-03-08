#!/usr/bin/env python3
"""JARVIS V19 - CLI Launcher"""
import sys, argparse, logging
from jarvis_config import ensure_data_dirs
ensure_data_dirs()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("JARVIS")

class Colors:
    RESET = "\033[0m"; RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
    BLUE = "\033[94m"; MAGENTA = "\033[95m"; CYAN = "\033[96m"

def banner():
    print(f"""
{Colors.CYAN}╔═══════════════════════════════════════════════════╗
           🤖 JARVIS V19 - AI Assistant          ║
  • Modular architecture                         ║
  • Czech language support                      ║
  • Local LLM (Ollama)                         ║
  • Semantic memory                            ║
  • Task Manager                              ║
{Colors.RESET}
""")

def interactive(jarvis):
    banner()
    print(f"{Colors.GREEN}Type 'help' or 'exit'{Colors.RESET}\n")
    while True:
        try:
            q = input(f"{Colors.CYAN}👤 Ty: {Colors.RESET}").strip()
            if not q: continue
            if q.lower() in ("exit", "quit"):
                print(f"\n{Colors.GREEN}👋 Na shledanou!{Colors.RESET}")
                break
            if q.lower() == "help":
                print("Commands: exit, clear, tasks, facts")
                continue
            if q.lower() == "tasks":
                print(f"\n{jarvis.tools['manage_tasks']({'action': 'list'})}\n")
                continue
            if q.lower() == "facts":
                facts = jarvis.memory.get_all_facts()
                print(f"\n{Colors.BLUE}🧠 Facts:{Colors.RESET}")
                for f in facts[:10]: print(f"  • {f.content}")
                print()
                continue
            print(f"\n{Colors.GREEN}🤖 JARVIS: {Colors.RESET}", end="", flush=True)
            jarvis.process(q, stream_callback=lambda t: print(t, end="", flush=True))
            print("\n")
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Type 'exit' to quit{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(description="JARVIS V19")
    parser.add_argument("query", nargs="?", help="One-shot query")
    parser.add_argument("--stream/--no-stream", default=True, dest="stream")
    parser.add_argument("--debug", action="store_true", help="Enable maximum debug logging")
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    try:
        from jarvis_core import JarvisV19
        jarvis = JarvisV19(streaming=args.stream)
    except Exception as e:
        print(f"{Colors.RED}Init failed: {e}{Colors.RESET}")
        sys.exit(1)
    
    if args.query:
        print(f"\n{Colors.GREEN}🤖 JARVIS: {Colors.RESET}", end="", flush=True)
        jarvis.process(args.query, stream_callback=lambda t: print(t, end="", flush=True))
        print()
    else:
        interactive(jarvis)

if __name__ == "__main__": main()
