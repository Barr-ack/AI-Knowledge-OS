/**
 * Enterprise Knowledge Assistant — Frontend JavaScript
 *
 * Handles:
 * - Chat interface (send/receive messages, streaming-style rendering)
 * - Document upload with drag-and-drop
 * - Conversation session management
 * - Source citation display
 * - Sidebar and history management
 * - Toast notifications
 */

'use strict';

// ─── Configuration ────────────────────────────────────────────────────────────

const CONFIG = {
  API_BASE: 'http://localhost:8000',
  MAX_CHAR: 2000,
};

// ─── State ────────────────────────────────────────────────────────────────────

const state = {
  sessionId: generateUUID(),
  isLoading: false,
  uploadedDocs: [],          // { name, chunks, type }
  conversations: [],         // { id, title, messages[] }
  currentConvId: null,
  kbHasDocuments: false,
};

// ─── DOM References ───────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const dom = {
  sidebar:          $('sidebar'),
  sidebarToggle:    $('sidebarToggle'),
  menuBtn:          $('menuBtn'),
  newChatBtn:       $('newChatBtn'),
  fileInput:        $('fileInput'),
  uploadZone:       $('uploadZone'),
  browseBtn:        $('browseBtn'),
  uploadProgress:   $('uploadProgress'),
  uploadFileName:   $('uploadFileName'),
  uploadPercent:    $('uploadPercent'),
  progressBarFill:  $('progressBarFill'),
  documentsList:    $('documentsList'),
  kbStatus:         $('kbStatus'),
  kbStatusDot:      $('kbStatusDot'),
  kbStatusText:     $('kbStatusText'),
  historyList:      $('historyList'),
  messagesContainer: $('messagesContainer'),
  welcomeScreen:    $('welcomeScreen'),
  messagesList:     $('messagesList'),
  messageInput:     $('messageInput'),
  sendBtn:          $('sendBtn'),
  charCount:        $('charCount'),
  clearChatBtn:     $('clearChatBtn'),
  topbarTitle:      $('topbarTitle'),
  attachBtn:        $('attachBtn'),
  connectionIndicator: $('connectionIndicator'),
  toast:            $('toast'),
  toastMessage:     $('toastMessage'),
  toastIcon:        $('toastIcon'),
};

// ─── Initialization ───────────────────────────────────────────────────────────

async function init() {
  bindEvents();
  await checkHealth();
  restoreSessionFromStorage();
}

// ─── Event Bindings ───────────────────────────────────────────────────────────

function bindEvents() {
  // Sidebar toggle
  dom.sidebarToggle.addEventListener('click', closeSidebar);
  dom.menuBtn.addEventListener('click', openSidebar);

  // New chat
  dom.newChatBtn.addEventListener('click', startNewChat);

  // File upload
  dom.browseBtn.addEventListener('click', e => { e.stopPropagation(); dom.fileInput.click(); });
  dom.uploadZone.addEventListener('click', () => dom.fileInput.click());
  dom.fileInput.addEventListener('change', e => handleFileSelect(e.target.files));
  dom.attachBtn.addEventListener('click', () => dom.fileInput.click());

  // Drag and drop
  dom.uploadZone.addEventListener('dragover', e => { e.preventDefault(); dom.uploadZone.classList.add('drag-over'); });
  dom.uploadZone.addEventListener('dragleave', () => dom.uploadZone.classList.remove('drag-over'));
  dom.uploadZone.addEventListener('drop', e => {
    e.preventDefault();
    dom.uploadZone.classList.remove('drag-over');
    handleFileSelect(e.dataTransfer.files);
  });

  // Chat input
  dom.messageInput.addEventListener('input', onInputChange);
  dom.messageInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!dom.sendBtn.disabled) sendMessage();
    }
  });

  // Send
  dom.sendBtn.addEventListener('click', sendMessage);

  // Clear chat
  dom.clearChatBtn.addEventListener('click', clearCurrentChat);

  // Suggestion chips
  document.addEventListener('click', e => {
    const chip = e.target.closest('.suggestion-chip');
    if (chip) {
      const q = chip.dataset.q;
      dom.messageInput.value = q;
      onInputChange();
      sendMessage();
    }
  });
}

// ─── Input Handling ───────────────────────────────────────────────────────────

function onInputChange() {
  const val = dom.messageInput.value;
  const len = val.length;

  // Update char counter
  dom.charCount.textContent = `${len}/${CONFIG.MAX_CHAR}`;
  dom.charCount.style.color = len > CONFIG.MAX_CHAR * 0.9 ? 'var(--warning)' : '';

  // Enable/disable send button
  dom.sendBtn.disabled = len === 0 || state.isLoading;

  // Auto-resize textarea
  dom.messageInput.style.height = 'auto';
  dom.messageInput.style.height = Math.min(dom.messageInput.scrollHeight, 160) + 'px';
}

