let statusInterval; // To store the interval ID for polling

// Check that a URL is available before enabling a download link.
// Uses HEAD with cache-busting and up to 3 quick retries.
async function checkUrlAvailable(url, attempts = 3, delayMs = 300) {
    for (let i = 0; i < attempts; i++) {
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 4000);
            const res = await fetch(url, { method: 'HEAD', cache: 'no-store', signal: controller.signal });
            clearTimeout(timeout);
            if (res.ok) return true;
        } catch (e) {
            // ignore and retry
        }
        if (i < attempts - 1) await new Promise(r => setTimeout(r, delayMs));
    }
    return false;
}

document.getElementById('video-form').addEventListener('submit', async function(event) {
    event.preventDefault();

    const form = event.target;
    const formData = new FormData(form);
    const generateBtn = document.getElementById('generate-btn');
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');
    const statusContainer = document.getElementById('status-container');
    const elapsedEl = document.getElementById('elapsed-time');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    let startTs = null;
    let timerInterval = null;

    // Reset UI
    generateBtn.disabled = true;
    loadingDiv.style.display = 'block';
    resultDiv.innerHTML = '';
    // Show checklist/timer immediately
    statusContainer.style.display = 'block';
    // Reset progress visuals
    if (progressBar) progressBar.style.width = '0%';
    if (progressText) progressText.textContent = '0%';
    // Reset and start elapsed timer immediately
    if (elapsedEl) elapsedEl.textContent = 'Time: 00:00';
    startTs = Date.now();
    if (timerInterval) clearInterval(timerInterval);
    if (elapsedEl) {
        timerInterval = setInterval(() => {
            const ms = Date.now() - startTs;
            const seconds = Math.floor(ms / 1000);
            const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
            const ss = String(seconds % 60).padStart(2, '0');
            elapsedEl.textContent = `Time: ${mm}:${ss}`;
        }, 1000);
    }
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
                // no logs UI

                // Start polling for status
                statusInterval = setInterval(async () => {
                    const statusResponse = await fetch(`/status/${taskId}`);
                    const statusData = await statusResponse.json();

                    if (statusResponse.ok) {
                        // Update overall weighted progress
                        let pct = 0;
                        if (typeof statusData.progress === 'number') {
                            pct = Math.max(0, Math.min(100, statusData.progress));
                        }
                        if (progressBar) progressBar.style.width = `${pct}%`;
                        if (progressText) progressText.textContent = `${pct}%`;

                        // Check overall status
                        if (statusData.status === 'completed') {
                            clearInterval(statusInterval);
                            if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
                            resultDiv.innerHTML = `<p>Video generation complete!</p>`;
                            if (statusData.video_url) {
                                const bust = `t=${Date.now()}`;
                                const sep = statusData.video_url.includes('?') ? '&' : '?';
                                const url = `${statusData.video_url}${sep}${bust}`;
                                // Verify availability before showing the link
                                const ready = await checkUrlAvailable(url);
                                const link = document.createElement('a');
                                link.textContent = 'Download Video';
                                link.className = 'btn-download';
                                link.href = url;
                                // Suggest filename when available
                                if (statusData.output_video_filename) {
                                    link.setAttribute('download', statusData.output_video_filename);
                                } else {
                                    link.setAttribute('download', '');
                                }
                                // If not ready yet, disable click and retry once clicked
                                if (!ready) {
                                    const prep = document.createElement('p');
                                    prep.textContent = 'Preparing download…';
                                    resultDiv.appendChild(prep);
                                    link.addEventListener('click', async (e) => {
                                        e.preventDefault();
                                        const ok = await checkUrlAvailable(url, 5, 300);
                                        if (ok) {
                                            prep.remove();
                                            window.location.href = url;
                                        }
                                    }, { once: true });
                                }
                                resultDiv.appendChild(link);
                            }
                            generateBtn.disabled = false;
                            // Optionally hide loading area now that we're done
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
                }, 2000); // Poll every 2 seconds to reduce backend load

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
const posValueEl = document.getElementById('position-value');
const aspectSelect = document.getElementById('aspect_ratio');

function applyAspectPositionRule() {
    if (!aspectSelect || !posSlider || !posValueEl) return;
    if (aspectSelect.value === '16:9') {
        // Force 20% for 16:9 and disable slider
        posSlider.value = 20;
        posSlider.disabled = true;
        posValueEl.textContent = '20%';
    } else {
        // Enable slider for 9:16
        posSlider.disabled = false;
        posValueEl.textContent = `${posSlider.value}%`;
    }
}

if (posSlider) {
    posSlider.addEventListener('input', function(event) {
        if (posValueEl) posValueEl.textContent = `${event.target.value}%`;
    });
}
if (aspectSelect) {
    aspectSelect.addEventListener('change', applyAspectPositionRule);
    // Apply on load
    applyAspectPositionRule();
}

// Background music slider bindings
const bgmCheckbox = document.getElementById('background_music');
const bgmSlider = document.getElementById('background_music_level');
const bgmValueEl = document.getElementById('bgm-level-value');

function updateBgmUI() {
    if (!bgmCheckbox || !bgmSlider) return;
    const enabled = bgmCheckbox.checked;
    bgmSlider.disabled = !enabled;
    if (bgmValueEl) {
        const val = bgmSlider.value;
        bgmValueEl.textContent = `${val}%`;
    }
}

if (bgmSlider) {
    bgmSlider.addEventListener('input', () => {
        if (bgmValueEl) bgmValueEl.textContent = `${bgmSlider.value}%`;
    });
}
if (bgmCheckbox) {
    bgmCheckbox.addEventListener('change', updateBgmUI);
    // Initialize state on load
    updateBgmUI();
}
