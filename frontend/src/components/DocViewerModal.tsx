/**
 * Modal to view full markdown document, with interactive section breakdown,
 * client-side text similarity search, and smart section highlighting.
 */

import React, { useMemo, useState, useEffect, useRef } from 'react';
import { 
  X, 
  Copy, 
  Check, 
  FileText, 
  ExternalLink, 
  ChevronDown, 
  ChevronUp, 
  Search, 
  Layers, 
  List, 
  Sparkles,
  ArrowUp,
  ArrowDown,
  ArrowDownUp,
  SlidersHorizontal,
  Eye,
  Database
} from 'lucide-react';
import { SearchDocResponse, DocSection } from '../types';
import { marked } from 'marked';
import { parseDocumentSections, getSectionStyle } from '../utils/sectionParser';
import { 
  calculateDocumentSimilarity, 
  highlightHtmlContent, 
  SectionSimilarityResult 
} from '../utils/documentSimilarity';
import { getDocumentMarkdown } from '../services/apiClient';

interface DocViewerModalProps {
  doc: SearchDocResponse | null;
  onClose: () => void;
  onAskAboutChunk?: (chunkId: string, docTitle: string) => void;
  onBookmarkSection?: (section: DocSection) => void;
  onSearchSection?: (sectionMarkdown: string) => void;
}

