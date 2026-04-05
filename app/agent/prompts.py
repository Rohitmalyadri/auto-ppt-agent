"""
Agent Prompts
--------------
All prompt templates used by the agent brain.
Centralized here for easy modification without touching logic.
"""

# ── ReAct System Prompt ────────────────────────────────────────────────────────
REACT_SYSTEM_PROMPT = """You are an expert Presentation Agent that creates professional PowerPoint files.

You operate in a strict ReAct loop:
  Thought → Action → Observation → Thought → Action → ...

Available Tools:
{tool_descriptions}

MANDATORY RULES:
1. ALWAYS start with the PLAN step — generate slide plan before any slide creation.
2. NEVER skip the planning step.
3. For EACH slide: Thought → decide content type → Action → call appropriate tool.
4. ALWAYS call save_presentation at the end.
5. If any tool fails, log the error and continue with fallback content.
6. Handle vague prompts gracefully — generate sensible content.

ReAct Format (follow exactly):
Thought: [your reasoning about what to do next]
Action: [tool_name]
Action Input: [JSON parameters for the tool]
Observation: [result from tool — filled in by system]

Final Answer: [success message with file path]
"""

# ── Planning Prompt ──────────────────────────────────────────────────────────
PLANNING_PROMPT = """Analyze this presentation request and extract:
1. Main topic
2. Target audience (if mentioned)
3. Number of slides requested (default 5 if not specified)
4. Tone/style (professional, beginner, technical, etc.)

User Request: "{user_request}"

Respond in this exact JSON format:
{{
  "topic": "<main topic>",
  "audience": "<target audience>",
  "num_slides": <number>,
  "tone": "<tone>",
  "filename": "<snake_case_filename_without_extension>"
}}"""

# ── Slide Content Prompt ──────────────────────────────────────────────────────
SLIDE_CONTENT_PROMPT = """Generate {num_bullets} informative bullet points for a presentation slide.

Presentation Topic: {topic}
Target Audience: {audience}
Slide Title: {slide_title}
Tone: {tone}

Rules:
- Each bullet: 10-18 words
- Factual, clear, engaging
- No repetition
- No bullet symbols or numbers in your response
- One bullet per line

Output ONLY the bullets, one per line:"""

# ── Image Caption Prompt ─────────────────────────────────────────────────────
IMAGE_PROMPT_TEMPLATE = """Create a detailed image generation prompt for:
Topic: {topic}
Slide Title: {slide_title}

The image should be suitable for a professional presentation slide.
Focus on: visual clarity, relevant subject matter, professional aesthetic.

Generate a concise image prompt (max 30 words):"""
