/**
 * AeroReg Simple Chatbot — Client Application
 * Communicates with the FastAPI backend via /llm/ask
 */

// Application State
const state = {
  apiUrl: localStorage.getItem('aeroreg_api_url') || '/api',
  provider: localStorage.getItem('aeroreg_provider') || 'lm_studio',
  geminiModel: localStorage.getItem('aeroreg_gemini_model') || 'gemini-2.5-flash',
  topK: parseInt(localStorage.getItem('aeroreg_topk') || '3', 10),
  domain: 'all',
  source: 'all',
  keywordFilter: '',
  messages: [],
  isLoading: false,
  isOnline: false,
};

// DOM Elements
const elements = {
  statusPill: document.getElementById('backend-status'),
  statusDot: document.getElementById('status-dot'),
  statusText: document.getElementById('status-text'),
  btnOpenSettings: document.getElementById('btn-open-settings'),
  btnCloseSettings: document.getElementById('btn-close-settings'),
  btnSaveSettings: document.getElementById('btn-save-settings'),
  settingsModal: document.getElementById('settings-modal'),
  settingApiUrl: document.getElementById('setting-api-url'),
  settingProvider: document.getElementById('setting-provider'),
  settingGeminiModel: document.getElementById('setting-gemini-model'),
  groupGeminiModel: document.getElementById('group-gemini-model'),
  settingTopk: document.getElementById('setting-topk'),
  topkVal: document.getElementById('topk-val'),
  btnClearChat: document.getElementById('btn-clear-chat'),
  sourceChipsContainer: document.getElementById('source-chips-container'),
  activeSourcePill: document.getElementById('active-source-pill'),
  domainChipsContainer: document.getElementById('domain-chips-container'),
  activeDomainPill: document.getElementById('active-domain-pill'),
  keywordFilterInput: document.getElementById('keyword-filter-input'),
  btnClearKeyword: document.getElementById('btn-clear-keyword'),
  activeKeywordPill: document.getElementById('active-keyword-pill'),
  keywordBadge: document.getElementById('keyword-badge'),
  activeProviderPill: document.getElementById('active-provider-pill'),
  welcomeHero: document.getElementById('welcome-hero'),
  messagesViewport: document.getElementById('messages-viewport'),
  messagesList: document.getElementById('messages-list'),
  loadingIndicator: document.getElementById('loading-indicator'),
  loadingStatusText: document.getElementById('loading-status-text'),
  chatTextarea: document.getElementById('chat-textarea'),
  btnSendMessage: document.getElementById('btn-send-message'),
};

