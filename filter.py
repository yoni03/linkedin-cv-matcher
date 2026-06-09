import json

def score_job(title):
    title = title.lower()
    score = 0
    
    # Executive / Senior Management (matches Head of R&D / Engineering)
    if any(k in title for k in ["vp r&d", "vp engineering", "vice president", "head of r&d", "head of engineering", "director of engineering", "director of hw", "director of sw", "director of hardware", "director of software"]):
        score += 10
    
    # Group / Department Level Management
    if any(k in title for k in ["group manager", "department manager", "group lead"]):
        score += 8
        
    # Program / Project Management (matches his TPM/PM background)
    if any(k in title for k in ["tech program manager", "technical project manager", "program manager", "tpm", "project director"]):
        score += 7
        
    # System Engineering Management
    if any(k in title for k in ["head of systems", "system team leader", "system engineer", "systems integration", "system lead", "system manager"]):
        score += 6
        
    # Domain keywords matches (AI, Robotics, Automotive, etc.)
    if any(k in title for k in ["ai ", "robotics", "automotive", "hardware", "hw", "sw", "software", "machine learning"]):
        score += 3
        
    # Negative keywords (completely irrelevant)
    if any(k in title for k in ["sales", "marketing", "legal", "finance", "hr", "counsel", "account executive", "recruiter", "talent", "support", "procurement", "real estate", "office manager", "risk", "compliance", "assistant", "student", "intern", "junior"]):
        score -= 20
        
    return score

with open("/Users/yonih/.gemini/antigravity/scratch/linkedin_jobs_data.json", "r") as f:
    jobs = json.load(f)

scored_jobs = []
for job in jobs:
    score = score_job(job["title"])
    if score >= 6:
        job["score"] = score
        scored_jobs.append(job)

scored_jobs.sort(key=lambda x: x["score"], reverse=True)

with open("/Users/yonih/.gemini/antigravity/scratch/job_matches.md", "w") as f:
    for job in scored_jobs[:20]:
        t = job["title"]
        u = job["job_url"]
        c = job["company"]
        l = job["location"]
        s = job["score"]
        f.write(f"### [{t}]({u})\n")
        f.write(f"- **Company**: {c}\n")
        f.write(f"- **Location**: {l}\n\n")

print(f"Found {len(scored_jobs)} matches.")
