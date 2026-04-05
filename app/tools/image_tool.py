"""
MCP Tool: Image Generation
----------------------------
Primary:  Pollinations.ai  — free, no API key needed, real AI images
Fallback: Styled Pillow PNG — works 100% offline, no dependencies beyond Pillow

Prompt format optimised for presentation-quality slide visuals.
"""

import logging
import requests
import urllib.parse
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Output directory ────────────────────────────────────────────────────────────
_IMAGE_CACHE_DIR = Path(__file__).parent.parent.parent / "outputs" / "images"

# ── Pollinations.ai config ──────────────────────────────────────────────────────
# Free, open, no API key — returns real Stable-Diffusion quality images
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
POLLINATIONS_PARAMS = {
    "width":  1024,
    "height": 576,
    "nologo": "true",
    "enhance": "true",
    "model":  "flux",        # Best quality model on Pollinations
}


def _build_image_prompt(raw_prompt: str) -> str:
    """
    Transform a slide topic into a high-quality Stable-Diffusion style prompt.
    Uses concise, visual-first language optimised for presentation slides.
    """
    # Core prompt engineering for presentation visuals
    style_suffix = (
        "professional presentation illustration, "
        "clean minimal design, dark background, "
        "blue accent colors, corporate digital art, "
        "high quality, sharp details, 16:9 aspect ratio"
    )

    # Trim very long prompts to avoid URL limits
    topic_part = raw_prompt[:120] if len(raw_prompt) > 120 else raw_prompt

    # Negative concepts embedded as deprioritised terms
    full_prompt = f"{topic_part}, {style_suffix}"
    return full_prompt


# ══════════════════════════════════════════════════════════════════════════════
# MCP Tool: generate_image
# ══════════════════════════════════════════════════════════════════════════════
def generate_image(prompt: str, filename: str = "slide_image.png") -> Optional[str]:
    """
    MCP Tool — Generate a real AI image via Pollinations.ai (no API key needed).

    Falls back to a styled Pillow PNG if the request fails.

    Args:
        prompt:   Topic / description for the image.
        filename: Output PNG filename.

    Returns:
        Absolute path to the saved image file, or None on complete failure.
    """
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = str(_IMAGE_CACHE_DIR / filename)

    # ── Try Pollinations.ai (real AI image, no key) ────────────────────────
    result = _generate_pollinations(prompt, output_path)
    if result:
        return result

    # ── Fallback to styled Pillow PNG ─────────────────────────────────────
    logger.warning("[Image Tool] Pollinations failed. Generating styled placeholder.")
    return _generate_placeholder(prompt, output_path)


def _generate_pollinations(prompt: str, output_path: str) -> Optional[str]:
    """Call Pollinations.ai and save the returned image."""
    try:
        engineered_prompt = _build_image_prompt(prompt)
        encoded = urllib.parse.quote(engineered_prompt, safe="")

        url = POLLINATIONS_URL.format(prompt=encoded)
        logger.info(f"[Image Tool] → Pollinations.ai request: {prompt[:60]}...")

        resp = requests.get(
            url,
            params=POLLINATIONS_PARAMS,
            timeout=60,
            headers={"User-Agent": "Auto-PPT-Agent/1.0"},
            stream=True,
        )

        content_type = resp.headers.get("content-type", "")
        if resp.status_code == 200 and "image" in content_type:
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Validate the file has real image content
            size = Path(output_path).stat().st_size
            if size > 5000:   # real image should be > 5 KB
                logger.info(f"[Image Tool] ✅ AI image saved ({size // 1024} KB): {output_path}")
                return output_path
            else:
                logger.warning(f"[Image Tool] Image too small ({size} bytes) — likely error response")
                Path(output_path).unlink(missing_ok=True)
                return None

        else:
            logger.warning(
                f"[Image Tool] Pollinations returned {resp.status_code} "
                f"(content-type: {content_type})"
            )
            return None

    except requests.exceptions.Timeout:
        logger.warning("[Image Tool] Pollinations request timed out (60s).")
        return None
    except Exception as e:
        logger.error(f"[Image Tool] Pollinations error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Fallback: Styled Pillow PNG (100% offline, no anchor= needed)
# ══════════════════════════════════════════════════════════════════════════════
def _generate_placeholder(prompt: str, output_path: str) -> Optional[str]:
    """
    Generate a visually styled placeholder image using Pillow.
    Avoids Pillow 7.x incompatibilities (no anchor= parameter).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 1024, 576
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        # ── Gradient background (top → bottom) ──────────────────────────────
        for y in range(H):
            t = y / H
            r = int(13  + t * 18)
            g = int(16  + t * 25)
            b = int(23  + t * 55)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # ── Subtle grid ─────────────────────────────────────────────────────
        for x in range(0, W, 80):
            draw.line([(x, 0), (x, H)], fill=(28, 38, 65), width=1)
        for y in range(0, H, 80):
            draw.line([(0, y), (W, y)], fill=(28, 38, 65), width=1)

        cx, cy = W // 2, H // 2

        # ── Glowing rings ───────────────────────────────────────────────────
        for r in range(180, 0, -20):
            fade = int(60 * (1 - r / 180))
            draw.ellipse(
                [(cx - r, cy - r), (cx + r, cy + r)],
                outline=(94, 129, fade + 30),
                width=1,
            )

        # ── Bar chart icon ───────────────────────────────────────────────────
        bar_colors = [(94, 129, 244), (155, 89, 182), (52, 152, 219),
                      (46, 204, 113), (94, 129, 244)]
        bar_heights = [80, 120, 60, 100, 140]
        for i, bh in enumerate(bar_heights):
            bx = cx - 130 + i * 58
            top = cy - bh + 20
            bot = cy + 20
            draw.rectangle([(bx, top), (bx + 38, bot)], fill=bar_colors[i])
            # Highlight cap
            draw.rectangle([(bx, top), (bx + 38, top + 5)],
                           fill=(min(bar_colors[i][0] + 60, 255),
                                 min(bar_colors[i][1] + 60, 255),
                                 min(bar_colors[i][2] + 60, 255)))

        # ── Load font (safe cross-platform) ─────────────────────────────────
        def load_font(size: int):
            for name in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
                         "C:/Windows/Fonts/arial.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
                try:
                    return ImageFont.truetype(name, size)
                except Exception:
                    pass
            return ImageFont.load_default()

        font_title  = load_font(22)
        font_sub    = load_font(14)

        # ── Draw text WITHOUT anchor= (Pillow 7.x safe) ─────────────────────
        short = prompt[:70] + "..." if len(prompt) > 70 else prompt

        # Centre text manually using textbbox when available
        def draw_centred(text, y, font, color):
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
            except AttributeError:
                # Pillow < 8 fallback
                tw, _ = draw.textsize(text, font=font)
            x = (W - tw) // 2
            draw.text((x, y), text, font=font, fill=color)

        draw_centred(short,                       cy + 50, font_title, (200, 210, 240))
        draw_centred("[ AI Visual — Auto-PPT ]",  cy + 85, font_sub,   (94, 129, 244))

        img.save(output_path, "PNG")
        logger.info(f"[Image Tool] ✅ Placeholder saved: {output_path}")
        return output_path

    except ImportError:
        logger.error("[Image Tool] Pillow not installed.")
        return None
    except Exception as e:
        logger.error(f"[Image Tool] Placeholder failed: {e}")
        return None