// Simple Markdown Renderer
function renderMarkdown(md) {
  if (!md) return '';
  
  // Escape raw HTML tags
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks: ```lang ... ```
  html = html.replace(/```([\w-]*)\n([\s\S]*?)```/g, (_m, lang, code) => {
    return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headings: ###, ##, #
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Blockquotes
  html = html.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

  // Unordered list items: - or *
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
  // Clean nested duplicate <ul> tags
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Tables
  if (html.includes('|')) {
    const lines = html.split('\n');
    let inTable = false;
    let tableHtml = '';
    const newLines = [];

    for (const line of lines) {
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        const cells = line.split('|').map(c => c.trim()).filter((_c, i, a) => i > 0 && i < a.length - 1);
        if (!inTable) {
          inTable = true;
          tableHtml = '<table><thead><tr>' + cells.map(c => `<th>${c}</th>`).join('') + '</tr></thead><tbody>';
        } else if (line.includes('---')) {
          // Separator row
          continue;
        } else {
          tableHtml += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
        }
      } else {
        if (inTable) {
          tableHtml += '</tbody></table>';
          newLines.push(tableHtml);
          inTable = false;
          tableHtml = '';
        }
        newLines.push(line);
      }
    }
    if (inTable) {
      tableHtml += '</tbody></table>';
      newLines.push(tableHtml);
    }
    html = newLines.join('\n');
  }

  // Paragraphs
  const paragraphs = html.split(/\n\n+/);
  html = paragraphs.map(p => {
    const trimmed = p.trim();
    if (
      trimmed.startsWith('<h') ||
      trimmed.startsWith('<ul') ||
      trimmed.startsWith('<ol') ||
      trimmed.startsWith('<table') ||
      trimmed.startsWith('<pre') ||
      trimmed.startsWith('<blockquote')
    ) {
      return trimmed;
    }
    return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
  }).join('');

  return html;
}

// Health Check
async function checkBackendHealth() {
  elements.statusDot.className = 'status-dot';
  elements.statusText.textContent = 'Checking...';

  try {
    const res = await fetch(`${state.apiUrl}/regulations/catalog?limit=1`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: AbortSignal.timeout(4000)
    });
    
    if (res.ok) {
      state.isOnline = true;
      elements.statusDot.className = 'status-dot online';
      elements.statusText.textContent = 'Connected';
      elements.statusPill.title = `Backend reachable at ${state.apiUrl}`;
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (_e) {
    state.isOnline = false;
    elements.statusDot.className = 'status-dot offline';
    elements.statusText.textContent = 'Offline';
    elements.statusPill.title = `Unable to connect to ${state.apiUrl}. Check server or proxy settings.`;
  }
}

// Update Indicators
function updateIndicators() {
  const sourceLabels = {
    all: 'All Sources',
    easa: 'EASA',
    eu: 'EU (EUR-Lex)',
    faa: 'FAA',
    skybrary: 'SKYbrary',
    manual: 'Manuals',
    note: 'Notes'
  };
  if (elements.activeSourcePill) {
    elements.activeSourcePill.textContent = `Source: ${sourceLabels[state.source] || state.source}`;
  }

  const domainLabels = {
    all: 'All Domains',
    flight_ops: 'Flight Ops',
    airworthiness: 'Airworthiness',
    atm: 'ATM',
    aerodromes: 'Aerodromes',
    licensing: 'Licensing',
    drones: 'Drones / UAS'
  };
  elements.activeDomainPill.textContent = `Domain: ${domainLabels[state.domain] || state.domain}`;
  elements.activeProviderPill.textContent = state.provider === 'gemini' 
    ? `Gemini (${state.geminiModel})` 
    : 'LM Studio Local';

  if (state.keywordFilter && state.keywordFilter.trim()) {
    if (elements.activeKeywordPill) {
      elements.activeKeywordPill.style.display = 'inline-flex';
      elements.activeKeywordPill.textContent = `Keyword: "${state.keywordFilter}"`;
    }
    if (elements.btnClearKeyword) elements.btnClearKeyword.style.display = 'inline-block';
    if (elements.keywordBadge) elements.keywordBadge.style.display = 'inline-block';
  } else {
    if (elements.activeKeywordPill) elements.activeKeywordPill.style.display = 'none';
    if (elements.btnClearKeyword) elements.btnClearKeyword.style.display = 'none';
    if (elements.keywordBadge) elements.keywordBadge.style.display = 'none';
  }
}

// Send Message
async function handleSend(textToSend) {
  const query = (textToSend || elements.chatTextarea.value).trim();
  if (!query || state.isLoading) return;

  // Add User Message
  const userMsg = {
    id: 'user-' + Date.now(),
    role: 'user',
    content: query,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  };

  state.messages.push(userMsg);
  elements.chatTextarea.value = '';
  elements.chatTextarea.style.height = 'auto';
  renderChat();

  // Scroll to bottom
  elements.messagesViewport.scrollTop = elements.messagesViewport.scrollHeight;

  // Set Loading
  state.isLoading = true;
  elements.btnSendMessage.disabled = true;
  elements.loadingIndicator.style.display = 'flex';
  elements.loadingStatusText.textContent = state.provider === 'gemini'
    ? 'Consulting Gemini Cloud via /llm/ask...'
    : 'Querying Local LM Studio & Vector Retrieval...';

  try {
    // Build multi-turn context
    const conversationHistory = state.messages
      .filter(m => !m.isError)
      .map(m => ({ role: m.role, content: m.content }));

    const payload = {
      prompt: query,
      messages: conversationHistory,
      origin: state.source !== 'all' ? state.source : null,
      domain: state.domain !== 'all' ? state.domain : null,
      keyword_filter: state.keywordFilter.trim() || null,
      top_k: state.topK,
      provider: state.provider,
      model: state.provider === 'gemini' ? state.geminiModel : null,
      include_deactivated: false
    };

    const res = await fetch(`${state.apiUrl}/llm/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`API error ${res.status}: ${errText}`);
    }

    const data = await res.json();

    // Check if any referenced chunk is deactivated or superseded
    const referenced = data.referenced_chunks || [];
    const hasSuperseded = referenced.some(c => c.is_active === 0 || c.is_active === false || Boolean(c.superseded_by));

    const botMsg = {
      id: 'bot-' + Date.now(),
      role: 'assistant',
      content: data.answer || 'No response returned from the model.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      referencedChunks: referenced,
      suggestedFollowups: data.suggested_followups || [],
      providerInfo: data.provider_info,
      hasSuperseded
    };

    state.messages.push(botMsg);
  } catch (err) {
    const errorMsg = {
      id: 'err-' + Date.now(),
      role: 'assistant',
      isError: true,
      content: `**Request Failed:** ${err.message || 'Unknown network error'}\n\n*Make sure FastAPI is running on port 8000 and the \`/api\` proxy is active in Vite.*`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    state.messages.push(errorMsg);
  } finally {
    state.isLoading = false;
    elements.btnSendMessage.disabled = false;
    elements.loadingIndicator.style.display = 'none';
    renderChat();
    elements.messagesViewport.scrollTop = elements.messagesViewport.scrollHeight;
  }
}

// Render Chat Messages
function renderChat() {
  if (state.messages.length === 0) {
    elements.welcomeHero.style.display = 'block';
    elements.messagesList.innerHTML = '';
    return;
  }

  elements.welcomeHero.style.display = 'none';

  elements.messagesList.innerHTML = state.messages.map(msg => {
    if (msg.role === 'user') {
      return `
        <div class="message-row user" id="${msg.id}">
          <div class="message-bubble">
            ${renderMarkdown(msg.content)}
          </div>
          <div class="message-footer" style="justify-content: flex-end;">
            <span>${msg.timestamp}</span>
          </div>
        </div>
      `;
    }

    // Assistant Message
    const formattedContent = renderMarkdown(msg.content);

    // Citations Accordion
    let citationsHtml = '';
    if (msg.referencedChunks && msg.referencedChunks.length > 0) {
      const chunks = msg.referencedChunks;
      citationsHtml = `
        <div class="citations-box">
          <div class="citations-header" onclick="window.toggleCitations('${msg.id}')">
            <span>📚 Regulatory Sources (${chunks.length} Chunks)</span>
            <span id="chevron-${msg.id}">▼</span>
          </div>
          <div class="citations-list" id="citations-list-${msg.id}" style="display: none;">
            ${chunks.map(c => `
              <div class="citation-card">
                <div class="citation-title-row">
                  <span class="citation-title" title="${c.document_id}">${c.document_id}</span>
                  <span class="citation-source-pill">${c.source || 'REG'}</span>
                </div>
                ${c.superseded_by ? `<div style="color: #f59e0b; font-size: 0.7rem; font-weight: 600; margin-bottom: 2px;">⚠️ Superseded by: ${c.superseded_by} (0.1x fallback)</div>` : (c.is_active === 0 || c.is_active === false ? `<div style="color: #f59e0b; font-size: 0.7rem; font-weight: 600; margin-bottom: 2px;">⚠️ Deactivated / Suppressed (0.1x fallback)</div>` : '')}
                ${c.text ? `<div class="citation-excerpt">${c.text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Follow-ups
    let followupsHtml = '';
    if (msg.suggestedFollowups && msg.suggestedFollowups.length > 0) {
      followupsHtml = `
        <div class="followups-box">
          <div class="followups-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>
            Suggested Follow-Up Inquiries
          </div>
          <div class="followup-chips">
            ${msg.suggestedFollowups.map(f => `
              <button class="followup-btn" onclick="window.sendFollowup('${encodeURIComponent(f)}')">
                ↳ ${f}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Superseded Notice Alert Banner
    const supersededBanner = msg.hasSuperseded ? `
      <div class="alert-superseded">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <div><strong>Regulatory Notice:</strong> Portions of this answer reference regulatory instruments marked as superseded or deactivated. Verify with current consolidated amendments.</div>
      </div>
    ` : '';

    return `
      <div class="message-row assistant ${msg.isError ? 'error' : ''}" id="${msg.id}">
        <div class="message-bubble">
          ${formattedContent}
          ${supersededBanner}
          ${citationsHtml}
          ${followupsHtml}
        </div>
        <div class="message-footer">
          <span>${msg.providerInfo?.provider === 'gemini' ? 'Gemini Flash' : 'LM Studio'} · ${msg.timestamp}</span>
          <button class="footer-btn" onclick="window.copyAnswer('${msg.id}')">
            📋 Copy Answer
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// Window Global helpers for inline onclicks
window.toggleCitations = (msgId) => {
  const list = document.getElementById(`citations-list-${msgId}`);
  const chevron = document.getElementById(`chevron-${msgId}`);
  if (!list) return;
  const isHidden = list.style.display === 'none';
  list.style.display = isHidden ? 'flex' : 'none';
  if (chevron) chevron.textContent = isHidden ? '▲' : '▼';
};

window.sendFollowup = (encodedText) => {
  const text = decodeURIComponent(encodedText);
  handleSend(text);
};

window.copyAnswer = (msgId) => {
  const msg = state.messages.find(m => m.id === msgId);
  if (msg && msg.content) {
    navigator.clipboard.writeText(msg.content);
    alert('Answer copied to clipboard!');
  }
};

// Event Listeners Initialization
function initEvents() {
  // Source Chips
  if (elements.sourceChipsContainer) {
    elements.sourceChipsContainer.addEventListener('click', (e) => {
      const chip = e.target.closest('.filter-chip');
      if (!chip) return;
      
      elements.sourceChipsContainer.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.source = chip.dataset.source;
      updateIndicators();
    });
  }

  // Domain Chips
  elements.domainChipsContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip, .domain-chip');
    if (!chip) return;
    
    elements.domainChipsContainer.querySelectorAll('.filter-chip, .domain-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.domain = chip.dataset.domain;
    updateIndicators();
  });

  // Keyword Filter Input
  if (elements.keywordFilterInput) {
    elements.keywordFilterInput.addEventListener('input', (e) => {
      state.keywordFilter = e.target.value.trim();
      updateIndicators();
    });
  }

  if (elements.btnClearKeyword) {
    elements.btnClearKeyword.addEventListener('click', () => {
      if (elements.keywordFilterInput) elements.keywordFilterInput.value = '';
      state.keywordFilter = '';
      updateIndicators();
    });
  }

  // Prompt Cards in Hero
  elements.welcomeHero.addEventListener('click', (e) => {
    const card = e.target.closest('.prompt-card');
    if (!card) return;
    const prompt = card.dataset.prompt;
    const domain = card.dataset.domain;
    if (domain) {
      state.domain = domain;
      document.querySelectorAll('.domain-chip').forEach(c => {
        c.classList.toggle('active', c.dataset.domain === domain);
      });
      updateIndicators();
    }
    handleSend(prompt);
  });

  // Auto-resize Textarea
  elements.chatTextarea.addEventListener('input', () => {
    elements.chatTextarea.style.height = 'auto';
    elements.chatTextarea.style.height = Math.min(elements.chatTextarea.scrollHeight, 160) + 'px';
  });

  // Enter to send
  elements.chatTextarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Send Button
  elements.btnSendMessage.addEventListener('click', () => handleSend());

  // Clear Chat Button
  elements.btnClearChat.addEventListener('click', () => {
    if (state.messages.length === 0 || confirm('Start a new chat session? All active messages will be cleared.')) {
      state.messages = [];
      renderChat();
    }
  });

  // Settings Modal Open/Close
  elements.btnOpenSettings.addEventListener('click', () => {
    elements.settingApiUrl.value = state.apiUrl;
    elements.settingProvider.value = state.provider;
    elements.settingGeminiModel.value = state.geminiModel;
    elements.settingTopk.value = state.topK;
    elements.topkVal.textContent = state.topK;
    elements.groupGeminiModel.style.display = state.provider === 'gemini' ? 'flex' : 'none';
    elements.settingsModal.classList.add('open');
  });

  elements.btnCloseSettings.addEventListener('click', () => {
    elements.settingsModal.classList.remove('open');
  });

  elements.settingProvider.addEventListener('change', (e) => {
    elements.groupGeminiModel.style.display = e.target.value === 'gemini' ? 'flex' : 'none';
  });

  elements.settingTopk.addEventListener('input', (e) => {
    elements.topkVal.textContent = e.target.value;
  });

  elements.btnSaveSettings.addEventListener('click', () => {
    state.apiUrl = elements.settingApiUrl.value.trim() || '/api';
    state.provider = elements.settingProvider.value;
    state.geminiModel = elements.settingGeminiModel.value.trim() || 'gemini-2.5-flash';
    state.topK = parseInt(elements.settingTopk.value, 10) || 3;

    localStorage.setItem('aeroreg_api_url', state.apiUrl);
    localStorage.setItem('aeroreg_provider', state.provider);
    localStorage.setItem('aeroreg_gemini_model', state.geminiModel);
    localStorage.setItem('aeroreg_topk', state.topK.toString());

    updateIndicators();
    elements.settingsModal.classList.remove('open');
    checkBackendHealth();
  });
}

// Initialization
function init() {
  initEvents();
  updateIndicators();
  renderChat();
  checkBackendHealth();
}

document.addEventListener('DOMContentLoaded', init);
