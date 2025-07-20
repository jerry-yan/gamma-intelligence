// templates/agents/scripts/chat_api.js

// Get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Load user sessions
async function loadUserSessions() {
    try {
        const response = await fetch('/agents/api/sessions/');
        if (response.ok) {
            const data = await response.json();
            updateSessionsList(data.sessions);
        }
    } catch (error) {
        console.error('Failed to load sessions:', error);
    }
}

// Create new chat
async function createNewChat() {
    // Close mobile menu if open
    document.getElementById('chatSidebar').classList.remove('mobile-open');

    // Clear current session
    currentSession = null;

    // Clear messages
    document.getElementById('messagesContainer').innerHTML = '';

    // Show welcome screen
    const welcomeScreen = document.getElementById('welcomeScreen');
    if (welcomeScreen) {
        document.getElementById('messagesContainer').appendChild(welcomeScreen);
        welcomeScreen.style.display = 'flex';
    }

    // Reset title
    document.getElementById('chatTitle').textContent = 'New Chat';

    // Clear URL
    window.history.pushState({}, '', '/agents/');

    // Focus input
    document.getElementById('chatInput').focus();
}

// Create session
async function createSession() {
    try {
        const response = await fetch('/agents/api/sessions/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        if (response.ok) {
            const data = await response.json();
            currentSession = data.session_id;

            // Update URL
            window.history.pushState({}, '', `/agents/?session=${currentSession}`);

            // Reload sessions list
            loadUserSessions();

            return true;
        }
    } catch (error) {
        console.error('Failed to create session:', error);
    }
    return false;
}

// Load session
async function loadSession(sessionId) {
    try {
        const response = await fetch(`/agents/api/sessions/${sessionId}/history/`);
        if (response.ok) {
            const data = await response.json();

            currentSession = sessionId;

            // Update UI
            document.getElementById('chatTitle').textContent = data.title || 'New Chat';

            // Clear and rebuild messages
            const container = document.getElementById('messagesContainer');
            container.innerHTML = '';

            // Hide welcome screen
            const welcomeScreen = document.getElementById('welcomeScreen');
            if (welcomeScreen) {
                welcomeScreen.style.display = 'none';
            }

            // Add messages
            data.messages.forEach(msg => {
                if (msg.role !== 'system') {
                    addMessage(msg.role, msg.content, msg.knowledge_base_id, msg.id);
                }
            });

            // Update URL
            window.history.pushState({}, '', `/agents/?session=${sessionId}`);

            // Update sessions list
            loadUserSessions();

            // Close mobile menu
            document.getElementById('chatSidebar').classList.remove('mobile-open');
        }
    } catch (error) {
        console.error('Failed to load session:', error);
    }
}

// Send message
async function sendMessage(message) {
    if (!currentSession || !message.trim()) return;

    // Add user message
    addMessage('user', message, currentKnowledgeBase);

    // Show typing indicator
    showTypingIndicator();

    // Disable input
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;
    isStreaming = true;

    try {
        // Close existing event source if any
        if (currentEventSource) {
            currentEventSource.close();
        }

        // Create event source for streaming
        const params = new URLSearchParams({
            message: message,
            session_id: currentSession,
            knowledge_base_id: currentKnowledgeBase || ''
        });

        currentEventSource = new EventSource(`/agents/api/chat/stream/?${params}`);

        let assistantMessage = '';
        let messageElement = null;
        let hasError = false;

        currentEventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'start') {
                // Hide typing indicator and create message element
                hideTypingIndicator();
                messageElement = addMessage('assistant', '', currentKnowledgeBase, data.message_id);
            } else if (data.type === 'content') {
                // Append content
                assistantMessage += data.content;
                updateMessageContent(messageElement, assistantMessage);
            } else if (data.type === 'error') {
                hasError = true;
                if (!messageElement) {
                    hideTypingIndicator();
                    messageElement = addMessage('assistant', data.error, currentKnowledgeBase);
                } else {
                    updateMessageContent(messageElement, data.error);
                }
            } else if (data.type === 'done') {
                // Update title if needed
                if (data.session_updated) {
                    loadUserSessions();
                    document.getElementById('chatTitle').textContent = data.title || 'New Chat';
                }
            }
        };

        currentEventSource.onerror = (error) => {
            console.error('SSE Error:', error);
            currentEventSource.close();

            if (!hasError && !messageElement) {
                hideTypingIndicator();
                addMessage('assistant', 'Sorry, an error occurred while processing your request.', currentKnowledgeBase);
            }

            // Re-enable input
            sendBtn.disabled = false;
            isStreaming = false;
            currentEventSource = null;
        };

        currentEventSource.addEventListener('close', () => {
            currentEventSource.close();
            sendBtn.disabled = false;
            isStreaming = false;
            currentEventSource = null;
        });

    } catch (error) {
        console.error('Failed to send message:', error);
        hideTypingIndicator();
        addMessage('assistant', 'Sorry, an error occurred while sending your message.', currentKnowledgeBase);
        sendBtn.disabled = false;
        isStreaming = false;
    }
}

// Delete session
async function confirmDelete() {
    const sessionId = window.deleteTargetSession;
    if (!sessionId) return;

    try {
        const response = await fetch(`/agents/api/sessions/${sessionId}/delete/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        if (response.ok) {
            closeDeleteModal();

            // If deleting current session, create new chat
            if (sessionId === currentSession) {
                createNewChat();
            }

            // Reload sessions list
            loadUserSessions();
        }
    } catch (error) {
        console.error('Failed to delete session:', error);
    }
}

// Share functionality (placeholder)
async function generateShareLink() {
    // This is a placeholder - implement your sharing logic here
    const linkInput = document.getElementById('shareLink');
    linkInput.value = `${window.location.origin}/agents/share/${currentSession}`;

    // Auto-select the link
    linkInput.select();
}

function copyShareLink() {
    const linkInput = document.getElementById('shareLink');
    linkInput.select();
    document.execCommand('copy');
    showToast('Link copied to clipboard');
}

// Edit message (placeholder)
function editMessage(messageId, content) {
    // This is a placeholder for edit functionality
    console.log('Edit message:', messageId, content);
    showToast('Edit functionality coming soon');
}

// Initialize marked.js for markdown parsing
if (typeof marked !== 'undefined') {
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });
}