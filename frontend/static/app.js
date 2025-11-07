// Frontend JavaScript for YouTube Q&A

// DOM Elements
const ingestForm = document.getElementById('ingest-form');
const videoUrlInput = document.getElementById('video-url');
const ingestStatus = document.getElementById('ingest-status');
const clearBtn = document.getElementById('clear-btn');

const queryForm = document.getElementById('query-form');
const questionInput = document.getElementById('question');
const queryStatus = document.getElementById('query-status');
const answerContainer = document.getElementById('answer-container');
const answerText = document.getElementById('answer-text');
const sourcesList = document.getElementById('sources-list');

// Helper Functions
function showStatus(element, message, type) {
    element.textContent = message;
    element.className = `status ${type}`;
    element.classList.remove('hidden');
}

function hideStatus(element) {
    element.classList.add('hidden');
}

function hideAnswer() {
    answerContainer.classList.add('hidden');
}

// Ingest Form Handler
ingestForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const videoUrl = videoUrlInput.value.trim();
    
    if (!videoUrl) {
        showStatus(ingestStatus, 'Please enter a YouTube URL', 'error');
        return;
    }
    
    // Disable submit button
    const submitBtn = ingestForm.querySelector('button');
    submitBtn.disabled = true;
    
    showStatus(ingestStatus, 'Submitting video for ingestion...', 'loading');
    
    try {
        const response = await fetch('/ingest', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ video_url: videoUrl })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showStatus(
                ingestStatus, 
                `✓ Video submitted successfully! Processing will take ~30 seconds. Message ID: ${data.message_id}`, 
                'success'
            );
            videoUrlInput.value = '';
        } else {
            showStatus(ingestStatus, `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showStatus(ingestStatus, `Network error: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
    }
});

// Query Form Handler
queryForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const question = questionInput.value.trim();
    
    if (!question) {
        showStatus(queryStatus, 'Please enter a question', 'error');
        return;
    }
    
    // Disable submit button
    const submitBtn = queryForm.querySelector('button');
    submitBtn.disabled = true;
    
    showStatus(queryStatus, 'Asking question...', 'loading');
    hideAnswer();
    
    try {
        const response = await fetch('/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question: question })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Hide status, show answer
            hideStatus(queryStatus);
            
            // Display answer
            answerText.textContent = data.answer;
            
            // Display sources
            sourcesList.innerHTML = '';
            data.sources.forEach((source, index) => {
                const sourceDiv = document.createElement('div');
                sourceDiv.className = 'source-item';
                
                const videoId = source.video_id || 'Unknown';
                const excerpt = source.excerpt || '';
                const s3Uri = source.s3_uri || '';
                
                sourceDiv.innerHTML = `
                    <div class="source-video">📹 Video: ${videoId}</div>
                    <div class="source-excerpt">${excerpt}</div>
                    <div class="source-uri">${s3Uri}</div>
                `;
                
                sourcesList.appendChild(sourceDiv);
            });
            
            // Show answer container
            answerContainer.classList.remove('hidden');
            
            // Scroll to answer
            answerContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            showStatus(queryStatus, `Error: ${data.error}`, 'error');
            hideAnswer();
        }
    } catch (error) {
        showStatus(queryStatus, `Network error: ${error.message}`, 'error');
        hideAnswer();
    } finally {
        submitBtn.disabled = false;
    }
});

// Clear All Videos Handler
clearBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear ALL videos? This will delete all indexed transcripts.')) {
        return;
    }
    
    // Disable button
    clearBtn.disabled = true;
    
    showStatus(ingestStatus, 'Clearing all videos...', 'loading');
    hideAnswer();
    
    try {
        const response = await fetch('/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showStatus(
                ingestStatus, 
                `✓ ${data.message}. Knowledge Base index updated.`, 
                'success'
            );
        } else {
            showStatus(ingestStatus, `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showStatus(ingestStatus, `Network error: ${error.message}`, 'error');
    } finally {
        clearBtn.disabled = false;
    }
});

// Clear status messages when user starts typing
videoUrlInput.addEventListener('input', () => {
    if (!ingestStatus.classList.contains('hidden')) {
        setTimeout(() => hideStatus(ingestStatus), 3000);
    }
});

questionInput.addEventListener('input', () => {
    if (!queryStatus.classList.contains('hidden')) {
        setTimeout(() => hideStatus(queryStatus), 3000);
    }
});

