// Global variables
let isProcessing = false;
let chatHistory = [];

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadProgress = document.getElementById('uploadProgress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const processingSection = document.getElementById('processingSection');
const toggleProcessing = document.getElementById('toggleProcessing');
const processingDetails = document.getElementById('processingDetails');
const processingStages = document.getElementById('processingStages');
const proceedToChat = document.getElementById('proceedToChat');

// Chat page elements
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const viewPdfBtn = document.getElementById('viewPdfBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const newDocumentBtn = document.getElementById('newDocumentBtn');

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeUploadPage();
    initializeChatPage();
});

// Upload Page Functions
function initializeUploadPage() {
    if (!uploadArea) return;

    // File input handling
    uploadArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);

    // Processing toggle
    if (toggleProcessing) {
        toggleProcessing.addEventListener('click', toggleProcessingDetails);
    }

    if (proceedToChat) {
        proceedToChat.addEventListener('click', () => {
            window.location.href = '/chat';
        });
    }
}

function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        if (file.type === 'application/pdf') {
            uploadFile(file);
        } else {
            showNotification('Please select a PDF file.', 'error');
        }
    }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        uploadFile(file);
    }
}

function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Show progress
    uploadProgress.style.display = 'block';
    uploadArea.style.display = 'none';

    let progress = 0;
    const progressInterval = setInterval(() => {
        progress += Math.random() * 15;
        if (progress > 90) progress = 90;
        updateProgress(progress, 'Uploading file...');
    }, 200);

    // Enhanced error handling with detailed logging
    console.log('=== UPLOAD DEBUG ===');
    console.log('File name:', file.name);
    console.log('File size:', file.size, 'bytes');
    console.log('File type:', file.type);

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        clearInterval(progressInterval);
        
        console.log('=== RESPONSE DEBUG ===');
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        console.log('Response headers:', [...response.headers.entries()]);
        
        // Handle different status codes with specific messages
        if (response.status === 413) {
            throw new Error('File is too large. Please use a smaller PDF file.');
        } else if (response.status === 500) {
            throw new Error('Server error occurred. Please try again in a few minutes.');
        } else if (response.status === 400) {
            throw new Error('Invalid file or request. Please check your PDF file.');
        } else if (!response.ok) {
            throw new Error(`Upload failed with status ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    })
    .then(data => {
        console.log('=== UPLOAD SUCCESS ===');
        console.log('Upload response data:', data);
        
        if (data.success) {
            updateProgress(100, 'Upload complete!');
            setTimeout(() => {
                uploadProgress.style.display = 'none';
                processingSection.style.display = 'block';
                startProcessing();
            }, 1000);
        } else {
            throw new Error(data.error || 'Upload failed - no error message provided');
        }
    })
    .catch(error => {
        clearInterval(progressInterval);
        console.error('=== UPLOAD ERROR ===');
        console.error('Error details:', error);
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
        
        let errorMessage = 'Upload failed: ';
        
        if (error.message.includes('Failed to fetch')) {
            errorMessage += 'Network connection error. Please check your internet connection and try again.';
        } else if (error.message.includes('413') || error.message.includes('too large')) {
            errorMessage += 'File is too large. Please use a smaller PDF file.';
        } else if (error.message.includes('500') || error.message.includes('Server error')) {
            errorMessage += 'Server error occurred. Please try again in a few minutes.';
        } else if (error.message.includes('400')) {
            errorMessage += 'Invalid file or request. Please check your PDF file and try again.';
        } else {
            errorMessage += error.message;
        }
        
        showNotification(errorMessage, 'error');
        resetUploadArea();
    });
}

function updateProgress(percentage, text) {
    progressFill.style.width = percentage + '%';
    progressText.textContent = text;
}

function startProcessing() {
    isProcessing = true;
    
    // Create processing stages
    const stages = [
        { id: 'loading', text: 'Loading PDF document...', icon: 'fas fa-file-pdf' },
        { id: 'splitting', text: 'Splitting document into chunks...', icon: 'fas fa-cut' },
        { id: 'embedding', text: 'Creating embeddings...', icon: 'fas fa-brain' },
        { id: 'storing', text: 'Storing vectors in database...', icon: 'fas fa-database' },
        { id: 'complete', text: 'Processing complete!', icon: 'fas fa-check-circle' }
    ];

    processingStages.innerHTML = stages.map(stage => 
        `<div class="stage-item" id="stage-${stage.id}">
            <div class="stage-icon">
                <i class="${stage.icon}"></i>
            </div>
            <span>${stage.text}</span>
        </div>`
    ).join('');

    // Start processing with enhanced error handling
    console.log('=== PROCESSING START ===');
    
    fetch('/process-pdf', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        console.log('=== PROCESSING RESPONSE ===');
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        
        if (!response.ok) {
            throw new Error(`Processing failed with status ${response.status}: ${response.statusText}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('=== PROCESSING SUCCESS ===');
        console.log('Processing response data:', data);
        
        if (data.success) {
            // Simulate stage progression
            simulateProcessingStages(data.is_existing);
        } else {
            throw new Error(data.error || 'Processing failed - no error message provided');
        }
    })
    .catch(error => {
        console.error('=== PROCESSING ERROR ===');
        console.error('Error details:', error);
        console.error('Error message:', error.message);
        
        let errorMessage = 'Processing failed: ';
        
        if (error.message.includes('Failed to fetch')) {
            errorMessage += 'Network connection error during processing. Please try again.';
        } else if (error.message.includes('500')) {
            errorMessage += 'Server error during processing. Please try again in a few minutes.';
        } else {
            errorMessage += error.message;
        }
        
        showNotification(errorMessage, 'error');
        isProcessing = false;
        resetUploadArea();
    });
}

