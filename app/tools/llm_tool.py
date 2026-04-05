"""
MCP Tool: LLM / Text Generation
---------------------------------
Uses OpenRouter API (OpenAI-compatible) for text generation.
Falls back to rule-based content if API is unavailable.

OpenRouter supports 100+ models — free and paid.
Good free models: mistralai/mistral-7b-instruct:free, google/gemma-3-12b-it:free
"""

import os
import re
import json
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any

# ─── Load .env at import time (before any os.getenv calls) ────────────────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(_env_path, override=False)   # override=False keeps shell exports intact
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ─── OpenRouter Configuration ──────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Models in priority order (free tier first, then paid fallbacks)
OPENROUTER_MODELS = [
    "google/gemma-3-12b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct",       # Paid fallback
]
DEFAULT_MODEL = OPENROUTER_MODELS[0]


def _get_openrouter_token() -> str:
    """Read OpenRouter API key from environment."""
    token = os.getenv("OPENROUTER_API_KEY", "")
    if not token:
        logger.warning("[LLM Tool] OPENROUTER_API_KEY not set. Using fallback content generation.")
    return token


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool: generate_text
# ══════════════════════════════════════════════════════════════════════════════
def generate_text(prompt: str, max_tokens: int = 500) -> str:
    """
    MCP Tool — Generate text using OpenRouter API (OpenAI-compatible).

    Args:
        prompt: Instruction prompt for the model.
        max_tokens: Maximum tokens to generate.

    Returns:
        Generated text string.
    """
    token = _get_openrouter_token()

    if not token:
        logger.warning(
            "[LLM Tool] ⚠️  OPENROUTER_API_KEY not found in environment. "
            "Using rule-based fallback content. Set OPENROUTER_API_KEY in .env to enable AI generation."
        )
        return _fallback_generate(prompt)

    logger.info(f"[LLM Tool] ✅ API key detected ({token[:8]}...) — calling OpenRouter")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://auto-ppt-agent.local",
        "X-Title": "Auto-PPT Agent",
    }

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "top_p": 0.9,
    }

    for model in OPENROUTER_MODELS:
        try:
            logger.info(f"[LLM Tool] → Calling model: {model}")
            payload["model"] = model
            resp = requests.post(
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
                timeout=90,
            )

            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    logger.warning(f"[LLM Tool] {model} returned empty choices.")
                    continue
                text = choices[0].get("message", {}).get("content", "").strip()
                if text:
                    logger.info(f"[LLM Tool] ✅ Response received from {model} ({len(text)} chars)")
                    return text
                else:
                    logger.warning(f"[LLM Tool] {model} returned empty content.")
                    continue

            elif resp.status_code == 429:
                logger.warning(f"[LLM Tool] ⚠️  Rate limit on {model}. Trying next...")
                continue
            elif resp.status_code == 402:
                logger.warning(f"[LLM Tool] ⚠️  {model} requires credits. Trying next free model...")
                continue
            elif resp.status_code == 401:
                logger.error(f"[LLM Tool] ❌ Invalid API key (401). Check OPENROUTER_API_KEY in .env")
                break   # No point trying other models with a bad key
            else:
                err_body = resp.text[:300]
                logger.warning(f"[LLM Tool] {model} returned {resp.status_code}: {err_body}")
                continue

        except requests.exceptions.Timeout:
            logger.warning(f"[LLM Tool] ⏱ Timeout on {model}. Trying next...")
            continue
        except (KeyError, IndexError) as e:
            logger.warning(f"[LLM Tool] ⚠️ Unexpected response shape from {model}: {e}")
            continue
        except Exception as e:
            logger.error(f"[LLM Tool] Error with {model}: {e}")
            continue

    logger.warning("[LLM Tool] ⚠️  All OpenRouter models failed. Using rule-based fallback.")
    return _fallback_generate(prompt)


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool: generate_slide_plan
# ══════════════════════════════════════════════════════════════════════════════
def generate_slide_plan(user_prompt: str, num_slides: int = 5) -> List[Dict[str, Any]]:
    """
    MCP Tool — Generate a structured slide plan (titles + type) from user intent.

    This is the PLANNING STEP — called before any slide creation.

    Args:
        user_prompt: Raw user instruction.
        num_slides: Desired number of slides.

    Returns:
        List of slide plan dicts: [{title, type, is_image_slide}, ...]
    """
    logger.info(f"[LLM Tool] Generating slide plan for: '{user_prompt}'")

    planning_prompt = f"""You are a professional presentation designer AI.

The user wants: "{user_prompt}"

Create a structured plan for exactly {num_slides} slides.
Return ONLY a valid JSON array. No explanation, no markdown, just raw JSON.

Format:
[
  {{"slide_number": 1, "title": "Introduction", "type": "title_slide", "is_image_slide": false}},
  {{"slide_number": 2, "title": "What is X", "type": "content", "is_image_slide": false}},
  {{"slide_number": 3, "title": "Visual Overview", "type": "image", "is_image_slide": true}},
  {{"slide_number": 4, "title": "Key Points", "type": "content", "is_image_slide": false}},
  {{"slide_number": 5, "title": "Conclusion", "type": "content", "is_image_slide": false}}
]

Rules:
- Slide 1 must always be type "title_slide"
- Last slide must always be "Conclusion" or "Summary" type "content"
- At most 1 slide can be is_image_slide: true
- Titles should be concise (3-7 words)
- Return EXACTLY {num_slides} slides"""

    raw = generate_text(planning_prompt, max_tokens=600)
    plan = _parse_slide_plan(raw, num_slides, user_prompt)

    logger.info(f"[LLM Tool] Slide plan generated: {len(plan)} slides")
    for s in plan:
        logger.info(f"  Slide {s['slide_number']}: {s['title']} [{s['type']}]")

    return plan


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool: generate_slide_bullets
# ══════════════════════════════════════════════════════════════════════════════
def generate_slide_bullets(topic: str, slide_title: str, context: str = "") -> List[str]:
    """
    MCP Tool — Generate 4 bullet points for a given slide title.

    Args:
        topic: Overall presentation topic.
        slide_title: The specific slide title.
        context: Optional additional context from user prompt.

    Returns:
        List of 3–5 bullet point strings.
    """
    logger.info(f"[LLM Tool] Generating bullets for slide: '{slide_title}'")

    bullet_prompt = f"""You are a content writer for presentations.

Topic: "{topic}"
Slide Title: "{slide_title}"
{f'Context: {context}' if context else ''}

Write exactly 4 concise bullet points for this slide.
Each bullet must:
- Be 8–15 words long
- Be factual and informative
- NOT start with bullet symbols or numbers
- Be on a separate line

Return ONLY the 4 bullet points, one per line. No intro text, no numbering."""

    raw = generate_text(bullet_prompt, max_tokens=300)
    bullets = _parse_bullets(raw, slide_title, topic)

    logger.info(f"[LLM Tool] Generated {len(bullets)} bullets for '{slide_title}'")
    return bullets


