# LinkedIn CV Matcher 🚀

An autonomous, entirely local, and highly privacy-focused application that automatically scrapes LinkedIn jobs and compares them against your CV using advanced offline LLMs (like `phi4` via Ollama) or cloud-based AI.

## Features

- **Deep CV Parsing:** Automatically extracts your exact skills and experience from your CV.
- **LinkedIn Integration:** Scrapes recent job listings directly from LinkedIn without an API key.
- **Offline AI Pipeline:** Fully integrated with Ollama to run offline models (e.g. `phi4`) entirely locally to keep your CV strictly private. No data sent to the cloud.
- **Strict Alignment Logic:** The AI analyzes each job, determines if you are a match, and explicitly lists missing requirements.
- **Dual Mode:** Support for both Offline (Ollama) and Online (Gemini 2.0 Flash) evaluations.

## Installation

### Mac Users
1. Ensure you have Python 3.11+ installed.
2. Clone this repository.
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python app.py
   ```

### Windows Users
A pre-compiled `.exe` file is automatically built via GitHub Actions and available in the **Releases** tab.
1. Go to the [Releases](https://github.com/yourusername/linkedin-cv-matcher/releases) page.
2. Download the latest `LinkedIn_CV_Matcher_Windows.zip and LinkedIn_CV_Matcher_Mac.zip`.
3. Extract the folder and run `LinkedIn_CV_Matcher.exe`.

## Usage & Configuration
Your settings (CV path, default queries, and optional Gemini API keys) are safely and persistently stored in `~/.linkedin_matcher_config.json` after your first run. They are **never** tracked by Git.

### Offline Mode (Ollama)
If you want to use the app in strict privacy mode:
1. Ensure you have [Ollama](https://ollama.com) installed.
2. Open the "⚙️ API Keys & Models" tab.
3. Click **"Pull Selected Model"** to download the default offline model (`phi4`).
4. Select "offline" mode and evaluate!