export const DocViewerModal: React.FC<DocViewerModalProps> = ({
  doc,
  onClose,
  onAskAboutChunk,
  onBookmarkSection,
  onSearchSection,
}) => {
  const [copied, setCopied] = useState(false);
  const [copiedSectionId, setCopiedSectionId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'sections' | 'continuous'>('sections');
  
  // Filtering & Similarity Search States
  const [similarityQuery, setSimilarityQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [minThreshold, setMinThreshold] = useState<number>(15);
  const [sortBySimilarity, setSortBySimilarity] = useState<boolean>(false);
  const [autoExpandMatches, setAutoExpandMatches] = useState<boolean>(true);
  const [currentMatchIndex, setCurrentMatchIndex] = useState<number>(0);
  
  // Track open/collapsed state of sections
  const [openSectionIds, setOpenSectionIds] = useState<Record<string, boolean>>({});

  // Fetch full markdown if it's missing (e.g., from a lightweight search citation)
  const [fullDocMarkdown, setFullDocMarkdown] = useState<string | null>(doc?.markdown_doc || null);
  const [loadingDoc, setLoadingDoc] = useState(false);

  useEffect(() => {
    if (doc && !doc.markdown_doc && !fullDocMarkdown && !loadingDoc) {
      setLoadingDoc(true);
      getDocumentMarkdown(doc.document_id)
        .then((res) => {
          setFullDocMarkdown(res.markdown_doc);
        })
        .catch(err => {
          console.error("Failed to load document markdown", err);
        })
        .finally(() => {
          setLoadingDoc(false);
        });
    } else if (doc && doc.markdown_doc) {
      setFullDocMarkdown(doc.markdown_doc);
    }
  }, [doc]);

  // Container ref for scrolling into view
  const contentContainerRef = useRef<HTMLDivElement>(null);

  // Parse structured sections
  const sections = useMemo<DocSection[]>(() => {
    if (!fullDocMarkdown) return [];
    return parseDocumentSections(fullDocMarkdown);
  }, [fullDocMarkdown]);

  // Unique section types for filtering chips
  const sectionTypes = useMemo(() => {
    const types = new Set<string>();
    sections.forEach(s => {
      if (s.type && s.type !== 'doc_header') {
        types.add(s.type);
      }
    });
    return Array.from(types);
  }, [sections]);

  // Compute similarity scores for all sections
  const similarityResults = useMemo<Map<string, SectionSimilarityResult>>(() => {
    if (!similarityQuery.trim()) {
      return new Map();
    }
    return calculateDocumentSimilarity(similarityQuery, sections, minThreshold);
  }, [similarityQuery, sections, minThreshold]);

  // Sections that have a similarity match
  const matchingSections = useMemo(() => {
    if (!similarityQuery.trim()) return [];
    return sections.filter(sec => {
      const res = similarityResults.get(sec.id);
      return res && res.isMatch;
    });
  }, [sections, similarityResults, similarityQuery]);

  // Total occurrences of query terms in the document
  const totalOccurrences = useMemo(() => {
    let total = 0;
    similarityResults.forEach(res => {
      if (res.isMatch) total += res.matchCount;
    });
    return total;
  }, [similarityResults]);

  // Auto-expand matching sections when similarity query changes
  useEffect(() => {
    if (similarityQuery.trim() && autoExpandMatches && matchingSections.length > 0) {
      setOpenSectionIds(prev => {
        const next = { ...prev };
        matchingSections.forEach(s => {
          next[s.id] = true;
        });
        return next;
      });
    }
  }, [similarityQuery, autoExpandMatches, matchingSections]);

  // Reset match navigation when query changes
  useEffect(() => {
    setCurrentMatchIndex(0);
  }, [similarityQuery]);

  // Filtered & Sorted sections for display
  const displayedSections = useMemo(() => {
    let result = sections.filter(sec => {
      // Type filter
      if (typeFilter !== 'all' && sec.type !== typeFilter) {
        return false;
      }
      return true;
    });

    // If sorting by similarity when query is active
    if (similarityQuery.trim() && sortBySimilarity) {
      result = [...result].sort((a, b) => {
        const scoreA = similarityResults.get(a.id)?.score || 0;
        const scoreB = similarityResults.get(b.id)?.score || 0;
        return scoreB - scoreA;
      });
    }

    return result;
  }, [sections, typeFilter, similarityQuery, sortBySimilarity, similarityResults]);

  // Rendered full continuous markdown (fallback or continuous mode)
  const renderedContinuousMarkdown = useMemo(() => {
    if (!fullDocMarkdown) return '';
    try {
      const parsed = marked.parse(fullDocMarkdown) as string;
      if (similarityQuery.trim()) {
        return highlightHtmlContent(parsed, similarityQuery);
      }
      return parsed;
    } catch (e) {
      return `<pre class="whitespace-pre-wrap">${fullDocMarkdown}</pre>`;
    }
  }, [fullDocMarkdown, similarityQuery]);

  // Check if a section contains the matched search chunk from the original query
  const isSectionMatchedChunk = (sec: DocSection): boolean => {
    if (!doc?.text) return false;
    const snippet = doc.text.slice(0, 60).toLowerCase();
    const matchesSnippet = sec.markdown.toLowerCase().includes(snippet);
    const matchesChunkId = Boolean(doc.chunk_id && sec.id === doc.chunk_id);
    return matchesSnippet || matchesChunkId;
  };

  // Expand / Collapse All handlers
  const handleExpandAll = () => {
    const newOpenState: Record<string, boolean> = {};
    sections.forEach(s => {
      newOpenState[s.id] = true;
    });
    setOpenSectionIds(newOpenState);
  };

  const handleCollapseAll = () => {
    setOpenSectionIds({});
  };

  const toggleSection = (id: string) => {
    setOpenSectionIds(prev => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  // Scroll to a matching section by index
  const scrollToMatch = (index: number) => {
    if (matchingSections.length === 0) return;
    const boundedIndex = (index + matchingSections.length) % matchingSections.length;
    setCurrentMatchIndex(boundedIndex);
    const targetSection = matchingSections[boundedIndex];

    // Ensure it's expanded
    setOpenSectionIds(prev => ({
      ...prev,
      [targetSection.id]: true,
    }));

    // Scroll element into view
    setTimeout(() => {
      const el = document.getElementById(`sec-card-${targetSection.id}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 50);
  };

  const handleCopySection = (sec: DocSection, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(sec.markdown);
    setCopiedSectionId(sec.id);
    setTimeout(() => setCopiedSectionId(null), 2000);
  };

  const handleCopyDoc = () => {
    if (!doc && !fullDocMarkdown) return;
    navigator.clipboard.writeText(fullDocMarkdown || doc?.text || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!doc) return null;

  const hasMultipleSections = sections.length > 1;
  const isSimilarityActive = Boolean(similarityQuery.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative flex flex-col w-full max-w-5xl max-h-[94vh] bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 bg-slate-900/95 shrink-0">
          <div className="flex items-center gap-3 min-w-0 pr-4">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20 shrink-0">
              <FileText className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs text-slate-400 flex-wrap">
                <span className="font-mono text-sky-400 uppercase tracking-wider">{doc.source}</span>
                <span aria-hidden="true">·</span>
                <span className="font-mono">{doc.document_id}</span>
                <span aria-hidden="true">·</span>
                <span className="font-mono text-emerald-400">Score: {(doc.score * 100).toFixed(1)}%</span>
                {hasMultipleSections && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="px-1.5 py-0.2 font-mono text-[10px] bg-slate-800 text-sky-300 rounded border border-slate-700">
                      {sections.length} Sections
                    </span>
                  </>
                )}
              </div>
              <h2 className="text-base font-semibold text-slate-100 truncate">
                {doc.path[doc.path.length - 1] || doc.chunk_id}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* View Mode Toggle Button */}
            {hasMultipleSections && (
              <div className="flex items-center p-0.5 bg-slate-950 border border-slate-800 rounded-lg text-xs">
                <button
                  onClick={() => setViewMode('sections')}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                    viewMode === 'sections' 
                      ? 'bg-sky-600 text-white font-medium shadow-sm' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="View segmented by sections"
                >
                  <Layers className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Sections</span>
                </button>
                <button
                  onClick={() => setViewMode('continuous')}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                    viewMode === 'continuous' 
                      ? 'bg-sky-600 text-white font-medium shadow-sm' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="View as continuous document"
                >
                  <List className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Continuous</span>
                </button>
              </div>
            )}

            {onAskAboutChunk && (
              <button
                onClick={() => {
                  onAskAboutChunk(doc.chunk_id, doc.path[doc.path.length - 1] || doc.chunk_id);
                  onClose();
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-sky-300 bg-sky-950/60 hover:bg-sky-900/60 border border-sky-800/60 rounded-md transition-colors whitespace-nowrap"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Ask LLM</span>
              </button>
            )}

            <button
              onClick={handleCopyDoc}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-md transition-colors whitespace-nowrap"
              title="Copy markdown text"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{copied ? 'Copied' : 'Copy Doc'}</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
              aria-label="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Path Breadcrumbs */}
        <div className="px-5 py-2 bg-slate-950/60 border-b border-slate-800/80 text-xs text-slate-400 overflow-x-auto whitespace-nowrap shrink-0 flex items-center">
          <span className="text-slate-500 mr-2 shrink-0">Path:</span>
          {doc.path.map((segment, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && <span className="mx-1 text-slate-600">/</span>}
              <span className={idx === doc.path.length - 1 ? 'text-slate-200 font-medium' : 'text-slate-400'}>
                {segment}
              </span>
            </React.Fragment>
          ))}
        </div>

        {/* CLIENT-SIDE SIMILARITY SEARCH & HIGHLIGHTING BAR */}
        <div className="px-5 py-3 bg-slate-950/90 border-b border-slate-800 shrink-0 space-y-2.5">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-sky-400" />
              <input
                type="text"
                value={similarityQuery}
                onChange={(e) => setSimilarityQuery(e.target.value)}
                placeholder="Search document sections (client-side text similarity & highlighting)..."
                className="w-full pl-9 pr-9 py-1.5 text-xs text-slate-200 bg-slate-900 border border-slate-700/80 rounded-lg focus:outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-400/40 placeholder:text-slate-500 transition-all shadow-inner"
              />
              {similarityQuery && (
                <button
                  onClick={() => setSimilarityQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
                  title="Clear similarity search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Similarity Match Navigation & Controls */}
            {isSimilarityActive && (
              <div className="flex items-center gap-2 shrink-0">
                {/* Match Counter Badge */}
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded-lg font-medium">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                  <span>
                    {matchingSections.length} sections ({totalOccurrences} hits)
                  </span>
                </div>

                {/* Match Stepper Buttons */}
                {matchingSections.length > 0 && viewMode === 'sections' && (
                  <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5">
                    <button
                      onClick={() => scrollToMatch(currentMatchIndex - 1)}
                      className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
                      title="Previous matching section"
                    >
                      <ArrowUp className="w-3.5 h-3.5" />
                    </button>
                    <span className="text-[11px] font-mono text-slate-400 px-1.5">
                      {currentMatchIndex + 1}/{matchingSections.length}
                    </span>
                    <button
                      onClick={() => scrollToMatch(currentMatchIndex + 1)}
                      className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
                      title="Next matching section"
                    >
                      <ArrowDown className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Secondary Controls Bar (Threshold, Sort, Auto-expand) */}
          {hasMultipleSections && (
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs pt-0.5">
              <div className="flex items-center gap-3 text-slate-400 flex-wrap">
                {/* Sensitivity Threshold */}
                {isSimilarityActive && (
                  <div className="flex items-center gap-1.5 bg-slate-900/80 px-2 py-1 rounded-md border border-slate-800">
                    <SlidersHorizontal className="w-3 h-3 text-slate-500" />
                    <span className="text-[11px] text-slate-400">Min Score:</span>
                    <button
                      onClick={() => setMinThreshold(10)}
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors ${
                        minThreshold === 10 ? 'bg-sky-500/20 text-sky-300' : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      10%
                    </button>
                    <button
                      onClick={() => setMinThreshold(25)}
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors ${
                        minThreshold === 25 ? 'bg-sky-500/20 text-sky-300' : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      25%
                    </button>
                    <button
                      onClick={() => setMinThreshold(50)}
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors ${
                        minThreshold === 50 ? 'bg-sky-500/20 text-sky-300' : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      50%
                    </button>
                  </div>
                )}

                {/* Sort by Similarity Toggle */}
                {isSimilarityActive && viewMode === 'sections' && (
                  <button
                    onClick={() => setSortBySimilarity(!sortBySimilarity)}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md border transition-colors ${
                      sortBySimilarity
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-medium'
                        : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200'
                    }`}
                    title="Toggle sorting sections by similarity relevance"
                  >
                    <ArrowDownUp className="w-3 h-3" />
                    <span>Sort by Relevance</span>
                  </button>
                )}

                {/* Auto Expand Matches Toggle */}
                {isSimilarityActive && viewMode === 'sections' && (
                  <label className="inline-flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-slate-200">
                    <input
                      type="checkbox"
                      checked={autoExpandMatches}
                      onChange={(e) => setAutoExpandMatches(e.target.checked)}
                      className="rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-0 focus:ring-offset-0 w-3 h-3"
                    />
                    <span className="text-[11px]">Auto-expand matches</span>
                  </label>
                )}
              </div>

              {/* Expand / Collapse All for standard sections */}
              {viewMode === 'sections' && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleExpandAll}
                    className="px-2 py-1 text-[11px] text-slate-300 bg-slate-800/60 hover:bg-slate-800 border border-slate-700/80 rounded transition-colors whitespace-nowrap"
                  >
                    Expand All
                  </button>
                  <button
                    onClick={handleCollapseAll}
                    className="px-2 py-1 text-[11px] text-slate-300 bg-slate-800/60 hover:bg-slate-800 border border-slate-700/80 rounded transition-colors whitespace-nowrap"
                  >
                    Collapse All
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Section Category Filter Chips */}
          {hasMultipleSections && viewMode === 'sections' && sectionTypes.length > 1 && (
            <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 text-xs">
              <span className="text-slate-500 text-[11px] mr-1">Filter Type:</span>
              <button
                onClick={() => setTypeFilter('all')}
                className={`px-2 py-0.5 rounded-full border text-[11px] transition-colors whitespace-nowrap ${
                  typeFilter === 'all'
                    ? 'bg-sky-500/20 text-sky-300 border-sky-500/50 font-medium'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                }`}
              >
                All ({sections.length})
              </button>
              {sectionTypes.map((type) => {
                const count = sections.filter(s => s.type === type).length;
                const style = getSectionStyle(type);
                return (
                  <button
                    key={type}
                    onClick={() => setTypeFilter(type)}
                    className={`px-2 py-0.5 rounded-full border text-[11px] transition-colors whitespace-nowrap ${
                      typeFilter === type
                        ? 'bg-sky-500/20 text-sky-300 border-sky-500/50 font-medium'
                        : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    {style.label} ({count})
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Modal Scrollable Content Container */}
        <div ref={contentContainerRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
          {/* Matched Search Chunk Preview Box from Search query */}
          <div className="p-4 bg-sky-950/20 border border-sky-800/40 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-sky-400 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                Original Query Chunk ({doc.chunk_id})
              </span>
            </div>
            <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed font-sans">
              {doc.text}
            </p>
          </div>

          {/* Render Sections View or Continuous View */}
          {hasMultipleSections && viewMode === 'sections' ? (
            <div className="space-y-3">
              {displayedSections.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-sm border border-dashed border-slate-800 rounded-xl">
                  No sections match the current category filter.
                </div>
              ) : (
                displayedSections.map((sec) => {
                  const isOpen = openSectionIds[sec.id] ?? false;
                  const isChunkMatched = isSectionMatchedChunk(sec);
                  const style = getSectionStyle(sec.type);
                  
                  // Similarity score for this section
                  const simResult = similarityResults.get(sec.id);
                  const simScore = simResult?.score || 0;
                  const isSimMatch = simResult?.isMatch ?? false;

                  // Highlighting border and styling priority:
                  // 1. High similarity match (score >= 60) -> Amber glowing border & ring
                  // 2. Medium similarity match (score >= 25) -> Sky border & ring
                  // 3. Matched search chunk from API -> Sky cyan border
                  // 4. Default -> Slate card
                  let borderClass = 'border-slate-800 bg-slate-900/60 hover:border-slate-700/80';
                  let containerExtraClass = '';

                  if (isSimilarityActive) {
                    if (simScore >= 60) {
                      borderClass = 'border-amber-500/80 bg-amber-950/20 ring-2 ring-amber-500/40 shadow-lg shadow-amber-950/40';
                    } else if (isSimMatch) {
                      borderClass = 'border-sky-500/70 bg-sky-950/20 ring-1 ring-sky-500/30';
                    } else {
                      containerExtraClass = 'opacity-65 hover:opacity-100 transition-opacity';
                    }
                  } else if (isChunkMatched) {
                    borderClass = 'bg-slate-900/90 border-sky-500/60 ring-1 ring-sky-500/30';
                  }

                  // Render individual section markdown with in-text highlighting
                  let renderedSecHtml = '';
                  try {
                    const parsedHtml = marked.parse(sec.markdown) as string;
                    renderedSecHtml = isSimilarityActive
                      ? highlightHtmlContent(parsedHtml, similarityQuery)
                      : parsedHtml;
                  } catch (e) {
                    renderedSecHtml = `<pre>${sec.markdown}</pre>`;
                  }

                  return (
                    <div
                      key={sec.id}
                      id={`sec-card-${sec.id}`}
                      className={`border rounded-xl transition-all duration-200 overflow-hidden ${borderClass} ${containerExtraClass}`}
                    >
                      {/* Section Card Header */}
                      <div
                        onClick={() => toggleSection(sec.id)}
                        className="flex items-center justify-between px-4 py-3 cursor-pointer select-none gap-3 hover:bg-slate-800/40 transition-colors"
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <button
                            type="button"
                            className="p-1 text-slate-400 hover:text-slate-200 transition-colors shrink-0"
                          >
                            {isOpen ? (
                              <ChevronUp className="w-4 h-4 text-sky-400" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>

                          {/* Section Type Badge */}
                          <span className={`px-2 py-0.5 text-[11px] font-medium border rounded-md shrink-0 ${style.badgeClass}`}>
                            {style.label}
                          </span>

                          {/* SIMILARITY SCORE BADGE */}
                          {isSimilarityActive && isSimMatch && (
                            <span 
                              className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[11px] font-mono font-semibold rounded-md border shrink-0 ${
                                simScore >= 60
                                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-sm'
                                  : 'bg-sky-500/20 text-sky-300 border-sky-500/40'
                              }`}
                              title={`Similarity score: ${simScore}% based on query '${similarityQuery}'`}
                            >
                              <Sparkles className="w-3 h-3 text-amber-400" />
                              <span>{simScore}% Match</span>
                            </span>
                          )}

                          {/* Matched Search Result Chunk from API */}
                          {!isSimilarityActive && isChunkMatched && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase bg-sky-500/20 text-sky-300 border border-sky-500/40 rounded-md shrink-0">
                              <Eye className="w-3 h-3" />
                              Matched Result
                            </span>
                          )}

                          {/* Section Title */}
                          <h4 className="text-sm font-semibold text-slate-200 truncate flex-1">
                            {sec.title}
                          </h4>
                        </div>

                        {/* Card Right Actions */}
                        <div className="flex items-center gap-2 shrink-0">
                          {isSimilarityActive && simResult && simResult.matchCount > 0 && (
                            <span className="text-[11px] font-mono text-amber-400/90 hidden sm:inline">
                              {simResult.matchCount} hit{simResult.matchCount > 1 ? 's' : ''}
                            </span>
                          )}

                          <span className="text-[11px] text-slate-500 font-mono hidden md:inline">
                            {sec.wordCount} words
                          </span>

                          {onSearchSection && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onSearchSection(sec.markdown.slice(0, 500)); // use up to 500 chars as query
                                onClose();
                              }}
                              className="p-1.5 text-xs text-sky-400 hover:text-sky-300 hover:bg-sky-950/40 rounded-md transition-colors"
                              title="Search related topics based on this section"
                            >
                              <Search className="w-3.5 h-3.5" />
                            </button>
                          )}

                          {onAskAboutChunk && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onAskAboutChunk(sec.id, sec.title);
                                onClose();
                              }}
                              className="p-1.5 text-xs text-sky-400 hover:text-sky-300 hover:bg-sky-950/40 rounded-md transition-colors"
                              title="Ask LLM about this section"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </button>
                          )}

                          {onBookmarkSection && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onBookmarkSection(sec);
                                setCopiedSectionId(`bm-${sec.id}`);
                                setTimeout(() => setCopiedSectionId(null), 2000);
                              }}
                              className="p-1.5 text-xs text-emerald-400 hover:text-emerald-300 hover:bg-emerald-950/40 rounded-md transition-colors"
                              title="Bookmark section to active chat"
                            >
                              {copiedSectionId === `bm-${sec.id}` ? (
                                <Check className="w-3.5 h-3.5" />
                              ) : (
                                <Database className="w-3.5 h-3.5" />
                              )}
                            </button>
                          )}

                          <button
                            onClick={(e) => handleCopySection(sec, e)}
                            className="p-1.5 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
                            title="Copy section markdown"
                          >
                            {copiedSectionId === sec.id ? (
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Collapsible Section Body */}
                      {isOpen && (
                        <div className="px-5 py-4 border-t border-slate-800/80 bg-slate-950/40">
                          <div 
                            className="prose prose-invert prose-slate max-w-none text-sm leading-relaxed 
                              prose-headings:text-slate-100 prose-headings:font-semibold 
                              prose-h1:text-lg prose-h2:text-base prose-h3:text-sm prose-h4:text-xs prose-h4:uppercase prose-h4:tracking-wider prose-h4:text-sky-400
                              prose-p:text-slate-300 prose-p:my-2
                              prose-ul:text-slate-300 prose-li:my-1
                              prose-strong:text-slate-100 prose-code:text-sky-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                              prose-blockquote:border-sky-500/50 prose-blockquote:bg-sky-950/20 prose-blockquote:text-slate-300 prose-blockquote:py-1 prose-blockquote:px-4"
                            dangerouslySetInnerHTML={{ __html: renderedSecHtml }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          ) : (
            /* Continuous View */
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Full Regulatory Document Representation
                </h3>
                {hasMultipleSections && (
                  <span className="text-xs text-slate-500">
                    Showing continuous view · {sections.length} sections embedded
                  </span>
                )}
              </div>
              {loadingDoc ? (
                <div className="flex items-center gap-2 text-slate-400 py-10 px-4">
                  <Sparkles className="w-4 h-4 animate-spin text-emerald-500" />
                  Loading full document content...
                </div>
              ) : (
                <div 
                  className="prose prose-invert prose-slate max-w-none text-sm leading-relaxed 
                    prose-headings:text-slate-100 prose-headings:font-semibold 
                    prose-h1:text-lg prose-h2:text-base prose-h3:text-sm prose-h4:text-xs prose-h4:uppercase prose-h4:tracking-wider prose-h4:text-sky-400
                    prose-p:text-slate-300 prose-p:my-2
                    prose-ul:text-slate-300 prose-li:my-1
                    prose-strong:text-slate-100 prose-code:text-sky-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                    prose-blockquote:border-sky-500/50 prose-blockquote:bg-sky-950/20 prose-blockquote:text-slate-300 prose-blockquote:py-1 prose-blockquote:px-4"
                  dangerouslySetInnerHTML={{ __html: renderedContinuousMarkdown }}
                />
              )}
            </div>
          )}

          {/* Document Metadata Block */}
          {doc.metadata && Object.keys(doc.metadata).length > 0 && (
            <div className="pt-4 border-t border-slate-800">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Document Metadata
              </h4>
              <div className="bg-slate-950/60 rounded-lg p-3 border border-slate-800 text-xs font-mono text-slate-300 space-y-1">
                {Object.entries(doc.metadata).map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <span className="text-slate-500 min-w-32">{k}:</span>
                    <span className="text-slate-300 break-all">
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