# ══════════════════════════════════════════════════════════════════════════════
# Parsing Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences that LLMs often wrap JSON in."""
    # Strip ```json ... ``` or ``` ... ``` blocks
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text.strip())
    return text.strip()


def _parse_slide_plan(raw: str, num_slides: int, user_prompt: str) -> List[Dict[str, Any]]:
    """Parse JSON slide plan from LLM output, with fallback."""
    if not raw or raw == "FALLBACK":
        logger.info("[LLM Tool] No API content — using fallback slide plan.")
        return _fallback_slide_plan(user_prompt, num_slides)

    logger.debug(f"[LLM Tool] Parsing slide plan from raw ({len(raw)} chars): {raw[:150]}...")

    # Strategy 1: Strip markdown fences then parse full text as JSON
    try:
        cleaned = _strip_markdown_fences(raw)
        plan = json.loads(cleaned)
        if isinstance(plan, list) and len(plan) >= 2:
            logger.info(f"[LLM Tool] ✅ Slide plan parsed (strategy 1 — direct JSON): {len(plan)} slides")
            return _normalise_plan(plan, num_slides)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Find a JSON array anywhere in the text
    try:
        match = re.search(r'\[\s*\{.*?\}\s*\]', raw, re.DOTALL)
        if match:
            plan = json.loads(match.group())
            if isinstance(plan, list) and len(plan) >= 2:
                logger.info(f"[LLM Tool] ✅ Slide plan parsed (strategy 2 — regex extract): {len(plan)} slides")
                return _normalise_plan(plan, num_slides)
    except (json.JSONDecodeError, AttributeError):
        pass

    logger.warning("[LLM Tool] ⚠️  Could not parse JSON from LLM response. Using fallback plan.")
    logger.debug(f"[LLM Tool] Raw response was: {raw[:500]}")
    return _fallback_slide_plan(user_prompt, num_slides)


def _normalise_plan(plan: list, num_slides: int) -> List[Dict[str, Any]]:
    """Ensure all required fields are present in every slide dict."""
    for i, slide in enumerate(plan):
        slide.setdefault("slide_number", i + 1)
        slide.setdefault("type", "content")
        slide.setdefault("is_image_slide", False)
    return plan[:num_slides]


def _parse_bullets(raw: str, slide_title: str, topic: str) -> List[str]:
    """Parse bullet list from LLM output, with fallback."""
    if not raw or raw == "FALLBACK":
        logger.info(f"[LLM Tool] No API content — using fallback bullets for '{slide_title}'.")
        return _fallback_bullets(slide_title, topic)

    # Strip markdown fences if present
    raw = _strip_markdown_fences(raw)

    lines = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Skip meta lines
        if line.lower().startswith(("here are", "here's", "bullet", "---", "**slide", "note:")):
            continue
        if line.startswith("#"):
            continue
        lines.append(line)

    # Remove common bullet/number prefixes added by LLMs
    cleaned = []
    for line in lines:
        # Remove: "1.", "1)", "-", "*", "•", "▸", "**text**"
        line = re.sub(r'^(\d+[\.\)]|[\-\*\•\▸\>])\s+', '', line)
        # Remove bold markdown **text**
        line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        line = line.strip()
        # Accept lines of any reasonable length (lowered threshold)
        if len(line) >= 8:
            cleaned.append(line)

    if len(cleaned) >= 2:
        logger.info(f"[LLM Tool] ✅ Parsed {len(cleaned)} bullets from API response")
        return cleaned[:5]

    logger.warning(f"[LLM Tool] ⚠️  Could not extract bullets from LLM response. Using fallback.")
    return _fallback_bullets(slide_title, topic)


