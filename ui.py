import gradio as gr
import os
import sys
import time
import threading
import queue
import concurrent.futures

# Ensure the scratch directory is in the path to import our engine
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from linkedin_cv_matcher import (
    extract_cv_text, fetch_jobs, fetch_job_description, 
    evaluate_jobs_batch_with_ai, start_ollama_if_needed
)

# Default values
DEFAULT_CV_PATH = os.path.expanduser("")
DEFAULT_QUERY = '"CEO" OR "Chief Executive Officer" OR "VP" OR "Vice President" OR "SVP" OR "Director" OR "Head of" OR "Group manager" OR "Group lead" OR "group leader" OR ("system" AND ("leader" OR "lead" OR "manager"))'
DEFAULT_KEY_1 = ""
DEFAULT_KEY_2 = ""

# ── Shared run-control state ──────────────────────────────────────────────
_stop = threading.Event()
_pause = threading.Event()
_pause.set()  # not paused initially

def _reset_controls():
    _stop.clear()
    _pause.set()

# ── Button callbacks ─────────────────────────────────────────────────────
def on_run_start():
    _reset_controls()
    return (
        gr.update(interactive=False),                         # run
        gr.update(interactive=True, value="⏸  Pause"),       # pause
        gr.update(interactive=True),                          # stop
        "",                                                   # clear logs
        "*Waiting for results…*",                             # clear report
    )

def on_run_end():
    return (
        gr.update(interactive=True),                          # run
        gr.update(interactive=False, value="⏸  Pause"),      # pause
        gr.update(interactive=False),                         # stop
    )

def on_stop():
    _stop.set()
    _pause.set()  
    return gr.update(interactive=False), gr.update(interactive=False)

def on_pause():
    if _pause.is_set():
        _pause.clear()
        return gr.update(value="▶  Resume")
    else:
        _pause.set()
        return gr.update(value="⏸  Pause")

def highlight_query(q):
    if not q: return ""
    q = q.replace(" OR ", " <strong style='color:#3b82f6;'>OR</strong> ")
    q = q.replace(" AND ", " <strong style='color:#22c55e;'>AND</strong> ")
    q = q.replace(" NOT ", " <strong style='color:#ef4444;'>NOT</strong> ")
    q = q.replace("(", "<strong style='color:#9ca3af;'>(</strong>")
    q = q.replace(")", "<strong style='color:#9ca3af;'>)</strong>")
    return f"<div style='padding: 10px; background: #1e293b; color: #e2e8f0; font-family: monospace; font-size: 14px; white-space: pre-wrap; word-break: break-word; border-top: 1px dashed #334155;'>{q}</div>"

