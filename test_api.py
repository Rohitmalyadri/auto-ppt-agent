"""
API Connection Test Script
---------------------------
Run this FIRST to verify your OpenRouter API key is working
before running the full agent.

Usage:
    python test_api.py

This script will:
1. Load your .env file
2. Check OPENROUTER_API_KEY is present
3. Make a real API call to OpenRouter
4. Print the model's response
"""

import sys
import os
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"✅  Loaded .env from: {env_path}")
    except ImportError:
        print("⚠️  python-dotenv not installed. Reading .env manually...")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
else:
    print(f"❌  No .env file found at: {env_path}")
    print("    Create one from .env.example and add your OPENROUTER_API_KEY")
    sys.exit(1)

# ── Check key ──────────────────────────────────────────────────────────────────
token = os.getenv("OPENROUTER_API_KEY", "")
if not token or token == "your_openrouter_api_key_here":
    print("\n❌  OPENROUTER_API_KEY is not set or still has the placeholder value.")
    print("    Edit .env and replace 'your_openrouter_api_key_here' with your real key.")
    print("    Get a free key at: https://openrouter.ai/keys")
    sys.exit(1)

print(f"✅  OPENROUTER_API_KEY found: {token[:8]}...")

# ── Make test API call ─────────────────────────────────────────────────────────
print("\n🔄  Testing API connection with a short prompt...")

import requests

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://auto-ppt-agent.local",
    "X-Title": "Auto-PPT Agent",
}

TEST_MODEL = "google/gemma-3-12b-it:free"

payload = {
    "model": TEST_MODEL,
    "messages": [{"role": "user", "content": "Say 'API connection successful' and nothing else."}],
    "max_tokens": 20,
}

try:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )

    print(f"   Status code  : {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        print(f"   Model        : {TEST_MODEL}")
        print(f"   Response     : {text}")
        print("\n✅  SUCCESS — OpenRouter API is working correctly!")
        print("    Your agent will use AI-generated content for slides.\n")

    elif resp.status_code == 401:
        print("\n❌  401 Unauthorized — Invalid API key.")
        print("    Double-check your OPENROUTER_API_KEY in .env\n")
        sys.exit(1)

    elif resp.status_code == 429:
        print("\n⚠️  429 Rate Limited — Key works but you've hit the rate limit.")
        print("    Wait a moment and try again, or use a different model.\n")

    else:
        print(f"\n⚠️  Unexpected status: {resp.status_code}")
        print(f"    Response: {resp.text[:400]}\n")

except requests.exceptions.Timeout:
    print("\n⏱  Request timed out. Check your internet connection.\n")
    sys.exit(1)
except Exception as e:
    print(f"\n❌  Error: {e}\n")
    sys.exit(1)
