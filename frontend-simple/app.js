/**
 * AeroReg Simple Chatbot — Client Application
 * Communicates with the FastAPI backend via /llm/ask
 */

const SETTINGS_KEY_V2 = 'aerolex_eu_settings_v2';

function loadAppSettings() {
  let v2 = null;
  try {
    const raw = localStorage.getItem(SETTINGS_KEY_V2);
    if (raw) v2 = JSON.parse(raw);
  } catch (e) {
    console.warn('Could not read aerolex_eu_settings_v2', e);
  }

  const apiUrl = v2?.apiUrl || localStorage.getItem('aeroreg_api_url') || '/api';
  const apiAuthToken = v2?.apiAuthToken || localStorage.getItem('aeroreg_api_token') || '';
  
  // provider: 'local' (default) or 'gemini'
  let provider = v2?.researchProvider || localStorage.getItem('aeroreg_provider') || 'local';
  if (provider === 'lm_studio') provider = 'local';
  
  const geminiApiKey = v2?.geminiApiKey || localStorage.getItem('aeroreg_gemini_api_key') || '';
  let geminiModel = v2?.geminiModel || localStorage.getItem('aeroreg_gemini_model') || 'gemini-3.5-flash';
  if (!geminiModel || geminiModel.startsWith('gemini-1.') || geminiModel.startsWith('gemini-2.')) {
    geminiModel = 'gemini-3.5-flash';
  }
  
  const enableReranker = v2 ? v2.enableReranker !== false : (localStorage.getItem('aeroreg_enable_reranker') !== 'false');
  const rerankerModel = v2?.rerankerModel || localStorage.getItem('aeroreg_reranker_model') || 'text-embedding-baai-bge-reranker-v2-m3-m3';
  const topK = v2?.defaultTopK ? parseInt(v2.defaultTopK, 10) : parseInt(localStorage.getItem('aeroreg_topk') || '5', 10);
  const defaultOrigin = v2?.defaultOrigin || localStorage.getItem('aeroreg_default_origin') || 'all';

  return {
    apiUrl,
    apiAuthToken,
    provider,
    geminiApiKey,
    geminiModel,
    enableReranker,
    rerankerModel,
    topK,
    defaultOrigin,
  };
}

const initialSettings = loadAppSettings();

// Application State
const state = {
  apiUrl: initialSettings.apiUrl,
  apiAuthToken: initialSettings.apiAuthToken,
  provider: initialSettings.provider, // 'local' | 'gemini'
  geminiApiKey: initialSettings.geminiApiKey,
  geminiModel: initialSettings.geminiModel,
  enableReranker: initialSettings.enableReranker,
  rerankerModel: initialSettings.rerankerModel,
  topK: initialSettings.topK,
  domain: 'all',
  source: initialSettings.defaultOrigin,
  keywordFilter: '',
  messages: [],
  isLoading: false,
  isOnline: false,

  // Knowledge Notes State
  activeTab: 'chat',
  notes: [],
  selectedNoteId: null,
  selectedNote: null,
  notesFilter: '',
  isNotesLoading: false,
  isSavingNote: false,
  isGeneratingKeywords: false,
};

function saveAppSettings(cfg) {
  // Update in-memory state
  state.apiUrl = cfg.apiUrl;
  state.apiAuthToken = cfg.apiAuthToken;
  state.provider = cfg.provider;
  state.geminiApiKey = cfg.geminiApiKey;
  state.geminiModel = cfg.geminiModel;
  state.enableReranker = cfg.enableReranker;
  state.rerankerModel = cfg.rerankerModel;
  state.topK = cfg.topK;
  if (cfg.defaultOrigin) state.source = cfg.defaultOrigin;

  // Save to legacy aeroreg_* keys
  localStorage.setItem('aeroreg_api_url', cfg.apiUrl);
  localStorage.setItem('aeroreg_api_token', cfg.apiAuthToken || '');
  localStorage.setItem('aeroreg_provider', cfg.provider);
  localStorage.setItem('aeroreg_gemini_api_key', cfg.geminiApiKey || '');
  localStorage.setItem('aeroreg_gemini_model', cfg.geminiModel);
  localStorage.setItem('aeroreg_enable_reranker', cfg.enableReranker ? 'true' : 'false');
  localStorage.setItem('aeroreg_reranker_model', cfg.rerankerModel);
  localStorage.setItem('aeroreg_topk', cfg.topK.toString());
  localStorage.setItem('aeroreg_default_origin', cfg.defaultOrigin || 'all');

  // Also sync into aerolex_eu_settings_v2 so main frontend & simple frontend share configuration
  try {
    const raw = localStorage.getItem(SETTINGS_KEY_V2);
    const existing = raw ? JSON.parse(raw) : {};
    const updated = {
      ...existing,
      apiUrl: cfg.apiUrl,
      apiAuthToken: cfg.apiAuthToken || '',
      researchProvider: cfg.provider,
      geminiApiKey: cfg.geminiApiKey || '',
      geminiModel: cfg.geminiModel,
      enableReranker: cfg.enableReranker,
      rerankerModel: cfg.rerankerModel,
      defaultTopK: cfg.topK,
      defaultOrigin: cfg.defaultOrigin || existing.defaultOrigin || 'all'
    };
    localStorage.setItem(SETTINGS_KEY_V2, JSON.stringify(updated));
  } catch (e) {
    console.warn('Could not save aerolex_eu_settings_v2', e);
  }
}

