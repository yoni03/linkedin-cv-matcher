import requests
from bs4 import BeautifulSoup
import urllib.parse
import json
import time
import sys
import os
import hashlib
import argparse
import logging
import subprocess
from pypdf import PdfReader
import google.generativeai as genai
import gradio as gr
import threading
import queue
import concurrent.futures

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CONFIG_FILE = os.path.expanduser("~/.linkedin_matcher_config.json")

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_config(updates):
    config = load_config()
    config.update(updates)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        logging.warning(f"Could not save config: {e}")

def load_saved_cv_path():
    path = load_config().get("cv_path")
    if path and os.path.exists(path):
        return path
    return None

def save_cv_path(file_obj):
    if not file_obj:
        return
    path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
    save_config({"cv_path": path})

DEFAULT_QUERY = '"CEO" OR "Chief Executive Officer" OR "VP" OR "Vice President" OR "SVP" OR "Director" OR "Head of" OR "Group manager" OR "Group lead" OR "group leader" OR ("system" AND ("leader" OR "lead" OR "manager"))'

# CV text cache
_cv_cache = {}

# ── Shared run-control state ──────────────────────────────────────────────
_stop = threading.Event()
_pause = threading.Event()
_pause.set()  # not paused initially

def _reset_controls():
    _stop.clear()
    _pause.set()

# ── LinkedIn Scraper Engine ───────────────────────────────────────────────
def build_search_url(query, date_posted="Past Week", distance=100):
    base_url = "https://www.linkedin.com/jobs/search/"
    
    time_filters = {
        "Past 24 Hours": "r86400",
        "Past Week": "r604800",
        "Past Month": "r2592000",
        "Anytime": ""
    }
    
    params = {
        "currentJobId": "4425170722",
        "distance": str(distance),
        "geoId": "101620260",
        "keywords": query,
        "origin": "JOB_SEARCH_PAGE_JOB_FILTER"
    }
    
    f_tpr = time_filters.get(date_posted, "")
    if f_tpr:
        params["f_TPR"] = f_tpr
        
    return f"{base_url}?{urllib.parse.urlencode(params)}"

def parse_url(url):
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    for k in params:
        params[k] = params[k][0]
    return params

def fetch_jobs(query, date_posted="Past Week", distance=100, max_jobs=None):
    base_url = build_search_url(query, date_posted, distance)
    params = parse_url(base_url)
    start = 0
    api_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    all_jobs = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    session = requests.Session()
    session.headers.update(headers)

    while True:
        params['start'] = start
        logging.info(f"Fetching jobs list starting at {start}...")
        try:
            response = session.get(api_url, params=params, timeout=10)
            if response.status_code == 429:
                logging.warning("Rate limit hit (429) on job search. Sleeping for 10 seconds.")
                time.sleep(10)
                continue
            elif response.status_code != 200:
                break

            soup = BeautifulSoup(response.text, "html.parser")
            job_cards = soup.find_all("li")

            if not job_cards:
                break

            for card in job_cards:
                job_data = {}
                base_card = card.find("div", class_="base-search-card")
                if base_card and base_card.has_attr("data-entity-urn"):
                    urn = base_card["data-entity-urn"]
                    job_data["job_id"] = urn.split(":")[-1]
                else:
                    continue

                title_tag = card.find("h3", class_="base-search-card__title")
                if title_tag:
                    job_data["title"] = title_tag.get_text(strip=True)

                company_tag = card.find("h4", class_="base-search-card__subtitle")
                if company_tag:
                    job_data["company"] = company_tag.get_text(strip=True)

                location_tag = card.find("span", class_="job-search-card__location")
                if location_tag:
                    job_data["location"] = location_tag.get_text(strip=True)

                link_tag = card.find("a", class_="base-card__full-link")
                if link_tag and link_tag.has_attr("href"):
                    job_data["job_url"] = link_tag["href"].split("?")[0]

                all_jobs.append(job_data)

            if max_jobs and len(all_jobs) >= max_jobs:
                all_jobs = all_jobs[:max_jobs]
                break

            start += len(job_cards)
            time.sleep(2)
        except Exception as e:
            logging.error(f"Error fetching job list: {e}")
            break

    return all_jobs

