import time
import app
import json
import os

def run_test():
    print("--- Starting End-to-End Pipeline Test ---")
    
    cv_text = "Software Engineer with 5 years of experience in Python, Kubernetes, Docker, and React. Managed a team of 3 engineers. Built scalable web applications."
    
    print("\n1. Fetching jobs from LinkedIn (query: 'Python Engineer', max_jobs: 3)...")
    fetch_start = time.time()
    jobs = app.fetch_jobs("Python Engineer", date_posted="Past 24 Hours", max_jobs=3)
    
    if not jobs:
        print("Error: Could not fetch jobs from LinkedIn.")
        return
        
    for job in jobs:
        job['description'] = app.fetch_job_description(job['job_id'])
        
    fetch_time = time.time() - fetch_start
    print(f"   Fetching took {fetch_time:.2f} seconds.")

    # Load keys
    config = app.load_config()
    api_keys = []
    if config.get("key1"): api_keys.append(config.get("key1"))
    if config.get("key2"): api_keys.append(config.get("key2"))

    # Test Offline
    print("\n2. Evaluating batch of 3 jobs with OFFLINE (phi4)...")
    eval_start = time.time()
    results_off = app.evaluate_jobs_batch_with_ai(
        cv_text=cv_text, jobs_batch=jobs, alignment_level="medium", mode="offline",
        api_keys=[], online_model="gemini-2.0-flash", offline_model="phi4"
    )
    print(f"   Offline Evaluation took {time.time() - eval_start:.2f} seconds.")
    for r in results_off.values(): print(f"   - Match: {r.get('match')}")

    # Test Online
    print("\n3. Evaluating batch of 3 jobs with ONLINE (gemini-2.0-flash)...")
    if not api_keys:
        print("   Skipping online test because no API keys found in config.")
    else:
        eval_start = time.time()
        results_on = app.evaluate_jobs_batch_with_ai(
            cv_text=cv_text, jobs_batch=jobs, alignment_level="medium", mode="online",
            api_keys=api_keys, online_model="gemini-2.0-flash", offline_model="phi4"
        )
        print(f"   Online Evaluation took {time.time() - eval_start:.2f} seconds.")
        for r in results_on.values(): print(f"   - Match: {r.get('match')}")

if __name__ == "__main__":
    run_test()
