"""
Flask Web App — Auto-PPT Agent UI
------------------------------------
Provides a browser-based interface to:
  - Enter a presentation prompt
  - Monitor generation progress (via SSE streaming)
  - Download the generated .pptx file
"""

import os
import sys
import json
import uuid
import logging
import threading
import queue
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    send_file, Response, stream_with_context
)

# ─── Path setup ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# ─── In-memory job tracker ────────────────────────────────────────────────────
# job_id → {"status", "progress", "log", "file_path", "error"}
_jobs: dict = {}
_job_queues: dict = {}   # job_id → queue.Queue for SSE events
_jobs_lock = threading.Lock()

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """Start a new PPT generation job in a background thread."""
    data = request.get_json()
    prompt = (data or {}).get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Prompt cannot be empty."}), 400
    if len(prompt) > 500:
        return jsonify({"error": "Prompt too long (max 500 characters)."}), 400

    job_id = str(uuid.uuid4())
    q = queue.Queue()

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "progress": 0,
            "log": [],
            "file_path": None,
            "error": None,
            "prompt": prompt,
            "started_at": datetime.now().isoformat(),
        }
        _job_queues[job_id] = q

    # Start background thread
    thread = threading.Thread(
        target=_run_agent_job,
        args=(job_id, prompt, q),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    """Server-Sent Events endpoint — streams progress to the browser."""
    def event_generator():
        q = _job_queues.get(job_id)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
            return

        while True:
            try:
                event = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                # Keep-alive ping
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return Response(
        stream_with_context(event_generator()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/status/<job_id>")
def status(job_id: str):
    """Polling fallback — returns current job status."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<job_id>")
def download(job_id: str):
    """Download the generated .pptx file."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "done":
        return jsonify({"error": "Job not complete yet"}), 400

    file_path = job.get("file_path")
    if not file_path or not Path(file_path).exists():
        return jsonify({"error": "File not found on disk"}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=Path(file_path).name,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.route("/health")
def health():
    """Diagnostic endpoint — shows API config status."""
    token = os.getenv("OPENROUTER_API_KEY", "")
    has_key = bool(token)
    return jsonify({
        "status": "ok",
        "api_configured": has_key,
        "api_key_preview": token[:8] + "..." if has_key else None,
        "mode": "openrouter_ai" if has_key else "fallback_rule_based",
        "message": (
            f"OpenRouter key detected ({token[:8]}...). AI content generation active."
            if has_key
            else "No OPENROUTER_API_KEY found. Using rule-based fallback content. "
                 "Add your key to the .env file to enable AI generation."
        ),
    })


# ══════════════════════════════════════════════════════════════════════════════
# Background Agent Runner
# ══════════════════════════════════════════════════════════════════════════════

def _run_agent_job(job_id: str, prompt: str, q: queue.Queue):
    """Run the PPT agent in a background thread, pushing SSE events to queue."""

    def push(event_type: str, message: str, progress: int = None, data: dict = None):
        """Push an SSE event to the queue."""
        payload = {"type": event_type, "message": message}
        if progress is not None:
            payload["progress"] = progress
        if data:
            payload.update(data)
        q.put(payload)
        # Also update job state
        with _jobs_lock:
            job = _jobs.get(job_id, {})
            job["log"].append(message)
            if progress is not None:
                job["progress"] = progress

    try:
        push("log", "🚀 Agent started...", progress=5)

        # ── Setup logging to capture agent output ──────────────────────────
        class QueueHandler(logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                # Filter out noisy debug lines for the UI
                if any(skip in msg for skip in ["werkzeug", "urllib3", "PIL"]):
                    return
                push("log", msg)

        qh = QueueHandler()
        qh.setFormatter(logging.Formatter("%(message)s"))
        qh.setLevel(logging.INFO)
        logging.getLogger().addHandler(qh)

        push("log", "🧠 Initializing agent components...", progress=10)

        # ── Import and run agent ───────────────────────────────────────────
        from app.agent.ppt_agent import PPTAgent

        push("log", f"📋 Analyzing prompt: '{prompt}'", progress=15)
        agent = PPTAgent()

        push("log", "📝 Planning slide structure...", progress=25)
        result = agent.run(prompt)

        # Remove queue handler after completion
        logging.getLogger().removeHandler(qh)

        if result["status"] == "success":
            file_path = result["file_path"]
            slides = result["slides_created"]

            with _jobs_lock:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["file_path"] = file_path
                _jobs[job_id]["progress"] = 100

            push("done", f"✅ Done! {slides} slides generated.", progress=100, data={
                "file_path": file_path,
                "filename": Path(file_path).name,
                "slides": slides,
                "topic": result.get("topic", ""),
            })
        else:
            raise RuntimeError(result.get("message", "Agent failed"))

    except Exception as e:
        logger.error(f"[Web] Job {job_id} failed: {e}", exc_info=True)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = str(e)
        q.put({"type": "error", "message": f"❌ Error: {str(e)}", "progress": 0})


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_web():
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"\n  🌐  Auto-PPT Agent Web UI")
    print(f"  ➜   http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_web()
