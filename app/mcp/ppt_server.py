"""
MCP PPT Server
---------------
Exposes all PPT and content generation tools as a unified MCP-style
server interface. This is the tool registry that the agent calls into.

Acts as a message bus: Agent sends ToolCall → Server routes → Tool executes → Returns result.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ─── Tool Registry ─────────────────────────────────────────────────────────────
class ToolName(str, Enum):
    CREATE_PRESENTATION = "create_presentation"
    ADD_TITLE_SLIDE     = "add_title_slide"
    ADD_SLIDE           = "add_slide"
    ADD_IMAGE_SLIDE     = "add_image_slide"
    SAVE_PRESENTATION   = "save_presentation"
    GENERATE_TEXT       = "generate_text"
    GENERATE_IMAGE      = "generate_image"
    GENERATE_SLIDE_PLAN = "generate_slide_plan"
    GENERATE_BULLETS    = "generate_slide_bullets"


@dataclass
class ToolCall:
    """Structured tool invocation (MCP message format)."""
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Structured result from a tool invocation."""
    tool: str
    status: str          # "ok" | "error"
    data: Any = None
    message: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# MCP Server Class
# ══════════════════════════════════════════════════════════════════════════════
class MCPPPTServer:
    """
    Central MCP Server that routes tool calls to the appropriate implementation.
    Provides a clean interface between the agent and underlying tool modules.
    """

    def __init__(self):
        self._import_tools()
        logger.info("[MCP Server] PPT Server initialized. Tools ready.")

    def _import_tools(self):
        """Lazy import of tool modules to allow partial usage."""
        try:
            from app.tools import ppt_tool
            self.ppt = ppt_tool
        except ImportError as e:
            logger.error(f"[MCP Server] PPT tool import failed: {e}")
            self.ppt = None

        try:
            from app.tools import llm_tool
            self.llm = llm_tool
        except ImportError as e:
            logger.error(f"[MCP Server] LLM tool import failed: {e}")
            self.llm = None

        try:
            from app.tools import image_tool
            self.img = image_tool
        except ImportError as e:
            logger.error(f"[MCP Server] Image tool import failed: {e}")
            self.img = None

    # ── Public dispatch method ─────────────────────────────────────────────
    def call(self, tool_call: ToolCall) -> ToolResult:
        """
        Route a ToolCall to the appropriate tool function.

        Args:
            tool_call: ToolCall object with tool name and parameters.

        Returns:
            ToolResult with status and data.
        """
        tool = tool_call.tool
        params = tool_call.params

        logger.info(f"[MCP Server] → Routing tool: '{tool}' | params: {list(params.keys())}")

        try:
            result = self._dispatch(tool, params)
            logger.info(f"[MCP Server] ← Tool '{tool}' completed: {result.get('status', 'unknown')}")
            return ToolResult(
                tool=tool,
                status=result.get("status", "ok"),
                data=result.get("data") or result.get("path") or result.get("message"),
                message=result.get("message", ""),
            )
        except Exception as e:
            logger.error(f"[MCP Server] Tool '{tool}' raised exception: {e}")
            return ToolResult(tool=tool, status="error", message=str(e))

    def _dispatch(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Internal routing logic."""

        # ── PPT Tools ───────────────────────────────────────────────────────
        if tool == ToolName.CREATE_PRESENTATION:
            return self.ppt.create_presentation(
                filename=params.get("filename", "presentation.pptx")
            )

        elif tool == ToolName.ADD_TITLE_SLIDE:
            return self.ppt.add_title_slide(
                title=params.get("title", "Untitled"),
                subtitle=params.get("subtitle", ""),
            )

        elif tool == ToolName.ADD_SLIDE:
            return self.ppt.add_slide(
                title=params.get("title", "Slide"),
                bullets=params.get("bullets", ["Content coming soon..."]),
                slide_number=params.get("slide_number", 0),
            )

        elif tool == ToolName.ADD_IMAGE_SLIDE:
            return self.ppt.add_image_slide(
                title=params.get("title", "Visual"),
                image_path=params.get("image_path", ""),
                caption=params.get("caption", ""),
            )

        elif tool == ToolName.SAVE_PRESENTATION:
            return self.ppt.save_presentation()

        # ── LLM Tools ───────────────────────────────────────────────────────
        elif tool == ToolName.GENERATE_TEXT:
            text = self.llm.generate_text(
                prompt=params.get("prompt", ""),
                max_tokens=params.get("max_tokens", 400),
            )
            return {"status": "ok", "data": text}

        elif tool == ToolName.GENERATE_SLIDE_PLAN:
            plan = self.llm.generate_slide_plan(
                user_prompt=params.get("user_prompt", ""),
                num_slides=params.get("num_slides", 5),
            )
            return {"status": "ok", "data": plan}

        elif tool == ToolName.GENERATE_BULLETS:
            bullets = self.llm.generate_slide_bullets(
                topic=params.get("topic", ""),
                slide_title=params.get("slide_title", ""),
                context=params.get("context", ""),
            )
            return {"status": "ok", "data": bullets}

        # ── Image Tools ─────────────────────────────────────────────────────
        elif tool == ToolName.GENERATE_IMAGE:
            path = self.img.generate_image(
                prompt=params.get("prompt", ""),
                filename=params.get("filename", "slide_image.png"),
            )
            return {"status": "ok" if path else "error", "path": path, "data": path}

        else:
            return {"status": "error", "message": f"Unknown tool: '{tool}'"}

    # ── Convenience wrappers ───────────────────────────────────────────────
    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return [t.value for t in ToolName]