// ─── Send Message ─────────────────────────────────────────────────────────────

async function sendMessage() {
  const question = dom.messageInput.value.trim();
  if (!question || state.isLoading) return;

  // Hide welcome screen, show messages
  dom.welcomeScreen.style.display = 'none';

  // Add user message to UI
  appendMessage('user', question);

  // Clear input
  dom.messageInput.value = '';
  dom.messageInput.style.height = 'auto';
  onInputChange();

  // Create/update conversation in history
  ensureConversation(question);

  // Show typing indicator
  const typingId = showTypingIndicator();

  state.isLoading = true;
  dom.sendBtn.disabled = true;

  try {
    const response = await fetch(`${CONFIG.API_BASE}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        session_id: state.sessionId,
      }),
    });

    removeTypingIndicator(typingId);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    // Append AI response
    appendMessage('assistant', data.answer, {
      sources: data.sources,
      hasContext: data.has_context,
    });

    // Save session ID from response (in case backend generated one)
    if (data.session_id) state.sessionId = data.session_id;

    // Update conversation in history
    saveConversationTurn(question, data.answer);

  } catch (err) {
    removeTypingIndicator(typingId);
    const isNetwork = err.message.includes('fetch') || err.message.includes('network');
    appendMessage('assistant',
      isNetwork
        ? '⚠️ Could not reach the backend server. Please make sure the API is running on port 8000.'
        : `Sorry, I encountered an error: ${err.message}`,
      { isError: true }
    );
    showToast(err.message, 'error');
  } finally {
    state.isLoading = false;
    onInputChange();
    scrollToBottom();
  }
}

// ─── Message Rendering ────────────────────────────────────────────────────────

function appendMessage(role, content, meta = {}) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const avatarHtml = role === 'user'
    ? `<div class="message-avatar">You</div>`
    : `<div class="message-avatar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
        </svg>
      </div>`;

  const renderedContent = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);

  let sourcesHtml = '';
  if (meta.sources && meta.sources.length > 0) {
    sourcesHtml = `
      <div class="sources-section">
        <div class="sources-header">
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2 2 2 0 002 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2 2 2 0 00-2-2V5a2 2 0 00-2-2H5z"/>
          </svg>
          Sources (${meta.sources.length})
        </div>
        ${meta.sources.map((s, i) => `
          <div class="source-item">
            <div class="source-num">${i + 1}</div>
            <div class="source-info">
              <div class="source-doc">
                ${escapeHtml(s.document)}
                ${s.page ? `<span style="color:var(--text-muted)"> · Page ${s.page}</span>` : ''}
                <span class="source-score">${(s.relevance_score * 100).toFixed(0)}% match</span>
              </div>
              ${s.excerpt ? `<div class="source-excerpt">${escapeHtml(s.excerpt.substring(0, 200))}...</div>` : ''}
            </div>
          </div>
        `).join('')}
      </div>`;
  }

  const noContextBanner = (role === 'assistant' && meta.hasContext === false && !meta.isError)
    ? `<div class="no-context-banner">
        <svg viewBox="0 0 16 16" fill="currentColor">
          <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
        </svg>
        No matching documents found. Upload relevant documents to improve answers.
      </div>`
    : '';

  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  msg.innerHTML = `
    ${avatarHtml}
    <div class="message-body">
      <div class="message-bubble">${renderedContent}</div>
      ${sourcesHtml}
      ${noContextBanner}
      <div class="message-meta">
        <span>${time}</span>
      </div>
    </div>`;

  dom.messagesList.appendChild(msg);
  scrollToBottom();
  return msg;
}

// Simple markdown renderer for assistant messages
function renderMarkdown(text) {
  return text
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // Unordered lists
    .replace(/^\s*[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // Line breaks — paragraphs
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hupol])(.+)$/gm, (_, p) => p ? p : '')
    // Wrap in paragraph tags if needed
    .replace(/^([^<].*)$/gm, (match) => {
      if (!match.startsWith('<') && match.trim()) return match;
      return match;
    })
    // Clean up extra breaks
    .replace(/\n/g, '<br>')
    // Wrap in p if plain text starts
    ;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── Typing Indicator ─────────────────────────────────────────────────────────

function showTypingIndicator() {
  const id = 'typing-' + Date.now();
  const el = document.createElement('div');
  el.id = id;
  el.className = 'message assistant';
  el.innerHTML = `
    <div class="message-avatar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
      </svg>
    </div>
    <div class="message-body">
      <div class="typing-indicator">
        <div class="typing-dots">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
        <span class="typing-label">Searching knowledge base...</span>
      </div>
    </div>`;
  dom.messagesList.appendChild(el);
  scrollToBottom();
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ─── File Upload ──────────────────────────────────────────────────────────────

async function handleFileSelect(files) {
  if (!files || files.length === 0) return;

  for (const file of Array.from(files)) {
    await uploadFile(file);
  }

  // Reset file input
  dom.fileInput.value = '';
}

async function uploadFile(file) {
  const allowed = ['.pdf', '.docx', '.doc', '.txt', '.md'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();

  if (!allowed.includes(ext)) {
    showToast(`Unsupported file type: ${ext}`, 'error');
    return;
  }

  if (file.size > 50 * 1024 * 1024) {
    showToast('File too large (max 50MB)', 'error');
    return;
  }

  // Show progress
  dom.uploadFileName.textContent = file.name;
  dom.uploadPercent.textContent = '0%';
  dom.progressBarFill.style.width = '0%';
  dom.uploadProgress.style.display = 'block';

  // Animate progress (simulated for UX while actual upload happens)
  let progress = 0;
  const progressInterval = setInterval(() => {
    progress = Math.min(progress + Math.random() * 15, 85);
    dom.progressBarFill.style.width = progress + '%';
    dom.uploadPercent.textContent = Math.floor(progress) + '%';
  }, 200);

  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${CONFIG.API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });

    clearInterval(progressInterval);

    // Complete progress
    dom.progressBarFill.style.width = '100%';
    dom.uploadPercent.textContent = '100%';

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    // Add to documents list
    addDocumentToList(file.name, data.chunks_created, ext.slice(1));
    state.kbHasDocuments = true;
    updateKBStatus(true, state.uploadedDocs.length);

    showToast(`"${file.name}" added — ${data.chunks_created} chunks indexed`, 'success');

    setTimeout(() => {
      dom.uploadProgress.style.display = 'none';
    }, 1500);

  } catch (err) {
    clearInterval(progressInterval);
    dom.uploadProgress.style.display = 'none';
    showToast(`Upload failed: ${err.message}`, 'error');
  }
}

function addDocumentToList(fileName, chunks, type) {
  const doc = { name: fileName, chunks, type };
  state.uploadedDocs.push(doc);

  const iconMap = { pdf: 'PDF', docx: 'DOC', doc: 'DOC', txt: 'TXT', md: 'MD' };
  const iconClass = ['pdf', 'docx', 'doc', 'txt', 'md'].includes(type) ? type : 'default';

  const el = document.createElement('div');
  el.className = 'doc-item';
  el.innerHTML = `
    <div class="doc-icon ${iconClass}">${iconMap[type] || 'FILE'}</div>
    <div class="doc-info">
      <div class="doc-name" title="${escapeHtml(fileName)}">${escapeHtml(fileName)}</div>
      <div class="doc-chunks">${chunks} chunks indexed</div>
    </div>
    <div class="doc-check">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="3 8 6.5 11.5 13 5"/>
      </svg>
    </div>`;

  dom.documentsList.appendChild(el);
}

function updateKBStatus(active, count) {
  dom.kbStatusDot.classList.toggle('active', active);
  dom.kbStatusText.textContent = active
    ? `${count} document${count !== 1 ? 's' : ''} loaded`
    : 'Knowledge base empty';
}

// ─── Conversation Management ──────────────────────────────────────────────────

function ensureConversation(firstQuestion) {
  if (!state.currentConvId) {
    const id = generateUUID();
    const title = firstQuestion.substring(0, 40) + (firstQuestion.length > 40 ? '...' : '');
    state.currentConvId = id;
    state.conversations.unshift({ id, title, messages: [] });
    renderHistoryList();
    dom.topbarTitle.textContent = title;
  }
}

function saveConversationTurn(question, answer) {
  const conv = state.conversations.find(c => c.id === state.currentConvId);
  if (conv) {
    conv.messages.push({ role: 'user', content: question });
    conv.messages.push({ role: 'assistant', content: answer });
    saveToLocalStorage();
  }
}

function renderHistoryList() {
  if (state.conversations.length === 0) {
    dom.historyList.innerHTML = '<div class="history-empty">No conversations yet</div>';
    return;
  }

  dom.historyList.innerHTML = state.conversations.map(conv => `
    <div class="history-item ${conv.id === state.currentConvId ? 'active' : ''}" 
         data-id="${conv.id}" title="${escapeHtml(conv.title)}">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M14 9.5a5 5 0 01-5 5 4.97 4.97 0 01-2.5-.67L2 15l1.17-4.5A4.97 4.97 0 012 8a5 5 0 015-5 5 5 0 017 4.5z"/>
      </svg>
      ${escapeHtml(conv.title)}
    </div>
  `).join('');

  // Click handlers
  dom.historyList.querySelectorAll('.history-item').forEach(item => {
    item.addEventListener('click', () => loadConversation(item.dataset.id));
  });
}

function loadConversation(convId) {
  const conv = state.conversations.find(c => c.id === convId);
  if (!conv) return;

  state.currentConvId = convId;
  state.sessionId = convId; // Use same ID for backend session

  // Clear and rebuild message list
  dom.messagesList.innerHTML = '';
  dom.welcomeScreen.style.display = 'none';

  conv.messages.forEach(msg => {
    appendMessage(msg.role, msg.content);
  });

  dom.topbarTitle.textContent = conv.title;
  renderHistoryList();

  // On mobile, close sidebar after selecting
  if (window.innerWidth < 768) closeSidebar();
}

function startNewChat() {
  state.currentConvId = null;
  state.sessionId = generateUUID();
  dom.messagesList.innerHTML = '';
  dom.welcomeScreen.style.display = 'flex';
  dom.topbarTitle.textContent = 'Enterprise Knowledge Assistant';
  renderHistoryList();
  dom.messageInput.focus();
}

function clearCurrentChat() {
  if (!state.currentConvId) return;

  // Clear messages in UI
  dom.messagesList.innerHTML = '';
  dom.welcomeScreen.style.display = 'flex';

  // Clear backend session
  fetch(`${CONFIG.API_BASE}/session/${state.sessionId}`, { method: 'DELETE' })
    .catch(() => {});

  // Remove from conversations
  state.conversations = state.conversations.filter(c => c.id !== state.currentConvId);
  state.currentConvId = null;
  state.sessionId = generateUUID();
  dom.topbarTitle.textContent = 'Enterprise Knowledge Assistant';
  renderHistoryList();
  saveToLocalStorage();
}

// ─── Health Check ─────────────────────────────────────────────────────────────

async function checkHealth() {
  try {
    const res = await fetch(`${CONFIG.API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      const data = await res.json();
      // Update KB status if documents are already loaded
      if (data.vector_store?.is_initialized) {
        state.kbHasDocuments = true;
        const count = data.vector_store?.total_vectors || '?';
        updateKBStatus(true, count + ' vectors');
      }
      setConnectionStatus(true);
    } else {
      setConnectionStatus(false);
    }
  } catch {
    setConnectionStatus(false);
  }
}

function setConnectionStatus(connected) {
  const dot = dom.connectionIndicator.querySelector('.conn-dot');
  const label = dom.connectionIndicator.querySelector('.conn-label');
  dot.style.background = connected ? 'var(--success)' : 'var(--error)';
  label.textContent = connected ? 'Connected' : 'Offline';
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

function openSidebar() {
  if (window.innerWidth < 768) {
    dom.sidebar.classList.add('open');
  } else {
    dom.sidebar.classList.remove('collapsed');
  }
}

function closeSidebar() {
  if (window.innerWidth < 768) {
    dom.sidebar.classList.remove('open');
  } else {
    dom.sidebar.classList.add('collapsed');
  }
}

// ─── Toast ────────────────────────────────────────────────────────────────────

let toastTimeout;

function showToast(message, type = 'info') {
  clearTimeout(toastTimeout);

  const icons = {
    success: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 8 6.5 11.5 13 5"/></svg>`,
    error: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>`,
    info: `<svg viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M8 16A8 8 0 108 0a8 8 0 000 16zm1-11a1 1 0 10-2 0v2a1 1 0 102 0V5zm-1 6a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>`,
  };

  dom.toast.className = `toast ${type}`;
  dom.toastIcon.innerHTML = icons[type] || icons.info;
  dom.toastMessage.textContent = message;
  dom.toast.classList.add('show');

  toastTimeout = setTimeout(() => dom.toast.classList.remove('show'), 4000);
}

// ─── Local Storage ────────────────────────────────────────────────────────────

function saveToLocalStorage() {
  try {
    localStorage.setItem('eka_conversations', JSON.stringify(state.conversations));
    localStorage.setItem('eka_docs', JSON.stringify(state.uploadedDocs));
  } catch {}
}

function restoreSessionFromStorage() {
  try {
    const convs = localStorage.getItem('eka_conversations');
    const docs = localStorage.getItem('eka_docs');

    if (convs) {
      state.conversations = JSON.parse(convs);
      renderHistoryList();
    }

    if (docs) {
      state.uploadedDocs = JSON.parse(docs);
      state.uploadedDocs.forEach(doc => {
        addDocumentToList(doc.name, doc.chunks, doc.type);
      });
      if (state.uploadedDocs.length > 0) {
        updateKBStatus(true, state.uploadedDocs.length);
      }
    }
  } catch {}
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function scrollToBottom() {
  requestAnimationFrame(() => {
    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
  });
}

function generateUUID() {
  return 'xxxx-4xxx-yxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  }) + '-' + Date.now().toString(36);
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', init);
