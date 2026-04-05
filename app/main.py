"""
Auto-PPT Agent — Main Entry Point
===================================
CLI interface for the Auto-PPT Agent.

Usage:
    python main.py "Create a 5-slide presentation on Artificial Intelligence"
    python main.py  (interactive mode)
    python main.py --topic "Machine Learning" --slides 6

Example prompts:
    "Create a 5-slide presentation on Artificial Intelligence for beginners"
    "Make a 7-slide ppt on Climate Change for high school students"
    "Build a presentation about Python programming"
"""

import sys
import os
import logging
import argparse
from pathlib import Path
from datetime import datetime

# ─── Project root setup ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Load environment variables ───────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # dotenv optional

# ─── Logging Setup ────────────────────────────────────────────────────────────
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure rich-colored logging output."""
    level = logging.DEBUG if verbose else logging.INFO

    # Try using colorlog for styled output
    try:
        import colorlog
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "red,bg_white",
            }
        ))
    except ImportError:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        ))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # File logging
    log_dir = PROJECT_ROOT / "outputs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)


def print_banner():
    """Print the Auto-PPT Agent banner."""
    banner = r"""
 ╔══════════════════════════════════════════════════════════════╗
 ║                                                              ║
 ║      🤖  AUTO-PPT AGENT  |  MCP + Hugging Face             ║
 ║                                                              ║
 ║   Agentic Architecture  •  ReAct Loop  •  MCP Tools        ║
 ╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_result(result: dict):
    """Pretty-print the agent result."""
    if result["status"] == "success":
        print("\n" + "═" * 62)
        print("  ✅  PRESENTATION GENERATED SUCCESSFULLY")
        print("═" * 62)
        print(f"  📁  File     : {result['file_path']}")
        print(f"  📊  Topic    : {result['topic']}")
        print(f"  🎯  Slides   : {result['slides_created']}/{result['total_slides']}")
        print("═" * 62)
        print(f"\n{result['summary']}")
        print()
    else:
        print("\n" + "═" * 62)
        print("  ❌  AGENT ENCOUNTERED AN ERROR")
        print("═" * 62)
        print(f"  Error: {result.get('message', 'Unknown error')}")
        print("═" * 62)


def validate_env():
    """Check environment and warn about missing tokens."""
    hf_token = os.getenv("HF_API_TOKEN", "")
    if not hf_token:
        print("\n  ⚠️  WARNING: HF_API_TOKEN not set in .env")
        print("     → LLM and Image generation will use fallback mode.")
        print("     → Set your token in .env for full Hugging Face AI content.\n")
    else:
        print(f"  ✅  HF_API_TOKEN detected ({hf_token[:8]}...)")


def run_agent(prompt: str, verbose: bool = False):
    """Initialize and run the PPT agent."""
    logger = setup_logging(verbose)
    print_banner()
    validate_env()

    print(f"  🎬  Starting agent for: '{prompt}'\n")

    # Import here to allow logging to be set up first
    from app.agent.ppt_agent import PPTAgent

    agent = PPTAgent()
    result = agent.run(prompt)

    print_result(result)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CLI Interface
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Auto-PPT Agent — Generate PowerPoint presentations with AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "Create a 5-slide presentation on Artificial Intelligence for beginners"
  python main.py "Make a 7-slide ppt on Climate Change for high school students"
  python main.py --topic "Machine Learning" --slides 6
  python main.py  (runs in interactive mode)
        """
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        type=str,
        help="Natural language presentation request",
    )
    parser.add_argument(
        "--topic",
        type=str,
        help="Presentation topic (shorthand when not using full prompt)",
    )
    parser.add_argument(
        "--slides",
        type=int,
        default=5,
        help="Number of slides (default: 5)",
    )
    parser.add_argument(
        "--audience",
        type=str,
        default="",
        help="Target audience (e.g., 'beginners', 'high school students')",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args()

    # Build prompt
    if args.prompt:
        prompt = args.prompt
    elif args.topic:
        parts = [f"Create a {args.slides}-slide presentation on {args.topic}"]
        if args.audience:
            parts.append(f"for {args.audience}")
        prompt = " ".join(parts)
    else:
        # Interactive mode
        print_banner()
        print("  🎤  INTERACTIVE MODE")
        print("  Enter your presentation request below:")
        print("  Example: 'Create a 5-slide presentation on Artificial Intelligence'\n")
        try:
            prompt = input("  > ").strip()
            if not prompt:
                prompt = "Create a 5-slide presentation on Artificial Intelligence for beginners"
                print(f"  Using default: '{prompt}'")
        except (KeyboardInterrupt, EOFError):
            print("\n  Exiting...")
            sys.exit(0)

    run_agent(prompt, verbose=args.verbose)


if __name__ == "__main__":
    main()
