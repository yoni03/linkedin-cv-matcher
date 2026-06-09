# LinkedIn CV Matcher 🚀

An autonomous, entirely local, and highly privacy-focused application that automatically scrapes LinkedIn jobs and compares them against your CV using advanced offline LLMs (like `phi4` via Ollama) or cloud-based AI.

## Features

- **Deep CV Parsing:** Automatically extracts your exact skills and experience from your CV.
- **LinkedIn Integration:** Scrapes recent job listings directly from LinkedIn without an API key.
- **Offline AI Pipeline:** Fully integrated with Ollama to run offline models (e.g. `phi4`) entirely locally to keep your CV strictly private. No data sent to the cloud.
- **Strict Alignment Logic:** The AI analyzes each job, determines if you are a match, and explicitly lists missing requirements.
- **Dual Mode:** Support for both Offline (Ollama) and Online (Gemini 2.0 Flash) evaluations.

## Installation

The application is pre-packaged for both **Mac** and **Windows** so you don't need to install Python or use the command line to run it!

1. Go to the [Releases](https://github.com/yoni03/linkedin-cv-matcher/releases/latest) page.
2. Download the appropriate file for your operating system:
   - **Mac:** Download `LinkedIn_CV_Matcher_Mac.zip`, extract it, and launch the `LinkedIn CV Matcher.app` application. *(Note: You may need to Right Click -> Open on the first launch to bypass macOS security warnings).*
   - **Windows:** Download `LinkedIn_CV_Matcher_Windows.zip`, extract the folder, and run the `LinkedIn_CV_Matcher.exe` file.

### Running from Source (For Developers)
If you prefer to run the application directly from the Python source code:
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

## Usage & Configuration
Your settings (CV path, default queries, and optional Gemini API keys) are safely and persistently stored in `~/.linkedin_matcher_config.json` after your first run. They are **never** tracked by Git.

### Offline Mode (Ollama)
If you want to use the app in strict privacy mode:
1. Ensure you have [Ollama](https://ollama.com) installed.
2. Open the "⚙️ API Keys & Models" tab.
3. Click **"Pull Selected Model"** to download the default offline model (`phi4`).
4. Select "offline" mode and evaluate!
