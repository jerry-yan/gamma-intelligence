// templates/agents/scripts/chat_api.js

// Get CSRF token from cookies
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
    window.history.pushState({}, '', '/agents/v2/');

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
            window.history.pushState({}, '', `/agents/v2/?session=${currentSession}`);

            // Reload sessions list
            loadUserSessions();

            return true;
        }
    } catch (error) {
        console.error('Failed to create session:', error);
    }
    return false;
}

// Load session history
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
            window.history.pushState({}, '', `/agents/v2/?session=${sessionId}`);

            // Update sessions list
            loadUserSessions();

            // Close mobile menu
            document.getElementById('chatSidebar').classList.remove('mobile-open');
        }
    } catch (error) {
        console.error('Failed to load session:', error);
    }
}

// Send message with streaming response
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
        // Prepare request body
        const body = {
            message: message,
            session_id: currentSession
        };

        if (currentKnowledgeBase) {
            body.knowledge_base_id = currentKnowledgeBase;
        }

        // Make POST request
        const response = await fetch('/agents/api/chat/stream/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Read SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let assistantMessage = '';
        let messageElement = null;
        let hasError = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.trim() === '') continue;

                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        switch (data.type) {
                            case 'start':
                                // Hide typing indicator and create message element
                                hideTypingIndicator();
                                messageElement = addMessage('assistant', '', currentKnowledgeBase, data.message_id);
                                break;

                            case 'content':
                                // Append content
                                if (data.content) {
                                    assistantMessage += data.content;
                                    updateMessageContent(messageElement, assistantMessage);
                                }
                                break;

                            case 'tool_use':
                                // Handle tool usage indicators
                                if (data.tool === 'file_search' && data.status === 'searching') {
                                    console.log('Searching knowledge base...');
                                }
                                break;

                            case 'info':
                                console.log('Info:', data.message);
                                break;

                            case 'error':
                                hasError = true;
                                if (!messageElement) {
                                    hideTypingIndicator();
                                    messageElement = addMessage('assistant', data.error, currentKnowledgeBase);
                                } else {
                                    updateMessageContent(messageElement, data.error);
                                }
                                break;

                            case 'done':
                                // Update title if this is a new conversation
                                if (data.session_updated) {
                                    loadUserSessions();
                                    if (data.title) {
                                        document.getElementById('chatTitle').textContent = data.title;
                                    }
                                }
                                break;

                            case 'reasoning':
                                // Keep connection alive during reasoning
                                console.log('Reasoning:', data.status);
                                break;
                        }
                    } catch (e) {
                        console.error('Error parsing SSE data:', e, line);
                    }
                }
            }
        }

    } catch (error) {
        console.error('Failed to send message:', error);
        hideTypingIndicator();

        // Show error message if not already shown
        if (!messageElement) {
            addMessage('assistant', 'Sorry, an error occurred while sending your message. Please try again.', currentKnowledgeBase);
        }
    } finally {
        // Re-enable input
        sendBtn.disabled = false;
        isStreaming = false;

        // Focus back on input
        const input = document.getElementById('chatInput');
        input.focus();
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
        showToast('Failed to delete chat');
    }
}

// Clear session
async function clearSession() {
    if (!currentSession) return;

    try {
        const response = await fetch(`/agents/api/sessions/${currentSession}/clear/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        if (response.ok) {
            // Reload current session
            await loadSession(currentSession);
        }
    } catch (error) {
        console.error('Failed to clear session:', error);
        showToast('Failed to clear chat');
    }
}

// Delete individual message
async function deleteMessage(messageId) {
    if (!confirm('Delete this message and all messages after it?')) return;

    try {
        const response = await fetch(`/agents/api/messages/${messageId}/delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        if (response.ok) {
            // Reload current session
            if (currentSession) {
                await loadSession(currentSession);
            }
        }
    } catch (error) {
        console.error('Failed to delete message:', error);
        showToast('Failed to delete message');
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
        mangle: false,
        sanitize: false // Let DOMPurify handle sanitization
    });

    // If highlight.js is available, use it
    if (typeof hljs !== 'undefined') {
        marked.setOptions({
            highlight: function(code, lang) {
                const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                return hljs.highlight(code, { language }).value;
            },
            langPrefix: 'hljs language-'
        });
    }
}