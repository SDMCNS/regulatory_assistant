/**
 * RegulationsWorkspace Component
 * 
 * Comprehensive workspace allowing users to:
 * 1. Browse and search the regulation catalog at the title/document level with local cache indicators.
 * 2. Select multiple regulations and download/cache them for offline in-app viewing via IndexedDB.
 * 3. In a dedicated workspace, execute high-speed SQLite FTS5 search across the selected documents.
 * 4. Interactively visualize where and how the search concept overlaps across documents
 *    with a side-by-side multi-column comparison matrix, overlap metrics, and direct section inspection.
 * 5. High-Value Client-Side Features:
 *    - "Requirement Lens": Normative modal verb analyzer & highlighter (SHALL, SHOULD, MAY, PROHIBITED).
 *    - In-Memory Instant Chunk Filter (zero-latency client-side search across loaded sections).
 *    - Cross-Regulation Shared Concept Matrix (analyzing term co-occurrence across documents).
 *    - Compliance Working Dossier & Pinned Shelf (saving chunks, adding reviewer notes, and exporting Markdown).
 *    - Word-by-Word Diff Algorithm & Text Alignment in the dual chunk comparison drawer.
 *    - Direct integration with Deep Research consulted sources.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  BookOpen,
  Download,
  CheckSquare,
  Square,
  Layers,
  ArrowRight,
  RefreshCw,
  Eye,
  SlidersHorizontal,
  ExternalLink,
  Split,
  Sparkles,
  FileText,
  ShieldAlert,
  ShieldCheck,
  X,
  FileCheck,
  ChevronDown,
  ChevronUp,
  Columns,
  ListFilter,
  Check,
  Copy,
  MessageSquareQuote,
  Filter,
  Trash2,
  Bookmark,
  BookmarkCheck,
  Scale,
  FileSpreadsheet,
  Tag,
  HardDrive,
  Cpu,
  CheckCircle2
} from 'lucide-react';
import {
  RegulationItem,
  DownloadedDocItem,
  WorkspaceChunkMatch,
  WorkspaceFtsResponse,
  SearchDocResponse,
  AppSettings
} from '../types';
import {
  getRegulationsCatalog,
  batchDownloadRegulations,
  searchWorkspaceFts,
  saveRegulationsToLocalCache,
  downloadRegulationsAsJsonFile,
  getCachedRegulationDocIds
} from '../services/apiClient';

interface DossierItem {
  chunk_id: string;
  document_id: string;
  document_title: string;
  section_title: string;
  text: string;
  userNote: string;
  pinnedAt: number;
}

interface RegulationsWorkspaceProps {
  settings: AppSettings;
  onViewDoc: (doc: SearchDocResponse) => void;
  onAskAboutChunk?: (chunkId: string, title: string) => void;
  onSendToAssistant?: (prompt: string, chunkIds: string[]) => void;
  initialSelectedDocIds?: string[];
  initialQuery?: string;
  onClearInitialContext?: () => void;
}

const DOSSIER_STORAGE_KEY = 'aerolex_compliance_dossier_v1';

// -------------------------------------------------------------
// Normative Legal Verb Analyzers
// -------------------------------------------------------------
const MANDATE_REGEX = /\b(shall|must|is required to|are required to|shall ensure)\b/gi;
const PROHIBITION_REGEX = /\b(shall not|must not|may not|prohibited|is prohibited)\b/gi;
const RECOMMENDATION_REGEX = /\b(should|is recommended to|are recommended to)\b/gi;
const GUIDANCE_REGEX = /\b(may|can|acceptable means|guidance material)\b/gi;

function analyzeRequirements(text: string | undefined | null) {
  if (!text || typeof text !== 'string') {
    return { mandates: 0, prohibitions: 0, recommendations: 0, guidance: 0 };
  }
  const mandates = (text.match(MANDATE_REGEX) || []).length;
  const prohibitions = (text.match(PROHIBITION_REGEX) || []).length;
  const recommendations = (text.match(RECOMMENDATION_REGEX) || []).length;
  const guidance = (text.match(GUIDANCE_REGEX) || []).length;
  return { mandates, prohibitions, recommendations, guidance };
}

// -------------------------------------------------------------
// Word Diff Helper for Dual Chunk Comparison
// -------------------------------------------------------------
function computeWordDiff(textA: string | undefined | null, textB: string | undefined | null) {
  const wordsA = (textA || '').split(/\s+/).filter(Boolean);
  const wordsB = (textB || '').split(/\s+/).filter(Boolean);
  const clean = (w: string) => w.toLowerCase().replace(/[^a-z0-9]/g, '');
  
  const setA = new Set(wordsA.map(clean).filter(Boolean));
  const setB = new Set(wordsB.map(clean).filter(Boolean));
  
  let intersection = 0;
  setA.forEach(w => {
    if (setB.has(w)) intersection++;
  });
  const union = new Set([...setA, ...setB]).size;
  const similarityScore = union > 0 ? Math.round((intersection / union) * 100) : 0;

  return { wordsA, wordsB, setA, setB, similarityScore, clean };
}

export const RegulationsWorkspace: React.FC<RegulationsWorkspaceProps> = ({
  settings,
  onViewDoc,
  onAskAboutChunk,
  onSendToAssistant,
  initialSelectedDocIds,
  initialQuery,
  onClearInitialContext
}) => {
  // Navigation View: 'catalog' | 'workspace'
  const [activeView, setActiveView] = useState<'catalog' | 'workspace'>('catalog');

  // -------------------------------------------------------------
  // Catalog State
  // -------------------------------------------------------------
  const [catalog, setCatalog] = useState<RegulationItem[]>([]);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState<boolean>(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  // Filters & Search
  const [titleQuery, setTitleQuery] = useState<string>('');
  const [originFilter, setOriginFilter] = useState<'all' | 'easa' | 'eu'>('all');
  const [sortBy, setSortBy] = useState<'chunks' | 'title' | 'date'>('chunks');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Multi-Selection
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());

  // Download / Cache State
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [downloadProgress, setDownloadProgress] = useState<string | null>(null);
  const [downloadSuccessMessage, setDownloadSuccessMessage] = useState<string | null>(null);
  const [cachedDocIds, setCachedDocIds] = useState<Set<string>>(new Set());

  // -------------------------------------------------------------
  // Dedicated Workspace State
  // -------------------------------------------------------------
  const [workspaceDocIds, setWorkspaceDocIds] = useState<string[]>([]);
  const [ftsQuery, setFtsQuery] = useState<string>('');
  const [isSearchingFts, setIsSearchingFts] = useState<boolean>(false);
  const [ftsResults, setFtsResults] = useState<WorkspaceFtsResponse | null>(null);
  const [ftsError, setFtsError] = useState<string | null>(null);

  // Workspace Comparison Mode: 'grid' (multi-column) | 'list'
  const [comparisonMode, setComparisonMode] = useState<'grid' | 'list'>('grid');

  // Client-Side Enhancements State
  const [instantFilter, setInstantFilter] = useState<string>('');
  const [isRequirementLensActive, setIsRequirementLensActive] = useState<boolean>(false);
  const [requirementFilter, setRequirementFilter] = useState<'all' | 'mandate' | 'prohibition' | 'recommendation' | 'guidance'>('all');

  // Side-by-Side Chunk Comparison Drawer
  const [compareChunkA, setCompareChunkA] = useState<WorkspaceChunkMatch | null>(null);
  const [compareChunkB, setCompareChunkB] = useState<WorkspaceChunkMatch | null>(null);
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [diffViewMode, setDiffViewMode] = useState<'side-by-side' | 'word-diff'>('side-by-side');

  // Compliance Working Dossier (Pinned Chunks)
  const [dossier, setDossier] = useState<DossierItem[]>(() => {
    try {
      const raw = localStorage.getItem(DOSSIER_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [isDossierOpen, setIsDossierOpen] = useState<boolean>(false);

  // -------------------------------------------------------------
  // Refresh IndexedDB Cached Doc IDs
  // -------------------------------------------------------------
  const refreshCachedDocIds = useCallback(async () => {
    try {
      const ids = await getCachedRegulationDocIds();
      setCachedDocIds(ids);
    } catch (e) {
      console.warn('Failed to inspect cached keys', e);
    }
  }, []);

  useEffect(() => {
    refreshCachedDocIds();
  }, [refreshCachedDocIds]);

  // -------------------------------------------------------------
  // Load Catalog
  // -------------------------------------------------------------
  const fetchCatalog = useCallback(async () => {
    setIsLoadingCatalog(true);
    setCatalogError(null);
    try {
      const res = await getRegulationsCatalog({
        query: titleQuery,
        origin: originFilter,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit: 1500,
      }, settings);
      setCatalog(res.regulations || []);
    } catch (err: any) {
      setCatalogError(err.message || 'Failed to load regulations catalog');
    } finally {
      setIsLoadingCatalog(false);
    }
  }, [titleQuery, originFilter, sortBy, sortOrder, settings]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchCatalog();
    }, 150);
    return () => clearTimeout(timer);
  }, [fetchCatalog]);

  // Map of loaded catalog items for quick title lookup
  const catalogMap = useMemo(() => {
    const map = new Map<string, RegulationItem>();
    catalog.forEach(item => map.set(item.document_id, item));
    return map;
  }, [catalog]);

  // -------------------------------------------------------------
  // Selection Handlers
  // -------------------------------------------------------------
  const toggleSelectDoc = (docId: string) => {
    setSelectedDocIds(prev => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const handleSelectAllFiltered = () => {
    setSelectedDocIds(new Set(catalog.map(c => c.document_id)));
  };

  const handleClearSelection = () => {
    setSelectedDocIds(new Set());
  };

  // -------------------------------------------------------------
  // Download & In-App Caching Handlers
  // -------------------------------------------------------------
  const handleDownloadSelected = async (exportJsonFile = false) => {
    if (selectedDocIds.size === 0) return;
    setIsDownloading(true);
    setDownloadProgress(`Preparing download of ${selectedDocIds.size} regulations...`);
    setDownloadSuccessMessage(null);

    try {
      const docIdsArray = Array.from(selectedDocIds);
      setDownloadProgress(`Fetching markdown representations from API (${docIdsArray.length} items)...`);
      const res = await batchDownloadRegulations(docIdsArray, settings);

      setDownloadProgress(`Saving ${res.count} documents to local in-app cache (IndexedDB)...`);
      const cachedCount = await saveRegulationsToLocalCache(res.documents);
      await refreshCachedDocIds();

      if (exportJsonFile) {
        setDownloadProgress(`Exporting offline JSON bundle...`);
        downloadRegulationsAsJsonFile(res.documents);
      }

      setDownloadSuccessMessage(
        `Successfully downloaded and cached ${cachedCount} regulation(s) for local in-app viewing!`
      );
      setTimeout(() => setDownloadSuccessMessage(null), 5000);
    } catch (err: any) {
      alert(`Download failed: ${err.message}`);
    } finally {
      setIsDownloading(false);
      setDownloadProgress(null);
    }
  };

  // -------------------------------------------------------------
  // Enter Workspace with Selected Regulations
  // -------------------------------------------------------------
  const handleOpenWorkspaceWithSelected = (docsToUse?: string[]) => {
    const docs = docsToUse || Array.from(selectedDocIds);
    if (docs.length === 0) return;
    setWorkspaceDocIds(docs);
    setActiveView('workspace');
    setFtsResults(null);
  };

  const handleRemoveFromWorkspace = (docId: string) => {
    setWorkspaceDocIds(prev => prev.filter(id => id !== docId));
  };

  // -------------------------------------------------------------
  // Workspace FTS Overlap Search Execution
  // -------------------------------------------------------------
  const executeWorkspaceSearch = useCallback(async (queryToUse: string, docsToUse: string[]) => {
    if (!queryToUse.trim() || docsToUse.length === 0) return;

    setIsSearchingFts(true);
    setFtsError(null);

    try {
      const res = await searchWorkspaceFts(
        queryToUse.trim(),
        docsToUse,
        10, // top_k_per_doc
        60, // total_top_k
        settings
      );
      setFtsResults(res);
    } catch (err: any) {
      setFtsError(err.message || 'Failed to search workspace regulations');
    } finally {
      setIsSearchingFts(false);
    }
  }, [settings]);

  const handleExecuteWorkspaceFts = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    executeWorkspaceSearch(ftsQuery, workspaceDocIds);
  };

  // Handle incoming props from Deep Research or external triggers
  const handledInitialContextRef = React.useRef<string>('');

  useEffect(() => {
    if (initialSelectedDocIds && initialSelectedDocIds.length > 0) {
      const uniqueDocs = Array.from(new Set(initialSelectedDocIds.filter(Boolean)));
      const key = `${uniqueDocs.join('|')}::${initialQuery || ''}`;
      if (handledInitialContextRef.current === key) return;
      handledInitialContextRef.current = key;

      setSelectedDocIds(new Set(uniqueDocs));
      setWorkspaceDocIds(uniqueDocs);
      setActiveView('workspace');

      if (initialQuery) {
        setFtsQuery(initialQuery);
        executeWorkspaceSearch(initialQuery, uniqueDocs);
      }
      if (onClearInitialContext) {
        onClearInitialContext();
      }
    }
  }, [initialSelectedDocIds, initialQuery, executeWorkspaceSearch, onClearInitialContext]);

  // -------------------------------------------------------------
  // View Document in DocViewerModal
  // -------------------------------------------------------------
  const handleOpenDocViewer = (documentId: string, queryForViewer?: string) => {
    const cat = catalogMap.get(documentId);
    const docResponse: SearchDocResponse = {
      chunk_id: '',
      score: 1.0,
      source: cat?.origin === 'easa' ? 'EASA Easy Access Rules' : 'EU Formex',
      document_id: documentId,
      path: [cat?.title || documentId],
      text: '',
      metadata: cat?.metadata || {},
      markdown_doc: '' // DocViewerModal will automatically fetch or read from IndexedDB cache
    };
    onViewDoc(docResponse);
  };

  // -------------------------------------------------------------
  // Client-Side Cross-Regulation Shared Concept Matrix
  // -------------------------------------------------------------
  const sharedConcepts = useMemo(() => {
    if (!ftsResults || !ftsResults.results_by_document) return [];
    const stopwords = new Set([
      'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have', 'been', 'which', 'their', 'other',
      'shall', 'must', 'should', 'each', 'such', 'when', 'where', 'then', 'will', 'than', 'into',
      'under', 'over', 'these', 'those', 'also', 'more', 'some', 'only', 'any', 'all', 'than',
      'article', 'annex', 'regulation', 'point', 'paragraph', 'accordance', 'subpart', 'section',
      'part', 'amc', 'gm', 'cs', 'table', 'figure', 'chapter', 'title', 'issue'
    ]);

    const wordDocMap = new Map<string, Set<string>>();
    for (const [docId, matches] of Object.entries(ftsResults.results_by_document)) {
      if (!Array.isArray(matches)) continue;
      for (const m of matches) {
        const textContent = m.source_text || m.text || m.snippet || '';
        const words = textContent
          .toLowerCase()
          .replace(/[^a-z0-9\-\/]/g, ' ')
          .split(/\s+/)
          .filter(w => w.length >= 4 && !stopwords.has(w) && !/^\d+$/.test(w));
        for (const w of words) {
          if (!wordDocMap.has(w)) wordDocMap.set(w, new Set());
          wordDocMap.get(w)!.add(docId);
        }
      }
    }

    const docCountThreshold = Math.min(2, Object.keys(ftsResults.results_by_document).length);
    const concepts: { term: string; docCount: number; totalDocs: number }[] = [];
    wordDocMap.forEach((docSet, term) => {
      if (docSet.size >= docCountThreshold) {
        concepts.push({ term, docCount: docSet.size, totalDocs: Object.keys(ftsResults.results_by_document).length });
      }
    });

    return concepts.sort((a, b) => b.docCount - a.docCount).slice(0, 14);
  }, [ftsResults]);

  // -------------------------------------------------------------
  // Client-Side Filtered Matches (Instant Filter + Requirement Lens)
  // -------------------------------------------------------------
  const filteredMatchesByDoc = useMemo(() => {
    if (!ftsResults || !ftsResults.results_by_document) return {};
    const queryLower = instantFilter.trim().toLowerCase();
    const res: Record<string, WorkspaceChunkMatch[]> = {};

    for (const [docId, matches] of Object.entries(ftsResults.results_by_document)) {
      if (!Array.isArray(matches)) {
        res[docId] = [];
        continue;
      }
      res[docId] = matches.filter(m => {
        const textContent = m.source_text || m.text || m.snippet || '';

        // 1. Text substring filter
        if (queryLower) {
          const inSection = (m.section_title || '').toLowerCase().includes(queryLower);
          const inText = textContent.toLowerCase().includes(queryLower);
          if (!inSection && !inText) return false;
        }

        // 2. Requirement Lens type filter
        if (requirementFilter !== 'all') {
          const req = analyzeRequirements(textContent);
          if (requirementFilter === 'mandate' && req.mandates === 0) return false;
          if (requirementFilter === 'prohibition' && req.prohibitions === 0) return false;
          if (requirementFilter === 'recommendation' && req.recommendations === 0) return false;
          if (requirementFilter === 'guidance' && req.guidance === 0) return false;
        }
        return true;
      });
    }
    return res;
  }, [ftsResults, instantFilter, requirementFilter]);

  // Total filtered matches count
  const totalFilteredCount = useMemo(() => {
    return Object.values(filteredMatchesByDoc).reduce((acc, list) => acc + list.length, 0);
  }, [filteredMatchesByDoc]);

  // -------------------------------------------------------------
  // Compliance Working Dossier Handlers
  // -------------------------------------------------------------
  const togglePinChunk = (chunk: WorkspaceChunkMatch, docTitle: string) => {
    setDossier(prev => {
      const exists = prev.some(p => p.chunk_id === chunk.chunk_id);
      let next: DossierItem[];
      if (exists) {
        next = prev.filter(p => p.chunk_id !== chunk.chunk_id);
      } else {
        next = [...prev, {
          chunk_id: chunk.chunk_id,
          document_id: chunk.document_id,
          document_title: docTitle,
          section_title: chunk.section_title,
          text: chunk.source_text || chunk.text || chunk.snippet || '',
          userNote: '',
          pinnedAt: Date.now()
        }];
      }
      try {
        localStorage.setItem(DOSSIER_STORAGE_KEY, JSON.stringify(next));
      } catch (e) {
        console.warn('Failed to persist dossier', e);
      }
      return next;
    });
  };

  const updateDossierNote = (chunkId: string, note: string) => {
    setDossier(prev => {
      const next = prev.map(p => p.chunk_id === chunkId ? { ...p, userNote: note } : p);
      try {
        localStorage.setItem(DOSSIER_STORAGE_KEY, JSON.stringify(next));
      } catch (e) {
        console.warn('Failed to persist dossier', e);
      }
      return next;
    });
  };

  const handleClearDossier = () => {
    if (confirm('Clear all pinned regulatory items from your working dossier?')) {
      setDossier([]);
      localStorage.removeItem(DOSSIER_STORAGE_KEY);
    }
  };

  const handleExportDossierMarkdown = () => {
    if (dossier.length === 0) return;
    let md = `# Regulatory Compliance & Overlap Dossier\n\n`;
    md += `*Generated: ${new Date().toLocaleString()} via AeroLex EU Workspace*\n\n`;
    md += `| Item | Regulation | Section | Key Requirement / Provision | Reviewer Compliance Notes |\n`;
    md += `| :--- | :--- | :--- | :--- | :--- |\n`;
    dossier.forEach((item, i) => {
      const excerpt = item.text.replace(/[\r\n]+/g, ' ').slice(0, 240) + '...';
      md += `| ${i + 1} | **${item.document_title}** | ${item.section_title} | "${excerpt}" | ${item.userNote || '*(No note added)*'} |\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `regulatory_compliance_dossier_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSendDossierToAssistant = () => {
    if (dossier.length === 0 || !onSendToAssistant) return;
    const chunkIds = dossier.map(d => d.chunk_id);
    const prompt = `Please provide a unified legal & certification synthesis of the following ${dossier.length} pinned regulatory clauses from ${Array.from(new Set(dossier.map(d => d.document_title))).join(', ')}. Focus on mandatory requirements (shall), technical conditions, and any compliance divergence.`;
    onSendToAssistant(prompt, chunkIds);
  };

  // Preset search idea pills
  const presetIdeas = [
    'surveillance radar ADS-B',
    'fatigue management rest periods',
    'ATSEP qualification training',
    'safety management system risk assessment',
    'voice channel spacing 8.33 kHz',
    'data link services CPDLC'
  ];

  // Helper to highlight search terms and modal verbs in text snippets
  const highlightSnippet = (
    text: string | undefined | null,
    query: string | undefined | null,
    lensActive: boolean
  ) => {
    if (!text || typeof text !== 'string') return '';

    // If lensActive, highlight normative verbs
    if (lensActive) {
      const parts = text.split(/\b(shall not|must not|may not|prohibited|shall|must|is required to|are required to|should|recommended|may|can)\b/gi);
      return parts.map((part, i) => {
        const lower = part.toLowerCase();
        if (['shall not', 'must not', 'may not', 'prohibited'].includes(lower)) {
          return (
            <mark key={i} className="bg-rose-950 text-rose-300 font-bold px-1 py-0.5 rounded border border-rose-800/80 mx-0.5">
              {part}
            </mark>
          );
        }
        if (['shall', 'must', 'is required to', 'are required to'].includes(lower)) {
          return (
            <mark key={i} className="bg-emerald-950 text-emerald-300 font-bold px-1 py-0.5 rounded border border-emerald-800/80 mx-0.5">
              {part}
            </mark>
          );
        }
        if (['should', 'recommended'].includes(lower)) {
          return (
            <mark key={i} className="bg-amber-950 text-amber-300 font-bold px-1 py-0.5 rounded border border-amber-800/80 mx-0.5">
              {part}
            </mark>
          );
        }
        if (['may', 'can'].includes(lower)) {
          return (
            <mark key={i} className="bg-sky-950 text-sky-300 font-bold px-1 py-0.5 rounded border border-sky-800/80 mx-0.5">
              {part}
            </mark>
          );
        }
        return part;
      });
    }

    if (!query || typeof query !== 'string' || !query.trim()) return text;
    const words = query.trim().split(/\s+/).filter(w => w.length > 2);
    if (words.length === 0) return text;

    const wordSet = new Set(words.map(w => w.toLowerCase().replace(/[^a-z0-9]/gi, '')).filter(Boolean));
    if (wordSet.size === 0) return text;

    try {
      const pattern = words
        .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .filter(Boolean)
        .join('|');
      if (!pattern) return text;

      const regex = new RegExp(`(${pattern})`, 'gi');
      const parts = text.split(regex);
      return parts.map((part, i) => {
        const cleanPart = part.toLowerCase().replace(/[^a-z0-9]/gi, '');
        return wordSet.has(cleanPart) ? (
          <mark key={i} className="bg-amber-500/30 text-amber-200 px-1 py-0.5 rounded font-medium">
            {part}
          </mark>
        ) : part;
      });
    } catch {
      return text;
    }
  };

  // Word Diff Computation
  const activeDiff = useMemo(() => {
    if (!compareChunkA || !compareChunkB) return null;
    return computeWordDiff(compareChunkA.source_text || compareChunkA.text, compareChunkB.source_text || compareChunkB.text);
  }, [compareChunkA, compareChunkB]);

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-slate-950 text-slate-100 overflow-y-auto">
      {/* ------------------------------------------------------------- */}
      {/* TOP NAVIGATION & VIEW SWITCHER                                */}
      {/* ------------------------------------------------------------- */}
      <div className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-20 px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-950/80 border border-emerald-800/60 flex items-center justify-center text-emerald-400 shadow-sm">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white tracking-tight flex items-center gap-2">
              <span>Regulations Catalog & Workspace</span>
              {workspaceDocIds.length > 0 && (
                <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800">
                  {workspaceDocIds.length} Pinned
                </span>
              )}
            </h1>
            <p className="text-xs text-slate-400">
              Browse regulatory instruments, batch cache offline, and cross-analyze requirement overlap via SQLite FTS5.
            </p>
          </div>
        </div>

        {/* Navigation Tabs (Catalog vs Dedicated Workspace) */}
        <div className="flex items-center gap-2">
          <div className="flex items-center p-1 bg-slate-950 border border-slate-800 rounded-xl text-xs font-medium">
            <button
              onClick={() => setActiveView('catalog')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                activeView === 'catalog'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Catalog & Download ({catalog.length})</span>
            </button>

            <button
              onClick={() => {
                if (workspaceDocIds.length === 0 && selectedDocIds.size > 0) {
                  handleOpenWorkspaceWithSelected();
                } else {
                  setActiveView('workspace');
                }
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                activeView === 'workspace'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Split className="w-3.5 h-3.5" />
              <span>Dedicated Workspace {workspaceDocIds.length > 0 ? `(${workspaceDocIds.length})` : ''}</span>
            </button>
          </div>

          {/* Dossier Quick Button */}
          {dossier.length > 0 && (
            <button
              onClick={() => setIsDossierOpen(!isDossierOpen)}
              className="flex items-center gap-1.5 px-3 py-2 bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/80 text-indigo-300 text-xs font-semibold rounded-xl shadow-sm transition-all"
              title="Open Compliance Working Dossier"
            >
              <Bookmark className="w-3.5 h-3.5 text-indigo-400" />
              <span>Dossier ({dossier.length})</span>
            </button>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* MODE 1: CATALOG & BATCH DOWNLOAD                              */}
      {/* ------------------------------------------------------------- */}
      {activeView === 'catalog' && (
        <div className="p-6 flex-1 flex flex-col gap-6 max-w-7xl w-full mx-auto">
          {/* Search, Filter & Action Bar */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col gap-4 shadow-sm backdrop-blur">
            <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
              {/* Title Search Input */}
              <div className="flex-1 relative">
                <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type="text"
                  value={titleQuery}
                  onChange={(e) => setTitleQuery(e.target.value)}
                  placeholder="Filter regulations by title or document number (e.g. 'Air Traffic', '2018/1139', 'CS-ACNS')..."
                  className="w-full pl-10 pr-4 py-2 bg-slate-950 border border-slate-800 focus:border-emerald-500/60 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none transition-colors"
                />
                {titleQuery && (
                  <button
                    onClick={() => setTitleQuery('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Origin Pills: All, EASA, EU */}
              <div className="flex items-center p-1 bg-slate-950 border border-slate-800 rounded-xl text-xs shrink-0">
                <button
                  onClick={() => setOriginFilter('all')}
                  className={`px-3 py-1.5 rounded-lg transition-colors font-medium ${
                    originFilter === 'all' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  All ({catalog.length})
                </button>
                <button
                  onClick={() => setOriginFilter('easa')}
                  className={`px-3 py-1.5 rounded-lg transition-colors font-medium ${
                    originFilter === 'easa' ? 'bg-emerald-950 text-emerald-300 font-semibold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  EASA Rules
                </button>
                <button
                  onClick={() => setOriginFilter('eu')}
                  className={`px-3 py-1.5 rounded-lg transition-colors font-medium ${
                    originFilter === 'eu' ? 'bg-sky-950 text-sky-300 font-semibold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  EU Standards
                </button>
              </div>

              {/* Sort Order */}
              <div className="flex items-center gap-2 shrink-0">
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as any)}
                  className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
                >
                  <option value="chunks">Most Chunks</option>
                  <option value="title">Title (A-Z)</option>
                  <option value="date">Publication Date</option>
                </select>
              </div>
            </div>

            {/* Selection & Batch Action Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800/80">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-400 font-mono">
                  Selected:{' '}
                  <strong className="text-emerald-400 font-bold">{selectedDocIds.size}</strong> of {catalog.length}
                </span>

                <button
                  onClick={handleSelectAllFiltered}
                  className="px-2.5 py-1 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                >
                  Select All
                </button>
                <span className="text-slate-700">|</span>
                <button
                  onClick={handleClearSelection}
                  disabled={selectedDocIds.size === 0}
                  className="px-2.5 py-1 text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-40 rounded-lg transition-colors"
                >
                  Clear Selection
                </button>
              </div>

              {/* Batch Action Buttons */}
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => handleDownloadSelected(false)}
                  disabled={selectedDocIds.size === 0 || isDownloading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-medium text-slate-200 transition-colors shadow-sm"
                  title="Save full text to in-app local IndexedDB cache"
                >
                  {isDownloading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <HardDrive className="w-3.5 h-3.5 text-emerald-400" />}
                  <span>Download & Cache in App</span>
                </button>

                <button
                  onClick={() => handleDownloadSelected(true)}
                  disabled={selectedDocIds.size === 0 || isDownloading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-medium text-slate-300 transition-colors shadow-sm"
                  title="Export offline JSON bundle"
                >
                  <Download className="w-3.5 h-3.5 text-slate-400" />
                  <span>Export JSON</span>
                </button>

                <button
                  onClick={() => handleOpenWorkspaceWithSelected()}
                  disabled={selectedDocIds.size === 0}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-xs font-semibold text-white transition-colors shadow-md"
                  title="Open selected documents in dedicated overlap workspace"
                >
                  <Split className="w-3.5 h-3.5" />
                  <span>Open in Workspace ({selectedDocIds.size})</span>
                  <ArrowRight className="w-3.5 h-3.5 ml-0.5" />
                </button>
              </div>
            </div>

            {/* Notification / Progress feedback */}
            {downloadSuccessMessage && (
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-300 bg-emerald-950/60 p-2.5 rounded-lg border border-emerald-800/80 animate-in fade-in duration-200">
                <Check className="w-4 h-4 text-emerald-400" />
                <span>{downloadSuccessMessage}</span>
              </div>
            )}

            {downloadProgress && (
              <div className="flex items-center gap-2 text-xs font-mono text-sky-400 bg-sky-950/40 p-2.5 rounded-lg border border-sky-800/40 animate-pulse">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>{downloadProgress}</span>
              </div>
            )}
          </div>

          {/* Catalog Listing */}
          {isLoadingCatalog ? (
            <div className="p-12 text-center text-slate-500 flex flex-col items-center gap-3">
              <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />
              <p className="text-sm font-mono">Loading regulations catalog...</p>
            </div>
          ) : catalogError ? (
            <div className="p-8 text-center text-rose-400 bg-rose-950/20 border border-rose-900/40 rounded-2xl">
              <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-rose-500" />
              <p className="text-sm">{catalogError}</p>
            </div>
          ) : catalog.length === 0 ? (
            <div className="p-12 text-center text-slate-500 bg-slate-900/40 border border-slate-800/60 rounded-2xl">
              <BookOpen className="w-8 h-8 mx-auto mb-2 text-slate-600" />
              <p className="text-sm">No regulations matched your title search filter.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-2.5">
              {catalog.map((item) => {
                const isSelected = selectedDocIds.has(item.document_id);
                const isEasa = item.origin === 'easa';
                const isCachedLocally = cachedDocIds.has(item.document_id);

                return (
                  <div
                    key={item.document_id}
                    onClick={() => toggleSelectDoc(item.document_id)}
                    className={`group p-4 rounded-xl border transition-all cursor-pointer flex items-start gap-4 ${
                      isSelected
                        ? 'bg-slate-900 border-emerald-500/50 shadow-sm'
                        : 'bg-slate-900/40 hover:bg-slate-900/70 border-slate-800/80 hover:border-slate-700'
                    }`}
                  >
                    {/* Checkbox */}
                    <div className="pt-0.5 shrink-0" onClick={(e) => { e.stopPropagation(); toggleSelectDoc(item.document_id); }}>
                      <div className={`w-5 h-5 rounded-md border flex items-center justify-center transition-colors ${
                        isSelected
                          ? 'bg-emerald-600 border-emerald-500 text-white'
                          : 'border-slate-700 bg-slate-950 text-transparent group-hover:border-slate-600'
                      }`}>
                        <Check className="w-3.5 h-3.5 stroke-[3]" />
                      </div>
                    </div>

                    {/* Metadata & Title */}
                    <div className="flex-1 min-w-0 flex flex-col gap-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Origin Pill */}
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-semibold border ${
                          isEasa
                            ? 'bg-emerald-950 text-emerald-400 border-emerald-800/60'
                            : 'bg-sky-950 text-sky-400 border-sky-800/60'
                        }`}>
                          {isEasa ? 'EASA Easy Access' : 'EU Regulation'}
                        </span>

                        {/* Local Cache Badge */}
                        {isCachedLocally && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 flex items-center gap-1">
                            <HardDrive className="w-3 h-3 text-emerald-400" />
                            Cached Offline
                          </span>
                        )}

                        {/* Chunk Count */}
                        <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                          {item.chunk_count.toLocaleString()} chunks
                        </span>

                        {/* Date if available */}
                        {item.date && (
                          <span className="text-[11px] font-mono text-slate-500">
                            {item.date}
                          </span>
                        )}

                        <span className="text-[11px] font-mono text-slate-500 truncate max-w-[200px]" title={item.document_id}>
                          {item.document_id}
                        </span>
                      </div>

                      {/* Regulation Title */}
                      <h2 className="text-sm font-medium text-slate-100 group-hover:text-white leading-snug">
                        {highlightSnippet(item.title, titleQuery, false)}
                      </h2>
                    </div>

                    {/* Actions */}
                    <div className="shrink-0 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleOpenDocViewer(item.document_id)}
                        className="px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-lg transition-colors flex items-center gap-1.5"
                        title="View Full Markdown in App"
                      >
                        <Eye className="w-3.5 h-3.5 text-sky-400" />
                        <span className="hidden sm:inline">View in App</span>
                      </button>

                      <button
                        onClick={() => handleOpenWorkspaceWithSelected([item.document_id])}
                        className="px-2.5 py-1.5 text-xs font-medium text-emerald-400 hover:text-emerald-300 bg-emerald-950/40 hover:bg-emerald-900/40 border border-emerald-800/60 rounded-lg transition-colors flex items-center gap-1.5"
                        title="Open this regulation in dedicated overlap workspace"
                      >
                        <Split className="w-3.5 h-3.5" />
                        <span className="hidden md:inline">Workspace</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODE 2: DEDICATED WORKSPACE & FTS OVERLAP ANALYZER            */}
      {/* ------------------------------------------------------------- */}
      {activeView === 'workspace' && (
        <div className="p-6 flex-1 flex flex-col gap-6 max-w-7xl w-full mx-auto">
          {/* Active Workspace Regulations Shelf */}
          <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 flex flex-col gap-3 shadow-sm backdrop-blur">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 font-mono">
                  Active Workspace Regulations ({workspaceDocIds.length})
                </span>
                <span className="text-[11px] text-slate-500 font-mono">
                  FTS queries will be restricted to these specific instruments
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveView('catalog')}
                  className="px-2.5 py-1 text-xs font-medium text-emerald-400 hover:text-emerald-300 bg-slate-950 border border-emerald-800/60 rounded-lg transition-colors flex items-center gap-1"
                >
                  <ListFilter className="w-3 h-3" />
                  <span>Manage / Add Regulations</span>
                </button>
                {workspaceDocIds.length > 0 && (
                  <button
                    onClick={() => {
                      setWorkspaceDocIds([]);
                      setFtsResults(null);
                      if (onClearInitialContext) onClearInitialContext();
                    }}
                    className="px-2.5 py-1 text-xs font-medium text-slate-400 hover:text-rose-400 bg-slate-950 border border-slate-800 rounded-lg transition-colors"
                  >
                    Clear Workspace
                  </button>
                )}
              </div>
            </div>

            {/* Chips of Active Documents */}
            {workspaceDocIds.length === 0 ? (
              <div className="p-6 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                <p className="text-sm">No regulations loaded into your workspace yet.</p>
                <button
                  onClick={() => setActiveView('catalog')}
                  className="mt-2 px-3 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors"
                >
                  Select Regulations from Catalog
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                {workspaceDocIds.map((docId) => {
                  const item = catalogMap.get(docId);
                  const isEasa = item?.origin === 'easa';
                  const isCached = cachedDocIds.has(docId);

                  return (
                    <div
                      key={docId}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 group"
                    >
                      <span className={`w-2 h-2 rounded-full ${isEasa ? 'bg-emerald-400' : 'bg-sky-400'}`} />
                      <span className="font-medium max-w-[280px] truncate" title={item?.title || docId}>
                        {item?.title || docId}
                      </span>
                      {isCached && (
                        <span title="Stored locally in IndexedDB">
                          <HardDrive className="w-3 h-3 text-emerald-400" />
                        </span>
                      )}
                      {item && (
                        <span className="text-[10px] font-mono text-slate-500">
                          ({item.chunk_count}c)
                        </span>
                      )}
                      <button
                        onClick={() => handleRemoveFromWorkspace(docId)}
                        className="text-slate-500 hover:text-rose-400 transition-colors ml-1"
                        title="Remove from workspace"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* FTS Search Input Bar */}
          {workspaceDocIds.length > 0 && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 flex flex-col gap-4 shadow-sm">
              <form onSubmit={handleExecuteWorkspaceFts} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                <div className="flex-1 relative">
                  <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-sky-400" />
                  <input
                    type="text"
                    value={ftsQuery}
                    onChange={(e) => setFtsQuery(e.target.value)}
                    placeholder="Enter an idea or requirement to analyze cross-document overlap (e.g. 'surveillance radar ADS-B', 'fatigue management rest periods')..."
                    className="w-full pl-10 pr-4 py-3 bg-slate-950 border border-slate-800 focus:border-sky-500/60 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isSearchingFts || !ftsQuery.trim()}
                  className="px-5 py-3 text-sm font-semibold bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-xl shadow-sm transition-colors flex items-center justify-center gap-2 shrink-0"
                >
                  {isSearchingFts ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Searching FTS...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Search & Compare Overlap</span>
                    </>
                  )}
                </button>
              </form>

              {/* Preset Idea Buttons */}
              <div className="flex items-center gap-2 flex-wrap text-xs text-slate-400">
                <span className="font-mono text-[11px] text-slate-500">Suggested Ideas:</span>
                {presetIdeas.map(idea => (
                  <button
                    key={idea}
                    type="button"
                    onClick={() => {
                      setFtsQuery(idea);
                      executeWorkspaceSearch(idea, workspaceDocIds);
                    }}
                    className="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-850 border border-slate-800 text-slate-300 hover:text-white transition-colors"
                  >
                    {idea}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* FTS Search Results & Overlap Breakdown */}
          {ftsError && (
            <div className="p-4 bg-rose-950/30 border border-rose-900/40 rounded-xl text-rose-300 text-sm">
              {ftsError}
            </div>
          )}

          {ftsResults && (
            <div className="flex flex-col gap-5">
              {/* Overlap Summary Card */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <span>Concept Overlap Analysis:</span>
                      <span className="text-emerald-400 font-mono">"{ftsResults.query}"</span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Matched{' '}
                      <strong className="text-white font-mono">{ftsResults.overlap_summary.total_documents_matched}</strong>{' '}
                      of{' '}
                      <strong className="text-white font-mono">{ftsResults.overlap_summary.total_documents_queried}</strong>{' '}
                      regulations across{' '}
                      <strong className="text-white font-mono">{ftsResults.total_matches}</strong> total regulatory chunks
                    </p>
                  </div>

                  {/* Overlap Rate Indicator */}
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col items-end">
                      <span className="text-xs font-mono text-slate-400">Overlap Rate</span>
                      <span className="text-lg font-bold font-mono text-emerald-400">
                        {Math.round(ftsResults.overlap_summary.overlap_rate * 100)}%
                      </span>
                    </div>

                    {/* View Switcher: Grid vs List */}
                    <div className="flex items-center p-1 bg-slate-950 border border-slate-800 rounded-lg">
                      <button
                        onClick={() => setComparisonMode('grid')}
                        className={`p-1.5 rounded-md transition-colors ${
                          comparisonMode === 'grid' ? 'bg-slate-800 text-sky-400' : 'text-slate-400 hover:text-slate-200'
                        }`}
                        title="Side-by-side columns"
                      >
                        <Columns className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setComparisonMode('list')}
                        className={`p-1.5 rounded-md transition-colors ${
                          comparisonMode === 'list' ? 'bg-slate-800 text-sky-400' : 'text-slate-400 hover:text-slate-200'
                        }`}
                        title="Grouped list view"
                      >
                        <Layers className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Overlap Heatmap / Bars per Document */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-3 border-t border-slate-800/80">
                  {ftsResults.overlap_summary.document_summaries.map((docSum) => {
                    const matchPercent = ftsResults.total_matches > 0 
                      ? Math.round((docSum.match_count / ftsResults.total_matches) * 100) 
                      : 0;

                    return (
                      <div
                        key={docSum.document_id}
                        className={`p-3 rounded-xl border flex flex-col gap-2 ${
                          docSum.has_match
                            ? 'bg-slate-950/70 border-slate-800'
                            : 'bg-slate-950/30 border-slate-900 opacity-60'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-slate-200 truncate" title={docSum.title}>
                            {docSum.title}
                          </span>
                          <span className={`text-[11px] font-mono px-2 py-0.5 rounded-full font-bold ${
                            docSum.has_match
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                              : 'bg-slate-900 text-slate-500'
                          }`}>
                            {docSum.match_count} chunks
                          </span>
                        </div>

                        {/* Progress Bar */}
                        <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-500 ${
                              docSum.has_match ? 'bg-gradient-to-r from-emerald-500 to-sky-500' : 'bg-slate-800'
                            }`}
                            style={{ width: `${Math.max(matchPercent, docSum.has_match ? 15 : 0)}%` }}
                          />
                        </div>

                        <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                          <span>{(docSum.origin || 'eu').toUpperCase()}</span>
                          {docSum.top_section ? (
                            <span className="truncate max-w-[160px] text-slate-400" title={docSum.top_section}>
                              Top: {docSum.top_section}
                            </span>
                          ) : (
                            <span>No overlap match</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* --------------------------------------------------------- */}
              {/* CLIENT-SIDE HIGH-VALUE FUNCTION 1: SHARED CONCEPTS MATRIX */}
              {/* --------------------------------------------------------- */}
              {sharedConcepts.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap p-3.5 rounded-xl bg-slate-900/60 border border-slate-800">
                  <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 font-semibold shrink-0">
                    <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                    Shared Concept Matrix:
                  </span>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {sharedConcepts.map(sc => {
                      const isActive = instantFilter.toLowerCase() === sc.term.toLowerCase();
                      return (
                        <button
                          key={sc.term}
                          onClick={() => setInstantFilter(isActive ? '' : sc.term)}
                          className={`text-[11px] font-mono px-2.5 py-1 rounded-lg border transition-all flex items-center gap-1.5 ${
                            isActive
                              ? 'bg-sky-600 text-white border-sky-500 shadow-sm'
                              : 'bg-slate-950 text-slate-300 hover:text-white border-slate-800 hover:border-slate-700'
                          }`}
                          title={`Occurs across ${sc.docCount} of ${sc.totalDocs} selected regulations`}
                        >
                          <span>{sc.term}</span>
                          <span className={`text-[10px] font-bold ${isActive ? 'text-white' : 'text-sky-400'}`}>
                            {sc.docCount}/{sc.totalDocs}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* --------------------------------------------------------- */}
              {/* CLIENT-SIDE HIGH-VALUE FUNCTION 2: WORKSPACE TOOLBAR      */}
              {/* (Instant In-Memory Filter + Requirement Lens Filter)      */}
              {/* --------------------------------------------------------- */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3">
                {/* Instant Live In-Memory Filter */}
                <div className="relative flex-1 min-w-[220px] max-w-md">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Instant filter across loaded chunks (section / clause text)..."
                    value={instantFilter}
                    onChange={(e) => setInstantFilter(e.target.value)}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-8 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                  />
                  {instantFilter && (
                    <button onClick={() => setInstantFilter('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {/* Requirement Lens & Filter Controls */}
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => setIsRequirementLensActive(!isRequirementLensActive)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                      isRequirementLensActive
                        ? 'bg-emerald-950 text-emerald-300 border-emerald-700 shadow-sm'
                        : 'bg-slate-950 text-slate-400 hover:text-slate-200 border-slate-800'
                    }`}
                    title="Highlight normative modal verbs (shall, must, should, may, prohibited)"
                  >
                    <Scale className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Requirement Lens: {isRequirementLensActive ? 'ON' : 'OFF'}</span>
                  </button>

                  <select
                    value={requirementFilter}
                    onChange={(e) => setRequirementFilter(e.target.value as any)}
                    className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
                  >
                    <option value="all">All Clauses ({totalFilteredCount})</option>
                    <option value="mandate">Mandatory Only (Shall / Must)</option>
                    <option value="prohibition">Prohibitions (Shall Not)</option>
                    <option value="recommendation">AMC Recommendations (Should)</option>
                    <option value="guidance">GM Guidance (May / Can)</option>
                  </select>

                  {/* Working Dossier Trigger */}
                  <button
                    onClick={() => setIsDossierOpen(!isDossierOpen)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                      dossier.length > 0
                        ? 'bg-indigo-950 text-indigo-300 border-indigo-700/80 shadow-sm'
                        : 'bg-slate-950 text-slate-400 hover:text-slate-200 border-slate-800'
                    }`}
                  >
                    <Bookmark className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Compliance Dossier ({dossier.length})</span>
                  </button>
                </div>
              </div>

              {/* --------------------------------------------------------- */}
              {/* SIDE-BY-SIDE MULTI-COLUMN COMPARISON GRID                 */}
              {/* --------------------------------------------------------- */}
              {comparisonMode === 'grid' && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 items-start">
                  {workspaceDocIds.map((docId) => {
                    const matches = filteredMatchesByDoc[docId] || [];
                    const catItem = catalogMap.get(docId);
                    const title = catItem?.title || docId;
                    const origin = catItem?.origin || 'eu';

                    return (
                      <div
                        key={docId}
                        className="bg-slate-900/60 border border-slate-800 rounded-2xl flex flex-col overflow-hidden max-h-[820px]"
                      >
                        {/* Column Header */}
                        <div className="p-4 border-b border-slate-800 bg-slate-900/90 flex flex-col gap-1.5 sticky top-0 z-10">
                          <div className="flex items-center justify-between gap-2">
                            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold border ${
                              origin === 'easa'
                                ? 'bg-emerald-950 text-emerald-400 border-emerald-800/60'
                                : 'bg-sky-950 text-sky-400 border-sky-800/60'
                            }`}>
                              {(origin || 'eu').toUpperCase()}
                            </span>
                            <span className="text-xs font-mono text-slate-400">
                              {matches.length} matched sections
                            </span>
                          </div>
                          <h4 className="text-sm font-semibold text-slate-100 line-clamp-2 leading-snug" title={title}>
                            {title}
                          </h4>
                          <button
                            onClick={() => handleOpenDocViewer(docId, ftsResults.query)}
                            className="text-[11px] font-medium text-sky-400 hover:text-sky-300 flex items-center gap-1 self-start mt-0.5"
                          >
                            <Eye className="w-3 h-3" />
                            <span>View Full Document</span>
                          </button>
                        </div>

                        {/* Column Matching Chunks List */}
                        <div className="p-3 flex-1 overflow-y-auto flex flex-col gap-3">
                          {matches.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-xs">
                              No sections in this regulation matched the active filters.
                            </div>
                          ) : (
                            matches.map((m) => {
                              const textContent = (m.source_text || m.text || m.snippet || '') + '';
                              const req = analyzeRequirements(textContent);
                              const isPinned = dossier.some(d => d.chunk_id === m.chunk_id);

                              return (
                                <div
                                  key={m.chunk_id}
                                  className="p-3 bg-slate-950 border border-slate-800/90 hover:border-slate-700 rounded-xl flex flex-col gap-2 transition-colors group"
                                >
                                  {/* Section Title & Score */}
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="text-xs font-semibold text-slate-200 line-clamp-1 group-hover:text-emerald-300 transition-colors" title={m.section_title}>
                                      {m.section_title}
                                    </span>
                                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-900 text-slate-400 shrink-0">
                                      {(m.score * 100).toFixed(0)}%
                                    </span>
                                  </div>

                                  {/* Modal Verb Badges */}
                                  {(req.mandates > 0 || req.prohibitions > 0 || req.recommendations > 0) && (
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      {req.mandates > 0 && (
                                        <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                                          {req.mandates} SHALL
                                        </span>
                                      )}
                                      {req.prohibitions > 0 && (
                                        <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
                                          {req.prohibitions} PROHIBITED
                                        </span>
                                      )}
                                      {req.recommendations > 0 && (
                                        <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">
                                          {req.recommendations} SHOULD
                                        </span>
                                      )}
                                      {req.guidance > 0 && (
                                        <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800">
                                          {req.guidance} MAY
                                        </span>
                                      )}
                                    </div>
                                  )}

                                  {/* Text Snippet with query / modal verb highlight */}
                                  <p className="text-xs text-slate-400 leading-relaxed line-clamp-4">
                                    {highlightSnippet(m.snippet || m.source_text || m.text, ftsResults.query, isRequirementLensActive)}
                                  </p>

                                  {/* Action Buttons */}
                                  <div className="flex items-center justify-between pt-1 border-t border-slate-900 text-[11px]">
                                    <button
                                      onClick={() => handleOpenDocViewer(m.document_id, ftsResults.query)}
                                      className="text-sky-400 hover:text-sky-300 flex items-center gap-1"
                                      title="Open document scrolled to this section"
                                    >
                                      <ExternalLink className="w-3 h-3" />
                                      <span>Read Section</span>
                                    </button>

                                    <div className="flex items-center gap-1.5">
                                      {/* Pin to Dossier Button */}
                                      <button
                                        onClick={() => togglePinChunk(m, title)}
                                        className={`p-1 rounded transition-colors ${
                                          isPinned
                                            ? 'bg-indigo-600 text-white'
                                            : 'text-slate-400 hover:text-indigo-300 bg-slate-900 hover:bg-slate-850'
                                        }`}
                                        title={isPinned ? 'Remove from Compliance Dossier' : 'Pin to Compliance Dossier'}
                                      >
                                        <Bookmark className="w-3.5 h-3.5" />
                                      </button>

                                      <button
                                        onClick={() => {
                                          if (!compareChunkA) {
                                            setCompareChunkA(m);
                                            setIsComparing(true);
                                          } else if (!compareChunkB && compareChunkA.chunk_id !== m.chunk_id) {
                                            setCompareChunkB(m);
                                            setIsComparing(true);
                                          } else {
                                            setCompareChunkA(m);
                                            setCompareChunkB(null);
                                          }
                                        }}
                                        className="text-xs text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-850"
                                        title="Compare this chunk side-by-side with another chunk"
                                      >
                                        Compare
                                      </button>

                                      {onAskAboutChunk && (
                                        <button
                                          onClick={() => onAskAboutChunk(m.chunk_id, m.section_title)}
                                          className="text-xs text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-850 flex items-center gap-1"
                                          title="Ask Assistant about this specific requirement"
                                        >
                                          <MessageSquareQuote className="w-3 h-3" />
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* --------------------------------------------------------- */}
              {/* GROUPED COMPARATIVE LIST VIEW                             */}
              {/* --------------------------------------------------------- */}
              {comparisonMode === 'list' && (
                <div className="flex flex-col gap-4">
                  {workspaceDocIds.map((docId) => {
                    const matches = filteredMatchesByDoc[docId] || [];
                    const catItem = catalogMap.get(docId);
                    const title = catItem?.title || docId;

                    return (
                      <div
                        key={docId}
                        className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 flex flex-col gap-3"
                      >
                        <div className="flex items-center justify-between">
                          <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                            <span>{title}</span>
                            <span className="text-xs font-mono font-normal text-slate-400">
                              ({matches.length} matches)
                            </span>
                          </h4>
                          <button
                            onClick={() => handleOpenDocViewer(docId, ftsResults.query)}
                            className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>View Full Document</span>
                          </button>
                        </div>

                        {matches.length === 0 ? (
                          <p className="text-xs text-slate-500">No matching sections found in this regulation for the active filter.</p>
                        ) : (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {matches.map((m) => {
                              const isPinned = dossier.some(d => d.chunk_id === m.chunk_id);
                              return (
                                <div
                                  key={m.chunk_id}
                                  className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl flex flex-col gap-2"
                                >
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs font-medium text-emerald-300">
                                      {m.section_title}
                                    </span>
                                    <span className="text-[10px] font-mono text-slate-400">
                                      {(m.score * 100).toFixed(0)}%
                                    </span>
                                  </div>
                                  <p className="text-xs text-slate-300 leading-relaxed">
                                    {highlightSnippet(m.snippet || m.source_text || m.text, ftsResults.query, isRequirementLensActive)}
                                  </p>
                                  <div className="flex items-center justify-between pt-1 border-t border-slate-900">
                                    <button
                                      onClick={() => handleOpenDocViewer(m.document_id, ftsResults.query)}
                                      className="text-sky-400 hover:text-sky-300 text-xs flex items-center gap-1"
                                    >
                                      <ExternalLink className="w-3 h-3" />
                                      <span>Read</span>
                                    </button>
                                    <button
                                      onClick={() => togglePinChunk(m, title)}
                                      className={`p-1 rounded text-xs ${isPinned ? 'text-indigo-400 font-bold' : 'text-slate-400'}`}
                                    >
                                      <Bookmark className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* CLIENT-SIDE HIGH-VALUE FUNCTION 3: WORD DIFF IN DUAL DRAWER   */}
      {/* ------------------------------------------------------------- */}
      {isComparing && (compareChunkA || compareChunkB) && (
        <div className="fixed inset-x-0 bottom-0 max-h-[85vh] bg-slate-900 border-t border-slate-700/80 shadow-2xl z-50 flex flex-col rounded-t-2xl animate-in slide-in-from-bottom duration-200">
          <div className="px-6 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
            <div className="flex items-center gap-3">
              <Split className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-white">
                Side-by-Side Regulatory Requirement Comparison
              </h3>

              {/* View Mode Toggle: Side-by-Side vs Word Diff */}
              {compareChunkA && compareChunkB && (
                <div className="flex items-center p-0.5 bg-slate-900 border border-slate-800 rounded-lg text-xs ml-4">
                  <button
                    onClick={() => setDiffViewMode('side-by-side')}
                    className={`px-2.5 py-1 rounded-md transition-colors ${
                      diffViewMode === 'side-by-side' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Side-by-Side
                  </button>
                  <button
                    onClick={() => setDiffViewMode('word-diff')}
                    className={`px-2.5 py-1 rounded-md transition-colors ${
                      diffViewMode === 'word-diff' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Word Diff Alignment ({activeDiff?.similarityScore}% overlap)
                  </button>
                </div>
              )}
            </div>

            <button
              onClick={() => {
                setIsComparing(false);
                setCompareChunkA(null);
                setCompareChunkB(null);
              }}
              className="p-1 rounded-lg text-slate-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6 overflow-y-auto max-h-[60vh]">
            {/* Slot A */}
            <div className="flex flex-col gap-2 p-4 bg-slate-950 rounded-xl border border-slate-800">
              <span className="text-[11px] font-mono text-emerald-400 uppercase font-semibold">
                Reference A: {compareChunkA?.document_id}
              </span>
              {compareChunkA ? (
                <>
                  <h4 className="text-sm font-semibold text-white">{compareChunkA.section_title}</h4>
                  <div className="text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap bg-slate-900/60 p-3 rounded-lg border border-slate-800/60 max-h-[300px] overflow-y-auto">
                    {diffViewMode === 'word-diff' && activeDiff ? (
                      activeDiff.wordsA.map((w, idx) => {
                        const c = activeDiff.clean(w);
                        const isCommon = c && activeDiff.setB.has(c);
                        return (
                          <span
                            key={idx}
                            className={isCommon ? 'text-slate-200' : 'bg-rose-950/80 text-rose-300 line-through px-0.5 rounded'}
                          >
                            {w}{' '}
                          </span>
                        );
                      })
                    ) : (
                      compareChunkA.source_text || compareChunkA.text
                    )}
                  </div>
                </>
              ) : (
                <div className="p-8 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded-lg">
                  Click "Compare" on another chunk to place it here.
                </div>
              )}
            </div>

            {/* Slot B */}
            <div className="flex flex-col gap-2 p-4 bg-slate-950 rounded-xl border border-slate-800">
              <span className="text-[11px] font-mono text-sky-400 uppercase font-semibold">
                Reference B: {compareChunkB?.document_id}
              </span>
              {compareChunkB ? (
                <>
                  <h4 className="text-sm font-semibold text-white">{compareChunkB.section_title}</h4>
                  <div className="text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap bg-slate-900/60 p-3 rounded-lg border border-slate-800/60 max-h-[300px] overflow-y-auto">
                    {diffViewMode === 'word-diff' && activeDiff ? (
                      activeDiff.wordsB.map((w, idx) => {
                        const c = activeDiff.clean(w);
                        const isCommon = c && activeDiff.setA.has(c);
                        return (
                          <span
                            key={idx}
                            className={isCommon ? 'text-slate-200' : 'bg-emerald-950/80 text-emerald-300 font-semibold underline px-0.5 rounded'}
                          >
                            {w}{' '}
                          </span>
                        );
                      })
                    ) : (
                      compareChunkB.source_text || compareChunkB.text
                    )}
                  </div>
                </>
              ) : (
                <div className="p-8 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded-lg">
                  Click "Compare" on another chunk to place it here for dual comparison.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* CLIENT-SIDE HIGH-VALUE FUNCTION 4: COMPLIANCE WORKING DOSSIER */}
      {/* ------------------------------------------------------------- */}
      {isDossierOpen && (
        <div className="fixed inset-x-0 bottom-0 max-h-[85vh] bg-slate-900 border-t border-slate-700/80 shadow-2xl z-50 flex flex-col rounded-t-2xl animate-in slide-in-from-bottom duration-200">
          <div className="px-6 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
            <div className="flex items-center gap-3">
              <Bookmark className="w-4 h-4 text-indigo-400" />
              <div>
                <h3 className="text-sm font-semibold text-white">
                  Compliance Working Dossier ({dossier.length} items pinned)
                </h3>
                <p className="text-[11px] text-slate-400">
                  Annotate key regulatory provisions, cross-reference clauses, and export audit matrices.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleExportDossierMarkdown}
                disabled={dossier.length === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-medium text-slate-200 rounded-lg transition-colors"
                title="Download formatted audit table as Markdown file"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export Markdown</span>
              </button>

              {onSendToAssistant && (
                <button
                  onClick={handleSendDossierToAssistant}
                  disabled={dossier.length === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-xs font-semibold text-white rounded-lg transition-colors shadow-md"
                  title="Send all pinned clauses to AI Assistant for synthesis"
                >
                  <Cpu className="w-3.5 h-3.5" />
                  <span>Synthesize in Assistant</span>
                </button>
              )}

              <button
                onClick={handleClearDossier}
                disabled={dossier.length === 0}
                className="p-1.5 text-slate-400 hover:text-rose-400 disabled:opacity-30 rounded-lg transition-colors"
                title="Clear Dossier"
              >
                <Trash2 className="w-4 h-4" />
              </button>

              <button
                onClick={() => setIsDossierOpen(false)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg transition-colors ml-2"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="p-6 overflow-y-auto max-h-[60vh] space-y-4">
            {dossier.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded-2xl">
                <Bookmark className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                <p className="text-sm text-slate-400 font-medium">Your compliance working dossier is empty.</p>
                <p className="text-slate-500 mt-1">
                  Click the bookmark icon on any regulatory chunk in the workspace to pin it here and add reviewer notes.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4">
                {dossier.map((item, idx) => (
                  <div
                    key={item.chunk_id}
                    className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col md:flex-row gap-4 items-start"
                  >
                    <div className="flex-1 space-y-2 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                          Item #{idx + 1}
                        </span>
                        <span className="text-xs font-semibold text-slate-200">
                          {item.document_title}
                        </span>
                        <span className="text-slate-600">·</span>
                        <span className="text-xs font-mono text-emerald-400">
                          {item.section_title}
                        </span>
                      </div>

                      <p className="text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap bg-slate-900/50 p-3 rounded-lg border border-slate-800/80 max-h-32 overflow-y-auto">
                        {item.text}
                      </p>
                    </div>

                    {/* Inline User Note Input */}
                    <div className="w-full md:w-80 flex flex-col gap-2 shrink-0">
                      <label className="text-[11px] font-medium text-slate-400">
                        Reviewer Compliance Note / Rationale:
                      </label>
                      <textarea
                        value={item.userNote}
                        onChange={(e) => updateDossierNote(item.chunk_id, e.target.value)}
                        placeholder="e.g., Mandatory dual equipment required by point ATM/ANS.OR.C.020..."
                        rows={3}
                        className="w-full p-2.5 bg-slate-900 border border-slate-800 focus:border-indigo-500 rounded-lg text-xs text-slate-200 placeholder-slate-600 focus:outline-none"
                      />
                      <div className="flex items-center justify-between">
                        <button
                          onClick={() => handleOpenDocViewer(item.document_id)}
                          className="text-[11px] text-sky-400 hover:text-sky-300 flex items-center gap-1"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span>View Full Document</span>
                        </button>
                        <button
                          onClick={() => togglePinChunk({ chunk_id: item.chunk_id } as any, '')}
                          className="text-[11px] text-rose-400 hover:text-rose-300"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
