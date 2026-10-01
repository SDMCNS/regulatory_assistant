/**
 * Utility to parse markdown documents with embedded section break comments
 * and return structured DocSection objects.
 */

import { DocSection } from '../types';

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
    sections.push({
      index: 0,
      id: 'doc-header',
      type: 'doc_header',
      title: 'Document Overview',
      meta: { type: 'doc_header', title: 'Document Overview' },
      markdown: parts[0].trim(),
      wordCount: countWords(parts[0].trim()),
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
      });
      secCount++;
    }

    idx += 2;
  }

  // If no section breaks were found in the document, return the whole document as a single section
  if (sections.length === 0 && markdownDoc.trim()) {
    sections.push({
      index: 0,
      id: 'full-doc',
      type: 'document',
      title: 'Full Document',
      meta: {},
      markdown: markdownDoc.trim(),
      wordCount: countWords(markdownDoc.trim()),
    });
  }

  return sections;
}

function countWords(str: string): number {
  return str.split(/\s+/).filter(Boolean).length;
}

/**
 * Helper to get user-friendly badges and visual styling for each regulatory section type
 */
export function getSectionStyle(type: string): {
  label: string;
  badgeClass: string;
} {
  const norm = type.toLowerCase();

  if (norm === 'doc_header' || norm === 'document') {
    return {
      label: 'Overview',
      badgeClass: 'bg-slate-800 text-slate-300 border-slate-700',
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