def fetch_job_description(job_id):
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            if desc_div:
                return desc_div.get_text(separator="\n", strip=True)
    except Exception as e:
        pass
    return ""

# ── CV & AI Matcher Engine ────────────────────────────────────────────────
def _file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def extract_cv_text(pdf_path):
    pdf_path = os.path.expanduser(pdf_path)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"CV file not found at {pdf_path}")

    fhash = _file_hash(pdf_path)
    if fhash in _cv_cache:
        return _cv_cache[fhash]

    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + " "
            
    # Extremely aggressive token compression for the CV
    import re
    text = re.sub(r'\s+', ' ', text) # Compress all newlines and multiple spaces into a single space
    text = re.sub(r'[^a-zA-Z0-9\s.,;:\-@/()\[\]+*]', '', text) # Strip emojis, weird bullets, and unhelpful formatting
    text = text.strip()
    
    _cv_cache[fhash] = text
    return text

def check_ollama_running():
    try:
        response = requests.get("http://localhost:11434/", timeout=2)
        return response.status_code == 200
    except:
        return False

def start_ollama_if_needed():
    if check_ollama_running():
        return True
    try:
        logging.info("Ollama is not running. Attempting to start it automatically via macOS 'open -a Ollama'...")
        subprocess.Popen(["open", "-a", "Ollama"])
        for _ in range(10):
            time.sleep(1)
            if check_ollama_running():
                return True
    except Exception as e:
        logging.error(f"Failed to start Ollama automatically: {e}")
    return False

