"""
Web UI Launcher
---------------
Run as: python web.py
Then open: http://localhost:5000
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.web.app import run_web

if __name__ == "__main__":
    run_web()
