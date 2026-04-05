# 🤖 Auto-PPT Agent — MCP + Hugging Face

> **Agentic AI** that autonomously generates professional PowerPoint presentations from a single natural-language prompt.

---

## 🏗️ Architecture

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                  PPT AGENT (Brain)                  │
│  ┌─────────────┐         ┌──────────────────────┐  │
│  │ PlannerAgent│ ──plan──▶│   ExecutorAgent      │  │
│  │  (Step 1-2) │         │   (Step 3-5)         │  │
│  └─────────────┘         └──────────────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │ ToolCall (MCP messages)
                         ▼
            ┌────────────────────────┐
            │    MCP PPT Server      │
            │   (Tool Registry)      │
            └─────┬────────┬─────────┘
                  │        │
       ┌──────────┘        └──────────┐
       ▼                              ▼
┌──────────────┐              ┌───────────────┐
│  PPT Tools   │              │  LLM / Image  │
│  ppt_tool.py │              │  llm_tool.py  │
│              │              │ image_tool.py │
│ - create()   │              │               │
│ - add_slide()│              │ HuggingFace   │
│ - save()     │              │ Inference API │
└──────────────┘              └───────────────┘
       │
       ▼
  📄 output/*.pptx
```

---

## 📁 Project Structure

```
auto-ppt-agent/
├── main.py                    ← Entry point (run this)
├── requirements.txt
├── .env.example               ← Copy to .env
├── outputs/                   ← Generated PPT files saved here
│   ├── *.pptx
│   ├── images/                ← AI-generated slide images
│   └── logs/                  ← Agent decision logs
└── app/
    ├── main.py                ← CLI interface
    ├── agent/
    │   ├── ppt_agent.py       ← Agent Brain + Planner + Executor
    │   └── prompts.py         ← All prompt templates
    ├── mcp/
    │   └── ppt_server.py      ← MCP Tool Registry / Router
    └── tools/
        ├── ppt_tool.py        ← PowerPoint MCP tools
        ├── llm_tool.py        ← Text generation MCP tools
        └── image_tool.py      ← Image generation MCP tools
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env and add your Hugging Face token
```

Get a **free** HF API token at: https://huggingface.co/settings/tokens

### 3. Run the agent
```bash
# Full natural language prompt
python main.py "Create a 5-slide presentation on Artificial Intelligence for beginners"

# Quick shorthand
python main.py --topic "Climate Change" --slides 6 --audience "high school students"

# Interactive mode (prompts for input)
python main.py

# Verbose/debug mode
python main.py "Create a ppt on Machine Learning" --verbose
```

---

## 🧠 Agent Behavior (ReAct Loop)

The agent **ALWAYS** follows this loop — no steps skipped:

| Step | Sub-Agent | Action |
|------|-----------|--------|
| 1 | **Brain** | Parse user prompt, extract topic/slides/audience |
| 2 | **Planner** | Generate structured slide plan (MANDATORY) |
| 3 | **Brain** | Call `create_presentation` MCP tool |
| 4 | **Executor** | For each slide: generate content → call MCP tool |
| 5 | **Brain** | Call `save_presentation` MCP tool |
| 6 | **Brain** | Return success message with file path |

---

## 🛠️ MCP Tools

| Tool | Description |
|------|-------------|
| `create_presentation(filename)` | Initialize new PPTX file |
| `add_title_slide(title, subtitle)` | Add hero/cover slide |
| `add_slide(title, bullets)` | Add content slide with bullets |
| `add_image_slide(title, image_path)` | Add image-based slide |
| `save_presentation()` | Save PPTX to disk |
| `generate_text(prompt)` | HF text generation |
| `generate_slide_plan(prompt, n)` | Generate slide structure plan |
| `generate_slide_bullets(topic, title)` | Generate slide bullet points |
| `generate_image(prompt)` | HF Stable Diffusion image |

---

## 🤖 Hugging Face Models

| Type | Model | Fallback |
|------|-------|---------|
| Text | `mistralai/Mistral-7B-Instruct-v0.3` | Rule-based content |
| Text | `HuggingFaceH4/zephyr-7b-beta` | Rule-based content |
| Image | `stabilityai/stable-diffusion-2-1` | Pillow placeholder |

> **No token?** The agent runs in **fallback mode** — generates rule-based, topic-aware content without any API calls. Fully functional!

---

## 🎨 Design Features

The generated PPTX uses:
- **Dark theme** with electric blue accents
- **Professional typography** with visual hierarchy
- **Styled bullet points** with color-coded indicators
- **Image slides** with AI-generated visuals
- **Hero title slide** with gradient accents

---

## 📋 Example Output

Input: `"Create a 5-slide presentation on Artificial Intelligence for beginners"`

Generated slide plan:
```
[01] 📝 Introduction to Artificial Intelligence  [title_slide]
[02] 📝 What is Artificial Intelligence?         [content]
[03] 📝 Core Concepts of AI                       [content]
[04] 🖼️ Visual Overview                           [image]
[05] 📝 Summary & Conclusion                      [content]
```

Output: `outputs/artificial_intelligence_HHMM.pptx`

---

## 🛡️ Error Handling

| Scenario | Behavior |
|----------|----------|
| No HF token | Fallback content generation |
| API timeout | Try next model, then fallback |
| Vague prompt ("make a ppt") | Extracts topic, generates sensible content |
| Image generation fails | Generates Pillow placeholder |
| Slide creation fails | Adds fallback text slide, continues |

The agent **never crashes** — it always produces a valid `.pptx` file.
