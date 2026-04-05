"""
Top-level launcher — delegates to app/main.py
Run as: python main.py "Create a 5-slide presentation on AI"
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Run the CLI
from app.main import main

if __name__ == "__main__":
    main()
