document.addEventListener('DOMContentLoaded', () => {
    // ============================================
    // ELEMENTS
    // ============================================
    const chatForm       = document.getElementById('chat-form');
    const userInput      = document.getElementById('user-input');
    const chatHistory    = document.getElementById('chat-history');
    const sendBtn        = document.getElementById('send-btn');
    const newChatBtn     = document.getElementById('new-chat-btn');
    const sessionsList   = document.getElementById('sessions-list');
    const sessionTitle   = document.getElementById('session-title');
    const clearChatBtn   = document.getElementById('clear-chat-btn');
    const sidebarToggle  = document.getElementById('sidebar-toggle');
    const themeToggle    = document.getElementById('theme-toggle');
    const sidebar        = document.getElementById('sidebar');
    const welcomeState   = document.getElementById('welcome-state');
    const toast          = document.getElementById('toast');
    const body           = document.body;

    // ============================================
    // THEME MANAGEMENT
    // ============================================
    const THEME_KEY = 'atlas_theme_v1';
    let currentTheme = localStorage.getItem(THEME_KEY) || 'dark';
    
    if (currentTheme === 'light') {
        body.classList.add('light-mode');
        updateThemeIcons();
    }

    themeToggle.addEventListener('click', () => {
        console.log('[Nexus AI] Theme toggle clicked. Current classes:', body.className);
        const isLight = body.classList.toggle('light-mode');
        console.log('[Nexus AI] New state - isLight:', isLight);
        currentTheme = isLight ? 'light' : 'dark';
        localStorage.setItem(THEME_KEY, currentTheme);
        updateThemeIcons();
    });

    function updateThemeIcons() {
        console.log('[Nexus AI] Theme updated, Mode:', body.classList.contains('light-mode') ? 'light' : 'dark');
        // Icons now handled by CSS classes .sun-icon / .moon-icon
    }

    // ============================================
    // STATE
    // ============================================
    const STORAGE_KEY = 'atlas_sessions_v2';
    let sessions = loadSessions();
    let activeId  = null;

    if (sessions.length === 0) {
        startNewSession();
    } else {
        activateSession(sessions[0].id);
    }
    renderSidebar();

    // ============================================
    // AUTO-RESIZE TEXTAREA
    // ============================================
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
    });

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!userInput.disabled) chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // ============================================
    // SUGGESTION CHIPS / FOLLOW UPS
    // ============================================
    document.body.addEventListener('click', (e) => {
        // Handle Welcome Chips
        const chip = e.target.closest('.chip');
        if (chip) {
            userInput.value = chip.dataset.q;
            userInput.dispatchEvent(new Event('input'));
            if (!userInput.disabled) chatForm.dispatchEvent(new Event('submit'));
            return;
        }

        // Handle Follow-up Buttons
        const followUp = e.target.closest('.follow-up-btn');
        if (followUp) {
            userInput.value = followUp.dataset.q;
            userInput.dispatchEvent(new Event('input'));
            if (!userInput.disabled) chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // ============================================
    // SIDEBAR TOGGLE
    // ============================================
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
    });

    newChatBtn.addEventListener('click', () => {
        startNewSession();
        renderSidebar();
        userInput.focus();
    });

    clearChatBtn.addEventListener('click', () => {
        if (!activeId) return;
        if (!confirm('Are you sure you want to delete this entire conversation?')) return;
        
        sessions = sessions.filter(s => s.id !== activeId);
        saveSessions();
        
        if (sessions.length > 0) {
            activateSession(sessions[0].id);
        } else {
            startNewSession();
        }
        showToast('Conversation deleted');
    });

    // ============================================
    // SUBMIT
    // ============================================
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = userInput.value.trim();
        if (!text) return;

        const session = getSession(activeId);
        if (!session) return;

        // Auto-title on first message
        if (session.messages.length === 0) {
            session.title = text.length > 40 ? text.slice(0, 38) + '…' : text;
            sessionTitle.textContent = session.title;
            saveSessions();
            renderSidebar();
        }

        if (welcomeState) welcomeState.style.display = 'none';

        // Add user message
        const userMsg = { role: 'user', content: text, ts: Date.now() };
        session.messages.push(userMsg);
        saveSessions();
        appendMessage(userMsg);

        userInput.value = '';
        userInput.style.height = 'auto';
        userInput.disabled = true;
        sendBtn.disabled = true;

        const loaderId = addLoader();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            if (!response.ok) throw new Error(`Server error ${response.status}`);
            const data = await response.json();
            
            removeLoader(loaderId);

            // ATLAS returns a structured "data" object
            const atlasData = data.data || {};
            console.log('[Nexus AI] Received ATLAS data:', atlasData);
            
            const aiMsg = { 
                role: 'assistant', 
                atlasData: atlasData, 
                content: atlasData.answer || data.response || "No response received.",
                ts: Date.now() 
            };
            session.messages.push(aiMsg);
            saveSessions();
            appendMessage(aiMsg);

        } catch (err) {
            console.error(err);
            removeLoader(loaderId);
            const errMsg = { role: 'assistant', content: '⚠️ Unable to connect to the server. Please check if the backend is running.', ts: Date.now() };
            session.messages.push(errMsg);
            saveSessions();
            appendMessage(errMsg);
        } finally {
            userInput.disabled = false;
            sendBtn.disabled = false;
            userInput.focus();
        }
    });

    // ============================================
    // RENDER HELPERS
    // ============================================
    function renderMessages(session) {
        Array.from(chatHistory.children).forEach(el => {
            if (el.id !== 'welcome-state') el.remove();
        });

        if (session.messages.length === 0) {
            if (welcomeState) welcomeState.style.display = '';
        } else {
            if (welcomeState) welcomeState.style.display = 'none';
            session.messages.forEach(m => appendMessage(m, false));
        }
        scrollBottom();
    }

    function appendMessage(msg, animate = true) {
        const wrapper = document.createElement('div');
        wrapper.className = `message ${msg.role}`;
        if (!animate) wrapper.style.animation = 'none';

        const isAI = msg.role === 'assistant';
        const avatarSVG = isAI
            ? `<div class="avatar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></div>`
            : `<div class="avatar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>`;

        let contentHTML = '';

        if (!isAI) {
            // User message is plain text
            contentHTML = `<div class="bubble">${escapeHtml(msg.content)}</div>`;
        } else {
            // AI message might be ATLAS structured
            if (msg.atlasData && msg.atlasData.confidence !== undefined) {
                const data = msg.atlasData;
                
                let intentEmoji = { 'news': '📰', 'technical': '⚙️', 'opinion': '💬', 'factual': '📖', 'general': '🔍' }[data.query_intent] || '🔍';
                let confClass = 'badge-conf-mid';
                if (data.confidence >= 0.75) confClass = 'badge-conf-high';
                else if (data.confidence < 0.45) confClass = 'badge-conf-low';

                let badgesHTML = `
                    <div class="atlas-badges">
                        <span class="badge badge-intent">${intentEmoji} ${data.query_intent}</span>
                        <span class="badge ${confClass}">Conf: ${data.confidence_label} (${Math.round(data.confidence * 100)}%)</span>
                    </div>
                `;

                let warningsHTML = '';
                const staleThreshold = 60;
                // If 999, we treat as potentially old if context suggests it (handled by backend or as last resort here)
                const staleSources = (data.sources || []).filter(s => s.age_days > staleThreshold);
                const staleCount = staleSources.length;

                if ((data.warnings && data.warnings.length > 0) || staleCount > 0) {
                    warningsHTML = `<div class="atlas-warnings">`;
                    
                    // Add existing backend warnings
                    if (data.warnings) {
                        data.warnings.forEach(w => {
                            warningsHTML += `<div class="warning-box"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${escapeHtml(w.replace('⚠️ ', ''))}</div>`;
                        });
                    }

                    // Add stale source warning
                    if (staleCount > 0) {
                        const sourceWord = staleCount === 1 ? 'source is' : 'sources are';
                        const staleMsg = `${staleCount} ${sourceWord} older than 60 days`;
                        warningsHTML += `<div class="warning-box stale-warning"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> ${staleMsg}</div>`;
                    }

                    warningsHTML += `</div>`;
                }

                let answerHTML = `<div class="bubble">${marked.parse(data.answer || msg.content)}</div>`;

                let citationsHTML = '';
                if (data.citations && data.citations.length > 0) {
                    citationsHTML = `<div class="atlas-citations">`;
                    data.citations.forEach(c => {
                        citationsHTML += `
                            <a href="${c.url}" target="_blank" class="cite-link" title="${escapeHtml(c.title)}">
                                <span class="cite-domain">[${c.num}] ${escapeHtml(c.domain)}</span>
                                <span class="cite-title">${escapeHtml(c.title)}</span>
                            </a>
                        `;
                    });
                    citationsHTML += `</div>`;
                }

                let followUpHTML = '';
                if (data.follow_ups && data.follow_ups.length > 0) {
                    followUpHTML = `
                        <div class="atlas-follow-ups">
                            <div class="follow-up-label">Explore Further</div>
                    `;
                    data.follow_ups.forEach(f => {
                        followUpHTML += `
                            <button class="follow-up-btn" data-q="${escapeHtml(f)}">
                                <span>${escapeHtml(f)}</span>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                            </button>
                        `;
                    });
                    followUpHTML += `</div>`;
                }

                contentHTML = `
                    <div class="ai-content-box">
                        ${badgesHTML}
                        ${warningsHTML}
                        ${answerHTML}
                        ${citationsHTML}
                        ${followUpHTML}
                    </div>
                `;

            } else {
                // Fallback for simple markdown
                contentHTML = `<div class="bubble">${marked.parse(msg.content)}</div>`;
            }
        }

        const timeStr = formatTime(msg.ts);
        const copyBtnHtml = isAI
            ? `<button class="copy-btn" data-text="${encodeURIComponent(msg.content)}" title="Copy text">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                Copy
               </button>`
            : '';

        wrapper.innerHTML = `
            <div class="message-row">
                ${avatarSVG}
                ${contentHTML}
            </div>
            <div class="message-meta">
                <span>${timeStr}</span>
                ${copyBtnHtml}
            </div>
        `;

        const copyBtn = wrapper.querySelector('.copy-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                const text = decodeURIComponent(copyBtn.dataset.text);
                navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!'));
            });
        }

        chatHistory.appendChild(wrapper);
        scrollBottom();
    }

    function addLoader() {
        const id = 'loader-' + Date.now();
        const el = document.createElement('div');
        el.className = 'message assistant';
        el.id = id;
        el.innerHTML = `
            <div class="message-row">
                <div class="avatar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></div>
                <div class="bubble" style="padding: 16px 20px; width: auto;">
                    <div class="loader-bars"><span></span><span></span><span></span></div>
                </div>
            </div>
        `;
        chatHistory.appendChild(el);
        scrollBottom();
        return id;
    }

    function removeLoader(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function scrollBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // ============================================
    // SESSION MANAGEMENT
    // ============================================
    function startNewSession() {
        const id = 'session-' + Date.now();
        const session = { id, title: 'New Conversation', messages: [], ts: Date.now() };
        sessions.unshift(session);
        saveSessions();
        activateSession(id);
    }

    function activateSession(id) {
        activeId = id;
        const session = getSession(id);
        if (!session) return;
        sessionTitle.textContent = session.title;
        renderMessages(session);
        renderSidebar();
    }

    function getSession(id) {
        return sessions.find(s => s.id === id) || null;
    }

    function renderSidebar() {
        sessionsList.innerHTML = '';
        sessions.slice(0, 30).forEach(s => {
            const item = document.createElement('div');
            item.className = 'session-item' + (s.id === activeId ? ' active' : '');
            item.innerHTML = `
                <div class="session-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </div>
                <span class="session-label">${escapeHtml(s.title)}</span>
            `;
            item.addEventListener('click', () => activateSession(s.id));
            sessionsList.appendChild(item);
        });
    }

    // ============================================
    // LOCAL STORAGE
    // ============================================
    function loadSessions() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
        } catch {
            return [];
        }
    }

    function saveSessions() {
        const trimmed = sessions.slice(0, 30).map(s => ({
            ...s,
            messages: s.messages.slice(-50)
        }));
        localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
    }

    // ============================================
    // UTILITIES
    // ============================================
    function formatTime(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function showToast(msg) {
        toast.textContent = msg;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 2200);
    }
});