def evaluate_jobs_batch_with_ai(cv_text, jobs_batch, alignment_level, mode="online", api_keys=None, online_model="gemini-2.0-flash", offline_model="qwen3.6:27b", log_callback=None):
    if log_callback is None:
        log_callback = lambda m: None

    jobs_text = ""
    for j in jobs_batch:
        jobs_text += f"\n--- JOB ID: {j['job_id']} | Title: {j.get('title')} ---\n"
        jobs_text += j.get('description', 'No description')[:3000] + "\n"

    strictness_instructions = ""
    if alignment_level == "strict":
        strictness_instructions = (
            "CRITICAL INSTRUCTION: You are in STRICT mode. You must be EXTREMELY RUTHLESS. "
            "You MUST REJECT the candidate (match: false) if ANY of the following apply:\n"
            "1. The candidate lacks the exact years of experience required for the seniority level.\n"
            "2. The candidate does not have prior experience in the exact core domain or industry if explicitly required.\n"
            "3. The job requires a mandatory primary technology or skill that the candidate does not have.\n"
            "If there is any doubt, or if the candidate is only a 'partial' fit, you MUST output false."
        )
    elif alignment_level == "medium":
        strictness_instructions = (
            "INSTRUCTION: You are in MEDIUM mode. The candidate must have the core skills and equivalent seniority, "
            "but minor domain or secondary technology mismatches are acceptable."
        )
    else:
        strictness_instructions = (
            "INSTRUCTION: You are in LOOSE mode. Accept the candidate if there is any reasonable partial overlap in skills."
        )

    prompt = f"""
You are an expert technical recruiter evaluating if a candidate is a fit for the provided job(s).

{strictness_instructions}

To ensure accurate evaluation, you must think step-by-step. 
CRITICAL: You MUST evaluate EVERY SINGLE job provided. Your output must be a JSON array containing exactly one object for every job. Do NOT omit any jobs, even if they are not a match.

Output ONLY a valid JSON array of objects matching this exact schema. Do not output any markdown code blocks or conversational text.
[
  {{
      "job_id": "The ID of the job",
      "missing_requirements": "List specifically what required skills or experience the candidate is missing. If none, write 'None'.",
      "match": true/false,
      "reason": "Brief explanation of why it is or isn't a match, based on the missing_requirements.",
      "short_description": "A 1-2 sentence pitch of the job if it's a match, else empty"
  }}
]

--- CANDIDATE CV ---
{cv_text}

{jobs_text}
"""

    if mode == "offline":
        url = "http://localhost:11434/api/generate"
        import re
        payload = {
            "model": offline_model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": 16384}
        }
        try:
            response = requests.post(url, json=payload, timeout=900)
            if response.status_code == 200:
                data = response.json()
                original_response = data.get("response", "").strip()
                response_str = original_response
                
                # Robustly extract JSON from markdown or conversational text
                import re
                match = re.search(r'```json(.*?)```', response_str, re.DOTALL)
                if match:
                    response_str = match.group(1).strip()
                else:
                    match = re.search(r'```(.*?)```', response_str, re.DOTALL)
                    if match:
                        response_str = match.group(1).strip()
                        
                start_idx = -1
                for i, c in enumerate(response_str):
                    if c in '[{':
                        start_idx = i
                        break
                if start_idx != -1:
                    end_idx = -1
                    for i in range(len(response_str)-1, -1, -1):
                        if response_str[i] in ']}':
                            end_idx = i
                            break
                    if end_idx != -1 and end_idx >= start_idx:
                        response_str = response_str[start_idx:end_idx+1]
                else:
                    response_str = "[]"
                        
                try:
                    results = json.loads(response_str)
                except json.JSONDecodeError:
                    log_callback(f"⚠️ JSON Decode Error (Offline). Raw AI Output:\n{response_str[:500]}")
                    results = []
                
                if isinstance(results, dict):
                    for k, v in results.items():
                        if isinstance(v, list):
                            results = v
                            break
                    else:
                        results = [results]
                        
                parsed_results = {str(r.get("job_id")): r for r in results if isinstance(r, dict)}
                
                # Robustness for single-batch offline models that forget the job_id
                batch_job_id = str(jobs_batch[0]["job_id"]) if jobs_batch else ""
                if len(jobs_batch) == 1 and len(results) == 1 and isinstance(results[0], dict):
                    if not results[0].get("job_id") or str(results[0].get("job_id")) != batch_job_id:
                        results[0]["job_id"] = batch_job_id
                        parsed_results[batch_job_id] = results[0]
                        
                if batch_job_id and batch_job_id not in parsed_results:
                     # EXTREME FALLBACK: Force evaluation to avoid dropping the job from the UI
                     parsed_results[batch_job_id] = {
                         "job_id": batch_job_id,
                         "missing_requirements": f"AI model failed to evaluate (Empty Output).",
                         "match": False,
                         "reason": "The local AI returned an empty response. Try lowering batch size or switching models.",
                         "short_description": ""
                     }
                     
                return parsed_results
            else:
                log_callback(f"❌ Ollama API Error: Status {response.status_code}")
                raise RuntimeError(f"Ollama API returned status: {response.status_code}. Are you sure the model '{offline_model}' is pulled?")
        except Exception as e:
            log_callback(f"❌ Offline Evaluation Error: {str(e)}")
            raise RuntimeError(f"Offline AI evaluation failed: {e}")

    if not api_keys:
        raise RuntimeError("No API keys provided for online mode.")
        
    for i, key in enumerate(api_keys):
        key = key.strip()
        if not key: continue
        
        retries = 0
        max_retries = 3
        while retries < max_retries:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(online_model)
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                response_str = response.text
                try:
                    results = json.loads(response_str)
                except json.JSONDecodeError:
                    log_callback(f"⚠️ JSON Decode Error (Online). Raw AI Output:\n{response_str[:500]}")
                    results = []
                parsed_results = {str(r.get("job_id")): r for r in results if isinstance(r, dict)}
                
                # Robustness for single-batch models that forget the job_id
                if len(jobs_batch) == 1 and len(results) == 1 and isinstance(results[0], dict):
                    batch_job_id = str(jobs_batch[0]["job_id"])
                    if not results[0].get("job_id") or str(results[0].get("job_id")) != batch_job_id:
                        results[0]["job_id"] = batch_job_id
                        parsed_results[batch_job_id] = results[0]
                        
                return parsed_results
            except Exception as e:
                error_str = str(e).lower()
                
                # Check for hard quota/billing limits first
                if "quota" in error_str and "billing" in error_str:
                    log_callback(f"❌ Key {i+1} has exhausted its hard billing quota. Instantly switching keys...")
                    break
                    
                log_callback(f"⚠️ API Error on Key {i+1}: {str(e)[:150]}")
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    retries += 1
                    wait = 30 * retries  # Increased wait time for standard rate limits (30s, 60s, 90s)
                    log_callback(f"⏳ Rate limited! Sleeping for {wait}s before retry {retries}/3...")
                    time.sleep(wait)
                elif "403" in error_str or "api key" in error_str or "404" in error_str:
                    log_callback(f"❌ API Key {i+1} is invalid or lacks access.")
                    break
                else:
                    break

    raise RuntimeError("All configured API keys exhausted or rate-limited.")

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
        batch_size = 10 if mode == "online" else 3
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

    save_config({'query': query, 'key1': key1, 'key2': key2})

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

