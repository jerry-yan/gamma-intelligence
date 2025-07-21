// templates/agents/scripts/chat_core.js

// Initialize chat application
function initializeChat() {
    // Load user sessions
    loadUserSessions();

    // Set up event listeners
    setupEventListeners();

    // Auto-resize textarea
    setupTextareaAutoResize();

    // Check for session in URL or create new
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session');
    if (sessionId) {
        loadSession(sessionId);
    }

    // Set default model to o3
    const modelSelector = document.getElementById('modelSelector');
    if (modelSelector) {
        modelSelector.value = 'o3'; // Ensure o3 is selected
        currentModel = 'o3';
    }
}

// Setup all event listeners
function setupEventListeners() {
    // Mobile menu toggle
    document.getElementById('mobileMenuToggle').addEventListener('click', toggleMobileMenu);

    // New chat button
    document.getElementById('newChatBtn').addEventListener('click', createNewChat);

    // Chat form submission
    document.getElementById('chatForm').addEventListener('submit', handleSubmit);

    // Knowledge base selector
    document.getElementById('knowledgeBaseSelect').addEventListener('change', (e) => {
        currentKnowledgeBase = e.target.value || null;
    });

    // Model selector
    document.getElementById('modelSelector').addEventListener('change', (e) => {
        currentModel = e.target.value;
    });

    // Share button
    document.getElementById('shareBtn').addEventListener('click', openShareModal);

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);

    // Character counter
    document.getElementById('chatInput').addEventListener('input', updateCharCounter);
}

// Setup textarea auto-resize
function setupTextareaAutoResize() {
    const textarea = document.getElementById('chatInput');

    textarea.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
}

// Handle keyboard shortcuts
function handleKeyboardShortcuts(e) {
    // Cmd/Ctrl + K for new chat
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        createNewChat();
    }

    // Escape to close modals
    if (e.key === 'Escape') {
        closeAllModals();
    }
}

// Update character counter
function updateCharCounter() {
    const input = document.getElementById('chatInput');
    const counter = document.getElementById('charCounter');
    const length = input.value.length;
    counter.textContent = `${length} / 4000`;

    if (length > 3800) {
        counter.style.color = '#ef4444';
    } else {
        counter.style.color = 'var(--text-secondary)';
    }
}

// Handle form submission
async function handleSubmit(e) {
    e.preventDefault();

    if (isStreaming) return;

    const input = document.getElementById('chatInput');
    const message = input.value.trim();

    if (!message || message.length > 4000) return;

    // Clear input immediately
    input.value = '';
    input.style.height = 'auto';
    updateCharCounter();

    // Hide welcome screen if visible
    const welcomeScreen = document.getElementById('welcomeScreen');
    if (welcomeScreen) {
        welcomeScreen.style.display = 'none';
    }

    // Create session if needed
    if (!currentSession) {
        await createSession();
    }

    // Send message
    await sendMessage(message);
}