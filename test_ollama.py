import requests
import json

prompt = """You are an expert technical recruiter evaluating if a candidate is a fit for the provided job(s).

INSTRUCTION: You are in LOOSE mode. Accept the candidate if there is any reasonable partial overlap in skills.

To ensure accurate evaluation, you must think step-by-step.
CRITICAL: You MUST evaluate EVERY SINGLE job provided. Your output must be a JSON array containing exactly one object for every job. Do NOT omit any jobs, even if they are not a match.

Output ONLY a valid JSON array of objects matching this exact schema. Do not output any markdown code blocks or conversational text.
[
  {
      "job_id": "The ID of the job",
      "missing_requirements": "List specifically what required skills or experience the candidate is missing. If none, write 'None'.",
      "match": true/false,
      "reason": "Brief explanation of why it is or isn't a match, based on the missing_requirements.",
      "short_description": "A 1-2 sentence pitch of the job if it's a match, else empty"
  }
]

--- CANDIDATE CV ---


--- JOB 1 ---
Title: VP R&D
Company: Confidential
Description: We are looking for a VP R&D to lead our engineering team. Must have 10+ years experience in software engineering and management.
ID: 12345
"""

url = "http://localhost:11434/api/generate"
payload = {
    "model": "qwen3.6:27b",
    "prompt": prompt,
    "stream": False
}
print("Sending request to Ollama...")
resp = requests.post(url, json=payload).json()
print("RAW RESPONSE:")
print(resp.get("response", "No response field"))
