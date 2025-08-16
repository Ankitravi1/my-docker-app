let statusInterval; // To store the interval ID for polling

document.getElementById('video-form').addEventListener('submit', async function(event) {
    event.preventDefault();

    const form = event.target;
    const formData = new FormData(form);
    const generateBtn = document.getElementById('generate-btn');
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');
    const statusContainer = document.getElementById('status-container');
    const statusLogsDiv = document.getElementById('status-logs');
    const checklistEl = document.getElementById('status-checklist');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const exportProgressBar = document.getElementById('export-progress-bar');
    const exportProgressText = document.getElementById('export-progress-text');
    const elapsedEl = document.getElementById('elapsed-time');
    let startTs = null;
    let timerInterval = null;

    // Reset UI
    generateBtn.disabled = true;
    loadingDiv.style.display = 'block';
    resultDiv.innerHTML = '';
    statusContainer.style.display = 'none';
    statusLogsDiv.innerHTML = '';
    if (checklistEl) checklistEl.innerHTML = '';
    if (progressBar) progressBar.style.width = '0%';
    if (progressText) progressText.textContent = '0%';
    if (exportProgressBar) exportProgressBar.style.width = '0%';
    if (exportProgressText) exportProgressText.textContent = 'Export 0%';
    if (elapsedEl) elapsedEl.textContent = 'Time: 00:00';
    startTs = Date.now();
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        if (!startTs || !elapsedEl) return;
        const ms = Date.now() - startTs;
        const seconds = Math.floor(ms / 1000);
        const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
        const ss = String(seconds % 60).padStart(2, '0');
        elapsedEl.textContent = `Time: ${mm}:${ss}`;
    }, 1000);
    clearInterval(statusInterval); // Clear any previous intervals

    try {
        const response = await fetch('/generate', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            if (data.status === 'success') {
                resultDiv.innerHTML = `<p>${data.message}</p>`;
                const taskId = data.task_id;
                statusContainer.style.display = 'block';
                statusLogsDiv.innerHTML = '<p>Starting video generation...</p>';

                // Start polling for status
                statusInterval = setInterval(async () => {
                    const statusResponse = await fetch(`/status/${taskId}`);
                    const statusData = await statusResponse.json();

                    if (statusResponse.ok) {
                        // Update logs
                        statusLogsDiv.innerHTML = ''; // Clear previous logs
                        statusData.logs.forEach(log => {
                            const p = document.createElement('p');
                            p.className = 'log-entry';
                            p.textContent = log;
                            statusLogsDiv.appendChild(p);
                        });
                        statusLogsDiv.scrollTop = statusLogsDiv.scrollHeight; // Scroll to bottom

                        // Update progress bar
                        if (typeof statusData.progress === 'number') {
                            const pct = Math.max(0, Math.min(100, statusData.progress));
                            if (progressBar) progressBar.style.width = pct + '%';
                            if (progressText) progressText.textContent = pct + '%';
                        }

                        // Update export progress bar
                        if (typeof statusData.export_progress === 'number') {
                            const epct = Math.max(0, Math.min(100, statusData.export_progress));
                            if (exportProgressBar) exportProgressBar.style.width = epct + '%';
                            if (exportProgressText) exportProgressText.textContent = 'Export ' + epct + '%';
                        }

                        // Update checklist
                        if (Array.isArray(statusData.steps) && checklistEl) {
                            checklistEl.innerHTML = '';
                            statusData.steps.forEach(step => {
                                const li = document.createElement('li');
                                const badge = document.createElement('span');
                                badge.className = 'badge ' + step.state;
                                badge.textContent = step.state.replace('_', ' ');
                                const label = document.createElement('span');
                                label.textContent = step.label;
                                li.appendChild(badge);
                                li.appendChild(label);
                                checklistEl.appendChild(li);
                            });
                        }

                        // Check overall status
                        if (statusData.status === 'completed') {
                            clearInterval(statusInterval);
                            if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
                            resultDiv.innerHTML = `<p>Video generation complete!</p>`;
                            if (exportProgressBar) exportProgressBar.style.width = '100%';
                            if (exportProgressText) exportProgressText.textContent = 'Export 100%';
                            if (statusData.video_url) {
                                const dl = document.createElement('a');
                                dl.href = statusData.video_url;
                                dl.textContent = 'Download Video';
                                dl.className = 'btn-download';
                                dl.setAttribute('download', '');
                                resultDiv.appendChild(dl);
                            }
                            generateBtn.disabled = false;
                            // Keep the loading section visible so the final elapsed time remains on screen
                            // loadingDiv.style.display = 'none';
                        } else if (statusData.status === 'error') {
                            clearInterval(statusInterval);
                            if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
                            resultDiv.innerHTML = `<p>Error during video generation: ${statusData.logs[statusData.logs.length - 1]}</p>`;
                            generateBtn.disabled = false;
                            loadingDiv.style.display = 'none';
                        }
                    } else {
                        clearInterval(statusInterval);
                        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
                        resultDiv.innerHTML = `<p>Error fetching status: ${statusData.message || 'Unknown error'}</p>`;
                        generateBtn.disabled = false;
                        loadingDiv.style.display = 'none';
                    }
                }, 2000); // Poll every 2 seconds

            } else {
                resultDiv.innerHTML = `<p>Error: ${data.message}</p>`;
                generateBtn.disabled = false;
                loadingDiv.style.display = 'none';
            }
        } else {
            resultDiv.innerHTML = `<p>Server Error: ${data.message || 'An unknown error occurred.'}</p>`;
            generateBtn.disabled = false;
            loadingDiv.style.display = 'none';
        }
    } catch (error) {
        resultDiv.innerHTML = `<p>An error occurred: ${error.message}</p>`;
        generateBtn.disabled = false;
        loadingDiv.style.display = 'none';
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    }
});

const posSlider = document.getElementById('position_vertical');
if (posSlider) {
    posSlider.addEventListener('input', function(event) {
        document.getElementById('position-value').textContent = `${event.target.value}%`;
    });
}