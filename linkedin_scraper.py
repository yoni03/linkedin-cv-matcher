import requests
from bs4 import BeautifulSoup
import urllib.parse
import json
import time
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_url(url):
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    # parse_qs returns a list for each value, we take the first item
    for k in params:
        params[k] = params[k][0]
    return params

def fetch_jobs(base_url, max_jobs=None):
    params = parse_url(base_url)
    
    # Always start at 0 to get the full list, ignoring any 'start' parameter in the copied URL
    start = 0
    
    # Endpoint for guest job search
    api_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    all_jobs = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    while True:
        params['start'] = start
        logging.info(f"Fetching jobs starting at {start}...")
        
        try:
            response = session.get(api_url, params=params, timeout=10)
            
            if response.status_code == 429:
                logging.warning("Rate limit hit (429). Sleeping for 10 seconds.")
                time.sleep(10)
                continue
            elif response.status_code != 200:
                logging.error(f"Failed to fetch. Status code: {response.status_code}")
                break
                
            soup = BeautifulSoup(response.text, "html.parser")
            job_cards = soup.find_all("li")
            
            if not job_cards:
                logging.info("No more jobs found.")
                break
                
            for card in job_cards:
                job_data = {}
                
                # Job ID
                base_card = card.find("div", class_="base-search-card")
                if base_card and base_card.has_attr("data-entity-urn"):
                    urn = base_card["data-entity-urn"]
                    job_data["job_id"] = urn.split(":")[-1]
                else:
                    continue
                    
                # Title
                title_tag = card.find("h3", class_="base-search-card__title")
                if title_tag:
                    job_data["title"] = title_tag.get_text(strip=True)
                    
                # Company
                company_tag = card.find("h4", class_="base-search-card__subtitle")
                if company_tag:
                    job_data["company"] = company_tag.get_text(strip=True)
                    company_link = company_tag.find("a")
                    if company_link and company_link.has_attr("href"):
                        job_data["company_url"] = company_link["href"]
                
                # Location
                location_tag = card.find("span", class_="job-search-card__location")
                if location_tag:
                    job_data["location"] = location_tag.get_text(strip=True)
                    
                # Date
                date_tag = card.find("time")
                if date_tag and date_tag.has_attr("datetime"):
                    job_data["date_posted"] = date_tag["datetime"]
                    
                # Link
                link_tag = card.find("a", class_="base-card__full-link")
                if link_tag and link_tag.has_attr("href"):
                    # Strip tracking parameters
                    clean_url = link_tag["href"].split("?")[0]
                    job_data["job_url"] = clean_url
                    
                all_jobs.append(job_data)
                
            logging.info(f"Fetched {len(job_cards)} jobs on this page. Total so far: {len(all_jobs)}")
            
            if max_jobs and len(all_jobs) >= max_jobs:
                logging.info(f"Reached target max jobs ({max_jobs}). Stopping.")
                all_jobs = all_jobs[:max_jobs]
                break
                
            # Increment by the number of jobs returned (usually 25)
            start += len(job_cards)
            
            # Be polite to the server
            time.sleep(2)
            
        except Exception as e:
            logging.error(f"Error fetching jobs: {e}")
            break
            
    return all_jobs

if __name__ == "__main__":
    url = "https://www.linkedin.com/jobs/search/?currentJobId=4425170722&distance=25&f_TPR=r604800&geoId=101620260&keywords=%22CEO%22%20OR%20%22Chief%20Executive%20Officer%22%20OR%20%22VP%22%20OR%20%22Vice%20President%22%20OR%20%22SVP%22%20OR%20%22Director%22%20OR%20%22Head%20of%22%20OR%20%22Group%20manager%22%20OR%20%22Group%20lead%22%20OR%20%22group%20leader%22%20OR%20(%22system%22%20AND%20(%22leader%22%20OR%20%22lead%22%20OR%20%22manager%22))&origin=JOB_SEARCH_PAGE_JOB_FILTER&start=150"
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        
    logging.info(f"Starting scrape for URL: {url}")
    
    # Fetch ALL jobs without artificial limit
    jobs = fetch_jobs(url, max_jobs=None)
    
    output_file = "linkedin_jobs_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=4, ensure_ascii=False)
        
    logging.info(f"Saved {len(jobs)} jobs to {output_file}")
