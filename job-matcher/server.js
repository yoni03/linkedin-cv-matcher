const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const { spawn } = require('child_process');
const fs = require('fs').promises;
const path = require('path');
const { GoogleGenAI } = require('@google/genai');
const crypto = require('crypto');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 3000;

// Initialize Gemini
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Configure Multer for PDF uploads
const upload = multer({ dest: 'uploads/' });

app.use(express.static('public'));
app.use(express.json());

app.post('/api/match-jobs', upload.single('cv'), async (req, res) => {
    try {
        const url = req.body.url;
        if (!url || !req.file) {
            return res.status(400).json({ error: 'URL and CV file are required' });
        }

        // 1. Extract Text from PDF
        const pdfBuffer = await fs.readFile(req.file.path);
        const pdfData = await pdfParse(pdfBuffer);
        const cvText = pdfData.text;

        // Clean up uploaded file
        await fs.unlink(req.file.path);

        // 2. Run Python Scraper
        const scrapeId = crypto.randomBytes(8).toString('hex');
        const outputJsonPath = path.join(__dirname, `jobs_${scrapeId}.json`);

        const pythonProcess = spawn('python3', [
            path.join(__dirname, 'linkedin_scraper.py'), 
            url, 
            outputJsonPath
        ]);

        await new Promise((resolve, reject) => {
            pythonProcess.on('close', (code) => {
                if (code === 0) resolve();
                else reject(new Error(`Scraper exited with code ${code}`));
            });
        });

        // 3. Read Scraped Jobs
        const jobsData = await fs.readFile(outputJsonPath, 'utf-8');
        const jobs = JSON.parse(jobsData);
        
        // Clean up jobs json file
        await fs.unlink(outputJsonPath).catch(console.error);

        if (jobs.length === 0) {
            return res.json({ matches: [] });
        }

        // 4. Use LLM to match and generate reports
        const prompt = `You are an expert technical recruiter and career coach.
I am providing a candidate's CV and a list of job postings scraped from LinkedIn in JSON format.
Analyze the CV and evaluate the fit for EACH job.
Filter out any jobs that are clearly a terrible fit.
For the remaining relevant jobs, generate a JSON array of objects. Each object must have:
- "job_id": The id of the job.
- "title": Job title.
- "company": Company name.
- "location": Job location.
- "job_url": The link to apply.
- "quick_report": A 2-3 sentence summary evaluating the candidate's fit based on their CV and the job title. Explain why they are a good match or what they might be missing.

CV Text:
"""
${cvText.substring(0, 10000)}
"""

Job Postings (JSON):
"""
${JSON.stringify(jobs)}
"""

Return ONLY a valid JSON array of the relevant job objects, nothing else.`;

        const response = await ai.models.generateContent({
            model: 'gemini-2.5-pro',
            contents: prompt,
            config: {
                 responseMimeType: "application/json"
            }
        });
        
        const rawResponse = response.text;
        // Parse the JSON array from response
        const matchData = JSON.parse(rawResponse);

        res.json({ matches: matchData });

    } catch (error) {
        console.error("Error matching jobs:", error);
        res.status(500).json({ error: error.message || 'Internal Server Error' });
    }
});

// Ensure uploads folder exists
fs.mkdir(path.join(__dirname, 'uploads'), { recursive: true }).then(() => {
    app.listen(port, () => {
        console.log(`Server listening at http://localhost:${port}`);
    });
});
