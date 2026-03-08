#!/usr/bin/env python3
"""JARVIS Universal Launcher - Supports V19 and V20"""
import sys
import argparse
import logging
import os
import subprocess

# Version configuration
JARVIS_V20_DIR = "jarvis_v20"
JARVIS_V19_DIR = "jarvis_v19"
JARVIS_VERSION = "20"  # Default to V20

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("JARVIS.UNIVERSAL_LAUNCHER")


def print_banner(version: str):
    """Print banner for selected version."""
    if version == "20":
        title = "JARVIS V20 - State-of-the-Art AI Agent"
        features = [
            "• Hierarchical Planning with Backtracking",
            "• Metacognitive Self-Reflection",
            "• Multi-Hop Reasoning Chains",
            "• Parallel Tool Execution",
            "• Smart Memory Pruning",
            "• Confidence Calibration",
            "• Explainable AI (XAI)",
            "• Self-Testing Framework",
            "• Advanced Code Generation",
        ]
    else:
        title = "JARVIS V19 - AI Assistant"
        features = [
            "• Modular architecture",
            "• Czech language support",
            "• Local LLM (Ollama)",
            "• Semantic memory",
            "• Task Manager",
        ]
    
    print("""
╔═══════════════════════════════════════════════════╗
║                                                               ║
║         {}         ║
║                                                               ║
║  {}          ║
╚═══════════════════════════════════════════════════╝
""".format(title, "\n║  ".join(features)))


def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def start_ollama():
    """Start Ollama service in background."""
    try:
        logger.info("Starting Ollama service...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        import time
        time.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Failed to start Ollama: {e}")
        return False


def run_version(version: str, args) -> int:
    """Run specific version of JARVIS."""
    logger.info(f"Starting JARVIS {version}...")
    
    # Import correct module based on version
    if version == "20":
        try:
            from jarvis_v20 import JarvisV20
            JarvisClass = JarvisV20
            logger.info("Loaded JARVIS V20 module")
        except ImportError as e:
            logger.error(f"Failed to import V20: {e}")
            print(f"❌ Chyba při načítání V20: {e}")
            return 1
    else:
        try:
            # For V19, we need to adjust the path
            sys.path.insert(0, os.path.join(os.getcwd(), JARVIS_V19_DIR))
            import importlib.util
            
            # Load jarvis_v19.py module
            spec = importlib.util.spec_from_file_location(
                "jarvis_v19_module",
                os.path.join(os.getcwd(), JARVIS_V19_DIR, "jarvis_v19.py")
            )
            jarvis_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jarvis_module)
            
            if hasattr(jarvis_module, 'JarvisV19'):
                JarvisClass = jarvis_module.JarvisV19
            else:
                # Try alternative class name
                JarvisClass = jarvis_module.Jarvis
            logger.info("Loaded JARVIS V19 module")
        except ImportError as e:
            logger.error(f"Failed to import V19: {e}")
            print(f"❌ Chyba při načítání V19: {e}")
            return 1
    
    # Initialize
    try:
        jarvis = JarvisClass(streaming=not args.no_stream)
        
        # Process query or interactive
        if args.query:
            print(f"\n🤖 JARVIS {version}: {args.query}")
            response = jarvis.process(args.query, stream_callback=lambda t: print(t, end="", flush=True))
            print()
        else:
            print_banner(version)
            print(f"✓ JARVIS {version} ready!")
            print("✓ Type 'help' for commands, 'exit' or 'quit' to exit\n")
            
            while True:
                try:
                    query = input("👤 You (Czech): ").strip()
                    if not query:
                        continue
                    
                    if query.lower() in ("exit", "quit"):
                        print("\n👋 Na shledanou!")
                        break
                    
                    if query.lower() == "help":
                        print("\n📋 Dostupné příkazy:")
                        print("  help     - Zobrazit tuto nápovědu")
                        print("  exit/quit - Ukončit")
                        print()
                        continue
                    
                    # Process query
                    response = jarvis.process(query)
                    print(f"\n🤖 JARVIS {version}: {response}")
                
                except KeyboardInterrupt:
                    print("\n⚠️ Stiskněte 'exit' pro ukončení.")
                except Exception as e:
                    print(f"❌ Chyba: {e}")
            
            return 0
        
    except Exception as e:
        logger.error(f"JARVIS {version} initialization failed: {e}")
        print(f"❌ Chyba při inicializaci: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="JARVIS Universal Launcher - Switch between V19 and V20",
        epilog=f"Default version: V20 (State-of-the-Art)\n\n"
                f"Přepněte verzi pomocí:\n"
                f"  export JARVIS_VERSION=19 (pro V19)\n"
                f"  export JARVIS_VERSION=20 (pro V20 - výchozí)"
    )
    
    parser.add_argument("query", nargs="?", help="One-shot query (Czech)")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--v19", action="store_true", help="Force use V19 version")
    parser.add_argument("--v20", action="store_true", help="Force use V20 version (default)")
    parser.add_argument("--version", "-v", action="version", version="JARVIS Universal Launcher 1.0.0")
    
    args = parser.parse_args()
    
    # Enable debug if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        for name in ["JARVIS", "JARVIS.UNIVERSAL_LAUNCHER"]:
            logging.getLogger(name).setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")
    
    # Determine version
    if args.v19:
        version = "19"
    elif args.v20:
        version = "20"
    else:
        # Check environment variable
        version_env = os.getenv("JARVIS_VERSION", JARVIS_VERSION)
        if version_env in ["19", "20"]:
            version = version_env
        else:
            version = "20"  # Default
    
    logger.info(f"Selected version: {version}")
    
    # Check Ollama
    if not check_ollama():
        logger.warning("Ollama is not running!")
        if not start_ollama():
            logger.error("Could not start Ollama automatically")
            print("[!] Warning: Ollama may not be running")
    
    # Run selected version
    exit_code = run_version(version, args)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
