import requests
import time
import json
import re

prompt = """
You are an expert technical recruiter evaluating if a candidate is a fit for the provided job(s).

INSTRUCTION: You are in MEDIUM mode. Require a solid match on core skills, but allow flexibility on years of experience or secondary tools.

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
{cv}

{job}
"""

def test_model_speed(model_name, cv_length_words, job_length_words):
    print(f"Testing {model_name} with CV ({cv_length_words} words) and Job ({job_length_words} words)...")
    
    cv_text = "Software Engineer with 10 years of experience in Python, Go, and Kubernetes. " * (cv_length_words // 12)
    job_text = "--- JOB 1 ---\njob_id: 12345\nTitle: Senior DevOps Engineer\nRequirements: 5+ years of Python, Docker, Kubernetes. " * (job_length_words // 13)
    
    final_prompt = prompt.format(cv=cv_text, job=job_text)
    
    payload = {
        "model": model_name,
        "prompt": final_prompt,
        "stream": False,
        "options": {"num_ctx": 8192} # Test with 8192 instead of 16384 to see if it's faster
    }
    
    start_time = time.time()
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=300)
        end_time = time.time()
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Time Taken: {end_time - start_time:.2f} seconds")
            print(f"Response: {data.get('response', '')[:100]}...")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    # Test with typical lengths
    test_model_speed("qwen3.6:27b", 800, 300)
    test_model_speed("qwen3.6:27b", 1500, 500)
