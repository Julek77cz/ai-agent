#!/usr/bin/env python3
"""JARVIS V20 - State-of-the-Art AI Agent Launcher"""
import sys
import argparse
import logging
from jarvis_v20 import JarvisV20, get_version

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("JARVIS.V20.LAUNCHER")


def print_banner():
    """Print JARVIS V20 banner."""
    print("""
╔═════════════════════════════════════════════════════════╗
║                                                               ║
║         🤖 JARVIS V20 - STATE-OF-THE-ART AI AGENT         ║
║                                                               ║
║  Features:                                                    ║
║  • Hierarchical Planning with Backtracking                      ║
║  • Metacognitive Self-Reflection                            ║
║  • Multi-Hop Reasoning Chains                               ║
║  • Parallel Tool Execution                                    ║
║  • Smart Memory Pruning                                     ║
║  • Confidence Calibration                                     ║
║  • Explainable AI (XAI)                                   ║
║  • Self-Testing Framework                                    ║
║  • Advanced Code Generation                                   ║
║                                                               ║
╚═══════════════════════════════════════════════════════════╝
""")


def interactive_mode(jarvis: JarvisV20):
    """Run JARVIS in interactive mode."""
    print_banner()
    print("✓ JARVIS V20 ready!")
    print("✓ Type 'help' for commands, 'explain' for reasoning analysis")
    print("✓ Type 'exit' or 'quit' to exit\n")

    while True:
        try:
            query = input("👤 You (Czech): ").strip()
            if not query:
                continue

            # Commands
            if query.lower() in ["exit", "quit"]:
                print("\n👋 Na shledanou!")
                break

            if query.lower() == "help":
                print("\n📋 Dostupné příkazy:")
                print("  help     - Zobrazit tuto nápovědu")
                print("  explain  - Vysvětlit poslední reasoning")
                print("  cap      - Zobrazit možnosti JARVIS V20")
                print("  exit/quit - Ukončit")
                print()
                continue

            if query.lower() == "explain":
                explanation = jarvis.explain_reasoning("Poslední dotaz")
                print("\n" + explanation)
                continue

            if query.lower() == "cap":
                caps = jarvis.get_capabilities()
                print("\n🚀 Možnosti JARVIS V20:")
                for key, value in caps.items():
                    print(f"  • {key}: {value}")
                print()
                continue

            # Process query
            response = jarvis.process(query)
            print(f"\n🤖 JARVIS: {response}\n")

        except KeyboardInterrupt:
            print("\n\n⚠️  Stiskněte 'exit' pro ukončení.")
        except Exception as e:
            logger.error("Error in interactive mode: %s", e)
            print(f"❌ Chyba: {e}")


def one_shot_mode(jarvis: JarvisV20, query: str, stream: bool = True):
    """Run JARVIS in one-shot mode."""
    print(f"\n🤖 JARVIS V20: {query}")
    response = jarvis.process(query, stream_callback=lambda t: print(t, end="", flush=True))
    print()
    return response


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="JARVIS V20 - State-of-the-Art AI Agent",
        epilog="Version: " + get_version()
    )

    parser.add_argument("query", nargs="?", help="One-shot query (Czech)")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {get_version()}")

    args = parser.parse_args()

    # Enable debug if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        for name in ["JARVIS", "JARVIS.V20", "JARVIS.V20.LAUNCHER"]:
            logging.getLogger(name).setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")

    # Initialize JARVIS V20
    try:
        jarvis = JarvisV20(streaming=not args.no_stream)
    except Exception as e:
        logger.error("Initialization failed: %s", e)
        print(f"❌ Chyba při inicializaci: {e}")
        sys.exit(1)

    # Run
    if args.query:
        one_shot_mode(jarvis, args.query, stream=not args.no_stream)
    else:
        interactive_mode(jarvis)


if __name__ == "__main__":
    main()