# ── Main Background Worker ───────────────────────────────────────────────
def background_worker(q, cv_path, query, date_posted, distance, alignment, mode, max_jobs, key1, key2, online_model, offline_model):
    try:
        if mode == "offline":
            q.put(("LOG", "🤖 Checking local Ollama connection..."))
            if not start_ollama_if_needed():
                msg = (
                    "❌ Offline Mode Error: Ollama could not be started or found on localhost:11434.\n"
                    "Please download Ollama from https://ollama.com, install it, and open the app.\n"
                    f"Then open your terminal and run: `ollama pull {offline_model}`"
                )
                q.put(("ERROR", msg))
                return
            q.put(("LOG", "✅ Ollama is running successfully."))

        q.put(("LOG", f"📄 Extracting CV text..."))
        cv_text = extract_cv_text(cv_path)
        
        q.put(("LOG", f"🔍 Fetching jobs from LinkedIn for query..."))
        max_to_fetch = int(max_jobs) if max_jobs > 0 else None
        jobs = fetch_jobs(query, date_posted=date_posted, distance=int(distance), max_jobs=max_to_fetch)
        
        if _stop.is_set(): return
        
        q.put(("LOG", f"📊 Found {len(jobs)} jobs. Downloading descriptions and batching AI..."))
        
        relevant_jobs = []
        batch_size = 10 if mode == "online" else 1
        total_eval = 0
        api_keys = [key1, key2]
        
        for i in range(0, len(jobs), batch_size):
            if _stop.is_set(): return
            while not _pause.is_set():
                if _stop.is_set(): return
                time.sleep(0.2)
                
            batch = jobs[i:i+batch_size]
            
            q.put(("LOG", f"\n⚡ Fetching descriptions for batch {i+1} to {min(i+batch_size, len(jobs))}..."))
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                desc_map = list(executor.map(fetch_job_description, [j['job_id'] for j in batch]))
                
            for j, d in zip(batch, desc_map):
                j['description'] = d

            valid_batch = [j for j in batch if j.get('description')]
            if not valid_batch:
                continue
                
            q.put(("LOG", f"🤖 Sending batch of {len(valid_batch)} jobs to AI ({mode})..."))
            try:
                evaluations = evaluate_jobs_batch_with_ai(
                    cv_text, valid_batch, alignment, mode, 
                    api_keys=api_keys, 
                    online_model=online_model, 
                    offline_model=offline_model,
                    log_callback=lambda msg: q.put(("LOG", msg))
                )
                
                for j in valid_batch:
                    total_eval += 1
                    jid = str(j['job_id'])
                    title = j.get("title", "?")
                    company = j.get("company", "?")
                    q.put(("LOG_LINE", f"[{total_eval}/{len(jobs)}] {title} @ {company}"))
                    
                    if jid in evaluations:
                        res = evaluations[jid]
                        is_match = str(res.get("match", False)).lower() == "true"
                        if is_match:
                            j["reason"] = res.get("reason", "")
                            j["short_description"] = res.get("short_description", "")
                            relevant_jobs.append(j)
                            q.put(("APPEND_LOG", "   ✅ MATCH!"))
                        else:
                            q.put(("APPEND_LOG", f"   ❌ {res.get('reason', '—')}"))
                    else:
                        q.put(("APPEND_LOG", "   ⚠️ AI dropped this job from response."))
                        
                    q.put(("REPORT", _build_report(relevant_jobs, alignment, mode, total_eval, len(jobs))))
                    
            except Exception as e:
                q.put(("LOG", f"❌ AI Batch Error: {e}"))
                if "Ollama" in str(e) or "API keys" in str(e):
                    return
                    
        q.put(("DONE", f"\n{'─'*50}\n✅ Done. {len(relevant_jobs)} matches from {total_eval} evaluated."))
        
    except Exception as e:
        q.put(("ERROR", f"Fatal error: {e}"))

# ── Main pipeline (generator loop) ───────────────────────────────────────
def process_ui(cv_file, query, date_posted, distance, alignment, mode, max_jobs, key1, key2, online_model, offline_model):
    log_lines = []
    report = "*Waiting for results…*"
    
    def format_logs():
        return "\n".join(log_lines)

    if cv_file is None:
        log_lines.append("❌  Please upload or select a CV PDF file.")
        yield format_logs(), report
        return

    cv_path = cv_file if isinstance(cv_file, str) else cv_file.name
    
    msg_queue = queue.Queue()
    worker = threading.Thread(
        target=background_worker, 
        args=(msg_queue, cv_path, query, date_posted, distance, alignment, mode, max_jobs, key1, key2, online_model, offline_model)
    )
    worker.start()
    
    while worker.is_alive() or not msg_queue.empty():
        if _stop.is_set():
            if log_lines and not log_lines[-1].startswith("🛑"):
                log_lines.append("\n🛑 Stopped by user.")
                yield format_logs(), report
            break
            
        try:
            msg_type, msg_content = msg_queue.get(timeout=0.1)
            
            if msg_type == "LOG":
                log_lines.append(msg_content)
                yield format_logs(), report
            elif msg_type == "LOG_LINE":
                log_lines.append(msg_content)
                yield format_logs(), report
            elif msg_type == "APPEND_LOG":
                if log_lines:
                    log_lines[-1] += msg_content
                else:
                    log_lines.append(msg_content)
                yield format_logs(), report
            elif msg_type == "REPORT":
                report = msg_content
                yield format_logs(), report
            elif msg_type == "ERROR":
                log_lines.append(msg_content)
                yield format_logs(), report
                break
            elif msg_type == "DONE":
                log_lines.append(msg_content)
                yield format_logs(), report
                break
                
        except queue.Empty:
            yield gr.update(), gr.update()
            
    if _stop.is_set():
        log_lines.append("\n🛑 Run aborted.")
        yield format_logs(), report

