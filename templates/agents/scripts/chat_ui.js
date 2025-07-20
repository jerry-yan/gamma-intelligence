// templates/agents/scripts/chat_ui.js

// Toggle mobile menu
function toggleMobileMenu() {
    const sidebar = document.getElementById('chatSidebar');
    sidebar.classList.toggle('mobile-open');
}

// Create message element
function createMessageElement(role, content, knowledgeBase = null, messageId = null) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${role}`;
    if (messageId) wrapper.dataset.messageId = messageId;

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'message-content-wrapper';

    // Avatar
    const avatar = document.createElement('div');
    avatar.className = `message-avatar ${role}-avatar`;
    avatar.textContent = role === 'user' ? 'U' : 'AI';

    // Message body
    const body = document.createElement('div');
    body.className = 'message-body';

    // Meta info
    const meta = document.createElement('div');
    meta.className = 'message-meta';

    const roleSpan = document.createElement('span');
    roleSpan.className = 'message-role';
    roleSpan.textContent = role === 'user' ? 'You' : 'Assistant';
    meta.appendChild(roleSpan);

    if (knowledgeBase) {
        const kbBadge = document.createElement('span');
        kbBadge.className = 'kb-badge';
        kbBadge.textContent = getKnowledgeBaseName(knowledgeBase);
        meta.appendChild(kbBadge);
    }

    body.appendChild(meta);

    // Message text
    const text = document.createElement('div');
    text.className = 'message-text';
    if (role === 'assistant') {
        text.innerHTML = marked.parse(content || '');
    } else {
        text.textContent = content;
    }
    body.appendChild(text);

    // Actions
    if (messageId) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';

        const copyBtn = document.createElement('button');
        copyBtn.className = 'message-action';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = () => copyMessage(content);
        actions.appendChild(copyBtn);

        if (role === 'user') {
            const editBtn = document.createElement('button');
            editBtn.className = 'message-action';
            editBtn.textContent = 'Edit';
            editBtn.onclick = () => editMessage(messageId, content);
            actions.appendChild(editBtn);
        }

        body.appendChild(actions);
    }

    contentWrapper.appendChild(avatar);
    contentWrapper.appendChild(body);
    wrapper.appendChild(contentWrapper);

    return wrapper;
}

// Add message to chat
function addMessage(role, content, knowledgeBase = null, messageId = null) {
    const container = document.getElementById('messagesContainer');
    const messageEl = createMessageElement(role, content, knowledgeBase, messageId);
    container.appendChild(messageEl);
    scrollToBottom();
    return messageEl;
}

// Update message content
function updateMessageContent(element, content) {
    const textEl = element.querySelector('.message-text');
    if (textEl) {
        textEl.innerHTML = marked.parse(content);
    }
}

// Scroll to bottom of messages
function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
}

// Show typing indicator
function showTypingIndicator() {
    const container = document.getElementById('messagesContainer');
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator active';
    indicator.id = 'typingIndicator';
    indicator.innerHTML = `
        <div class="message-content-wrapper">
            <div class="message-avatar assistant-avatar">AI</div>
            <div class="typing-dots">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        </div>
    `;
    container.appendChild(indicator);
    scrollToBottom();
}

// Hide typing indicator
function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// Update session list UI
function updateSessionsList(sessions) {
    const container = document.getElementById('sessionsList');
    container.innerHTML = '';

    if (!sessions || sessions.length === 0) {
        container.innerHTML = `
            <div class="text-center p-3">
                <small class="text-secondary">No chats yet</small>
            </div>
        `;
        return;
    }

    sessions.forEach(session => {
        const item = document.createElement('div');
        item.className = 'session-item';
        item.dataset.sessionId = session.session_id;

        if (session.session_id === currentSession) {
            item.classList.add('active');
        }

        const title = document.createElement('div');
        title.className = 'session-title';
        title.textContent = session.title || 'New Chat';

        const actions = document.createElement('div');
        actions.className = 'session-actions';

        const renameBtn = document.createElement('button');
        renameBtn.className = 'session-action-btn';
        renameBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11.5 2.5l2 2m-10 10v-2.5l7-7 2.5 2.5-7 7H3.5z"/>
            </svg>
        `;
        renameBtn.onclick = (e) => {
            e.stopPropagation();
            renameSession(session.session_id, session.title);
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'session-action-btn';
        deleteBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 5l6 6m0-6l-6 6"/>
            </svg>
        `;
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            openDeleteModal(session.session_id, session.title);
        };

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);

        item.appendChild(title);
        item.appendChild(actions);

        item.onclick = () => loadSession(session.session_id);

        container.appendChild(item);
    });
}

// Get knowledge base display name
function getKnowledgeBaseName(kbId) {
    const select = document.getElementById('knowledgeBaseSelect');
    const option = select.querySelector(`option[value="${kbId}"]`);
    return option ? option.textContent : 'Unknown KB';
}

// Copy message to clipboard
async function copyMessage(content) {
    try {
        await navigator.clipboard.writeText(content);
        // Show toast notification
        showToast('Copied to clipboard');
    } catch (err) {
        console.error('Failed to copy:', err);
    }
}

// Show toast notification
function showToast(message) {
    // Simple toast implementation
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 2rem;
        left: 50%;
        transform: translateX(-50%);
        background: var(--text-primary);
        color: var(--bg-main);
        padding: 0.75rem 1.5rem;
        border-radius: 0.5rem;
        font-size: 0.875rem;
        z-index: 3000;
        animation: fadeIn 0.3s ease;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

// Modal functions
function openShareModal() {
    document.getElementById('shareModal').style.display = 'flex';
}

function closeShareModal() {
    document.getElementById('shareModal').style.display = 'none';
}

function openDeleteModal(sessionId, title) {
    window.deleteTargetSession = sessionId;
    document.getElementById('deleteSessionTitle').textContent = title || 'this chat';
    document.getElementById('deleteConfirmModal').style.display = 'flex';
}

function closeDeleteModal() {
    window.deleteTargetSession = null;
    document.getElementById('deleteConfirmModal').style.display = 'none';
}

function closeAllModals() {
    closeShareModal();
    closeDeleteModal();
}

// Rename session
async function renameSession(sessionId, currentTitle) {
    const newTitle = prompt('Enter new chat title:', currentTitle || 'New Chat');
    if (newTitle && newTitle !== currentTitle) {
        try {
            const response = await fetch(`/agents/api/sessions/${sessionId}/rename/`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ title: newTitle })
            });

            if (response.ok) {
                loadUserSessions();
                if (sessionId === currentSession) {
                    document.getElementById('chatTitle').textContent = newTitle;
                }
            }
        } catch (error) {
            console.error('Failed to rename session:', error);
        }
    }
}