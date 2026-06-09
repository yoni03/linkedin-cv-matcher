import time
import app
import json

def run_benchmark():
    CV_PATH = "/private/var/folders/2p/53y85p250vv3bszq1tmcvh3r0000gn/T/gradio/b168a89243ffc8b567303e2bd8ae39ad971a39169aa714bd6d186ebe83c11173/CV_YoniH_070526.pdf"
    print("1. Extracting CV...")
    cv_text = app.extract_cv_text(CV_PATH)
    
    print("2. Fetching 10 jobs...")
    jobs = app.fetch_jobs("", date_posted="Past 24 Hours", max_jobs=10)
    for job in jobs:
        job['description'] = app.fetch_job_description(job['job_id'])
    
    # We will slice to ensure exactly 10 if there are more
    jobs = jobs[:10]
    print(f"Found {len(jobs)} valid jobs.")
    
    print("Starting Ollama...")
    app.start_ollama_if_needed()
    
    models = ["phi4", "gemma4:12b"]
    
    # Process in batches of 3
    batch_size = 3
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    
    for model in models:
        print(f"\n=========================================")
        print(f"Testing {model} ...")
        print(f"=========================================")
        start_time = time.time()
        
        all_results = {}
        for i, batch in enumerate(batches):
            print(f"  -> Batch {i+1}/{len(batches)}...")
            res = app.evaluate_jobs_batch_with_ai(
                cv_text=cv_text,
                jobs_batch=batch,
                alignment_level="strict",
                mode="offline",
                api_keys=[],
                online_model="gemini-2.0-flash",
                offline_model=model,
                log_callback=lambda x: None
            )
            all_results.update(res)
            
        end_time = time.time()
        print(f"\n[TIME] {model} took {end_time - start_time:.2f} seconds total.")
        
        # Save output for review
        with open(f"results_{model}.json", "w") as f:
            json.dump(all_results, f, indent=2)

if __name__ == "__main__":
    run_benchmark()