function simulateProcessingStages(isExisting) {
    const stages = ['loading', 'splitting', 'embedding', 'storing', 'complete'];
    let currentStage = 0;
    
    function nextStage() {
        if (currentStage < stages.length) {
            const stageElement = document.getElementById(`stage-${stages[currentStage]}`);
            
            if (currentStage > 0) {
                // Mark previous stage as completed
                const prevStageElement = document.getElementById(`stage-${stages[currentStage - 1]}`);
                prevStageElement.classList.remove('active');
                prevStageElement.classList.add('completed');
                prevStageElement.querySelector('.stage-icon i').className = 'fas fa-check';
            }
            
            // Mark current stage as active
            stageElement.classList.add('active');
            stageElement.querySelector('.stage-icon i').className += ' loading';
            
            currentStage++;
            
            // Shorter delays if existing
            const delay = isExisting ? 500 : 1500;
            setTimeout(nextStage, delay);
        } else {
            // All stages complete
            const lastStage = document.getElementById(`stage-${stages[stages.length - 1]}`);
            lastStage.classList.remove('active');
            lastStage.classList.add('completed');
            lastStage.querySelector('.stage-icon i').className = 'fas fa-check';
            
            isProcessing = false;
            proceedToChat.style.display = 'inline-flex';
        }
    }
    
    nextStage();
}

function toggleProcessingDetails() {
    const isVisible = processingDetails.style.display !== 'none';
    processingDetails.style.display = isVisible ? 'none' : 'block';
    toggleProcessing.innerHTML = isVisible 
        ? '<i class="fas fa-eye"></i> <span>View Details</span>'
        : '<i class="fas fa-eye-slash"></i> <span>Hide Details</span>';
}

function resetUploadArea() {
    uploadProgress.style.display = 'none';
    uploadArea.style.display = 'block';
    processingSection.style.display = 'none';
    if (proceedToChat) {
        proceedToChat.style.display = 'none';
    }
    fileInput.value = '';
}

// Chat Page Functions
function initializeChatPage() {
    if (!messageInput) return;

    // Load chat history
    loadChatHistory();

    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keydown', handleKeyDown);
    messageInput.addEventListener('input', autoResize);

    if (viewPdfBtn) {
        viewPdfBtn.addEventListener('click', viewPdf);
    }

    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', clearChat);
    }

    if (newDocumentBtn) {
        newDocumentBtn.addEventListener('click', newDocument);
    }

    // Auto-resize textarea
    autoResize.call(messageInput);
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 150) + 'px';
}

