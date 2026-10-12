/**
 * AeroLex Chat HTML Report Generator
 * Generates standalone, interactive, and beautifully formatted HTML audit reports
 * from chat sessions with full markdown rendering and regulatory standard citations.
 */

import { Marked } from 'marked';
import { ChatSession, ChatMessage, AppSettings } from '../types';

export function escapeHtml(str: string): string {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function generateChatReportHtml(chat: ChatSession, settings?: AppSettings): string {
  const markedInstance = new Marked();
  const title = chat.title || 'Aviation Regulatory Consultation';
  const createdDate = new Date(chat.createdAt).toLocaleString();
  const updatedDate = new Date(chat.updatedAt).toLocaleString();

  // Aggregate all referenced documents across the session
  const aggregatedStandardsMap = new Map<string, {
    documentId: string;
    title: string;
    source: string;
    sections: Set<string>;
    snippets: string[];
  }>();

  chat.messages.forEach(msg => {
    if (msg.referencedChunks && msg.referencedChunks.length > 0) {
      msg.referencedChunks.forEach((chunk: any) => {
        const docId = chunk.document_id || 'Unknown';
        const docTitle = chunk.title || chunk.metadata?.title || chunk.metadata?.description || docId;
        const source = chunk.source || 'database';
        const section = chunk.path && chunk.path.length > 0 
          ? chunk.path.join(' › ') 
          : chunk.metadata?.section || chunk.metadata?.clause || chunk.chunk_id;

        if (!aggregatedStandardsMap.has(docId)) {
          aggregatedStandardsMap.set(docId, {
            documentId: docId,
            title: docTitle,
            source,
            sections: new Set(),
            snippets: []
          });
        }

        const entry = aggregatedStandardsMap.get(docId)!;
        if (section) entry.sections.add(section);
        if (chunk.text && entry.snippets.length < 3 && !entry.snippets.includes(chunk.text.slice(0, 180))) {
          entry.snippets.push(chunk.text.slice(0, 180));
        }
      });
    }
  });

  const allStandards = Array.from(aggregatedStandardsMap.values());
  const userMessageCount = chat.messages.filter(m => m.role === 'user').length;
  const assistantMessageCount = chat.messages.filter(m => m.role === 'assistant').length;

  // Build HTML for messages
  const messagesHtml = chat.messages.map((msg: ChatMessage, index: number) => {
    const isUser = msg.role === 'user';
    const isAssistant = msg.role === 'assistant';
    const roleLabel = isUser ? 'Inquiry / Prompt' : isAssistant ? 'AeroLex Compliance Guidance' : 'System Notice';
    const roleBadgeClass = isUser ? 'badge-user' : isAssistant ? 'badge-assistant' : 'badge-system';
    const timeStr = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let bodyHtml = '';
    if (isUser) {
      bodyHtml = `<div class="message-user-text">${escapeHtml(msg.content).replace(/\n/g, '<br/>')}</div>`;
    } else {
      bodyHtml = `<div class="message-prose">${markedInstance.parse(msg.content)}</div>`;
    }

    // Referenced chunks section for this message
    let referencesHtml = '';
    if (msg.referencedChunks && msg.referencedChunks.length > 0) {
      const chunkCards = msg.referencedChunks.map((chunk: any) => {
        const docTitle = chunk.title || chunk.metadata?.title || chunk.metadata?.description || chunk.document_id;
        const sectionName = chunk.path && chunk.path.length > 0
          ? chunk.path.join(' › ')
          : chunk.metadata?.section || chunk.metadata?.clause || chunk.chunk_id;
        const snippet = chunk.text || chunk.metadata?.text || '';

        return `
          <div class="citation-card">
            <div class="citation-header">
              <span class="citation-title">${escapeHtml(docTitle)}</span>
              <span class="citation-source-tag">${escapeHtml(chunk.source || 'EASA/EU')}</span>
            </div>
            <div class="citation-section">
              <span class="citation-section-label">Section / Provision:</span>
              <span class="citation-section-val">${escapeHtml(sectionName)}</span>
            </div>
            ${chunk.document_id ? `<div class="citation-doc-id">Reference ID: <code>${escapeHtml(chunk.document_id)}</code></div>` : ''}
            ${snippet ? `<div class="citation-snippet">"${escapeHtml(snippet.slice(0, 240))}${snippet.length > 240 ? '...' : ''}"</div>` : ''}
          </div>
        `;
      }).join('');

      referencesHtml = `
        <div class="msg-citations-box">
          <div class="msg-citations-header">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Referenced Regulatory Standards & Clauses (${msg.referencedChunks.length})</span>
          </div>
          <div class="citation-grid">
            ${chunkCards}
          </div>
        </div>
      `;
    }

    // Follow-ups if present
    let followupsHtml = '';
    if (msg.suggestedFollowups && msg.suggestedFollowups.length > 0) {
      const items = msg.suggestedFollowups.map(f => `<li>${escapeHtml(f)}</li>`).join('');
      followupsHtml = `
        <div class="msg-followups-box">
          <div class="msg-followups-title">Suggested Follow-Up Considerations:</div>
          <ul class="msg-followups-list">
            ${items}
          </ul>
        </div>
      `;
    }

    // Model info footer
    let metaFooterHtml = '';
    if (msg.providerInfo) {
      metaFooterHtml = `
        <div class="msg-meta-footer">
          <span>Provider: ${escapeHtml(msg.providerInfo.provider || 'Local')}</span>
          ${msg.providerInfo.model ? `<span>· Model: ${escapeHtml(msg.providerInfo.model)}</span>` : ''}
          ${msg.providerInfo.chunks_retrieved ? `<span>· Clauses Analyzed: ${msg.providerInfo.chunks_retrieved}</span>` : ''}
        </div>
      `;
    }

    return `
      <div class="message-card ${isUser ? 'user-turn' : 'assistant-turn'}" id="turn-${index + 1}">
        <div class="message-card-header">
          <div class="header-left">
            <span class="turn-number">#${index + 1}</span>
            <span class="role-badge ${roleBadgeClass}">${roleLabel}</span>
          </div>
          <span class="time-stamp">${timeStr}</span>
        </div>
        <div class="message-body">
          ${bodyHtml}
          ${referencesHtml}
          ${followupsHtml}
          ${metaFooterHtml}
        </div>
      </div>
    `;
  }).join('');

  // Index table for all aggregated standards
  let standardsIndexHtml = '';
  if (allStandards.length > 0) {
    const rows = allStandards.map(std => {
      const sectionsList = Array.from(std.sections).slice(0, 8).map(s => `<code>${escapeHtml(s)}</code>`).join(' ');
      return `
        <tr>
          <td class="col-title">
            <strong>${escapeHtml(std.title)}</strong>
            <div class="sub-id">ID: <code>${escapeHtml(std.documentId)}</code></div>
          </td>
          <td class="col-source"><span class="source-tag">${escapeHtml(std.source.toUpperCase())}</span></td>
          <td class="col-sections">${sectionsList || '<span class="text-muted">General document context</span>'}</td>
        </tr>
      `;
    }).join('');

    standardsIndexHtml = `
      <section class="standards-index-section" id="standards-index">
        <div class="section-title-wrap">
          <h2>Consolidated Regulatory Standards Index</h2>
          <p class="section-desc">Compendium of all regulatory acts, binding technical standards, and guidance materials referenced in this session.</p>
        </div>
        <div class="table-container">
          <table class="standards-table">
            <thead>
              <tr>
                <th>Document Title & Specification</th>
                <th>Jurisdiction</th>
                <th>Provisions & Articles Cited</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AeroLex Consultation Report - ${escapeHtml(title)}</title>
  <style>
    :root {
      --bg-primary: #090d16;
      --bg-secondary: #0f172a;
      --bg-card: #1e293b;
      --bg-card-alt: #162032;
      --border-color: #334155;
      --border-subtle: #1e293b;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-sky: #38bdf8;
      --accent-sky-dark: #0284c7;
      --accent-emerald: #34d399;
      --accent-amber: #fbbf24;
      --accent-indigo: #818cf8;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    [data-theme="light"] {
      --bg-primary: #f8fafc;
      --bg-secondary: #f1f5f9;
      --bg-card: #ffffff;
      --bg-card-alt: #f8fafc;
      --border-color: #cbd5e1;
      --border-subtle: #e2e8f0;
      --text-main: #0f172a;
      --text-muted: #475569;
      --text-dim: #64748b;
      --accent-sky: #0284c7;
      --accent-sky-dark: #0369a1;
      --accent-emerald: #059669;
      --accent-amber: #d97706;
      --accent-indigo: #4f46e5;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: var(--font-family);
      background-color: var(--bg-primary);
      color: var(--text-main);
      line-height: 1.6;
      padding: 0;
      margin: 0;
      transition: background-color 0.2s ease, color 0.2s ease;
    }

    .container {
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 20px 80px 20px;
    }

    /* Top Navigation / Controls Bar */
    .top-controls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 12px 20px;
      margin-bottom: 28px;
      gap: 12px;
    }

    .controls-brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 15px;
      color: var(--accent-sky);
      letter-spacing: 0.5px;
    }

    .controls-actions {
      display: flex;
      gap: 10px;
    }

    .btn-action {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }

    .btn-action:hover {
      border-color: var(--accent-sky);
      color: var(--accent-sky);
    }

    /* Report Header Cover Card */
    .report-header {
      background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-card) 100%);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 32px;
      margin-bottom: 36px;
      box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.25);
    }

    .header-tagline {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--accent-sky);
      margin-bottom: 8px;
    }

    .header-title {
      font-size: 28px;
      font-weight: 800;
      color: var(--text-main);
      margin-bottom: 14px;
      line-height: 1.25;
    }

    .header-meta-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 24px;
      padding-top: 20px;
      border-top: 1px solid var(--border-color);
    }

    .meta-stat {
      background: var(--bg-primary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 10px 14px;
    }

    .meta-stat-label {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      margin-bottom: 4px;
    }

    .meta-stat-val {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-main);
    }

    /* Dialogue Timeline */
    .dialogue-timeline {
      display: flex;
      flex-direction: column;
      gap: 24px;
      margin-bottom: 48px;
    }

    .message-card {
      border-radius: 14px;
      border: 1px solid var(--border-color);
      background: var(--bg-card);
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      transition: border-color 0.15s ease;
    }

    .message-card.user-turn {
      border-left: 4px solid var(--accent-sky);
      background: linear-gradient(180deg, var(--bg-card) 0%, var(--bg-card-alt) 100%);
    }

    .message-card.assistant-turn {
      border-left: 4px solid var(--accent-emerald);
    }

    .message-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 20px;
      background: var(--bg-secondary);
      border-bottom: 1px solid var(--border-subtle);
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .turn-number {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      color: var(--text-dim);
      font-weight: 700;
    }

    .role-badge {
      font-size: 11px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 9999px;
      letter-spacing: 0.3px;
    }

    .badge-user {
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-sky);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }

    .badge-assistant {
      background: rgba(52, 211, 153, 0.15);
      color: var(--accent-emerald);
      border: 1px solid rgba(52, 211, 153, 0.3);
    }

    .badge-system {
      background: rgba(148, 163, 184, 0.15);
      color: var(--text-muted);
      border: 1px solid var(--border-color);
    }

    .time-stamp {
      font-size: 11px;
      font-family: ui-monospace, monospace;
      color: var(--text-dim);
    }

    .message-body {
      padding: 22px;
    }

    .message-user-text {
      font-size: 15px;
      font-weight: 500;
      color: var(--text-main);
      white-space: pre-wrap;
    }

    /* Markdown Prose Content */
    .message-prose {
      font-size: 14.5px;
      line-height: 1.7;
      color: var(--text-main);
    }

    .message-prose p {
      margin-bottom: 12px;
    }

    .message-prose h1, .message-prose h2, .message-prose h3, .message-prose h4 {
      color: var(--text-main);
      margin-top: 18px;
      margin-bottom: 10px;
      font-weight: 700;
    }

    .message-prose h3 { font-size: 16px; color: var(--accent-sky); }
    .message-prose h4 { font-size: 14px; }

    .message-prose ul, .message-prose ol {
      margin-left: 24px;
      margin-bottom: 14px;
    }

    .message-prose li {
      margin-bottom: 6px;
    }

    .message-prose strong {
      color: var(--text-main);
      font-weight: 700;
    }

    .message-prose code {
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      color: var(--accent-sky);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 13px;
      font-family: ui-monospace, monospace;
    }

    .message-prose blockquote {
      border-left: 3px solid var(--accent-sky);
      padding-left: 14px;
      margin: 14px 0;
      color: var(--text-muted);
      background: var(--bg-secondary);
      padding: 8px 14px;
      border-radius: 0 6px 6px 0;
    }

    /* Message Citations Box */
    .msg-citations-box {
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid var(--border-color);
    }

    .msg-citations-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--accent-sky);
      margin-bottom: 12px;
    }

    .citation-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }

    .citation-card {
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .citation-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
    }

    .citation-title {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.35;
    }

    .citation-source-tag {
      font-size: 9px;
      font-weight: 800;
      text-transform: uppercase;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-sky);
      padding: 2px 6px;
      border-radius: 4px;
      letter-spacing: 0.5px;
      white-space: nowrap;
    }

    .citation-section {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.4;
    }

    .citation-section-label {
      color: var(--text-dim);
      font-size: 11px;
      margin-right: 4px;
    }

    .citation-section-val {
      font-weight: 600;
      color: var(--accent-indigo);
    }

    .citation-doc-id {
      font-size: 11px;
      color: var(--text-dim);
    }

    .citation-doc-id code {
      font-size: 10px;
    }

    .citation-snippet {
      font-size: 11.5px;
      color: var(--text-muted);
      font-style: italic;
      background: var(--bg-primary);
      padding: 6px 8px;
      border-radius: 4px;
      border: 1px solid var(--border-subtle);
      margin-top: 4px;
      line-height: 1.4;
    }

    /* Followups Box */
    .msg-followups-box {
      margin-top: 16px;
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 12px 16px;
    }

    .msg-followups-title {
      font-size: 11.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--accent-amber);
      margin-bottom: 6px;
    }

    .msg-followups-list {
      margin-left: 18px;
      font-size: 12.5px;
      color: var(--text-muted);
    }

    .msg-followups-list li {
      margin-bottom: 4px;
    }

    /* Meta Footer */
    .msg-meta-footer {
      display: flex;
      gap: 8px;
      margin-top: 14px;
      font-size: 11px;
      color: var(--text-dim);
      font-family: ui-monospace, monospace;
    }

    /* Standards Index Table */
    .standards-index-section {
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 28px;
      margin-top: 40px;
    }

    .section-title-wrap h2 {
      font-size: 20px;
      font-weight: 800;
      color: var(--text-main);
      margin-bottom: 6px;
    }

    .section-desc {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 20px;
    }

    .table-container {
      overflow-x: auto;
    }

    .standards-table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }

    .standards-table th {
      background: var(--bg-primary);
      color: var(--text-muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      padding: 10px 14px;
      border-bottom: 2px solid var(--border-color);
    }

    .standards-table td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-color);
      vertical-align: top;
    }

    .standards-table tr:last-child td {
      border-bottom: none;
    }

    .col-title strong {
      color: var(--text-main);
      display: block;
      margin-bottom: 3px;
    }

    .sub-id {
      font-size: 11px;
      color: var(--text-dim);
    }

    .source-tag {
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-sky);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
    }

    .col-sections code {
      display: inline-block;
      margin: 2px 4px 2px 0;
      font-size: 11px;
    }

    /* Print Styles */
    @media print {
      body {
        background-color: #ffffff !important;
        color: #000000 !important;
      }
      .top-controls {
        display: none !important;
      }
      .message-card {
        border: 1px solid #ccc !important;
        box-shadow: none !important;
        page-break-inside: avoid;
        margin-bottom: 20px;
      }
      .container {
        padding: 0 !important;
        max-width: 100% !important;
      }
    }

    .icon {
      width: 15px;
      height: 15px;
      display: inline-block;
      vertical-align: middle;
    }
  </style>
</head>
<body data-theme="dark">
  <div class="container">
    <!-- Top Action Bar -->
    <header class="top-controls">
      <div class="controls-brand">
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
        <span>AeroLex Regulatory Assistant</span>
      </div>
      <div class="controls-actions">
        <button class="btn-action" onclick="toggleTheme()" title="Toggle Dark/Light Mode">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
          <span id="theme-btn-label">Light Mode</span>
        </button>
        <button class="btn-action" onclick="window.print()" title="Print or Save to PDF">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
          <span>Print / PDF</span>
        </button>
      </div>
    </header>

    <!-- Cover Summary Card -->
    <div class="report-header">
      <div class="header-tagline">Official Regulatory Consultation Transcript</div>
      <h1 class="header-title">${escapeHtml(title)}</h1>
      <p style="color: var(--text-muted); font-size: 14px;">
        Generated by AeroLex Autonomous Assistant. Contains legal Q&A dialogues grounded in validated European & International Civil Aviation regulations.
      </p>

      <div class="header-meta-grid">
        <div class="meta-stat">
          <div class="meta-stat-label">Inquiries</div>
          <div class="meta-stat-val">${userMessageCount} Questions</div>
        </div>
        <div class="meta-stat">
          <div class="meta-stat-label">Guidance Answers</div>
          <div class="meta-stat-val">${assistantMessageCount} Responses</div>
        </div>
        <div class="meta-stat">
          <div class="meta-stat-label">Regulations Cited</div>
          <div class="meta-stat-val">${allStandards.length} Documents</div>
        </div>
        <div class="meta-stat">
          <div class="meta-stat-label">Session Date</div>
          <div class="meta-stat-val" style="font-size: 13px;">${createdDate}</div>
        </div>
      </div>
    </div>

    <!-- Dialogue Messages -->
    <main class="dialogue-timeline">
      ${messagesHtml}
    </main>

    <!-- Consolidated Standards Index -->
    ${standardsIndexHtml}

    <footer style="margin-top: 50px; text-align: center; font-size: 12px; color: var(--text-dim); border-top: 1px solid var(--border-color); padding-top: 20px;">
      AeroLex Assistant Audit Report · Exported on ${new Date().toLocaleString()} · For regulatory compliance analysis only.
    </footer>
  </div>

  <script>
    function toggleTheme() {
      var body = document.body;
      var current = body.getAttribute('data-theme');
      var next = current === 'dark' ? 'light' : 'dark';
      body.setAttribute('data-theme', next);
      document.getElementById('theme-btn-label').textContent = next === 'dark' ? 'Light Mode' : 'Dark Mode';
    }
  </script>
</body>
</html>`;
}

export function downloadChatReportHtml(chat: ChatSession, settings?: AppSettings): void {
  const html = generateChatReportHtml(chat, settings);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  
  const cleanTitle = (chat.title || 'Chat_Report')
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'consultation';
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  
  link.setAttribute('download', `AeroLex_${cleanTitle}_${dateStr}.html`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
