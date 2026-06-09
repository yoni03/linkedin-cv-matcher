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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# CV text cache
_cv_cache = {}

def build_search_url(query, date_posted="Past Week", distance=100):
    base_url = "https://www.linkedin.com/jobs/search/"
    
    # Map readable strings to LinkedIn time filters (seconds)
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
        text += page.extract_text() + "\n"
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
        # Wait up to 10 seconds for it to bind to port
        for _ in range(10):
            time.sleep(1)
            if check_ollama_running():
                return True
    except Exception as e:
        logging.error(f"Failed to start Ollama automatically: {e}")
    return False

def evaluate_jobs_batch_with_ai(cv_text, jobs_batch, alignment_level, mode="online", api_keys=None, online_model="gemini-2.0-flash", offline_model="llama3", log_callback=None):
    """
    Evaluates a batch of jobs in a single prompt.
    """
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
        payload = {
            "model": offline_model,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        try:
            response = requests.post(url, json=payload, timeout=300)
            if response.status_code == 200:
                data = response.json()
                response_str = data.get("response", "[]")
                try:
                    results = json.loads(response_str)
                except json.JSONDecodeError:
                    log_callback(f"⚠️ JSON Decode Error (Offline). Raw AI Output:\n{response_str[:500]}")
                    results = []
                
                # Robust parsing: LLMs sometimes wrap the JSON array in an object (e.g. {"jobs": [...]})
                if isinstance(results, dict):
                    for k, v in results.items():
                        if isinstance(v, list):
                            results = v
                            break
                    else:
                        results = [results]
                        
                return {str(r.get("job_id")): r for r in results if isinstance(r, dict)}
            else:
                log_callback(f"❌ Ollama API Error: Status {response.status_code}")
                raise RuntimeError(f"Ollama API returned status: {response.status_code}. Are you sure the model '{offline_model}' is pulled? Run 'ollama pull {offline_model}'.")
        except Exception as e:
            log_callback(f"❌ Offline Evaluation Error: {str(e)}")
            raise RuntimeError(f"Offline AI evaluation failed: {e}")

    # Online mode: try each key
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
                return {str(r.get("job_id")): r for r in results if isinstance(r, dict)}
            except Exception as e:
                error_str = str(e).lower()
                log_callback(f"⚠️ API Error on Key {i+1}: {str(e)[:150]}")
                if "429" in error_str or "quota" in error_str:
                    retries += 1
                    wait = 15 * retries
                    log_callback(f"⏳ Rate limited! Sleeping for {wait}s before retry {retries}/3...")
                    time.sleep(wait)
                elif "403" in error_str or "api key" in error_str or "404" in error_str:
                    log_callback(f"❌ API Key {i+1} is invalid or lacks access.")
                    break
                else:
                    raise RuntimeError(f"AI error: {e}")

    raise RuntimeError("All configured API keys exhausted or rate-limited.")
