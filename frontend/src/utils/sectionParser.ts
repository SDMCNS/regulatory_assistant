/**
 * Utility to parse markdown documents with embedded section break comments
 * or standard markdown headers, returning structured DocSection objects.
 */

import { DocSection } from '../types';

export function countWords(str: string): number {
  return str.split(/\s+/).filter(Boolean).length;
}

/**
 * Normalizes chunk citations in markdown by wrapping the chunk URL in angle brackets `<chunk:...>`.
 * Handles chunk IDs containing colons, spaces, and balanced parentheses (such as EU Formex `:(1):0`
 * or EASA regulation titles `(Regulation (EU) 2015_340)`), preventing truncation and plain-text leakage.
 */
export function normalizeChunkCitations(content: string): string {
  if (!content) return '';
  let result = '';
  let i = 0;
  const len = content.length;

  while (i < len) {
    const linkStart = content.indexOf('](', i);
    if (linkStart === -1) {
      result += content.slice(i);
      break;
    }

    const openBracket = content.lastIndexOf('[', linkStart);
    if (openBracket === -1 || openBracket < i) {
      result += content.slice(i, linkStart + 2);
      i = linkStart + 2;
      continue;
    }

    const text = content.slice(openBracket + 1, linkStart);
    const afterParen = content.slice(linkStart + 2);

    let isAngle = false;
    let target = '';
    if (afterParen.startsWith('<chunk:')) {
      isAngle = true;
      target = '<chunk:';
    } else if (afterParen.startsWith('chunk:')) {
      target = 'chunk:';
    } else {
      result += content.slice(i, linkStart + 2);
      i = linkStart + 2;
      continue;
    }

    result += content.slice(i, openBracket);
    const destStart = linkStart + 2 + target.length;

    if (isAngle) {
      const angleClose = content.indexOf('>)', destStart);
      if (angleClose !== -1) {
        const chunkId = content.slice(destStart, angleClose).trim();
        result += `[${text}](<chunk:${chunkId}>)`;
        i = angleClose + 2;
        continue;
      }
    }

    // Balanced parentheses scanning
    let depth = 1;
    let destEnd = destStart;
    while (destEnd < len && depth > 0) {
      if (content[destEnd] === '(') depth++;
      else if (content[destEnd] === ')') depth--;
      if (depth === 0) break;
      destEnd++;
    }

    if (depth === 0) {
      const rawChunkId = content.slice(destStart, destEnd).trim();
      const cleanChunkId = rawChunkId.replace(/^[<"']+|[>"']+$/g, '').trim();
      result += `[${text}](<chunk:${cleanChunkId}>)`;
      i = destEnd + 1;
    } else {
      result += content.slice(openBracket, linkStart + 2);
      i = linkStart + 2;
    }
  }

  return result;
}

/**
 * Normalizes text for comparison (replaces curly quotes, dashes, multiple spaces).
 */
function normalizeIdKey(key: string): string {
  return key
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[—–]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Robustly finds the regulatory excerpt for a chunk citation.
 * Handles exact matches, punctuation/quote variations, suffix/locator matching,
 * and falls back to evaluation audit notes if available.
 */
export function findChunkExcerpt(
  chunkId: string,
  referencedChunks?: Record<string, string> | null,
  evaluationSummary?: any | null
): string {
  if (!chunkId) return 'Source regulatory chunk context not available.';
  const cleanId = chunkId.trim().replace(/^[<"']+|[>"']+$/g, '');

  if (referencedChunks) {
    // 1. Exact match
    if (referencedChunks[cleanId]) return referencedChunks[cleanId];
    if (referencedChunks[chunkId]) return referencedChunks[chunkId];

    // 2. Normalized key match (case, quotes, dashes)
    const normClean = normalizeIdKey(cleanId);
    for (const [k, v] of Object.entries(referencedChunks)) {
      if (normalizeIdKey(k) === normClean) return v;
    }

    // 3. Suffix match by section/ERULES/paragraph locator (e.g. ":ERULES-...", ":(1):0", ":621")
    const lastColonIdx = cleanId.lastIndexOf(':');
    if (lastColonIdx !== -1) {
      const suffix = cleanId.slice(lastColonIdx);
      if (suffix.length > 2) {
        for (const [k, v] of Object.entries(referencedChunks)) {
          if (k.endsWith(suffix)) return v;
        }
      }
    }
  }

  // 4. Check evaluation summary for negated or validated reasoning
  if (evaluationSummary) {
    const negated = evaluationSummary.negated_chunks || {};
    const validated = evaluationSummary.validated_chunks || {};

    if (negated[cleanId]) return `[Scope Evaluation: Excluded / Negated Provision]\n${negated[cleanId]}`;
    if (validated[cleanId]) return `[Scope Evaluation: Validated Regulatory Provision]\n${validated[cleanId]}`;

    const lastColonIdx = cleanId.lastIndexOf(':');
    if (lastColonIdx !== -1) {
      const suffix = cleanId.slice(lastColonIdx);
      if (suffix.length > 2) {
        for (const [k, v] of Object.entries(negated)) {
          if (k.endsWith(suffix)) return `[Scope Evaluation: Excluded / Negated Provision]\n${v}`;
        }
        for (const [k, v] of Object.entries(validated)) {
          if (k.endsWith(suffix)) return `[Scope Evaluation: Validated Regulatory Provision]\n${v}`;
        }
      }
    }
  }

  return `Source regulatory chunk context not available for:\n${cleanId}`;
}

export function countCitations(markdown: string): number {
  if (!markdown) return 0;
  const normalized = normalizeChunkCitations(markdown);
  const matches = normalized.match(/\[([^\]]*?)\]\(<chunk:([^>]+)>\)/g);
  return matches ? matches.length : 0;
}

/**
 * Splits a markdown document containing SECTION_BREAK tokens into structured sections.
 * 
 * Expected token format:
 * \n\n---\n<!-- SECTION_BREAK {"id": "...", "title": "...", "type": "..."} -->\n\n
 */
export function parseDocumentSections(markdownDoc: string): DocSection[] {
  if (!markdownDoc || !markdownDoc.trim()) {
    return [];
  }

  // Regex matching optional horizontal rule and SECTION_BREAK comment with optional JSON payload
  const breakPattern = /\n*(?:---\n*)?<!-- SECTION_BREAK\s*(\{.*?\})?\s*-->\n*/g;
  
  const parts = markdownDoc.split(breakPattern);
  const sections: DocSection[] = [];

  // Preamble / document header before first section break
  if (parts[0] && parts[0].trim()) {
    const text = parts[0].trim();
    sections.push({
      index: 0,
      id: 'doc-header',
      type: 'doc_header',
      title: 'Document Overview',
      meta: { type: 'doc_header', title: 'Document Overview' },
      markdown: text,
      wordCount: countWords(text),
      citationCount: countCitations(text),
    });
  }

  // Subsequent sections alternate between [metaJson, sectionContent]
  let idx = 1;
  let secCount = 1;
  while (idx < parts.length) {
    const metaRaw = parts[idx];
    const content = (parts[idx + 1] || '').trim();
    let meta: Record<string, any> = {};

    if (metaRaw) {
      try {
        meta = JSON.parse(metaRaw);
      } catch (e) {
        meta = {};
      }
    }

    const title = meta.title || `Section ${secCount}`;
    const id = meta.id || `section-${secCount}`;
    const type = (meta.type || 'section').trim();

    if (content) {
      sections.push({
        index: secCount,
        id,
        type,
        title,
        meta,
        markdown: content,
        wordCount: countWords(content),
        citationCount: countCitations(content),
      });
      secCount++;
    }

    idx += 2;
  }

  // If no section breaks were found in the document, return the whole document as a single section
  if (sections.length === 0 && markdownDoc.trim()) {
    const text = markdownDoc.trim();
    sections.push({
      index: 0,
      id: 'full-doc',
      type: 'document',
      title: 'Full Document',
      meta: {},
      markdown: text,
      wordCount: countWords(text),
      citationCount: countCitations(text),
    });
  }

  return sections;
}

/**
 * Splits a deep research report into structured sections using standard markdown
 * headers (## Header) or horizontal dividers (*** / ---).
 */
export function parseReportSections(markdownReport: string): DocSection[] {
  if (!markdownReport || !markdownReport.trim()) {
    return [];
  }

  // If the document already uses SECTION_BREAK comments, use standard parser
  if (markdownReport.includes('<!-- SECTION_BREAK')) {
    return parseDocumentSections(markdownReport);
  }

  // Split on optional horizontal rule followed by ## Header
  const headerSplitRegex = /\n+(?:\*{3,}|-{3,})?\n*(?=##\s+)/g;
  let rawParts = markdownReport.split(headerSplitRegex);

  // If no ## headers found, try splitting on horizontal rules alone
  if (rawParts.length <= 1) {
    const hrSplitRegex = /\n+(?:\*{3,}|-{3,})\n+/g;
    rawParts = markdownReport.split(hrSplitRegex);
  }

  // If still a single part, return full document as single section
  if (rawParts.length <= 1) {
    const trimmed = markdownReport.trim();
    return [{
      index: 0,
      id: 'report-sec-0',
      type: 'document',
      title: 'Report Content',
      meta: {},
      markdown: trimmed,
      wordCount: countWords(trimmed),
      citationCount: countCitations(trimmed),
    }];
  }

  const sections: DocSection[] = [];

  rawParts.forEach((part, idx) => {
    // Strip trailing or leading divider rules
    const cleanContent = part.trim().replace(/^[\*\-]{3,}\s*/, '').replace(/[\*\-]{3,}\s*$/, '').trim();
    if (!cleanContent) return;

    const lines = cleanContent.split('\n');
    let title = `Section ${idx + 1}`;
    let secType = 'section';

    if (idx === 0) {
      // Check for # Title in the overview/preamble
      const h1Match = lines[0].match(/^#\s+(.+)$/);
      title = h1Match ? h1Match[1].trim() : 'Document Overview';
      secType = 'doc_header';
    } else {
      // Check for ## Title
      const h2Match = lines[0].match(/^##\s+(.+)$/);
      if (h2Match) {
        title = h2Match[1].trim();
      } else {
        const anyHMatch = lines[0].match(/^#+\s+(.+)$/);
        if (anyHMatch) {
          title = anyHMatch[1].trim();
        }
      }

      const lower = title.toLowerCase();
      if (lower.includes('summary')) {
        secType = 'executive_summary';
      } else if (lower.includes('framework') || lower.includes('scope')) {
        secType = 'regulatory_framework';
      } else if (lower.includes('requirement') || lower.includes('mandate')) {
        secType = 'requirements';
      } else if (lower.includes('standard') || lower.includes('amc') || lower.includes('implementation') || lower.includes('gm')) {
        secType = 'standards';
      } else if (lower.includes('recommendation') || lower.includes('synthesis') || lower.includes('conclusion')) {
        secType = 'recommendations';
      }
    }

    sections.push({
      index: idx,
      id: `report-sec-${idx}`,
      type: secType,
      title,
      meta: { title, type: secType },
      markdown: cleanContent,
      wordCount: countWords(cleanContent),
      citationCount: countCitations(cleanContent),
    });
  });

  return sections;
}

/**
 * Helper to get user-friendly badges and visual styling for each regulatory and report section type
 */
export function getSectionStyle(type: string): {
  label: string;
  badgeClass: string;
} {
  const norm = type.toLowerCase();

  if (norm === 'doc_header' || norm === 'document') {
    return {
      label: 'Overview',
      badgeClass: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30',
    };
  }

  if (norm.includes('summary') || norm === 'executive_summary') {
    return {
      label: 'Executive Summary',
      badgeClass: 'bg-purple-500/10 text-purple-300 border-purple-500/30',
    };
  }

  if (norm.includes('framework') || norm.includes('scope')) {
    return {
      label: 'Regulatory Framework',
      badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    };
  }

  if (norm.includes('requirement') || norm.includes('mandate')) {
    return {
      label: 'Key Requirements',
      badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    };
  }

  if (norm.includes('standard') || norm.includes('amc') || norm.includes('implementation') || norm.includes('gm')) {
    return {
      label: 'Standards & AMC',
      badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    };
  }

  if (norm.includes('recommendation') || norm.includes('synthesis') || norm.includes('conclusion')) {
    return {
      label: 'Recommendations',
      badgeClass: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
    };
  }

  if (norm.startsWith('cs')) {
    return {
      label: 'Certification Spec',
      badgeClass: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
    };
  }

  if (norm.startsWith('amc')) {
    return {
      label: 'AMC (Compliance)',
      badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    };
  }

  if (norm === 'heading' || norm === 'subpart') {
    return {
      label: 'Subpart / Group',
      badgeClass: 'bg-purple-500/10 text-purple-300 border-purple-500/30',
    };
  }

  if (norm === 'article') {
    return {
      label: 'Article',
      badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    };
  }

  if (norm === 'annex') {
    return {
      label: 'Annex',
      badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    };
  }

  return {
    label: type.length > 20 ? type.slice(0, 20) + '…' : type || 'Section',
    badgeClass: 'bg-slate-800/80 text-slate-300 border-slate-700',
  };
}