function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isProcessing) return;

    // Add user message to chat
    addMessage('user', message);
    messageInput.value = '';
    autoResize.call(messageInput);

    // Show loading
    showLoading(true);

    // Send to backend
    fetch('/ask', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ question: message })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    })
    .then(data => {
        showLoading(false);
        
        if (data.success) {
            addMessage('assistant', data.answer, data.response_time, data.sources);
        } else {
            addMessage('assistant', 'Sorry, I encountered an error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        showLoading(false);
        console.error('Question error:', error);
        addMessage('assistant', 'Sorry, I encountered an error processing your request. Please try again.');
    });
}

function addMessage(type, content, responseTime = null, sources = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const avatar = type === 'user' 
        ? '<i class="fas fa-user"></i>'
        : '<i class="fas fa-robot"></i>';

    // Enhanced content processing for better formatting
    let formattedContent = content;
    if (type === 'assistant') {
        formattedContent = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/• /g, '<li>')
            .replace(/\n\n/g, '</li></ul><br><ul><li>')
            .replace(/^\* /gm, '<li>')
            .replace(/^(\d+\.) /gm, '<li>')
            .replace(/\n/g, '<br>');
        
        if (formattedContent.includes('<li>')) {
            formattedContent = '<ul><li>' + formattedContent + '</li></ul>';
            formattedContent = formattedContent.replace(/<\/li><ul><li>/g, '</li><li>');
            formattedContent = formattedContent.replace(/<ul><li><\/li><\/ul>/g, '');
            formattedContent = formattedContent.replace(/<ul><\/ul>/g, '');
        }
    }

    const responseTimeHtml = responseTime 
        ? `<div class="response-time">
             <i class="fas fa-clock"></i>
             ${responseTime}s
           </div>`
        : '';

    const sourcesHtml = sources && sources.length > 0
        ? `<button class="sources-btn" onclick="toggleSources(this)">
             <i class="fas fa-book"></i> View Sources (${sources.length})
           </button>`
        : '';

    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-bubble">${formattedContent}</div>
            <div class="message-info">
                ${responseTimeHtml}
                ${sourcesHtml}
            </div>
            ${sources ? createSourcesPanel(sources) : ''}
        </div>
    `;

    // Add welcome message removal
    const welcomeMsg = chatMessages.querySelector('.welcome-conversation, .compact-welcome-conversation');
    if (welcomeMsg && type === 'user') {
        welcomeMsg.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => welcomeMsg.remove(), 300);
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function createSourcesPanel(sources) {
    const sourcesHtml = sources.map((source, index) => 
        `<div class="source-item">
            <div class="source-content">${source.content}</div>
            <div class="source-meta">Source ${index + 1}</div>
        </div>`
    ).join('');

    return `<div class="sources-panel" style="display: none;">${sourcesHtml}</div>`;
}

function toggleSources(button) {
    const sourcesPanel = button.closest('.message-content').querySelector('.sources-panel');
    const isVisible = sourcesPanel.style.display !== 'none';
    
    sourcesPanel.style.display = isVisible ? 'none' : 'block';
    button.innerHTML = isVisible 
        ? '<i class="fas fa-book"></i> View Sources'
        : '<i class="fas fa-book-open"></i> Hide Sources';
}

function showLoading(show) {
    if (loadingOverlay) {
        loadingOverlay.style.display = show ? 'flex' : 'none';
    }
    sendBtn.disabled = show;
    isProcessing = show;
}

function loadChatHistory() {
    fetch('/get-chat-history')
    .then(response => response.json())
    .then(data => {
        data.chat_history.forEach(chat => {
            addMessage('user', chat.question);
            addMessage('assistant', chat.answer, chat.response_time, chat.sources);
        });
    })
    .catch(error => {
        console.error('Error loading chat history:', error);
    });
}

function viewPdf() {
    window.open('/view-pdf', '_blank');
}

function clearChat() {
    if (confirm('Are you sure you want to clear the chat history?')) {
        fetch('/clear-chat', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove all messages except welcome
                const messages = chatMessages.querySelectorAll('.message');
                messages.forEach(msg => msg.remove());
                showNotification('Chat history cleared!', 'success');
            }
        })
        .catch(error => {
            console.error('Error clearing chat:', error);
        });
    }
}

function newDocument() {
    if (confirm('Upload a new document? This will clear your current session.')) {
        // Enhanced reset with better error handling
        fetch('/reset', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log('Session reset successful');
                // Wait a moment then reload the page for a fresh start
                setTimeout(() => {
                    window.location.href = '/';
                }, 500);
            } else {
                throw new Error(data.error || 'Reset failed');
            }
        })
        .catch(error => {
            console.error('Error resetting session:', error);
            showNotification(`Reset failed: ${error.message}`, 'error');
            // Try reloading anyway
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        });
    }
}

// Utility Functions
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        background: ${type === 'error' ? '#ef4444' : 
                    type === 'success' ? '#10b981' : '#3b82f6'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.75rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        animation: slideUp 0.3s ease-out;
        max-width: 400px;
        word-wrap: break-word;
        font-size: 0.9rem;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    // Remove after 7 seconds for error messages, 4 seconds for others
    const timeout = type === 'error' ? 7000 : 4000;
    setTimeout(() => {
        notification.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, timeout);
}

// Add CSS for animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeOut {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);