# ══════════════════════════════════════════════════════════════════════════════
# Fallback Content Engine (rule-based, topic-aware)
# ══════════════════════════════════════════════════════════════════════════════

def _fallback_generate(prompt: str) -> str:
    """Simple rule-based fallback when LLM API is unavailable."""
    logger.info("[LLM Tool] Using rule-based fallback generation.")
    return "FALLBACK"


def _fallback_slide_plan(user_prompt: str, num_slides: int) -> List[Dict[str, Any]]:
    """Generate a sensible slide plan without LLM."""
    topic = _extract_topic(user_prompt)

    templates = [
        {"slide_number": 1, "title": f"Introduction to {topic}", "type": "title_slide", "is_image_slide": False},
        {"slide_number": 2, "title": f"What is {topic}?", "type": "content", "is_image_slide": False},
        {"slide_number": 3, "title": f"Core Concepts of {topic}", "type": "content", "is_image_slide": False},
        {"slide_number": 4, "title": f"Visual Overview", "type": "image", "is_image_slide": True},
        {"slide_number": 5, "title": f"Key Benefits & Applications", "type": "content", "is_image_slide": False},
        {"slide_number": 6, "title": f"Challenges & Limitations", "type": "content", "is_image_slide": False},
        {"slide_number": 7, "title": f"Future of {topic}", "type": "content", "is_image_slide": False},
        {"slide_number": 8, "title": "Summary & Conclusion", "type": "content", "is_image_slide": False},
    ]

    plan = templates[:num_slides]
    plan[-1]["title"] = "Summary & Conclusion"
    plan[-1]["type"] = "content"
    plan[-1]["is_image_slide"] = False
    return plan


def _fallback_bullets(slide_title: str, topic: str) -> List[str]:
    """Generate topic-aware fallback bullets."""
    title_lower = slide_title.lower()

    if "introduction" in title_lower or "what is" in title_lower:
        return [
            f"{topic} is a transformative field shaping modern technology and society",
            f"It encompasses a wide range of techniques, tools, and methodologies",
            f"Understanding {topic} is essential for professionals in all industries today",
            f"This presentation covers the fundamentals and practical applications",
        ]
    elif "benefit" in title_lower or "application" in title_lower:
        return [
            f"Dramatically improves efficiency and reduces operational costs across sectors",
            f"Enables data-driven decision making with greater accuracy and confidence",
            f"Accelerates innovation cycles and brings products to market faster",
            f"Creates new opportunities and business models previously not possible",
        ]
    elif "challenge" in title_lower or "limitation" in title_lower:
        return [
            f"Data quality and availability remain significant barriers to adoption",
            f"High computational costs can limit accessibility for smaller organizations",
            f"Ethical considerations around bias, fairness, and transparency are critical",
            f"Requires specialized expertise that is currently in high global demand",
        ]
    elif "future" in title_lower:
        return [
            f"Rapid advancements will continue to reshape industries over the next decade",
            f"Integration with other emerging technologies will create powerful synergies",
            f"Democratization efforts will make {topic} accessible to more users",
            f"Regulatory frameworks will evolve to ensure responsible and safe adoption",
        ]
    elif "conclusion" in title_lower or "summary" in title_lower:
        return [
            f"{topic} represents one of the most significant advances in modern technology",
            f"The applications span virtually every industry and human endeavor",
            f"Understanding the fundamentals today prepares you for tomorrow's challenges",
            f"Continuous learning and adaptation are key to thriving in this landscape",
        ]
    else:
        return [
            f"This aspect of {topic} plays a crucial role in the overall ecosystem",
            f"Key principles include structured thinking, iterative refinement, and validation",
            f"Real-world implementations demonstrate measurable and repeatable results",
            f"Best practices continue to evolve as the field matures and expands",
        ]


def _extract_topic(prompt: str) -> str:
    """Extract the main topic from a user prompt."""
    prompt_lower = prompt.lower()
    filler = [
        "create a", "make a", "generate a", "build a",
        "presentation on", "ppt on", "slides on", "slideshow on",
        "presentation about", "about", "for beginners", "for students",
        "slide", "slides", "ppt", "powerpoint",
    ]
    result = prompt_lower
    for f in filler:
        result = result.replace(f, " ")
    result = re.sub(r'\d+[\s\-]?slide[s]?', '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    topic = " ".join(w.capitalize() for w in result.split() if len(w) > 2)
    return topic if topic else "The Topic"
