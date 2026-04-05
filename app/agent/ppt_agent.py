"""
Auto-PPT Agent — ReAct Planning Agent
----------------------------------------
Implements the full agentic loop:
  1. Analyze user prompt
  2. Generate slide plan (MANDATORY planning step)
  3. Create presentation
  4. Per-slide: generate content → call MCP tool
  5. Save presentation
  6. Return result

Uses structured message passing through the MCP Server.
"""

import json
import logging
import re
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.mcp.ppt_server import MCPPPTServer, ToolCall, ToolResult
from app.agent.prompts import PLANNING_PROMPT

logger = logging.getLogger(__name__)


# ─── Agent Message Types (structured inter-component comms) ───────────────────
@dataclass
class AgentMessage:
    """Message passed between agent components."""
    role: str          # "agent" | "tool" | "planner" | "executor"
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SlideTask:
    """Represents work for a single slide."""
    slide_number: int
    title: str
    slide_type: str         # "title_slide" | "content" | "image"
    is_image_slide: bool
    bullets: List[str] = field(default_factory=list)
    image_path: Optional[str] = None
    status: str = "pending"  # "pending" | "done" | "error"


@dataclass
class ExecutionPlan:
    """The complete execution plan produced during planning phase."""
    topic: str
    audience: str
    tone: str
    num_slides: int
    filename: str
    slides: List[SlideTask] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# Planner Sub-Agent