def open_ollama_download():
    import webbrowser
    webbrowser.open("https://ollama.com/download")
    return "Opened https://ollama.com/download in your browser."

def pull_ollama_model(model_name):
    yield f"🚀 Starting pull for {model_name}...\nThis may take a few minutes depending on your internet connection.\n\n"
    if not start_ollama_if_needed():
        yield "❌ Error: Ollama is not installed or not running. Please install Ollama first."
        return

    try:
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        output = f"🚀 Pulling {model_name}...\n\n"
        yield output
        
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                output += clean_line + "\n"
                # keep it bounded so browser doesn't lag
                yield output[-3000:]
            
        process.wait()
        if process.returncode == 0:
            output += f"\n✅ Successfully pulled {model_name}!"
        else:
            output += f"\n❌ Failed to pull model. Exit code {process.returncode}"
        yield output[-3000:]
    except Exception as e:
        yield f"❌ Error: {e}"

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
body, .gradio-container {
    margin-top: 45px !important;
}
"""

config = load_config()
init_query = config.get('query', DEFAULT_QUERY)
init_key1 = config.get('key1', '')
init_key2 = config.get('key2', '')

with gr.Blocks(title="LinkedIn CV Matcher", css=custom_css) as demo:
    gr.Markdown("# 🚀 LinkedIn CV Matcher")
    gr.Markdown("Upload your CV, type your job query keywords, and let AI find positions that match.")

    with gr.Row():
        with gr.Column(scale=1):
            cv_input = gr.File(
                label="Upload your CV (PDF)",
                value=load_saved_cv_path(),
            )
            cv_input.change(fn=save_cv_path, inputs=[cv_input])
            
            with gr.Group():
                query_input = gr.Textbox(label="Keywords Query", placeholder="Enter your boolean query here...", value=init_query, lines=2)
                query_html = gr.HTML(value=highlight_query(init_query))
                query_input.change(fn=highlight_query, inputs=query_input, outputs=query_html)

            with gr.Accordion("⚙️ Search Arguments & Filters", open=False):
                with gr.Row():
                    date_posted_input = gr.Dropdown(
                        ["Past 24 Hours", "Past Week", "Past Month", "Anytime"], 
                        value="Past 24 Hours",
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
                        ["online", "offline"], value="offline",
                        label="AI Model Mode",
                    )

                max_jobs_input = gr.Slider(
                    minimum=0, maximum=1000, step=10, value=0,
                    label="Max Jobs to Evaluate (0 = unlimited)",
                )
            
            with gr.Accordion("⚙️ API Keys & Models", open=False):
                with gr.Row():
                    key1_input = gr.Textbox(label="Gemini Key 1", value=init_key1, type="password")
                    key2_input = gr.Textbox(label="Gemini Key 2", value=init_key2, type="password")
                with gr.Row():
                    online_model_input = gr.Dropdown(
                        ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.5-flash"], 
                        value="gemini-2.5-flash", 
                        label="Online Model"
                    )
                    offline_model_input = gr.Dropdown(
                        ["qwen3.6:27b", "phi4"], 
                        value="phi4", 
                        label="Offline Model (Ollama)",
                    )
                    
            with gr.Accordion("🛠️ Setup & Maintenance", open=False):
                gr.Markdown("""
                **Online Mode Setup:**
                Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey) and paste it above.
                
                **Offline Mode Setup:**
                Requires Ollama. Click below to download it, install it, and then pull your desired model.
                """)
                with gr.Row():
                    install_ollama_btn = gr.Button("1. ⬇️ Download Ollama App")
                    pull_model_btn = gr.Button("2. 📥 Pull Selected Offline Model", variant="primary")

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
    
    install_ollama_btn.click(fn=open_ollama_download, outputs=[logs_box])
    pull_model_btn.click(fn=pull_ollama_model, inputs=[offline_model_input], outputs=[logs_box])

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