def _build_report(relevant_jobs, alignment, mode, evaluated, total):
    r = "# Relevant Job Opportunities\n\n"
    r += f"**Alignment:** {alignment.capitalize()}  ·  **Mode:** {mode.capitalize()}\n\n"
    r += f"**Evaluated:** {evaluated}/{total}  ·  **Matches:** {len(relevant_jobs)}\n\n---\n\n"
    for j in relevant_jobs:
        r += f"### [{j.get('title')} @ {j.get('company')}]({j.get('job_url')})\n"
        r += f"📍 {j.get('location', 'N/A')}\n\n"
        r += f"**Why it's a fit:** {j.get('short_description')}\n\n"
        r += f"*{j.get('reason')}*\n\n"
        r += f"[🔗 Apply Here]({j.get('job_url')})\n\n---\n\n"
    return r

# ── Gradio UI ─────────────────────────────────────────────────────────────
custom_css = """
#logs-box textarea {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace !important;
    font-size: 12px !important;
    line-height: 1.45 !important;
}
"""

with gr.Blocks(title="LinkedIn CV Matcher", css=custom_css) as demo:
    gr.Markdown("# 🚀 LinkedIn CV Matcher")
    gr.Markdown("Upload your CV, type your job query keywords, and let AI find positions that match.")

    with gr.Row():
        with gr.Column(scale=1):
            cv_input = gr.File(
                label="Upload your CV (PDF)",
                value=DEFAULT_CV_PATH if os.path.exists(DEFAULT_CV_PATH) else None,
            )
            
            with gr.Group():
                query_input = gr.Textbox(label="Keywords Query", placeholder="Enter your boolean query here...", value=DEFAULT_QUERY, lines=2)
                query_html = gr.HTML(value=highlight_query(DEFAULT_QUERY))
                query_input.change(fn=highlight_query, inputs=query_input, outputs=query_html)

            with gr.Accordion("⚙️ Search Arguments & Filters", open=False):
                with gr.Row():
                    date_posted_input = gr.Dropdown(
                        ["Past 24 Hours", "Past Week", "Past Month", "Anytime"], 
                        value="Past Week",
                        label="Date Posted",
                    )
                    distance_input = gr.Dropdown(
                        ["10", "25", "50", "100"],
                        value="100",
                        label="Distance (miles)",
                    )
                with gr.Row():
                    alignment_input = gr.Radio(
                        ["loose", "medium", "strict"], value="medium",
                        label="CV ↔ Requirements Alignment",
                    )
                    mode_input = gr.Radio(
                        ["online", "offline"], value="online",
                        label="AI Model Mode",
                    )

                max_jobs_input = gr.Slider(
                    minimum=0, maximum=1000, step=10, value=0,
                    label="Max Jobs to Evaluate (0 = unlimited)",
                )
            
            with gr.Accordion("⚙️ API Keys & Models", open=False):
                with gr.Row():
                    key1_input = gr.Textbox(label="Gemini Key 1", value=DEFAULT_KEY_1, type="password")
                    key2_input = gr.Textbox(label="Gemini Key 2", value=DEFAULT_KEY_2, type="password")
                with gr.Row():
                    online_model_input = gr.Dropdown(
                        ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.5-flash"], 
                        value="gemini-2.5-flash", 
                        label="Online Model"
                    )
                    offline_model_input = gr.Dropdown(
                        ["qwen3.6:27b", "gemma4:26b"], 
                        value="qwen3.6:27b", 
                        label="Offline Model (Ollama)"
                    )

            with gr.Row():
                run_btn   = gr.Button("▶  Run", variant="primary", scale=2)
                pause_btn = gr.Button("⏸  Pause", interactive=False, scale=1)
                stop_btn  = gr.Button("🛑  Stop", variant="stop", interactive=False, scale=1)

            logs_box = gr.Textbox(
                label="Live Logs",
                lines=20,
                max_lines=20,
                interactive=False,
                autoscroll=True,
                elem_id="logs-box",
            )

        with gr.Column(scale=1):
            output_md = gr.Markdown(value="*Results will appear here…*")

    # ── Wire events ───────────────────────────────────────────────────────
    stop_btn.click(fn=on_stop, outputs=[stop_btn, pause_btn])
    pause_btn.click(fn=on_pause, outputs=[pause_btn])

    run_btn.click(
        fn=on_run_start,
        outputs=[run_btn, pause_btn, stop_btn, logs_box, output_md],
    ).then(
        fn=process_ui,
        inputs=[cv_input, query_input, date_posted_input, distance_input, alignment_input, mode_input, max_jobs_input, key1_input, key2_input, online_model_input, offline_model_input],
        outputs=[logs_box, output_md],
    ).then(
        fn=on_run_end,
        outputs=[run_btn, pause_btn, stop_btn],
    )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