// DOM Elements
const elements = {
  statusPill: document.getElementById('backend-status'),
  statusDot: document.getElementById('status-dot'),
  statusText: document.getElementById('status-text'),
  btnOpenSettings: document.getElementById('btn-open-settings'),
  btnCloseSettings: document.getElementById('btn-close-settings'),
  btnCancelSettings: document.getElementById('btn-cancel-settings'),
  btnSaveSettings: document.getElementById('btn-save-settings'),
  settingsModal: document.getElementById('settings-modal'),

  settingApiUrl: document.getElementById('setting-api-url'),
  btnTestConnection: document.getElementById('btn-test-connection'),
  presetUrlProxy: document.getElementById('preset-url-proxy'),
  presetUrl127: document.getElementById('preset-url-127'),
  presetUrlLocal: document.getElementById('preset-url-local'),
  connectionTestResult: document.getElementById('connection-test-result'),

  providerCardLocal: document.getElementById('provider-card-local'),
  providerCardGemini: document.getElementById('provider-card-gemini'),
  providerRadioLocal: document.getElementById('provider-radio-local'),
  providerRadioGemini: document.getElementById('provider-radio-gemini'),

  drawerLmStudio: document.getElementById('drawer-lm-studio'),
  btnTestLmStudio: document.getElementById('btn-test-lm-studio'),
  lmStudioTestResult: document.getElementById('lm-studio-test-result'),

  drawerGemini: document.getElementById('drawer-gemini'),
  settingGeminiApiKey: document.getElementById('setting-gemini-api-key'),
  btnToggleGeminiKey: document.getElementById('btn-toggle-gemini-key'),
  btnTestGemini: document.getElementById('btn-test-gemini'),
  geminiTestResult: document.getElementById('gemini-test-result'),
  settingGeminiModelSelect: document.getElementById('setting-gemini-model-select'),
  settingGeminiModelCustom: document.getElementById('setting-gemini-model-custom'),
  geminiActiveModelBadge: document.getElementById('gemini-active-model-badge'),

  settingEnableReranker: document.getElementById('setting-enable-reranker'),
  drawerReranker: document.getElementById('drawer-reranker'),
  settingRerankerModel: document.getElementById('setting-reranker-model'),
  btnTestReranker: document.getElementById('btn-test-reranker'),
  presetRerankerLmstudio: document.getElementById('preset-reranker-lmstudio'),
  presetRerankerBgeV2: document.getElementById('preset-reranker-bge-v2'),
  presetRerankerBgeLarge: document.getElementById('preset-reranker-bge-large'),
  rerankerTestResult: document.getElementById('reranker-test-result'),

  settingTopk: document.getElementById('setting-topk'),
  topkVal: document.getElementById('topk-val'),
  settingDefaultSource: document.getElementById('setting-default-source'),

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

  // Navigation & Views
  navTabChat: document.getElementById('nav-tab-chat'),
  navTabNotes: document.getElementById('nav-tab-notes'),
  notesCountBadge: document.getElementById('notes-count-badge'),
  chatView: document.getElementById('chat-view'),
  notesView: document.getElementById('notes-view'),

  // Notes Sidebar
  notesSearchInput: document.getElementById('notes-search-input'),
  btnClearNotesSearch: document.getElementById('btn-clear-notes-search'),
  btnOpenAddNote: document.getElementById('btn-open-add-note'),
  btnRefreshNotes: document.getElementById('btn-refresh-notes'),
  notesTotalLabel: document.getElementById('notes-total-label'),
  notesLoadingState: document.getElementById('notes-loading-state'),
  notesEmptyState: document.getElementById('notes-empty-state'),
  notesCardsContainer: document.getElementById('notes-cards-container'),

  // Notes Main Panel
  noteEmptyPlaceholder: document.getElementById('note-empty-placeholder'),
  btnPlaceholderAddNote: document.getElementById('btn-placeholder-add-note'),
  noteDetailViewer: document.getElementById('note-detail-viewer'),
  detailNoteType: document.getElementById('detail-note-type'),
  detailValidityBadge: document.getElementById('detail-validity-badge'),
  detailDocId: document.getElementById('detail-doc-id'),
  btnDeleteCurrentNote: document.getElementById('btn-delete-current-note'),
  btnCloseNoteDetail: document.getElementById('btn-close-note-detail'),
  detailTitle: document.getElementById('detail-title'),
  detailCreator: document.getElementById('detail-creator'),
  detailProjectWrap: document.getElementById('detail-project-wrap'),
  detailProject: document.getElementById('detail-project'),
  detailDate: document.getElementById('detail-date'),
  detailKeywordsWrap: document.getElementById('detail-keywords-wrap'),
  detailKeywordsChips: document.getElementById('detail-keywords-chips'),
  detailSectionsContainer: document.getElementById('detail-sections-container'),

  // Add Note Modal
  addNoteModal: document.getElementById('add-note-modal'),
  btnCloseAddNote: document.getElementById('btn-close-add-note'),
  btnCancelAddNote: document.getElementById('btn-cancel-add-note'),
  btnSubmitAddNote: document.getElementById('btn-submit-add-note'),
  submitNoteText: document.getElementById('submit-note-text'),
  inputNoteTitle: document.getElementById('input-note-title'),
  inputNoteCreator: document.getElementById('input-note-creator'),
  inputNoteType: document.getElementById('input-note-type'),
  inputNoteProject: document.getElementById('input-note-project'),
  validityIndefinite: document.getElementById('validity-indefinite'),
  validityExpires: document.getElementById('validity-expires'),
  inputNoteExpiresAt: document.getElementById('input-note-expires-at'),
  inputNoteKeywords: document.getElementById('input-note-keywords'),
  btnAiGenerateKeywords: document.getElementById('btn-ai-generate-keywords'),
  aiGenerateBtnText: document.getElementById('ai-generate-btn-text'),
  btnAddFormSection: document.getElementById('btn-add-form-section'),
  formSectionsList: document.getElementById('form-sections-list'),
  addNoteError: document.getElementById('add-note-error'),
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
    icao: 'ICAO',
    skybrary: 'SKYbrary',
    manual: 'Manuals',
    note: 'Notes',
    user: 'User Docs'
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
    ? `Gemini (${state.geminiModel || 'Flash'})` 
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
    ? `Consulting Gemini Cloud (${state.geminiModel || 'Flash'}) via /llm/ask...`
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
      rerank: state.enableReranker !== false,
      reranker_model: state.rerankerModel || 'text-embedding-baai-bge-reranker-v2-m3-m3',
      provider: state.provider === 'gemini' ? 'gemini' : 'local',
      gemini_api_key: state.provider === 'gemini' ? (state.geminiApiKey || undefined) : undefined,
      gemini_model: state.provider === 'gemini' ? (state.geminiModel || 'gemini-3.5-flash') : undefined,
      include_deactivated: false
    };

    const headers = { 'Content-Type': 'application/json' };
    if (state.apiAuthToken && state.apiAuthToken.trim()) {
      headers['Authorization'] = `Bearer ${state.apiAuthToken.trim()}`;
    }

    const res = await fetch(`${state.apiUrl}/llm/ask`, {
      method: 'POST',
      headers,
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
                ${c.skybrary_explanation ? `<div style="color: #818cf8; font-size: 0.7rem; font-weight: 500; margin-bottom: 2px;">ℹ️ ${c.skybrary_explanation}</div>` : ''}
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

  // =========================================================================
  // Settings Modal Controls & Diagnostics
  // =========================================================================

  function getSelectedGeminiModel() {
    const sel = elements.settingGeminiModelSelect ? elements.settingGeminiModelSelect.value : 'gemini-3.5-flash';
    if (sel === 'custom') {
      return (elements.settingGeminiModelCustom ? elements.settingGeminiModelCustom.value.trim() : '') || 'gemini-3.5-flash';
    }
    return sel || 'gemini-3.5-flash';
  }

  function setGeminiModelInUI(model) {
    const standard = ['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-3.1-pro-preview'];
    if (standard.includes(model)) {
      if (elements.settingGeminiModelSelect) elements.settingGeminiModelSelect.value = model;
      if (elements.settingGeminiModelCustom) elements.settingGeminiModelCustom.style.display = 'none';
    } else {
      if (elements.settingGeminiModelSelect) elements.settingGeminiModelSelect.value = 'custom';
      if (elements.settingGeminiModelCustom) {
        elements.settingGeminiModelCustom.value = model || '';
        elements.settingGeminiModelCustom.style.display = 'block';
      }
    }
    if (elements.geminiActiveModelBadge) {
      elements.geminiActiveModelBadge.textContent = `Active: ${model || 'gemini-3.5-flash'}`;
    }
  }

  function setProviderInUI(provider) {
    const isGemini = provider === 'gemini';
    if (elements.providerRadioLocal) elements.providerRadioLocal.checked = !isGemini;
    if (elements.providerRadioGemini) elements.providerRadioGemini.checked = isGemini;

    if (isGemini) {
      if (elements.providerCardGemini) elements.providerCardGemini.classList.add('selected-gemini');
      if (elements.providerCardLocal) elements.providerCardLocal.classList.remove('selected-local');
      if (elements.drawerGemini) elements.drawerGemini.style.display = 'flex';
      if (elements.drawerLmStudio) elements.drawerLmStudio.style.display = 'none';
    } else {
      if (elements.providerCardLocal) elements.providerCardLocal.classList.add('selected-local');
      if (elements.providerCardGemini) elements.providerCardGemini.classList.remove('selected-gemini');
      if (elements.drawerLmStudio) elements.drawerLmStudio.style.display = 'flex';
      if (elements.drawerGemini) elements.drawerGemini.style.display = 'none';
    }
  }

  function updateUrlPresetsActive(url) {
    if (elements.presetUrlProxy) elements.presetUrlProxy.classList.toggle('active', url === '/api');
    if (elements.presetUrl127) elements.presetUrl127.classList.toggle('active', url === 'http://127.0.0.1:8000');
    if (elements.presetUrlLocal) elements.presetUrlLocal.classList.toggle('active', url === 'http://localhost:8000');
  }

  function updateRerankerPresetsActive(model) {
    if (elements.presetRerankerLmstudio) elements.presetRerankerLmstudio.classList.toggle('active', model === 'text-embedding-baai-bge-reranker-v2-m3-m3');
    if (elements.presetRerankerBgeV2) elements.presetRerankerBgeV2.classList.toggle('active', model === 'BAAI/bge-reranker-v2-m3');
    if (elements.presetRerankerBgeLarge) elements.presetRerankerBgeLarge.classList.toggle('active', model === 'BAAI/bge-reranker-large');
  }

  // Settings Modal Open
  if (elements.btnOpenSettings) {
    elements.btnOpenSettings.addEventListener('click', () => {
      if (elements.settingApiUrl) elements.settingApiUrl.value = state.apiUrl;
      updateUrlPresetsActive(state.apiUrl);

      setProviderInUI(state.provider);

      if (elements.settingGeminiApiKey) elements.settingGeminiApiKey.value = state.geminiApiKey || '';
      setGeminiModelInUI(state.geminiModel);

      if (elements.settingEnableReranker) {
        elements.settingEnableReranker.checked = state.enableReranker !== false;
      }
      if (elements.drawerReranker) {
        elements.drawerReranker.style.display = state.enableReranker !== false ? 'flex' : 'none';
      }
      if (elements.settingRerankerModel) {
        elements.settingRerankerModel.value = state.rerankerModel || 'text-embedding-baai-bge-reranker-v2-m3-m3';
        updateRerankerPresetsActive(elements.settingRerankerModel.value);
      }

      if (elements.settingTopk) elements.settingTopk.value = state.topK;
      if (elements.topkVal) elements.topkVal.textContent = state.topK;
      if (elements.settingDefaultSource) elements.settingDefaultSource.value = state.source || 'all';

      // Clear any previous transient diagnostics
      if (elements.connectionTestResult) elements.connectionTestResult.style.display = 'none';
      if (elements.lmStudioTestResult) elements.lmStudioTestResult.style.display = 'none';
      if (elements.geminiTestResult) elements.geminiTestResult.style.display = 'none';
      if (elements.rerankerTestResult) elements.rerankerTestResult.style.display = 'none';

      elements.settingsModal.classList.add('open');
    });
  }

  // Settings Modal Close & Cancel
  if (elements.btnCloseSettings) {
    elements.btnCloseSettings.addEventListener('click', () => {
      elements.settingsModal.classList.remove('open');
    });
  }
  if (elements.btnCancelSettings) {
    elements.btnCancelSettings.addEventListener('click', () => {
      elements.settingsModal.classList.remove('open');
    });
  }

  // Provider Selection Event Listeners
  if (elements.providerCardLocal) {
    elements.providerCardLocal.addEventListener('click', () => setProviderInUI('local'));
  }
  if (elements.providerCardGemini) {
    elements.providerCardGemini.addEventListener('click', () => setProviderInUI('gemini'));
  }
  if (elements.providerRadioLocal) {
    elements.providerRadioLocal.addEventListener('change', () => setProviderInUI('local'));
  }
  if (elements.providerRadioGemini) {
    elements.providerRadioGemini.addEventListener('change', () => setProviderInUI('gemini'));
  }

  // URL Presets
  if (elements.presetUrlProxy) {
    elements.presetUrlProxy.addEventListener('click', () => {
      if (elements.settingApiUrl) elements.settingApiUrl.value = '/api';
      updateUrlPresetsActive('/api');
    });
  }
  if (elements.presetUrl127) {
    elements.presetUrl127.addEventListener('click', () => {
      const url = 'http://127.0.0.1:8000';
      if (elements.settingApiUrl) elements.settingApiUrl.value = url;
      updateUrlPresetsActive(url);
    });
  }
  if (elements.presetUrlLocal) {
    elements.presetUrlLocal.addEventListener('click', () => {
      const url = 'http://localhost:8000';
      if (elements.settingApiUrl) elements.settingApiUrl.value = url;
      updateUrlPresetsActive(url);
    });
  }

  // Test FastAPI Connection
  if (elements.btnTestConnection) {
    elements.btnTestConnection.addEventListener('click', async () => {
      const targetUrl = (elements.settingApiUrl?.value || '/api').trim().replace(/\/+$/, '') || '/api';
      const btn = elements.btnTestConnection;
      const icon = btn.querySelector('.test-icon');
      const text = btn.querySelector('.btn-test-text');
      const resultBox = elements.connectionTestResult;

      btn.disabled = true;
      if (icon) icon.classList.add('spin-fast');
      if (text) text.textContent = 'Testing...';
      if (resultBox) resultBox.style.display = 'none';

      const startTime = performance.now();
      try {
        const res = await fetch(`${targetUrl}/search?query=aviation&top_k=1&origin=all`, {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          signal: AbortSignal.timeout(4500)
        });
        const latency = Math.round(performance.now() - startTime);

        if (res.ok) {
          resultBox.className = 'diagnostics-box success';
          resultBox.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            <div><strong>FastAPI Connected (${latency}ms):</strong> API endpoint is fully reachable and operational.</div>
          `;
          resultBox.style.display = 'flex';
        } else {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }
      } catch (err) {
        resultBox.className = 'diagnostics-box error';
        resultBox.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <div><strong>FastAPI Offline / Unreachable:</strong> ${err.message}. Ensure backend is running or select the <code>/api (Vite Proxy)</code> preset.</div>
        `;
        resultBox.style.display = 'flex';
      } finally {
        btn.disabled = false;
        if (icon) icon.classList.remove('spin-fast');
        if (text) text.textContent = 'Test Connection';
      }
    });
  }

  // Test LM Studio Connection
  if (elements.btnTestLmStudio) {
    elements.btnTestLmStudio.addEventListener('click', async () => {
      const targetUrl = (elements.settingApiUrl?.value || state.apiUrl).trim().replace(/\/+$/, '') || '/api';
      const btn = elements.btnTestLmStudio;
      const icon = btn.querySelector('.test-icon');
      const text = btn.querySelector('.btn-test-text');
      const resultBox = elements.lmStudioTestResult;

      btn.disabled = true;
      if (icon) icon.classList.add('spin-fast');
      if (text) text.textContent = 'Probing...';
      if (resultBox) resultBox.style.display = 'none';

      const startTime = performance.now();
      try {
        const res = await fetch(`${targetUrl}/search?query=aviation&top_k=1&origin=all`, {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          signal: AbortSignal.timeout(5000)
        });
        const latency = Math.round(performance.now() - startTime);

        if (res.ok) {
          resultBox.className = 'diagnostics-box success';
          resultBox.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            <div><strong>LM Studio & Vector Retrieval Active (${latency}ms):</strong> Local embeddings and LLM communication operational on <code>http://localhost:1234/v1</code>.</div>
          `;
          resultBox.style.display = 'flex';
        } else {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }
      } catch (err) {
        resultBox.className = 'diagnostics-box error';
        resultBox.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <div><strong>LM Studio Check Failed:</strong> ${err.message}. Verify that LM Studio is running locally on port 1234 with a model loaded.</div>
        `;
        resultBox.style.display = 'flex';
      } finally {
        btn.disabled = false;
        if (icon) icon.classList.remove('spin-fast');
        if (text) text.textContent = 'Test LM Studio';
      }
    });
  }

  // Show / Hide Gemini API Key
  if (elements.btnToggleGeminiKey && elements.settingGeminiApiKey) {
    elements.btnToggleGeminiKey.addEventListener('click', () => {
      const isPwd = elements.settingGeminiApiKey.type === 'password';
      elements.settingGeminiApiKey.type = isPwd ? 'text' : 'password';
      const eyeIcon = elements.btnToggleGeminiKey.querySelector('svg');
      if (eyeIcon) {
        eyeIcon.innerHTML = isPwd
          ? '<path d="m9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/>'
          : '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>';
      }
    });
  }

  // Test Gemini API Key
  if (elements.btnTestGemini) {
    elements.btnTestGemini.addEventListener('click', async () => {
      const key = (elements.settingGeminiApiKey?.value || '').trim();
      const model = getSelectedGeminiModel();
      const targetUrl = (elements.settingApiUrl?.value || state.apiUrl).trim().replace(/\/+$/, '') || '/api';
      const resultBox = elements.geminiTestResult;
      const btn = elements.btnTestGemini;
      const icon = btn.querySelector('.test-icon');
      const text = btn.querySelector('.btn-test-text');

      if (!key) {
        resultBox.className = 'diagnostics-box warning';
        resultBox.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <div>Please enter a Google Gemini API Key before testing.</div>
        `;
        resultBox.style.display = 'flex';
        return;
      }

      btn.disabled = true;
      if (icon) icon.classList.add('spin-fast');
      if (text) text.textContent = 'Verifying...';
      if (resultBox) resultBox.style.display = 'none';

      try {
        const res = await fetch(`${targetUrl}/research/test-gemini`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: key, model }),
          signal: AbortSignal.timeout(15000)
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        }

        const data = await res.json();
        const isConnected = data.success === true || data.status === 'connected' ||
          (typeof data.message === 'string' && data.message.toLowerCase().includes('successfully connected'));

        if (isConnected) {
          resultBox.className = 'diagnostics-box success';
          resultBox.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            <div>
              <strong>Gemini API Connected Successfully (${data.model || model}):</strong>
              <div>${data.message || 'Model probed successfully with valid cloud response.'}</div>
            </div>
          `;
        } else {
          resultBox.className = 'diagnostics-box error';
          resultBox.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div><strong>Gemini Validation Failed:</strong> ${data.message || 'Invalid API key or model identifier.'}</div>
          `;
        }
        resultBox.style.display = 'flex';
      } catch (err) {
        resultBox.className = 'diagnostics-box error';
        resultBox.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <div><strong>Gemini Connection Error:</strong> ${err.message}</div>
        `;
        resultBox.style.display = 'flex';
      } finally {
        btn.disabled = false;
        if (icon) icon.classList.remove('spin-fast');
        if (text) text.textContent = 'Test Key';
      }
    });
  }

  // Gemini Model Select
  if (elements.settingGeminiModelSelect) {
    elements.settingGeminiModelSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      if (elements.settingGeminiModelCustom) {
        elements.settingGeminiModelCustom.style.display = val === 'custom' ? 'block' : 'none';
      }
      const activeModel = val === 'custom' ? (elements.settingGeminiModelCustom?.value || 'custom') : val;
      if (elements.geminiActiveModelBadge) {
        elements.geminiActiveModelBadge.textContent = `Active: ${activeModel}`;
      }
    });
  }
  if (elements.settingGeminiModelCustom) {
    elements.settingGeminiModelCustom.addEventListener('input', (e) => {
      if (elements.geminiActiveModelBadge) {
        elements.geminiActiveModelBadge.textContent = `Active: ${e.target.value.trim() || 'custom'}`;
      }
    });
  }

  // Reranker Enable Toggle
  if (elements.settingEnableReranker) {
    elements.settingEnableReranker.addEventListener('change', (e) => {
      if (elements.drawerReranker) {
        elements.drawerReranker.style.display = e.target.checked ? 'flex' : 'none';
      }
    });
  }

  // Reranker Presets
  if (elements.presetRerankerLmstudio) {
    elements.presetRerankerLmstudio.addEventListener('click', () => {
      const model = 'text-embedding-baai-bge-reranker-v2-m3-m3';
      if (elements.settingRerankerModel) elements.settingRerankerModel.value = model;
      updateRerankerPresetsActive(model);
    });
  }
  if (elements.presetRerankerBgeV2) {
    elements.presetRerankerBgeV2.addEventListener('click', () => {
      const model = 'BAAI/bge-reranker-v2-m3';
      if (elements.settingRerankerModel) elements.settingRerankerModel.value = model;
      updateRerankerPresetsActive(model);
    });
  }
  if (elements.presetRerankerBgeLarge) {
    elements.presetRerankerBgeLarge.addEventListener('click', () => {
      const model = 'BAAI/bge-reranker-large';
      if (elements.settingRerankerModel) elements.settingRerankerModel.value = model;
      updateRerankerPresetsActive(model);
    });
  }

  // Test Reranker
  if (elements.btnTestReranker) {
    elements.btnTestReranker.addEventListener('click', async () => {
      const model = (elements.settingRerankerModel?.value || 'text-embedding-baai-bge-reranker-v2-m3-m3').trim();
      const targetUrl = (elements.settingApiUrl?.value || state.apiUrl).trim().replace(/\/+$/, '') || '/api';
      const resultBox = elements.rerankerTestResult;
      const btn = elements.btnTestReranker;
      const icon = btn.querySelector('.test-icon');
      const text = btn.querySelector('.btn-test-text');

      btn.disabled = true;
      if (icon) icon.classList.add('spin-fast');
      if (text) text.textContent = 'Testing...';
      if (resultBox) resultBox.style.display = 'none';

      try {
        const res = await fetch(`${targetUrl}/search/rerank/test`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_name: model }),
          signal: AbortSignal.timeout(10000)
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        }

        const data = await res.json();
        if (data.success) {
          const latMs = data.test_inference_seconds !== undefined ? Math.round(data.test_inference_seconds * 1000) : null;
          resultBox.className = 'diagnostics-box success';
          resultBox.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            <div>
              <strong>Reranker Operational (${data.resolved_model || model}):</strong>
              <div>Device: <code>${(data.device || 'cpu').toUpperCase()}</code>${latMs !== null ? ` · Inference: ${latMs}ms` : ''}${data.test_score !== undefined ? ` · Score: ${data.test_score}` : ''}</div>
            </div>
          `;
        } else {
          resultBox.className = 'diagnostics-box error';
          resultBox.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div><strong>Reranker Test Failed:</strong> ${data.message || data.error || 'Initialization failed.'}</div>
          `;
        }
        resultBox.style.display = 'flex';
      } catch (err) {
        resultBox.className = 'diagnostics-box error';
        resultBox.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <div><strong>Reranker Error:</strong> ${err.message}</div>
        `;
        resultBox.style.display = 'flex';
      } finally {
        btn.disabled = false;
        if (icon) icon.classList.remove('spin-fast');
        if (text) text.textContent = 'Test Reranker';
      }
    });
  }

  // Top-K Slider
  if (elements.settingTopk) {
    elements.settingTopk.addEventListener('input', (e) => {
      if (elements.topkVal) elements.topkVal.textContent = e.target.value;
    });
  }

  // Save Settings
  if (elements.btnSaveSettings) {
    elements.btnSaveSettings.addEventListener('click', () => {
      const selectedProvider = elements.providerRadioGemini?.checked ? 'gemini' : 'local';
      const apiUrl = (elements.settingApiUrl?.value || '/api').trim() || '/api';
      const geminiApiKey = (elements.settingGeminiApiKey?.value || '').trim();
      const geminiModel = getSelectedGeminiModel();
      const enableReranker = elements.settingEnableReranker ? elements.settingEnableReranker.checked : true;
      const rerankerModel = (elements.settingRerankerModel?.value || 'text-embedding-baai-bge-reranker-v2-m3-m3').trim();
      const topK = parseInt(elements.settingTopk?.value || '5', 10) || 5;
      const defaultOrigin = elements.settingDefaultSource ? elements.settingDefaultSource.value : (state.source || 'all');

      saveAppSettings({
        apiUrl,
        apiAuthToken: state.apiAuthToken || '',
        provider: selectedProvider,
        geminiApiKey,
        geminiModel,
        enableReranker,
        rerankerModel,
        topK,
        defaultOrigin
      });

      updateIndicators();
      elements.settingsModal.classList.remove('open');
      checkBackendHealth();
    });
  }

  // AI Auto-Generate Keywords on Add Note Modal
  if (elements.btnAiGenerateKeywords) {
    elements.btnAiGenerateKeywords.addEventListener('click', handleAiGenerateKeywords);
  }

  async function handleAiGenerateKeywords() {
    const title = (document.getElementById('input-note-title')?.value || '').trim();
    const project = (document.getElementById('input-note-project')?.value || '').trim();

    // Collect section headings and contents
    const sectionsList = document.getElementById('form-sections-list');
    const secItems = sectionsList ? sectionsList.querySelectorAll('.form-section-item') : [];
    const sections = [];
    secItems.forEach(item => {
      const heading = (item.querySelector('.sec-heading')?.value || '').trim();
      const content = (item.querySelector('.sec-content')?.value || '').trim();
      if (heading || content) {
        sections.push({ heading, content });
      }
    });

    if (!title && sections.length === 0) {
      alert('Please enter a note title or some section content before generating keywords.');
      return;
    }

    const btn = elements.btnAiGenerateKeywords;
    const btnText = elements.aiGenerateBtnText;
    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = '✨ Analyzing...';

    try {
      const payload = {
        title,
        project,
        content: '',
        sections,
        provider: state.provider === 'gemini' ? 'gemini' : 'local',
        gemini_api_key: state.provider === 'gemini' ? (state.geminiApiKey || undefined) : undefined,
        gemini_model: state.provider === 'gemini' ? (state.geminiModel || undefined) : undefined,
      };

      const res = await fetch(`${state.apiUrl}/regulations/notes/generate-keywords`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }

      const data = await res.json();
      if (data.keywords && data.keywords.length > 0) {
        const kwInput = document.getElementById('input-note-keywords');
        const existing = (kwInput?.value || '').trim();
        const existingList = existing ? existing.split(',').map(s => s.trim()).filter(Boolean) : [];
        const combined = Array.from(new Set([...existingList, ...data.keywords]));
        if (kwInput) {
          kwInput.value = combined.join(', ');
        }
      }
    } catch (err) {
      console.error('Failed to generate keywords:', err);
      alert(`Could not generate keywords: ${err.message}`);
    } finally {
      if (btn) btn.disabled = false;
      if (btnText) btnText.textContent = '✨ Auto-Generate via AI';
    }
  }

  // =========================================================================
  // Knowledge Base Notes Event Listeners
  // =========================================================================

  // Navigation Tabs
  if (elements.navTabChat) {
    elements.navTabChat.addEventListener('click', () => switchTab('chat'));
  }
  if (elements.navTabNotes) {
    elements.navTabNotes.addEventListener('click', () => switchTab('notes'));
  }

  // Notes Search Filter
  if (elements.notesSearchInput) {
    elements.notesSearchInput.addEventListener('input', (e) => {
      state.notesFilter = e.target.value.trim();
      if (elements.btnClearNotesSearch) {
        elements.btnClearNotesSearch.style.display = state.notesFilter ? 'block' : 'none';
      }
      renderNotesList();
    });
  }

  if (elements.btnClearNotesSearch) {
    elements.btnClearNotesSearch.addEventListener('click', () => {
      if (elements.notesSearchInput) elements.notesSearchInput.value = '';
      state.notesFilter = '';
      elements.btnClearNotesSearch.style.display = 'none';
      renderNotesList();
    });
  }

  // Refresh Notes Button
  if (elements.btnRefreshNotes) {
    elements.btnRefreshNotes.addEventListener('click', () => fetchNotes());
  }

  // Open Add Note Modal
  if (elements.btnOpenAddNote) {
    elements.btnOpenAddNote.addEventListener('click', () => openAddNoteModal());
  }
  if (elements.btnPlaceholderAddNote) {
    elements.btnPlaceholderAddNote.addEventListener('click', () => openAddNoteModal());
  }

  // Close Add Note Modal
  if (elements.btnCloseAddNote) {
    elements.btnCloseAddNote.addEventListener('click', () => closeAddNoteModal());
  }
  if (elements.btnCancelAddNote) {
    elements.btnCancelAddNote.addEventListener('click', () => closeAddNoteModal());
  }
  if (elements.addNoteModal) {
    elements.addNoteModal.addEventListener('click', (e) => {
      if (e.target === elements.addNoteModal) {
        closeAddNoteModal();
      }
    });
  }

  // Validity Policy Radios
  if (elements.validityIndefinite) {
    elements.validityIndefinite.addEventListener('change', () => {
      if (elements.inputNoteExpiresAt) elements.inputNoteExpiresAt.disabled = true;
    });
  }
  if (elements.validityExpires) {
    elements.validityExpires.addEventListener('change', () => {
      if (elements.inputNoteExpiresAt) {
        elements.inputNoteExpiresAt.disabled = false;
        if (!elements.inputNoteExpiresAt.value) {
          const d = new Date();
          d.setFullYear(d.getFullYear() + 1);
          elements.inputNoteExpiresAt.value = d.toISOString().split('T')[0];
        }
      }
    });
  }

  // Auto-Generate Keywords via AI
  if (elements.btnAiGenerateKeywords) {
    elements.btnAiGenerateKeywords.addEventListener('click', () => handleAutoGenerateKeywords());
  }

  // Add Section to Form
  if (elements.btnAddFormSection) {
    elements.btnAddFormSection.addEventListener('click', () => addFormSection());
  }

  // Submit Note Form
  if (elements.btnSubmitAddNote) {
    elements.btnSubmitAddNote.addEventListener('click', () => handleSaveNote());
  }

  // Note Detail Viewer Controls
  if (elements.btnCloseNoteDetail) {
    elements.btnCloseNoteDetail.addEventListener('click', () => {
      state.selectedNoteId = null;
      state.selectedNote = null;
      if (elements.noteEmptyPlaceholder) elements.noteEmptyPlaceholder.style.display = 'flex';
      if (elements.noteDetailViewer) elements.noteDetailViewer.style.display = 'none';
      renderNotesList();
    });
  }

  if (elements.btnDeleteCurrentNote) {
    elements.btnDeleteCurrentNote.addEventListener('click', () => {
      if (state.selectedNote) {
        handleDeleteNote(state.selectedNote.document_id, state.selectedNote.title);
      }
    });
  }
}

// =========================================================================
// Knowledge Base Notes Management Functions
// =========================================================================

function switchTab(tab) {
  state.activeTab = tab;
  if (tab === 'chat') {
    elements.navTabChat?.classList.add('active');
    elements.navTabNotes?.classList.remove('active');
    if (elements.chatView) elements.chatView.style.display = 'flex';
    if (elements.notesView) elements.notesView.style.display = 'none';
  } else {
    elements.navTabNotes?.classList.add('active');
    elements.navTabChat?.classList.remove('active');
    if (elements.chatView) elements.chatView.style.display = 'none';
    if (elements.notesView) elements.notesView.style.display = 'flex';
    fetchNotes();
  }
}

async function fetchNotes() {
  state.isNotesLoading = true;
  if (elements.notesLoadingState) elements.notesLoadingState.style.display = 'flex';
  if (elements.notesEmptyState) elements.notesEmptyState.style.display = 'none';

  try {
    const res = await fetch(`${state.apiUrl}/regulations/notes`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const notes = await res.json();
    state.notes = Array.isArray(notes) ? notes : [];
    
    // Update badge in header
    if (elements.notesCountBadge) {
      elements.notesCountBadge.textContent = state.notes.length;
    }
    if (elements.notesTotalLabel) {
      elements.notesTotalLabel.textContent = `${state.notes.length} organizational note${state.notes.length === 1 ? '' : 's'}`;
    }

    renderNotesList();
  } catch (err) {
    console.error('Failed to fetch notes:', err);
    if (elements.notesTotalLabel) elements.notesTotalLabel.textContent = 'Error loading notes';
  } finally {
    state.isNotesLoading = false;
    if (elements.notesLoadingState) elements.notesLoadingState.style.display = 'none';
  }
}

function getFilteredNotes() {
  if (!state.notesFilter) return state.notes;
  const q = state.notesFilter.toLowerCase();
  return state.notes.filter(n => {
    const titleMatch = (n.title || '').toLowerCase().includes(q);
    const creatorMatch = (n.created_by || n.author || '').toLowerCase().includes(q);
    const projectMatch = (n.project || '').toLowerCase().includes(q);
    const typeMatch = (n.note_type || '').toLowerCase().includes(q);
    const keywordsMatch = (n.keywords || []).some(k => k.toLowerCase().includes(q));
    return titleMatch || creatorMatch || projectMatch || typeMatch || keywordsMatch;
  });
}

function renderNotesList() {
  if (!elements.notesCardsContainer) return;
  const filtered = getFilteredNotes();
  elements.notesCardsContainer.innerHTML = '';

  if (filtered.length === 0) {
    if (elements.notesEmptyState) {
      elements.notesEmptyState.style.display = 'block';
      elements.notesEmptyState.textContent = state.notes.length === 0
        ? 'No notes in knowledge base yet. Click "Add Note" to record one.'
        : 'No notes match your search filter.';
    }
    return;
  }

  if (elements.notesEmptyState) elements.notesEmptyState.style.display = 'none';

  filtered.forEach(note => {
    const card = document.createElement('div');
    card.className = `note-card ${state.selectedNoteId === note.document_id ? 'selected' : ''}`;
    card.dataset.id = note.document_id;

    // Validity badge
    let validityHtml = '';
    if (note.is_indefinite) {
      validityHtml = `<span class="badge-validity badge-indefinite">Indefinite</span>`;
    } else if (note.is_expired) {
      validityHtml = `<span class="badge-validity badge-expired">Expired (${note.expires_at || ''})</span>`;
    } else if (note.expires_at) {
      validityHtml = `<span class="badge-validity badge-expiring">Expires: ${note.expires_at}</span>`;
    }

    // Keywords chips
    let kwHtml = '';
    if (note.keywords && note.keywords.length > 0) {
      const shown = note.keywords.slice(0, 3);
      kwHtml = `<div class="note-card-keywords">
        ${shown.map(k => `<span class="kw-chip">#${escapeHtml(k)}</span>`).join('')}
        ${note.keywords.length > 3 ? `<span class="kw-chip" style="font-family: var(--font-mono);">+${note.keywords.length - 3}</span>` : ''}
      </div>`;
    }

    const typeStr = (note.note_type || 'note').replace('_', ' ');
    const creatorStr = note.created_by || note.author || 'Unknown';

    card.innerHTML = `
      <div class="note-card-header">
        <h4 class="note-card-title">${escapeHtml(note.title)}</h4>
        <button class="btn-card-delete" title="Delete note" data-id="${note.document_id}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18"/>
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
          </svg>
        </button>
      </div>
      <div class="note-card-author">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
        <span>By: <strong>${escapeHtml(creatorStr)}</strong></span>
        <span>·</span>
        <span style="font-size: 0.7rem; color: var(--text-dim);">${escapeHtml(note.date || '')}</span>
      </div>
      <div class="note-card-badges">
        <span class="badge-type">${escapeHtml(typeStr)}</span>
        ${validityHtml}
        ${note.project ? `<span class="badge-project">${escapeHtml(note.project)}</span>` : ''}
      </div>
      ${kwHtml}
    `;

    // Click on card selects note
    card.addEventListener('click', (e) => {
      if (e.target.closest('.btn-card-delete')) return;
      selectNote(note.document_id);
    });

    // Delete button
    const delBtn = card.querySelector('.btn-card-delete');
    if (delBtn) {
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDeleteNote(note.document_id, note.title);
      });
    }

    elements.notesCardsContainer.appendChild(card);
  });
}

async function selectNote(document_id) {
  state.selectedNoteId = document_id;
  renderNotesList();

  if (elements.noteEmptyPlaceholder) elements.noteEmptyPlaceholder.style.display = 'none';
  if (elements.noteDetailViewer) elements.noteDetailViewer.style.display = 'block';

  try {
    const res = await fetch(`${state.apiUrl}/regulations/notes/${document_id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const note = await res.json();
    state.selectedNote = note;
    renderNoteDetail(note);
  } catch (err) {
    console.error('Failed to load note detail:', err);
    if (elements.noteDetailViewer) {
      elements.noteDetailViewer.innerHTML = `<div style="padding: 24px; color: var(--accent-rose);">Error loading note: ${err.message}</div>`;
    }
  }
}

function renderNoteDetail(note) {
  if (!elements.noteDetailViewer) return;

  // Header badges
  if (elements.detailNoteType) {
    elements.detailNoteType.textContent = (note.note_type || 'note').replace('_', ' ');
  }
  if (elements.detailDocId) {
    elements.detailDocId.textContent = note.document_id || '';
  }

  // Validity badge
  if (elements.detailValidityBadge) {
    elements.detailValidityBadge.className = 'badge-validity';
    if (note.is_indefinite) {
      elements.detailValidityBadge.classList.add('badge-indefinite');
      elements.detailValidityBadge.textContent = 'Indefinite Validity';
    } else if (note.is_expired) {
      elements.detailValidityBadge.classList.add('badge-expired');
      elements.detailValidityBadge.textContent = `Expired (${note.expires_at || ''})`;
    } else if (note.expires_at) {
      elements.detailValidityBadge.classList.add('badge-expiring');
      elements.detailValidityBadge.textContent = `Valid until ${note.expires_at}`;
    } else {
      elements.detailValidityBadge.style.display = 'none';
    }
  }

  // Title
  if (elements.detailTitle) elements.detailTitle.textContent = note.title;

  // Creator
  if (elements.detailCreator) {
    elements.detailCreator.textContent = note.created_by || note.author || 'Unknown';
  }

  // Project
  if (elements.detailProjectWrap && elements.detailProject) {
    if (note.project) {
      elements.detailProjectWrap.style.display = 'flex';
      elements.detailProject.textContent = note.project;
    } else {
      elements.detailProjectWrap.style.display = 'none';
    }
  }

  // Date
  if (elements.detailDate) {
    elements.detailDate.textContent = note.date || '';
  }

  // Associated Keywords
  if (elements.detailKeywordsWrap && elements.detailKeywordsChips) {
    if (note.keywords && note.keywords.length > 0) {
      elements.detailKeywordsWrap.style.display = 'flex';
      elements.detailKeywordsChips.innerHTML = note.keywords.map(kw => `
        <span class="kw-chip kw-chip-highlight">#${escapeHtml(kw)}</span>
      `).join('');
    } else {
      elements.detailKeywordsWrap.style.display = 'none';
      elements.detailKeywordsChips.innerHTML = '';
    }
  }

  // Sections
  if (elements.detailSectionsContainer) {
    elements.detailSectionsContainer.innerHTML = '';

    if (note.sections && note.sections.length > 0) {
      note.sections.forEach((sec, idx) => {
        const secCard = document.createElement('div');
        secCard.className = 'note-section-card';
        secCard.innerHTML = `
          <div class="note-section-heading">
            <span>${escapeHtml(sec.heading || `Section ${idx + 1}`)}</span>
            ${sec.tags && sec.tags.length > 0 ? `
              <div style="display: flex; gap: 4px;">
                ${sec.tags.map(t => `<span class="badge-type" style="font-size: 0.6rem;">${escapeHtml(t)}</span>`).join('')}
              </div>
            ` : ''}
          </div>
          <div class="note-section-body">
            ${renderMarkdown(sec.content || '')}
          </div>
        `;
        elements.detailSectionsContainer.appendChild(secCard);
      });
    } else if (note.rendered_markdown) {
      const bodyDiv = document.createElement('div');
      bodyDiv.className = 'note-section-body';
      bodyDiv.innerHTML = note.rendered_markdown;
      elements.detailSectionsContainer.appendChild(bodyDiv);
    } else if (note.markdown_doc) {
      const bodyDiv = document.createElement('div');
      bodyDiv.className = 'note-section-body';
      bodyDiv.innerHTML = renderMarkdown(note.markdown_doc);
      elements.detailSectionsContainer.appendChild(bodyDiv);
    }
  }
}

async function handleDeleteNote(document_id, title) {
  if (!confirm(`Are you sure you want to delete note "${title || document_id}"? This will remove its vectors and text from the organizational knowledge base.`)) {
    return;
  }

  try {
    const res = await fetch(`${state.apiUrl}/regulations/notes/${encodeURIComponent(document_id)}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    if (state.selectedNoteId === document_id) {
      state.selectedNoteId = null;
      state.selectedNote = null;
      if (elements.noteEmptyPlaceholder) elements.noteEmptyPlaceholder.style.display = 'flex';
      if (elements.noteDetailViewer) elements.noteDetailViewer.style.display = 'none';
    }

    await fetchNotes();
  } catch (err) {
    alert(`Failed to delete note: ${err.message}`);
  }
}

function openAddNoteModal() {
  hideAddNoteError();
  // Reset form
  if (elements.inputNoteTitle) elements.inputNoteTitle.value = '';
  if (elements.inputNoteCreator) elements.inputNoteCreator.value = '';
  if (elements.inputNoteType) elements.inputNoteType.value = 'project_note';
  if (elements.inputNoteProject) elements.inputNoteProject.value = '';
  if (elements.validityIndefinite) elements.validityIndefinite.checked = true;
  if (elements.inputNoteExpiresAt) {
    elements.inputNoteExpiresAt.value = '';
    elements.inputNoteExpiresAt.disabled = true;
  }
  if (elements.inputNoteKeywords) elements.inputNoteKeywords.value = '';

  // Reset sections to 1
  if (elements.formSectionsList) {
    elements.formSectionsList.innerHTML = `
      <div class="form-section-item" data-index="0">
        <div class="section-item-header">
          <input type="text" class="form-input sec-heading" placeholder="Section Heading (e.g. Operational Background)" value="Overview & Context">
          <button type="button" class="btn-remove-section" title="Remove Section" style="display: none;">&times;</button>
        </div>
        <textarea class="form-textarea sec-content" rows="4" placeholder="Section markdown content..."></textarea>
      </div>
    `;
  }

  if (elements.addNoteModal) {
    elements.addNoteModal.classList.add('open');
  }
}

function closeAddNoteModal() {
  if (elements.addNoteModal) {
    elements.addNoteModal.classList.remove('open');
  }
}

function showAddNoteError(msg) {
  if (elements.addNoteError) {
    elements.addNoteError.textContent = msg;
    elements.addNoteError.style.display = 'block';
  }
}

function hideAddNoteError() {
  if (elements.addNoteError) {
    elements.addNoteError.style.display = 'none';
    elements.addNoteError.textContent = '';
  }
}

function addFormSection() {
  if (!elements.formSectionsList) return;
  const count = elements.formSectionsList.querySelectorAll('.form-section-item').length;
  const item = document.createElement('div');
  item.className = 'form-section-item';
  item.dataset.index = count;
  item.innerHTML = `
    <div class="section-item-header">
      <input type="text" class="form-input sec-heading" placeholder="Section Heading (e.g. Technical Findings)" value="Section ${count + 1}">
      <button type="button" class="btn-remove-section" title="Remove Section">&times;</button>
    </div>
    <textarea class="form-textarea sec-content" rows="4" placeholder="Section markdown content..."></textarea>
  `;

  item.querySelector('.btn-remove-section').addEventListener('click', () => {
    item.remove();
    updateSectionRemoveButtons();
  });

  elements.formSectionsList.appendChild(item);
  updateSectionRemoveButtons();
}

function updateSectionRemoveButtons() {
  if (!elements.formSectionsList) return;
  const items = elements.formSectionsList.querySelectorAll('.form-section-item');
  items.forEach(item => {
    const btn = item.querySelector('.btn-remove-section');
    if (btn) btn.style.display = items.length > 1 ? 'block' : 'none';
  });
}

async function handleAutoGenerateKeywords() {
  const title = elements.inputNoteTitle?.value.trim() || '';
  const creator = elements.inputNoteCreator?.value.trim() || '';
  const project = elements.inputNoteProject?.value.trim() || '';

  const sectionItems = elements.formSectionsList ? elements.formSectionsList.querySelectorAll('.form-section-item') : [];
  const sectionsText = Array.from(sectionItems).map(item => {
    const heading = item.querySelector('.sec-heading')?.value.trim() || '';
    const content = item.querySelector('.sec-content')?.value.trim() || '';
    return `${heading}\n${content}`;
  }).join('\n\n').trim();

  if (!title && !sectionsText) {
    showAddNoteError('Please enter a note title or section content first to auto-extract keywords.');
    return;
  }

  hideAddNoteError();
  state.isGeneratingKeywords = true;
  if (elements.btnAiGenerateKeywords) elements.btnAiGenerateKeywords.disabled = true;
  if (elements.aiGenerateBtnText) elements.aiGenerateBtnText.textContent = 'Extracting via AI...';

  try {
    const res = await fetch(`${state.apiUrl}/regulations/notes/generate-keywords`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title || 'Aviation Note',
        text: sectionsText || title,
        created_by: creator,
        project: project
      })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.keywords && data.keywords.length > 0) {
      const existing = (elements.inputNoteKeywords?.value || '')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
      const combined = Array.from(new Set([...existing, ...data.keywords]));
      if (elements.inputNoteKeywords) {
        elements.inputNoteKeywords.value = combined.join(', ');
      }
    }
  } catch (err) {
    console.error('Failed to generate keywords:', err);
    showAddNoteError(`Keyword generation note: ${err.message}. You can type keywords manually.`);
  } finally {
    state.isGeneratingKeywords = false;
    if (elements.btnAiGenerateKeywords) elements.btnAiGenerateKeywords.disabled = false;
    if (elements.aiGenerateBtnText) elements.aiGenerateBtnText.textContent = '✨ Auto-Generate via AI';
  }
}

async function handleSaveNote() {
  const title = elements.inputNoteTitle?.value.trim() || '';
  const creator = elements.inputNoteCreator?.value.trim() || '';
  const noteType = elements.inputNoteType?.value || 'project_note';
  const project = elements.inputNoteProject?.value.trim() || '';
  const isIndefinite = elements.validityIndefinite?.checked ?? true;
  const expiresAt = elements.inputNoteExpiresAt?.value.trim() || '';

  // 1. Enforce Title
  if (!title) {
    showAddNoteError('Note title is required.');
    elements.inputNoteTitle?.focus();
    return;
  }

  // 2. Enforce Creator (Strict organizational governance requirement)
  if (!creator) {
    showAddNoteError('Who Created It (Author / Role) is required for organizational governance.');
    elements.inputNoteCreator?.focus();
    return;
  }

  // 3. Enforce Expiration policy
  if (!isIndefinite && !expiresAt) {
    showAddNoteError('Please specify an expiration date or select "Indefinite".');
    elements.inputNoteExpiresAt?.focus();
    return;
  }

  // 4. Gather keywords
  const keywords = (elements.inputNoteKeywords?.value || '')
    .split(',')
    .map(k => k.trim())
    .filter(Boolean);

  // 5. Gather sections
  const sectionItems = elements.formSectionsList ? elements.formSectionsList.querySelectorAll('.form-section-item') : [];
  let sections = Array.from(sectionItems).map((item, idx) => {
    const heading = item.querySelector('.sec-heading')?.value.trim() || `Section ${idx + 1}`;
    const content = item.querySelector('.sec-content')?.value.trim() || '';
    return { heading, content, tags: [] };
  }).filter(s => s.content.length > 0 || s.heading.length > 0);

  // Ensure content is non-empty for all submitted sections
  sections = sections.map(s => ({
    ...s,
    content: s.content || title
  }));

  if (sections.length === 0) {
    sections = [{ heading: 'Overview', content: title, tags: [] }];
  }

  hideAddNoteError();
  state.isSavingNote = true;
  if (elements.btnSubmitAddNote) elements.btnSubmitAddNote.disabled = true;
  if (elements.submitNoteText) elements.submitNoteText.textContent = 'Saving note...';

  try {
    const payload = {
      title,
      created_by: creator,
      author: creator,
      note_type: noteType,
      project: project || undefined,
      is_indefinite: isIndefinite,
      expires_at: isIndefinite ? null : expiresAt,
      keywords,
      tags: [],
      sections
    };

    const res = await fetch(`${state.apiUrl}/regulations/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      let msg = `HTTP ${res.status}`;
      if (typeof errData.detail === 'string') {
        msg = errData.detail;
      } else if (Array.isArray(errData.detail)) {
        msg = errData.detail.map(d => `${d.loc ? d.loc.slice(-1) : 'field'}: ${d.msg}`).join(', ');
      }
      throw new Error(msg);
    }

    const result = await res.json();
    closeAddNoteModal();
    await fetchNotes();
    if (result.document_id) {
      await selectNote(result.document_id);
    }
  } catch (err) {
    console.error('Failed to create note:', err);
    showAddNoteError(`Save failed: ${err.message}`);
  } finally {
    state.isSavingNote = false;
    if (elements.btnSubmitAddNote) elements.btnSubmitAddNote.disabled = false;
    if (elements.submitNoteText) elements.submitNoteText.textContent = 'Save & Index Note';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialization
function init() {
  initEvents();
  updateIndicators();
  renderChat();
  checkBackendHealth();
  fetchNotes();
}

document.addEventListener('DOMContentLoaded', init);