# ══════════════════════════════════════════════════════════════════════════════
class PlannerAgent:
    """
    Sub-agent responsible for:
    - Parsing user prompt
    - Generating structured slide plan
    - NEVER skipped (enforced by main agent)
    """

    def __init__(self, mcp_server: MCPPPTServer):
        self.mcp = mcp_server

    def analyze_prompt(self, user_request: str) -> Dict[str, Any]:
        """Extract structured intent from raw user input."""
        logger.info("[Planner] Analyzing user prompt...")

        # Use LLM to parse intent
        result = self.mcp.call(ToolCall(
            tool="generate_text",
            params={
                "prompt": PLANNING_PROMPT.format(user_request=user_request),
                "max_tokens": 200,
            }
        ))

        parsed = self._parse_intent(result.data or "", user_request)
        logger.info(f"[Planner] Intent parsed: topic='{parsed['topic']}', slides={parsed['num_slides']}")
        return parsed

    def create_slide_plan(self, intent: Dict[str, Any], user_request: str) -> ExecutionPlan:
        """Generate the full slide plan — the MANDATORY planning step."""
        logger.info("[Planner] ═══ PLANNING STEP: Generating slide structure ═══")

        result = self.mcp.call(ToolCall(
            tool="generate_slide_plan",
            params={
                "user_prompt": user_request,
                "num_slides": intent["num_slides"],
            }
        ))

        raw_plan: List[Dict] = result.data if isinstance(result.data, list) else []

        slides = []
        for item in raw_plan:
            slides.append(SlideTask(
                slide_number=item.get("slide_number", len(slides) + 1),
                title=item.get("title", f"Slide {len(slides) + 1}"),
                slide_type=item.get("type", "content"),
                is_image_slide=item.get("is_image_slide", False),
            ))

        plan = ExecutionPlan(
            topic=intent["topic"],
            audience=intent["audience"],
            tone=intent["tone"],
            num_slides=intent["num_slides"],
            filename=intent["filename"],
            slides=slides,
        )

        logger.info(f"[Planner] Plan complete: {len(slides)} slides for '{plan.topic}'")
        return plan

    def _parse_intent(self, llm_output: str, user_request: str) -> Dict[str, Any]:
        """Parse LLM output for intent, with robust fallback."""
        try:
            match = re.search(r'\{.*?\}', llm_output, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return {
                    "topic": data.get("topic", self._extract_topic(user_request)),
                    "audience": data.get("audience", "general audience"),
                    "num_slides": max(3, min(12, int(data.get("num_slides", 5)))),
                    "tone": data.get("tone", "professional"),
                    "filename": data.get("filename", self._make_filename(user_request)),
                }
        except Exception:
            pass

        return {
            "topic": self._extract_topic(user_request),
            "audience": "general audience",
            "num_slides": self._extract_slide_count(user_request),
            "tone": "professional",
            "filename": self._make_filename(user_request),
        }

    @staticmethod
    def _extract_topic(prompt: str) -> str:
        """Rule-based topic extraction."""
        filler = [
            "create a", "make a", "generate a", "build a", "give me a",
            "presentation on", "ppt on", "slides on", "presentation about",
            "slide", "slides", "ppt", "powerpoint", "about",
        ]
        result = prompt.lower()
        for f in filler:
            result = result.replace(f, " ")
        result = re.sub(r'\d+[\s\-]?slide[s]?', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        topic = " ".join(w.capitalize() for w in result.split() if len(w) > 2)
        return topic or "Technology"

    @staticmethod
    def _extract_slide_count(prompt: str) -> int:
        """Extract slide count from prompt."""
        match = re.search(r'(\d+)\s*[\-]?\s*slide', prompt, re.IGNORECASE)
        if match:
            return max(3, min(12, int(match.group(1))))
        return 5

    @staticmethod
    def _make_filename(prompt: str) -> str:
        """Create a clean filename from prompt."""
        words = re.findall(r'[a-zA-Z]+', prompt)
        meaningful = [w.lower() for w in words if len(w) > 3][:4]
        timestamp = datetime.now().strftime("%H%M")
        return "_".join(meaningful) + f"_{timestamp}" if meaningful else f"presentation_{timestamp}"


# ══════════════════════════════════════════════════════════════════════════════
# Executor Sub-Agent
# ══════════════════════════════════════════════════════════════════════════════
class ExecutorAgent:
    """
    Sub-agent responsible for:
    - Creating slides according to the plan
    - Generating content per slide
    - Calling MCP tools in the correct order
    """

    def __init__(self, mcp_server: MCPPPTServer):
        self.mcp = mcp_server

    def execute_plan(self, plan: ExecutionPlan) -> List[AgentMessage]:
        """Run the full slide creation loop."""
        messages: List[AgentMessage] = []

        for task in plan.slides:
            msg = self._execute_slide(task, plan)
            messages.append(msg)

        return messages

    def _execute_slide(self, task: SlideTask, plan: ExecutionPlan) -> AgentMessage:
        """
        ReAct loop for a single slide:
        Thought → Action (generate content) → Observation → Action (add slide)
        """
        logger.info(f"\n[Executor] ── Slide {task.slide_number}: '{task.title}' ──────────────")

        try:
            # THOUGHT
            logger.info(f"[Executor] Thought: Deciding how to handle slide type='{task.slide_type}'")

            # ── TITLE SLIDE ─────────────────────────────────────────────
            if task.slide_type == "title_slide":
                return self._handle_title_slide(task, plan)

            # ── IMAGE SLIDE ─────────────────────────────────────────────
            elif task.is_image_slide:
                return self._handle_image_slide(task, plan)

            # ── CONTENT SLIDE ───────────────────────────────────────────
            else:
                return self._handle_content_slide(task, plan)

        except Exception as e:
            logger.error(f"[Executor] Slide {task.slide_number} failed: {e}")
            task.status = "error"
            # Graceful degradation — add simple slide
            self.mcp.call(ToolCall(
                tool="add_slide",
                params={
                    "title": task.title,
                    "bullets": [f"Content about {plan.topic}", "Key concepts explored here",
                                "Details to be added", "See supplementary materials"],
                    "slide_number": task.slide_number,
                }
            ))
            return AgentMessage(
                role="executor",
                content=f"Slide {task.slide_number} completed with fallback content",
                metadata={"slide_number": task.slide_number, "status": "fallback"},
            )

    def _handle_title_slide(self, task: SlideTask, plan: ExecutionPlan) -> AgentMessage:
        """Create the cover/title slide."""
        subtitle_parts = []
        if plan.audience != "general audience":
            subtitle_parts.append(f"For {plan.audience}")
        subtitle_parts.append(f"A {plan.tone.title()} Presentation")

        result = self.mcp.call(ToolCall(
            tool="add_title_slide",
            params={
                "title": task.title,
                "subtitle": "  •  ".join(subtitle_parts),
            }
        ))

        task.status = "done"
        logger.info(f"[Executor] Observation: Title slide → {result.status}")
        return AgentMessage(
            role="executor",
            content=f"Title slide created: '{task.title}'",
            metadata={"slide_number": task.slide_number, "status": result.status},
        )

    def _handle_image_slide(self, task: SlideTask, plan: ExecutionPlan) -> AgentMessage:
        """Generate image and create image slide."""
        logger.info(f"[Executor] Action: generate_image for '{task.title}'")

        # Generate image
        img_result = self.mcp.call(ToolCall(
            tool="generate_image",
            params={
                "prompt": f"{plan.topic}, {task.title}, professional illustration, digital art",
                "filename": f"slide_{task.slide_number}_img.png",
            }
        ))

        image_path = img_result.data
        caption = f"{task.title} — {plan.topic}"

        # Add image slide
        result = self.mcp.call(ToolCall(
            tool="add_image_slide",
            params={
                "title": task.title,
                "image_path": image_path or "",
                "caption": caption,
            }
        ))

        task.image_path = image_path
        task.status = "done"
        logger.info(f"[Executor] Observation: Image slide → {result.status}")
        return AgentMessage(
            role="executor",
            content=f"Image slide created: '{task.title}'",
            metadata={"slide_number": task.slide_number, "image_path": image_path},
        )

    def _handle_content_slide(self, task: SlideTask, plan: ExecutionPlan) -> AgentMessage:
        """Generate bullets and create content slide."""
        logger.info(f"[Executor] Action: generate_slide_bullets for '{task.title}'")

        # Generate bullets
        bullet_result = self.mcp.call(ToolCall(
            tool="generate_slide_bullets",
            params={
                "topic": plan.topic,
                "slide_title": task.title,
                "context": f"Audience: {plan.audience}, Tone: {plan.tone}",
            }
        ))

        bullets = bullet_result.data if isinstance(bullet_result.data, list) else [
            f"Key insight about {plan.topic}",
            "Detailed explanation of core concepts",
            "Practical applications and examples",
            "Expert recommendations for best results",
        ]

        # Add slide
        result = self.mcp.call(ToolCall(
            tool="add_slide",
            params={
                "title": task.title,
                "bullets": bullets,
                "slide_number": task.slide_number,
            }
        ))

        task.bullets = bullets
        task.status = "done"
        logger.info(f"[Executor] Observation: Content slide → {result.status}")
        return AgentMessage(
            role="executor",
            content=f"Content slide created: '{task.title}' with {len(bullets)} bullets",
            metadata={"slide_number": task.slide_number, "bullet_count": len(bullets)},
        )


# ══════════════════════════════════════════════════════════════════════════════
# Main PPT Agent (Brain)
# ══════════════════════════════════════════════════════════════════════════════
class PPTAgent:
    """
    The central Agent Brain that coordinates:
    - PlannerAgent (planning sub-agent)
    - ExecutorAgent (content generation sub-agent)
    - MCPPPTServer (tool registry)

    Implements: Analyze → Plan → Create → Execute → Save → Report
    """

    def __init__(self):
        logger.info("[Agent] ══════════════════════════════════════════")
        logger.info("[Agent] Auto-PPT Agent initializing...")
        logger.info("[Agent] ══════════════════════════════════════════")
        self.mcp = MCPPPTServer()
        self.planner = PlannerAgent(self.mcp)
        self.executor = ExecutorAgent(self.mcp)
        self._conversation: List[AgentMessage] = []
        logger.info("[Agent] All components initialized. Ready.")

    def run(self, user_request: str) -> Dict[str, Any]:
        """
        Main agent entry point — executes the full ReAct loop.

        Args:
            user_request: Natural language presentation request.

        Returns:
            Result dict with status, file path, and summary.
        """
        logger.info(f"\n[Agent] ▶ Starting for: '{user_request}'")
        self._log_message("agent", f"Received request: {user_request}")

        try:
            # ── STEP 1: Analyze ──────────────────────────────────────────
            logger.info("\n[Agent] ═══ STEP 1: ANALYZING PROMPT ═══")
            intent = self.planner.analyze_prompt(user_request)
            self._log_message("planner", f"Intent analyzed: {intent}")

            # ── STEP 2: PLAN (MANDATORY) ─────────────────────────────────
            logger.info("\n[Agent] ═══ STEP 2: PLANNING SLIDE STRUCTURE ═══")
            plan = self.planner.create_slide_plan(intent, user_request)
            self._log_message("planner", f"Plan created: {plan.num_slides} slides")
            self._print_plan(plan)

            # ── STEP 3: Create Presentation ──────────────────────────────
            logger.info("\n[Agent] ═══ STEP 3: CREATING PRESENTATION ═══")
            create_result = self.mcp.call(ToolCall(
                tool="create_presentation",
                params={"filename": plan.filename},
            ))
            if create_result.status == "error":
                raise RuntimeError(f"Failed to create presentation: {create_result.message}")
            self._log_message("tool", f"Presentation created at {create_result.data}")

            # ── STEP 4: Execute Slides ───────────────────────────────────
            logger.info("\n[Agent] ═══ STEP 4: GENERATING SLIDES ═══")
            slide_messages = self.executor.execute_plan(plan)
            for msg in slide_messages:
                self._conversation.append(msg)

            # ── STEP 5: Save ─────────────────────────────────────────────
            logger.info("\n[Agent] ═══ STEP 5: SAVING PRESENTATION ═══")
            save_result = self.mcp.call(ToolCall(tool="save_presentation", params={}))
            if save_result.status == "error":
                raise RuntimeError(f"Failed to save: {save_result.message}")

            output_path = save_result.data
            self._log_message("agent", f"Presentation saved: {output_path}")

            # ── STEP 6: Report ───────────────────────────────────────────
            completed = sum(1 for t in plan.slides if t.status == "done")
            summary = self._build_summary(plan, output_path, completed)

            logger.info(f"\n[Agent] ✅ SUCCESS: {output_path}")
            logger.info(f"[Agent] Slides completed: {completed}/{plan.num_slides}")

            return {
                "status": "success",
                "file_path": output_path,
                "topic": plan.topic,
                "slides_created": completed,
                "total_slides": plan.num_slides,
                "summary": summary,
            }

        except Exception as e:
            logger.error(f"\n[Agent] ❌ FATAL ERROR: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "file_path": None,
            }

    def _log_message(self, role: str, content: Any):
        """Record a message in the agent conversation log."""
        msg = AgentMessage(role=role, content=content)
        self._conversation.append(msg)
        logger.debug(f"[{role.upper()}] {content}")

    def _print_plan(self, plan: ExecutionPlan):
        """Log the slide plan in a readable format."""
        logger.info(f"\n{'─'*50}")
        logger.info(f"  SLIDE PLAN: {plan.topic}")
        logger.info(f"  Audience : {plan.audience}")
        logger.info(f"  Tone     : {plan.tone}")
        logger.info(f"  Slides   : {plan.num_slides}")
        logger.info(f"  File     : {plan.filename}.pptx")
        logger.info(f"{'─'*50}")
        for slide in plan.slides:
            icon = "🖼️" if slide.is_image_slide else "📝"
            logger.info(f"  {icon} [{slide.slide_number:02d}] {slide.title}")
        logger.info(f"{'─'*50}\n")

    def _build_summary(self, plan: ExecutionPlan, path: str, completed: int) -> str:
        return (
            f"✅ Presentation '{plan.topic}' created successfully!\n"
            f"   📁 File: {path}\n"
            f"   📊 Slides: {completed}/{plan.num_slides} completed\n"
            f"   👥 Audience: {plan.audience}\n"
            f"   🎨 Tone: {plan.tone}"
        )
