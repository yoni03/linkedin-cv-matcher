document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('cvInput');
    const fileMsg = document.querySelector('.file-msg');
    const dropArea = document.querySelector('.file-drop-area');

    // Update file name display
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            fileMsg.textContent = e.target.files[0].name;
        } else {
            fileMsg.textContent = 'Choose a PDF or drag it here';
        }
    });

    // Drag and drop styles
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'), false);
    });

    dropArea.addEventListener('drop', (e) => {
        let dt = e.dataTransfer;
        let files = dt.files;
        fileInput.files = files;
        
        if (files.length > 0) {
            fileMsg.textContent = files[0].name;
        }
    });

    const form = document.getElementById('matchForm');
    const submitBtn = document.getElementById('submitBtn');
    const resultsSection = document.getElementById('resultsSection');
    const jobsList = document.getElementById('jobsList');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // UI Loading State
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        resultsSection.classList.add('hidden');
        jobsList.innerHTML = '';

        const formData = new FormData(form);

        try {
            const response = await fetch('/api/match-jobs', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || 'Server error');
            }

            const data = await response.json();
            renderJobs(data.matches);
        } catch (error) {
            alert('Error: ' + error.message);
        } finally {
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    });

    function renderJobs(matches) {
        if (!matches || matches.length === 0) {
            jobsList.innerHTML = '<p>No suitable matches found.</p>';
            resultsSection.classList.remove('hidden');
            return;
        }

        matches.forEach((job, index) => {
            const card = document.createElement('div');
            card.className = 'job-card';
            card.style.animationDelay = `${index * 0.1}s`;

            card.innerHTML = `
                <div class="job-header">
                    <div>
                        <div class="job-title">${job.title || 'Unknown Title'}</div>
                        <div class="job-company">${job.company || 'Unknown Company'}</div>
                        <div class="job-location">${job.location || 'Unknown Location'}</div>
                    </div>
                    <a href="${job.job_url || '#'}" target="_blank" class="apply-btn">Apply Now</a>
                </div>
                <div class="job-report">
                    ${job.quick_report || 'No report generated.'}
                </div>
            `;

            jobsList.appendChild(card);
        });

        resultsSection.classList.remove('hidden');
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }
});
