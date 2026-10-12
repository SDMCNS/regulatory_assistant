/**
 * Utility to generate standalone, self-contained, and interactive HTML reports
 * for Autonomous Regulatory Deep Research jobs.
 * 
 * Features:
 * - Standalone single-file HTML (zero external network dependencies or CDNs).
 * - Interactive mouse-over tooltips on citation badges displaying chunk excerpts,
 *   regulatory scope validation status, and document references.
 * - Click-to-jump navigation from citations to the comprehensive Appendix index.
 * - Table of Contents with quick section navigation.
 * - Executive Audit & Scope Boundary summary card.
 * - Dark & Light mode toggle with preference persistence.
 * - Full print stylesheet (@media print) for clean PDF export.
 */

import { Marked } from 'marked';
import { 
  ResearchJobDetail, 
  ConsultedRegulation, 
  EvaluationSummary, 
  ResearchGap, 
  SkybraryReadingMaterial, 
  UserNoteReadingMaterial,
  DocSection 
} from '../types';
import { 
  normalizeChunkCitations, 
  findChunkExcerpt, 
  parseReportSections,
  getSectionStyle,
  countCitations 
} from './sectionParser';

export function escapeHtml(str: string): string {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

interface ChunkMeta {
  chunkId: string;
  statusClass: string;
  statusLabel: string;
  excerpt: string;
  docTitle?: string;
}

/**
 * Builds metadata index for all referenced chunks and citations.
 */
function buildChunkMetaIndex(
  job: ResearchJobDetail,
  allChunkIds: Set<string>
): Map<string, ChunkMeta> {
  const map = new Map<string, ChunkMeta>();
  const evaluationSummary = job.evaluation_summary;
  const validatedMap = evaluationSummary?.validated_chunks || {};
  const negatedMap = evaluationSummary?.negated_chunks || {};
  const referencedChunks = job.referenced_chunks || {};

  // Also include chunks from referenced_chunks map
  Object.keys(referencedChunks).forEach(id => allChunkIds.add(id));
  Object.keys(validatedMap).forEach(id => allChunkIds.add(id));
  Object.keys(negatedMap).forEach(id => allChunkIds.add(id));

  allChunkIds.forEach(id => {
    const cleanId = id.trim().replace(/^[<"']+|[>"']+$/g, '');
    let statusClass = 'status-referenced';
    let statusLabel = 'Referenced Regulatory Source';

    if (validatedMap[cleanId] || validatedMap[id]) {
      statusClass = 'status-validated';
      statusLabel = 'Validated Regulatory Provision';
    } else if (negatedMap[cleanId] || negatedMap[id]) {
      statusClass = 'status-negated';
      statusLabel = 'Excluded / Negated Provision';
    } else if (id.startsWith('note_') || id.includes('NOTE')) {
      statusClass = 'status-note';
      statusLabel = 'Internal Project Note';
    } else if (id.startsWith('skybrary_') || id.includes('SKYBRARY')) {
      statusClass = 'status-skybrary';
      statusLabel = 'Skybrary Flight Safety Literature';
    }

    const excerpt = findChunkExcerpt(cleanId, referencedChunks, evaluationSummary);

    // Try to find matching consulted regulation for doc title
    let docTitle: string | undefined;
    if (job.consulted_regulations) {
      for (const reg of job.consulted_regulations) {
        if (reg.document_id && cleanId.startsWith(reg.document_id)) {
          docTitle = reg.document_title || reg.title || reg.document_id;
          break;
        }
      }
    }

    map.set(cleanId, {
      chunkId: cleanId,
      statusClass,
      statusLabel,
      excerpt,
      docTitle
    });
  });

  return map;
}

/**
 * Scans markdown text to find all cited chunk IDs.
 */
function extractCitedChunkIds(markdown: string): Set<string> {
  const set = new Set<string>();
  if (!markdown) return set;

  const normalized = normalizeChunkCitations(markdown);
  // Match [text](<chunk:ID>) or [text](chunk:ID)
  const regex = /\[([^\]]*?)\]\((?:<chunk:|chunk:)([^>)]+)(?:>|\))/g;
  let match;
  while ((match = regex.exec(normalized)) !== null) {
    const rawId = match[2]?.trim();
    if (rawId) {
      const cleanId = rawId.replace(/^[<"']+|[>"']+$/g, '').trim();
      if (cleanId) set.add(cleanId);
    }
  }

  return set;
}

/**
 * Creates an isolated Marked instance with custom link renderer for citations.
 */
function createMarkedParser(chunkMetaMap: Map<string, ChunkMeta>): Marked {
  const customMarked = new Marked();

  customMarked.use({
    renderer: {
      link({ href, title, text }: any) {
        if (href && (href.startsWith('chunk:') || href.startsWith('<chunk:'))) {
          const rawChunkId = href.replace(/^<*chunk:/, '').replace(/>*$/, '').trim();
          const cleanId = rawChunkId.replace(/^[<"']+|[>"']+$/g, '').trim();
          const safeId = escapeHtml(cleanId);
          const safeText = escapeHtml(text || cleanId || 'Citation');

          const meta = chunkMetaMap.get(cleanId) || {
            chunkId: cleanId,
            statusClass: 'status-referenced',
            statusLabel: 'Referenced Regulatory Source',
            excerpt: 'Excerpt details available in Appendix.'
          };

          const safeExcerpt = escapeHtml(meta.excerpt || 'Source excerpt not available.');
          const safeLabel = escapeHtml(meta.statusLabel);
          const safeAnchor = `chunk-${safeId.replace(/[^a-zA-Z0-9_-]/g, '_')}`;

          return (
            `<span class="citation-badge-wrapper" data-chunk-id="${safeId}">` +
              `<a href="#${safeAnchor}" class="citation-badge ${meta.statusClass}" data-chunk-id="${safeId}" role="button" tabindex="0" title="Click to view full chunk in Appendix">` +
                `<svg class="cite-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>` +
                `<span class="cite-text">${safeText}</span>` +
              `</a>` +
              `<span class="citation-css-tooltip">` +
                `<span class="tt-header">` +
                  `<span class="tt-id">Chunk: ${safeId}</span>` +
                  `<span class="tt-tag ${meta.statusClass}">${safeLabel}</span>` +
                `</span>` +
                `<span class="tt-body">${safeExcerpt}</span>` +
                `<span class="tt-footer">✦ Click to jump to full excerpt</span>` +
              `</span>` +
            `</span>`
          );
        }

        // Standard markdown links
        const safeHref = escapeHtml(href || '#');
        const safeTitle = title ? ` title="${escapeHtml(title)}"` : '';
        const safeContent = text || '';
        return `<a href="${safeHref}"${safeTitle} target="_blank" rel="noopener noreferrer">${safeContent}</a>`;
      }
    }
  });

  return customMarked;
}

/**
 * Generates a complete, beautiful, standalone HTML document from a deep research job.
 */
export function generateResearchReportHtml(
  job: ResearchJobDetail,
  reportType: 'initial' | 'comprehensive' = 'initial'
): string {
  const activeMarkdown = (reportType === 'comprehensive' && job.comprehensive_report_markdown)
    ? job.comprehensive_report_markdown
    : (job.report_markdown || '');

  // Extract all chunk IDs and build metadata index
  const citedIds = extractCitedChunkIds(activeMarkdown);
  const chunkMetaMap = buildChunkMetaIndex(job, citedIds);

  // Parse structured report sections
  const sections = parseReportSections(activeMarkdown);

  // Setup markdown parser
  const parser = createMarkedParser(chunkMetaMap);

  let renderedContentHtml = '';
  try {
    if (sections.length > 1) {
      const sectionBlocks = sections.map((sec, idx) => {
        let markdownBody = sec.markdown;
        // Clean redundant duplicate top header if it directly mirrors the accordion title
        const firstLineMatch = markdownBody.match(/^#+\s+(.+)$/m);
        if (firstLineMatch && firstLineMatch[1].trim().toLowerCase() === sec.title.trim().toLowerCase()) {
          markdownBody = markdownBody.replace(/^#+\s+.+(\r?\n)+/, '').trim();
        }

        const secNorm = normalizeChunkCitations(markdownBody || sec.markdown);
        const secHtml = parser.parse(secNorm) as string;
        const style = getSectionStyle(sec.type);
        const citeCount = sec.citationCount ?? countCitations(sec.markdown);
        const wordCount = sec.wordCount ?? 0;

        return `
          <details class="report-section-accordion" id="section-${idx + 1}" open>
            <summary class="section-accordion-header">
              <div class="sah-left">
                <span class="accordion-chevron">
                  <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
                </span>
                <span class="pill ${style.badgeClass || 'pill-accent'}" style="font-size: 10px; padding: 2px 7px;">${escapeHtml(style.label || `Section ${idx + 1}`)}</span>
                <span class="section-accordion-title">${escapeHtml(sec.title)}</span>
              </div>
              <div class="sah-right">
                ${citeCount > 0 ? `<span class="pill pill-accent" style="font-size: 10px; padding: 1px 6px;">${citeCount} cite${citeCount > 1 ? 's' : ''}</span>` : ''}
                <span class="section-meta-words">${wordCount} words</span>
              </div>
            </summary>
            <div class="section-accordion-body">
              ${secHtml}
            </div>
          </details>
        `;
      }).join('\n');

      renderedContentHtml = `
        <div class="section-controls-bar">
          <div class="scb-left">
            <span class="scb-title">Structured Sections (${sections.length})</span>
            <span class="pill" style="font-size: 10px;">Interactive Accordion</span>
          </div>
          <div class="scb-right">
            <button type="button" class="btn btn-sm" id="btn-expand-all" title="Expand all report sections">
              <span>⤢ Expand All</span>
            </button>
            <button type="button" class="btn btn-sm" id="btn-collapse-all" title="Collapse all report sections">
              <span>⤡ Collapse All</span>
            </button>
          </div>
        </div>
        <div class="sections-accordion-container">
          ${sectionBlocks}
        </div>
      `;
    } else {
      const normalizedMarkdown = normalizeChunkCitations(activeMarkdown);
      renderedContentHtml = `
        <div class="sections-accordion-container">
          ${parser.parse(normalizedMarkdown) as string}
        </div>
      `;
    }
  } catch (err: any) {
    renderedContentHtml = `<pre class="error-pre">${escapeHtml(activeMarkdown)}</pre>`;
  }

  // Pre-serialize chunk data for client-side instant tooltips and search
  const chunkDataObj: Record<string, any> = {};
  chunkMetaMap.forEach((meta, id) => {
    chunkDataObj[id] = {
      id: meta.chunkId,
      statusClass: meta.statusClass,
      statusLabel: meta.statusLabel,
      excerpt: meta.excerpt,
      docTitle: meta.docTitle || null
    };
  });
  const serializedChunkData = JSON.stringify(chunkDataObj).replace(/</g, '\\u003c');

  // Format timestamps and metadata
  const createdDate = job.created_at ? new Date(job.created_at).toLocaleString() : 'N/A';
  const queryText = job.query || 'Regulatory Inquiries & Compliance Analysis';
  const reportVariantLabel = reportType === 'comprehensive' 
    ? 'Comprehensive Autonomous Synthesis (Gaps Resolved)' 
    : 'Executive Regulatory Deep Research Report';
  const providerLabel = job.provider === 'gemini' 
    ? `Google Gemini Cloud (${job.model || 'gemini-3.5-flash'})` 
    : `Local LM Studio Engine (${job.model || 'Local Model'})`;

  // Evaluation stats
  const evalSummary = job.evaluation_summary;
  const targetDomains = evalSummary?.target_domains || [];
  const excludedDomains = evalSummary?.excluded_domains || [];
  const validatedCount = evalSummary?.validated_count || 0;
  const negatedCount = evalSummary?.negated_count || 0;

  // Consulted regulations table rows
  const consultedRegs = job.consulted_regulations || [];
  const readingMaterials = job.skybrary_reading_materials || [];
  const userNotes = job.user_notes_reading_materials || [];
  const researchGaps = job.research_gaps || [];

  return `<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Autonomous Regulatory Report - ${escapeHtml(queryText.slice(0, 60))} [Job ${escapeHtml(job.job_id.slice(0, 8))}]</title>
  <style>
    /* ==========================================================================
       1. CSS Variables & Theming
       ========================================================================== */
    :root {
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      
      --color-primary: #6366f1;
      --color-primary-hover: #4f46e5;
      --color-primary-light: rgba(99, 102, 241, 0.15);
      
      --color-emerald: #10b981;
      --color-emerald-bg: rgba(16, 185, 129, 0.15);
      --color-emerald-border: rgba(16, 185, 129, 0.4);
      
      --color-rose: #f43f5e;
      --color-rose-bg: rgba(244, 63, 94, 0.15);
      --color-rose-border: rgba(244, 63, 94, 0.4);
      
      --color-cyan: #06b6d4;
      --color-cyan-bg: rgba(6, 182, 212, 0.15);
      --color-cyan-border: rgba(6, 182, 212, 0.4);
      
      --color-sky: #0284c7;
      --color-sky-bg: rgba(2, 132, 199, 0.15);
      --color-sky-border: rgba(2, 132, 199, 0.4);

      --color-amber: #f59e0b;
      --color-amber-bg: rgba(245, 158, 11, 0.15);
    }

    [data-theme="dark"] {
      --bg-page: #0b0f19;
      --bg-surface: #111827;
      --bg-surface-elevated: #1e293b;
      --bg-surface-card: rgba(17, 24, 39, 0.7);
      --border-subtle: #1e293b;
      --border-medium: #334155;
      --border-strong: #475569;
      
      --text-heading: #f8fafc;
      --text-primary: #e2e8f0;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      
      --tooltip-bg: rgba(15, 23, 42, 0.98);
      --tooltip-border: #6366f1;
      --shadow-elevation: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
    }

    [data-theme="light"] {
      --bg-page: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #f1f5f9;
      --bg-surface-card: #ffffff;
      --border-subtle: #e2e8f0;
      --border-medium: #cbd5e1;
      --border-strong: #94a3b8;
      
      --text-heading: #0f172a;
      --text-primary: #1e293b;
      --text-secondary: #475569;
      --text-muted: #64748b;
      
      --tooltip-bg: rgba(255, 255, 255, 0.98);
      --tooltip-border: #4f46e5;
      --shadow-elevation: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
    }

    /* ==========================================================================
       2. Base Reset & Typography
       ========================================================================== */
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: var(--font-sans);
      background-color: var(--bg-page);
      color: var(--text-primary);
      line-height: 1.7;
      font-size: 15px;
      -webkit-font-smoothing: antialiased;
      transition: background-color 0.2s ease, color 0.2s ease;
      padding-bottom: 80px;
    }

    .container {
      max-width: 1040px;
      margin: 0 auto;
      padding: 0 24px;
    }

    /* ==========================================================================
       3. Header & Navigation Controls
       ========================================================================== */
    .report-topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      backdrop-filter: blur(12px);
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
      padding: 12px 0;
      margin-bottom: 32px;
    }

    .topbar-inner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }

    .brand-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-icon {
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #6366f1, #a855f7);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: bold;
      font-size: 16px;
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
    }

    .brand-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-heading);
      letter-spacing: -0.01em;
    }

    .brand-sub {
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }

    .toolbar-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid var(--border-medium);
      background: var(--bg-surface-elevated);
      color: var(--text-heading);
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
    }

    .btn:hover {
      border-color: var(--color-primary);
      color: var(--color-primary);
    }

    .btn-primary {
      background: var(--color-primary);
      border-color: var(--color-primary);
      color: white;
    }

    .btn-primary:hover {
      background: var(--color-primary-hover);
      color: white;
    }

    /* ==========================================================================
       4. Hero Metadata Banner
       ========================================================================== */
    .hero-card {
      background: var(--bg-surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 28px;
      margin-bottom: 28px;
      box-shadow: var(--shadow-elevation);
      position: relative;
      overflow: hidden;
    }

    .hero-card::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 4px;
      background: linear-gradient(90deg, #6366f1, #a855f7, #06b6d4);
    }

    .hero-badge-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }

    .pill {
      font-size: 11px;
      font-family: var(--font-mono);
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      border: 1px solid var(--border-medium);
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
    }

    .pill-accent {
      background: var(--color-primary-light);
      border-color: var(--color-primary);
      color: var(--color-primary);
    }

    .pill-emerald {
      background: var(--color-emerald-bg);
      border-color: var(--color-emerald-border);
      color: var(--color-emerald);
    }

    .hero-title {
      font-size: 24px;
      font-weight: 800;
      color: var(--text-heading);
      line-height: 1.3;
      margin-bottom: 12px;
      letter-spacing: -0.02em;
    }

    .hero-query-box {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 12px 16px;
      margin-top: 14px;
      font-size: 13px;
      color: var(--text-secondary);
      display: flex;
      gap: 10px;
      align-items: flex-start;
    }

    .hero-query-label {
      font-weight: 700;
      text-transform: uppercase;
      font-size: 10px;
      letter-spacing: 0.05em;
      color: var(--color-primary);
      padding-top: 2px;
    }

    /* ==========================================================================
       5. Audit & Domain Boundary Grid
       ========================================================================== */
    .audit-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid var(--border-subtle);
    }

    .audit-col-title {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .audit-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    /* ==========================================================================
       6. Table of Contents & Navigation (Interactive Outline)
       ========================================================================== */
    .toc-accordion {
      background: var(--bg-surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      margin-bottom: 28px;
      overflow: hidden;
      box-shadow: var(--shadow-elevation);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .toc-accordion[open] {
      border-color: var(--border-medium);
    }

    .toc-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 20px;
      cursor: pointer;
      user-select: none;
      list-style: none;
      background: var(--bg-surface-elevated);
      transition: background-color 0.15s ease;
    }

    .toc-header::-webkit-details-marker {
      display: none;
    }

    .toc-header:hover {
      background: rgba(99, 102, 241, 0.08);
    }

    .toc-accordion[open] .accordion-chevron {
      transform: rotate(180deg);
      color: var(--color-primary);
    }

    .toc-body {
      padding: 18px 20px 22px 20px;
      border-top: 1px solid var(--border-subtle);
    }

    .toc-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .toc-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 9px;
      text-decoration: none;
      transition: all 0.15s ease;
    }

    .toc-item:hover {
      background: rgba(99, 102, 241, 0.08);
      border-color: var(--color-primary);
      transform: translateX(2px);
    }

    .toc-item-left {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      flex: 1;
    }

    .toc-num {
      font-family: var(--font-mono);
      font-weight: 700;
      font-size: 11px;
      color: var(--color-primary);
      background: var(--color-primary-light);
      padding: 2px 6px;
      border-radius: 4px;
      flex-shrink: 0;
    }

    .toc-item-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-heading);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .toc-item-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }

    .toc-arrow {
      color: var(--color-primary);
      font-size: 13px;
      opacity: 0.4;
      transition: opacity 0.15s, transform 0.15s;
    }

    .toc-item:hover .toc-arrow {
      opacity: 1;
      transform: translateX(3px);
    }

    .toc-quick-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding-top: 14px;
      border-top: 1px solid var(--border-subtle);
    }

    .toc-quick-label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-right: 4px;
    }

    .toc-quick-link {
      font-size: 11px;
      font-weight: 600;
      font-family: var(--font-mono);
      padding: 4px 10px;
      border-radius: 6px;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-medium);
      color: var(--text-secondary);
      text-decoration: none;
      transition: all 0.15s ease;
    }

    .toc-quick-link:hover {
      border-color: var(--color-primary);
      color: var(--color-primary);
      background: var(--color-primary-light);
    }

    /* ==========================================================================
       7. Markdown Content Typography
       ========================================================================== */
    .report-body {
      background: var(--bg-surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 40px;
      margin-bottom: 36px;
      box-shadow: var(--shadow-elevation);
    }

    .report-body h1, 
    .report-body h2, 
    .report-body h3, 
    .report-body h4 {
      color: var(--text-heading);
      font-weight: 700;
      line-height: 1.3;
      margin-top: 36px;
      margin-bottom: 16px;
      letter-spacing: -0.01em;
    }

    .report-body h1:first-child,
    .report-body h2:first-child {
      margin-top: 0;
    }

    .report-body h1 {
      font-size: 26px;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 12px;
      margin-bottom: 24px;
    }

    .report-body h2 {
      font-size: 20px;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 8px;
      color: var(--color-primary);
    }

    .report-body h3 {
      font-size: 16px;
    }

    .report-body p {
      margin-bottom: 16px;
      color: var(--text-primary);
    }

    .report-body ul, 
    .report-body ol {
      margin-bottom: 18px;
      padding-left: 24px;
    }

    .report-body li {
      margin-bottom: 8px;
    }

    .report-body blockquote {
      border-left: 4px solid var(--color-primary);
      background: var(--color-primary-light);
      padding: 14px 20px;
      margin: 20px 0;
      border-radius: 0 8px 8px 0;
      color: var(--text-secondary);
      font-style: italic;
    }

    .report-body table {
      width: 100%;
      border-collapse: collapse;
      margin: 24px 0;
      font-size: 13px;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      overflow: hidden;
    }

    .report-body th {
      background: var(--bg-surface-elevated);
      color: var(--text-heading);
      font-weight: 700;
      text-align: left;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-medium);
    }

    .report-body td {
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-primary);
    }

    .report-body tr:nth-child(even) {
      background: rgba(125, 125, 125, 0.03);
    }

    .report-body pre {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 12px;
      margin: 20px 0;
      color: var(--text-primary);
    }

    .report-body code {
      font-family: var(--font-mono);
      font-size: 12px;
      background: var(--bg-surface-elevated);
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--border-subtle);
    }

    .report-body hr {
      border: none;
      height: 1px;
      background: var(--border-subtle);
      margin: 36px 0;
    }

    /* ==========================================================================
       7.1. Section Accordions & Expand/Collapse
       ========================================================================== */
    .section-controls-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding: 10px 16px;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      margin-bottom: 20px;
    }

    .scb-left, .scb-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .scb-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-heading);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .btn-sm {
      padding: 4px 10px;
      font-size: 11px;
    }

    .sections-accordion-container {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .report-section-accordion {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      overflow: hidden;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .report-section-accordion[open] {
      border-color: var(--border-medium);
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
    }

    .report-section-accordion.highlighted {
      border-color: var(--color-primary);
      box-shadow: 0 0 0 2px var(--color-primary);
    }

    .section-accordion-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 18px;
      cursor: pointer;
      user-select: none;
      list-style: none; /* Hide default browser arrow */
      background: var(--bg-surface-elevated);
      transition: background-color 0.15s ease;
    }

    .section-accordion-header::-webkit-details-marker {
      display: none;
    }

    .section-accordion-header:hover {
      background: rgba(99, 102, 241, 0.08);
    }

    .sah-left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      flex: 1;
    }

    .sah-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }

    .accordion-chevron {
      width: 20px;
      height: 20px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--text-muted);
      transition: transform 0.2s ease, color 0.2s ease;
      flex-shrink: 0;
    }

    .chevron-icon {
      width: 15px;
      height: 15px;
    }

    .report-section-accordion[open] .accordion-chevron {
      transform: rotate(180deg);
      color: var(--color-primary);
    }

    .section-accordion-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-heading);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .section-meta-words {
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-muted);
    }

    .section-accordion-body {
      padding: 24px 28px;
      border-top: 1px solid var(--border-subtle);
      background: var(--bg-surface-card);
    }

    /* ==========================================================================
       8. Citation Badges & Tooltips (Interactive Mouse-Overs)
       ========================================================================== */
    .citation-badge-wrapper {
      position: relative;
      display: inline-flex;
      align-items: baseline;
      margin: 0 2px;
      vertical-align: baseline;
    }

    .citation-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 1px 7px;
      border-radius: 5px;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      user-select: none;
      border: 1px solid var(--border-medium);
      background: var(--bg-surface-elevated);
      color: var(--text-heading);
      transition: all 0.15s ease;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }

    .citation-badge:hover,
    .citation-badge:focus {
      border-color: var(--color-primary);
      transform: translateY(-1px);
      box-shadow: 0 4px 10px rgba(99, 102, 241, 0.25);
    }

    .citation-badge.status-validated {
      background: var(--color-emerald-bg);
      border-color: var(--color-emerald-border);
      color: var(--color-emerald);
    }

    .citation-badge.status-negated {
      background: var(--color-rose-bg);
      border-color: var(--color-rose-border);
      color: var(--color-rose);
      text-decoration: line-through;
    }

    .citation-badge.status-note {
      background: var(--color-cyan-bg);
      border-color: var(--color-cyan-border);
      color: var(--color-cyan);
    }

    .citation-badge.status-skybrary {
      background: var(--color-sky-bg);
      border-color: var(--color-sky-border);
      color: var(--color-sky);
    }

    .cite-icon {
      width: 12px;
      height: 12px;
      flex-shrink: 0;
      opacity: 0.85;
    }

    /* Pure CSS Fallback Tooltip */
    .citation-css-tooltip {
      visibility: hidden;
      opacity: 0;
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%) translateY(4px);
      width: 340px;
      max-width: 90vw;
      background: var(--tooltip-bg);
      border: 1px solid var(--border-medium);
      border-radius: 10px;
      padding: 12px 14px;
      box-shadow: var(--shadow-elevation);
      z-index: 1000;
      pointer-events: none;
      transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s;
      font-family: var(--font-sans);
      font-size: 12px;
      line-height: 1.5;
      text-align: left;
      white-space: normal;
    }

    .citation-badge-wrapper:hover .citation-css-tooltip {
      visibility: visible;
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }

    /* Dynamic JS Floating Tooltip */
    #floating-tooltip {
      position: fixed;
      z-index: 9999;
      width: 360px;
      max-width: calc(100vw - 32px);
      background: var(--tooltip-bg);
      border: 1px solid var(--color-primary);
      border-radius: 12px;
      padding: 14px 16px;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.3);
      backdrop-filter: blur(12px);
      pointer-events: none;
      display: none;
      opacity: 0;
      transform: scale(0.97);
      transition: opacity 0.12s ease, transform 0.12s ease;
      font-size: 12px;
      line-height: 1.55;
    }

    #floating-tooltip.active {
      display: block;
      opacity: 1;
      transform: scale(1);
    }

    .tt-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding-bottom: 8px;
      margin-bottom: 8px;
      border-bottom: 1px solid var(--border-subtle);
    }

    .tt-id {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      color: var(--color-primary);
      word-break: break-all;
    }

    .tt-tag {
      font-size: 9px;
      font-family: var(--font-mono);
      font-weight: 700;
      text-transform: uppercase;
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--border-medium);
      white-space: nowrap;
    }

    .tt-tag.status-validated {
      background: var(--color-emerald-bg);
      color: var(--color-emerald);
      border-color: var(--color-emerald-border);
    }

    .tt-tag.status-negated {
      background: var(--color-rose-bg);
      color: var(--color-rose);
      border-color: var(--color-rose-border);
    }

    .tt-tag.status-note {
      background: var(--color-cyan-bg);
      color: var(--color-cyan);
      border-color: var(--color-cyan-border);
    }

    .tt-tag.status-skybrary {
      background: var(--color-sky-bg);
      color: var(--color-sky);
      border-color: var(--color-sky-border);
    }

    .tt-body {
      color: var(--text-primary);
      max-height: 200px;
      overflow-y: auto;
      white-space: pre-line;
      margin-bottom: 8px;
    }

    .tt-footer {
      font-size: 10px;
      color: var(--text-muted);
      border-top: 1px solid var(--border-subtle);
      padding-top: 6px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    /* ==========================================================================
       9. Appendix Accordions & Collapsible Evidence
       ========================================================================== */
    .appendix-accordion {
      background: var(--bg-surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      margin-bottom: 20px;
      overflow: hidden;
      box-shadow: var(--shadow-elevation);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .appendix-accordion[open] {
      border-color: var(--border-medium);
    }

    .appendix-accordion.highlighted {
      border-color: var(--color-primary);
      box-shadow: 0 0 0 2px var(--color-primary);
    }

    .appendix-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 15px 22px;
      cursor: pointer;
      user-select: none;
      list-style: none;
      background: var(--bg-surface-elevated);
      transition: background-color 0.15s ease;
    }

    .appendix-header::-webkit-details-marker {
      display: none;
    }

    .appendix-header:hover {
      background: rgba(99, 102, 241, 0.08);
    }

    .ah-left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      flex: 1;
    }

    .ah-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }

    .appendix-header-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-heading);
    }

    .appendix-accordion[open] .accordion-chevron {
      transform: rotate(180deg);
      color: var(--color-primary);
    }

    .appendix-body {
      padding: 24px 28px;
      border-top: 1px solid var(--border-subtle);
    }

    .chunk-search-bar {
      margin-bottom: 18px;
    }

    .search-input {
      width: 100%;
      padding: 10px 14px;
      border-radius: 8px;
      border: 1px solid var(--border-medium);
      background: var(--bg-surface-elevated);
      color: var(--text-heading);
      font-size: 13px;
    }

    .chunk-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 14px;
      transition: border-color 0.2s, box-shadow 0.2s;
    }

    .chunk-card:target,
    .chunk-card.highlighted {
      border-color: var(--color-primary);
      box-shadow: 0 0 0 2px var(--color-primary);
    }

    .chunk-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }

    .chunk-card-id {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      color: var(--text-heading);
    }

    .chunk-card-text {
      font-size: 13px;
      color: var(--text-secondary);
      white-space: pre-wrap;
      line-height: 1.6;
    }

    /* ==========================================================================
       10. Print Stylesheet (@media print)
       ========================================================================== */
    @media print {
      body {
        background: white !important;
        color: black !important;
        padding-bottom: 0 !important;
      }

      .report-topbar,
      .citation-css-tooltip,
      #floating-tooltip,
      .chunk-search-bar,
      .toolbar-actions {
        display: none !important;
      }

      .container {
        max-width: 100% !important;
        padding: 0 !important;
      }

      .hero-card,
      .report-body,
      .appendix-section,
      .chunk-card {
        border: 1px solid #ccc !important;
        box-shadow: none !important;
        background: white !important;
        color: black !important;
        break-inside: avoid;
      }

      .citation-badge {
        border: 1px solid #999 !important;
        background: #f0f0f0 !important;
        color: black !important;
        text-decoration: underline !important;
      }

      .section-controls-bar,
      .accordion-chevron {
        display: none !important;
      }

      .report-section-accordion,
      .report-section-accordion[open],
      .report-section-accordion:not([open]),
      .appendix-accordion,
      .appendix-accordion[open],
      .appendix-accordion:not([open]) {
        display: block !important;
        border: 1px solid #ddd !important;
        margin-bottom: 20px !important;
        break-inside: avoid;
      }

      .section-accordion-header,
      .appendix-header {
        background: #f8f8f8 !important;
        pointer-events: none !important;
      }

      .section-accordion-body,
      .appendix-body {
        display: block !important;
        border-top: 1px solid #ddd !important;
      }
    }
  </style>
</head>
<body>

  <!-- Floating Fixed Dynamic Tooltip -->
  <div id="floating-tooltip">
    <div class="tt-header">
      <span class="tt-id" id="ft-id"></span>
      <span class="tt-tag" id="ft-tag"></span>
    </div>
    <div class="tt-body" id="ft-body"></div>
    <div class="tt-footer">
      <span>AeroLex Autonomous Evidence Citation</span>
      <span>Click to view in Appendix</span>
    </div>
  </div>

  <!-- Sticky Executive Topbar -->
  <header class="report-topbar">
    <div class="container topbar-inner">
      <div class="brand-group">
        <div class="brand-icon">✈</div>
        <div>
          <div class="brand-title">AeroLex Autonomous Regulatory Intelligence</div>
          <div class="brand-sub">Job ID: ${escapeHtml(job.job_id.slice(0, 12))} · L${job.recursion_level || 1} Recursion</div>
        </div>
      </div>

      <div class="toolbar-actions">
        <button class="btn" id="btn-theme-toggle" type="button" title="Toggle Light / Dark mode">
          <span id="theme-icon">🌓</span> Theme
        </button>
        <button class="btn" onclick="window.print()" type="button" title="Print report or save to PDF">
          🖨️ Print / PDF
        </button>
        <a class="btn" href="#appendix-chunks" title="Jump to full regulatory provisions index">
          📚 Citations (${chunkMetaMap.size})
        </a>
        <button class="btn btn-primary" id="btn-copy-md" type="button" title="Copy report markdown to clipboard">
          📋 Copy Markdown
        </button>
      </div>
    </div>
  </header>

  <main class="container">
    <!-- Hero Metadata Card -->
    <section class="hero-card">
      <div class="hero-badge-row">
        <span class="pill pill-accent">${escapeHtml(reportVariantLabel)}</span>
        <span class="pill pill-emerald">STATUS: ${escapeHtml(job.status || 'COMPLETED')}</span>
        <span class="pill">ENGINE: ${escapeHtml(providerLabel)}</span>
        <span class="pill">GENERATED: ${escapeHtml(createdDate)}</span>
      </div>

      <h1 class="hero-title">${escapeHtml(queryText)}</h1>

      <div class="hero-query-box">
        <span class="hero-query-label">Inquiry Scope</span>
        <div>${escapeHtml(queryText)}</div>
      </div>

      <!-- Scope Evaluation & Falsification Ledger -->
      <div class="audit-grid">
        <div>
          <div class="audit-col-title" style="color: var(--color-emerald)">
            <span>✓ Target Governing Domains</span>
          </div>
          <div class="audit-tags">
            ${targetDomains.length > 0 ? targetDomains.map(d => `<span class="pill pill-emerald">${escapeHtml(d)}</span>`).join('') : '<span class="pill">Autonomous Domain Scope</span>'}
          </div>
        </div>

        <div>
          <div class="audit-col-title" style="color: var(--color-rose)">
            <span>✕ Scope Falsification Boundaries</span>
          </div>
          <div class="audit-tags">
            ${excludedDomains.length > 0 ? excludedDomains.map(d => `<span class="pill" style="border-color: var(--color-rose); color: var(--color-rose); text-decoration: line-through">${escapeHtml(d)}</span>`).join('') : '<span class="pill">No exclusions declared</span>'}
          </div>
        </div>

        <div>
          <div class="audit-col-title" style="color: var(--color-primary)">
            <span>⚖ Provision Audit</span>
          </div>
          <div class="audit-tags">
            <span class="pill pill-emerald">${validatedCount} Validated</span>
            <span class="pill" style="color: var(--color-rose); border-color: var(--color-rose)">${negatedCount} Negated</span>
            <span class="pill">${chunkMetaMap.size} Indexed Chunks</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Table of Contents (Executive Structured Outline) -->
    ${sections.length > 1 ? `
    <details class="toc-accordion" open aria-label="Report Outline and Structure">
      <summary class="toc-header">
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="accordion-chevron">
            <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
          </span>
          <span style="font-size: 15px; font-weight: 700; color: var(--text-heading);">📑 Report Outline & Structured Sections</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="pill pill-accent" style="font-size: 11px;">${sections.length} Sections</span>
        </div>
      </summary>
      <div class="toc-body">
        <div class="toc-grid">
          ${sections.map((sec, i) => {
            const style = getSectionStyle(sec.type);
            const num = (i + 1).toString().padStart(2, '0');
            const citeCount = sec.citationCount ?? countCitations(sec.markdown);
            return `
              <a href="#section-${i + 1}" class="toc-item toc-link" title="Jump to ${escapeHtml(sec.title)}">
                <div class="toc-item-left">
                  <span class="toc-num">${num}</span>
                  <span class="pill ${style.badgeClass || 'pill-accent'}" style="font-size: 9px; padding: 1px 5px; flex-shrink: 0;">${escapeHtml(style.label || 'Section')}</span>
                  <span class="toc-item-title">${escapeHtml(sec.title)}</span>
                </div>
                <div class="toc-item-right">
                  ${citeCount > 0 ? `<span class="pill pill-accent" style="font-size: 10px; padding: 1px 5px;">${citeCount} cite${citeCount > 1 ? 's' : ''}</span>` : ''}
                  <span class="toc-arrow">→</span>
                </div>
              </a>
            `;
          }).join('')}
        </div>
        <div class="toc-quick-bar">
          <span class="toc-quick-label">Appendices:</span>
          ${researchGaps.length > 0 ? `<a href="#appendix-gaps" class="toc-quick-link">🔍 Self-Critique & Gaps (${researchGaps.length})</a>` : ''}
          ${consultedRegs.length > 0 ? `<a href="#appendix-regulations" class="toc-quick-link">📋 Appendix A: Regulations (${consultedRegs.length})</a>` : ''}
          <a href="#appendix-chunks" class="toc-quick-link">📚 Appendix B: Evidence Chunks (${chunkMetaMap.size})</a>
          ${(readingMaterials.length > 0 || userNotes.length > 0) ? `<a href="#appendix-materials" class="toc-quick-link">📖 Appendix C: Materials</a>` : ''}
        </div>
      </div>
    </details>
    ` : ''}

    <!-- Main Rendered Markdown Report -->
    <article class="report-body" id="report-content">
      ${renderedContentHtml}
    </article>

    <!-- Report Self-Critique & Regulatory Gaps (if present) -->
    ${researchGaps.length > 0 ? `
    <details class="appendix-accordion" id="appendix-gaps" open>
      <summary class="appendix-header">
        <div class="ah-left">
          <span class="accordion-chevron">
            <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
          </span>
          <span class="appendix-header-title">🔍 Report Self-Critique & Identified Regulatory Gaps</span>
        </div>
        <div class="ah-right">
          <span class="pill pill-accent">${researchGaps.length} Gaps</span>
        </div>
      </summary>
      <div class="appendix-body">
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 16px;">
          The deep research engine critiqued its own findings and identified potential regulatory ambiguities or tangential topics:
        </p>
        <div style="display: grid; gap: 12px;">
          ${researchGaps.map(gap => `
            <div class="chunk-card">
              <div style="font-weight: 700; color: var(--text-heading); font-size: 14px; margin-bottom: 4px;">
                ${escapeHtml(gap.topic)}
              </div>
              <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                ${escapeHtml(gap.description)}
              </p>
              <div style="font-size: 12px; font-family: var(--font-mono); color: var(--color-primary); background: var(--bg-surface-elevated); padding: 6px 10px; border-radius: 6px;">
                Sub-query: ${escapeHtml(gap.sub_query)}
              </div>
              ${gap.rationale ? `<div style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">Rationale: ${escapeHtml(gap.rationale)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    </details>
    ` : ''}

    <!-- Appendix A: Consulted Regulations & Official Documents -->
    ${consultedRegs.length > 0 ? `
    <details class="appendix-accordion" id="appendix-regulations" open>
      <summary class="appendix-header">
        <div class="ah-left">
          <span class="accordion-chevron">
            <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
          </span>
          <span class="appendix-header-title">📋 Appendix A: Consulted Regulations & Official Documents</span>
        </div>
        <div class="ah-right">
          <span class="pill">${consultedRegs.length} Documents</span>
        </div>
      </summary>
      <div class="appendix-body">
        <div style="overflow-x: auto;">
          <table>
            <thead>
              <tr>
                <th>Document ID</th>
                <th>Official Title / Regulation Number</th>
                <th>Source / Origin</th>
                <th>Publication Date</th>
              </tr>
            </thead>
            <tbody>
              ${consultedRegs.map(reg => `
                <tr>
                  <td style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(reg.document_id || 'N/A')}</td>
                  <td style="font-weight: 600;">${escapeHtml(reg.document_title || reg.title || reg.regulation_number || 'Official Publication')}</td>
                  <td><span class="pill">${escapeHtml(reg.source || 'EASA / FAA')}</span></td>
                  <td style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(reg.publication_date || 'N/A')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </details>
    ` : ''}

    <!-- Appendix B: Referenced Provisions & Chunk Excerpts Index -->
    <details class="appendix-accordion" id="appendix-chunks" open>
      <summary class="appendix-header">
        <div class="ah-left">
          <span class="accordion-chevron">
            <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
          </span>
          <span class="appendix-header-title">📚 Appendix B: Referenced Regulatory Provisions & Chunk Excerpts</span>
        </div>
        <div class="ah-right">
          <span class="pill pill-accent">${chunkMetaMap.size} Indexed Provisions</span>
        </div>
      </summary>
      <div class="appendix-body">
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 14px;">
          Full regulatory text excerpts for all citations referenced across this report. Move your mouse over any citation badge in the text above to preview its excerpt, or search below:
        </p>

        <div class="chunk-search-bar">
          <input type="text" id="chunk-filter-input" class="search-input" placeholder="Filter referenced chunks by ID or keyword...">
        </div>

        <div id="chunks-container">
          ${Array.from(chunkMetaMap.values()).map(meta => {
            const safeAnchor = `chunk-${escapeHtml(meta.chunkId.replace(/[^a-zA-Z0-9_-]/g, '_'))}`;
            return `
              <div class="chunk-card" id="${safeAnchor}" data-search="${escapeHtml((meta.chunkId + ' ' + meta.excerpt).toLowerCase())}">
                <div class="chunk-card-header">
                  <span class="chunk-card-id">${escapeHtml(meta.chunkId)}</span>
                  <span class="pill ${meta.statusClass}">${escapeHtml(meta.statusLabel)}</span>
                </div>
                ${meta.docTitle ? `<div style="font-size: 11px; color: var(--color-primary); margin-bottom: 8px;">Document: ${escapeHtml(meta.docTitle)}</div>` : ''}
                <div class="chunk-card-text">${escapeHtml(meta.excerpt)}</div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    </details>

    <!-- Appendix C: Reading Materials (Skybrary & Notes) -->
    ${(readingMaterials.length > 0 || userNotes.length > 0) ? `
    <details class="appendix-accordion" id="appendix-materials" open>
      <summary class="appendix-header">
        <div class="ah-left">
          <span class="accordion-chevron">
            <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>
          </span>
          <span class="appendix-header-title">📖 Appendix C: Supplementary Technical Materials</span>
        </div>
        <div class="ah-right">
          <span class="pill">${readingMaterials.length + userNotes.length} Items</span>
        </div>
      </summary>
      <div class="appendix-body">
        ${readingMaterials.length > 0 ? `
          <h3 style="font-size: 14px; font-weight: 700; margin-bottom: 12px; color: var(--color-sky);">
            Flight Safety Foundation Skybrary Articles (${readingMaterials.length})
          </h3>
          <div style="display: grid; gap: 10px; margin-bottom: 24px;">
            ${readingMaterials.map(mat => `
              <div class="chunk-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
                  <div style="font-weight: 700; color: var(--text-heading); font-size: 13px;">${escapeHtml(mat.title)}</div>
                  <span class="pill pill-accent">${Math.round((mat.relevance_score || 0) * 100)}% Match</span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted); margin: 4px 0 8px 0;">
                  Category: ${escapeHtml(mat.category || 'Safety')} · Author: ${escapeHtml(mat.author || 'Skybrary')}
                </div>
                ${mat.match_rationale ? `<div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">Rationale: ${escapeHtml(mat.match_rationale)}</div>` : ''}
                ${mat.key_excerpt ? `<div style="font-size: 12px; font-style: italic; color: var(--text-muted); background: var(--bg-surface-elevated); padding: 8px; border-radius: 6px;">"${escapeHtml(mat.key_excerpt)}"</div>` : ''}
              </div>
            `).join('')}
          </div>
        ` : ''}

        ${userNotes.length > 0 ? `
          <h3 style="font-size: 14px; font-weight: 700; margin-bottom: 12px; color: var(--color-cyan);">
            Internal Project Notes & Operational Journals (${userNotes.length})
          </h3>
          <div style="display: grid; gap: 10px;">
            ${userNotes.map(note => `
              <div class="chunk-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
                  <div style="font-weight: 700; color: var(--text-heading); font-size: 13px;">${escapeHtml(note.title)}</div>
                  <span class="pill pill-accent">${Math.round((note.relevance_score || 0) * 100)}% Match</span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted); margin: 4px 0 8px 0;">
                  Type: ${escapeHtml(note.note_type)} · Project: ${escapeHtml(note.project || 'General')} · Date: ${escapeHtml(note.date || 'N/A')}
                </div>
                ${note.match_rationale ? `<div style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(note.match_rationale)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    </details>
    ` : ''}
  </main>

  <!-- Embedded Data & Client Scripts -->
  <script type="application/json" id="citations-data">${serializedChunkData}</script>
  <script type="text/markdown" id="report-raw-markdown">${escapeHtml(activeMarkdown)}</script>

  <script>
    (function() {
      // 1. Parse Embedded Citation Metadata
      var citationData = {};
      try {
        var rawData = document.getElementById('citations-data').textContent;
        citationData = JSON.parse(rawData);
      } catch (e) {
        console.error('Failed to parse citations data', e);
      }

      // 2. Dynamic Floating Tooltip Positioning on Mouse-Over
      var tooltip = document.getElementById('floating-tooltip');
      var ftId = document.getElementById('ft-id');
      var ftTag = document.getElementById('ft-tag');
      var ftBody = document.getElementById('ft-body');
      var activeBadge = null;

      function showTooltip(badge) {
        activeBadge = badge;
        var chunkId = badge.getAttribute('data-chunk-id');
        if (!chunkId) return;

        var data = citationData[chunkId] || {
          id: chunkId,
          statusClass: 'status-referenced',
          statusLabel: 'Referenced Source',
          excerpt: 'Excerpt details available in Appendix B.'
        };

        ftId.textContent = 'Chunk: ' + data.id;
        ftTag.textContent = data.statusLabel;
        ftTag.className = 'tt-tag ' + data.statusClass;
        ftBody.textContent = data.excerpt || 'Source excerpt text not available.';

        tooltip.classList.add('active');
        positionTooltip(badge);
      }

      function hideTooltip() {
        activeBadge = null;
        tooltip.classList.remove('active');
      }

      function positionTooltip(badge) {
        var rect = badge.getBoundingClientRect();
        var ttWidth = 360;
        var ttHeight = tooltip.offsetHeight || 160;
        var padding = 16;

        // Calculate horizontal center
        var left = rect.left + (rect.width / 2) - (ttWidth / 2);
        left = Math.max(padding, Math.min(window.innerWidth - ttWidth - padding, left));

        // Place above if room, else below
        var top = rect.top - ttHeight - 10;
        if (top < padding) {
          top = rect.bottom + 10;
        }

        tooltip.style.left = left + 'px';
        tooltip.style.top = top + 'px';
      }

      // Attach event listeners to all citation badges
      var badges = document.querySelectorAll('.citation-badge');
      badges.forEach(function(badge) {
        badge.addEventListener('mouseenter', function() { showTooltip(badge); });
        badge.addEventListener('mouseleave', hideTooltip);
        badge.addEventListener('focus', function() { showTooltip(badge); });
        badge.addEventListener('blur', hideTooltip);

        // Click to smoothly jump and highlight target chunk in appendix
        badge.addEventListener('click', function(e) {
          var href = badge.getAttribute('href');
          if (href && href.startsWith('#')) {
            var targetId = href.substring(1);
            var targetEl = document.getElementById(targetId);
            if (targetEl) {
              // Auto-expand parent appendix if collapsed
              var parentDetails = targetEl.closest('details');
              if (parentDetails) {
                parentDetails.open = true;
              }
              targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
              targetEl.classList.add('highlighted');
              setTimeout(function() {
                targetEl.classList.remove('highlighted');
              }, 2500);
            }
          }
        });
      });

      window.addEventListener('scroll', function() {
        if (activeBadge) positionTooltip(activeBadge);
      }, { passive: true });

      // 3. Theme Toggle Switch
      var themeBtn = document.getElementById('btn-theme-toggle');
      var themeIcon = document.getElementById('theme-icon');
      
      // Load preference from localStorage or OS preference
      var currentTheme = localStorage.getItem('aerolex_theme') || 'dark';
      document.documentElement.setAttribute('data-theme', currentTheme);
      updateThemeIcon(currentTheme);

      themeBtn.addEventListener('click', function() {
        var newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('aerolex_theme', newTheme);
        updateThemeIcon(newTheme);
      });

      function updateThemeIcon(theme) {
        themeIcon.textContent = theme === 'dark' ? '🌙' : '☀️';
      }

      // 4. Copy Report Markdown Button
      var copyBtn = document.getElementById('btn-copy-md');
      if (copyBtn) {
        copyBtn.addEventListener('click', function() {
          var rawMd = document.getElementById('report-raw-markdown').textContent;
          navigator.clipboard.writeText(rawMd).then(function() {
            var original = copyBtn.innerHTML;
            copyBtn.innerHTML = '✓ Copied!';
            setTimeout(function() { copyBtn.innerHTML = original; }, 2000);
          }).catch(function() {
            alert('Could not copy to clipboard.');
          });
        });
      }

      // 5. Expand All / Collapse All Accordions (Sections & Appendices)
      var btnExpandAll = document.getElementById('btn-expand-all');
      var btnCollapseAll = document.getElementById('btn-collapse-all');

      if (btnExpandAll) {
        btnExpandAll.addEventListener('click', function() {
          document.querySelectorAll('.report-section-accordion, .appendix-accordion, .toc-accordion').forEach(function(el) {
            el.open = true;
          });
        });
      }

      if (btnCollapseAll) {
        btnCollapseAll.addEventListener('click', function() {
          document.querySelectorAll('.report-section-accordion, .appendix-accordion').forEach(function(el) {
            el.open = false;
          });
        });
      }

      // 6. Anchor Links (TOC & Appendices): Auto-expand target accordion on click
      document.querySelectorAll('a[href^="#"]').forEach(function(link) {
        link.addEventListener('click', function(e) {
          var href = link.getAttribute('href');
          if (href && href.length > 1) {
            var target = document.querySelector(href);
            if (target) {
              if (target.tagName.toLowerCase() === 'details') {
                target.open = true;
              }
              var parentDetails = target.closest('details');
              if (parentDetails) {
                parentDetails.open = true;
              }
              target.scrollIntoView({ behavior: 'smooth', block: 'start' });
              target.classList.add('highlighted');
              setTimeout(function() {
                target.classList.remove('highlighted');
              }, 2000);
            }
          }
        });
      });

      // 7. Appendix B Fast Search Filter
      var searchInput = document.getElementById('chunk-filter-input');
      var chunkCards = document.querySelectorAll('#chunks-container .chunk-card');

      if (searchInput) {
        searchInput.addEventListener('input', function(e) {
          var term = e.target.value.toLowerCase().trim();
          chunkCards.forEach(function(card) {
            var text = card.getAttribute('data-search') || '';
            if (!term || text.indexOf(term) !== -1) {
              card.style.display = 'block';
            } else {
              card.style.display = 'none';
            }
          });
        });
      }
    })();
  </script>
</body>
</html>`;
}

/**
 * Triggers an instant download of the report formatted as a rich standalone HTML document.
 */
export function downloadResearchReportHtml(
  job: ResearchJobDetail,
  reportType: 'initial' | 'comprehensive' = 'initial'
): void {
  const htmlContent = generateResearchReportHtml(job, reportType);
  const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const safeJobId = (job.job_id || 'report').slice(0, 8);
  link.setAttribute('download', `Regulatory_Research_${safeJobId}_${reportType}.html`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Downloads report as raw markdown.
 */
export function downloadResearchReportMarkdown(
  job: ResearchJobDetail,
  reportType: 'initial' | 'comprehensive' = 'initial'
): void {
  const activeMarkdown = (reportType === 'comprehensive' && job.comprehensive_report_markdown)
    ? job.comprehensive_report_markdown
    : (job.report_markdown || '');
  if (!activeMarkdown) return;
  const blob = new Blob([activeMarkdown], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const safeJobId = (job.job_id || 'report').slice(0, 8);
  link.setAttribute('download', `Regulatory_Research_${safeJobId}_${reportType}.md`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
