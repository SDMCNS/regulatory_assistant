/**
 * SearchExplorer Component
 * Clean frontend for FastAPI SEARCH operations:
 * - /search/keyword (SQLite FTS5 BM25 + Porter Stemming + LLM Query Expansion)
 * - /search (Dense Semantic Vector Search)
 * - /search/docs (Semantic Search with Full Markdown Documents)
 */

import React, { useState } from 'react';
import { 
  Search, FileText, Layers, Check, Copy, ArrowUpRight, 
  BookOpen, AlertCircle, RefreshCw, Key, Sparkles, Hash
} from 'lucide-react';
import { 
  AppSettings, KeywordSearchResponse, RegulationOrigin, 
  SearchDocResponse, SearchMethod, SearchResponse 
} from '../types';
import { 
  searchDocsRegulations, searchKeywordRegulations, searchRegulations 
} from '../services/apiClient';
import { recordQuery } from '../services/memoryService';

interface SearchExplorerProps {
  settings: AppSettings;
  onViewDoc: (doc: SearchDocResponse) => void;
  onAskAboutChunk: (chunkId: string, title: string) => void;
  targetedChunks: string[];
  onToggleTargetChunk: (chunkId: string) => void;
}

export const SearchExplorer: React.FC<SearchExplorerProps> = ({
  settings,
  onViewDoc,
  onAskAboutChunk,
  targetedChunks,
  onToggleTargetChunk,
}) => {
  const [query, setQuery] = useState('');
  const [searchMethod, setSearchMethod] = useState<SearchMethod>('keyword');
  const [useLLMExpansion, setUseLLMExpansion] = useState<boolean>(settings.defaultKeywordUseLLM);
  const [origin, setOrigin] = useState<RegulationOrigin>(settings.defaultOrigin);
  const [topK, setTopK] = useState<number>(settings.defaultTopK);

  const [results, setResults] = useState<(SearchResponse | KeywordSearchResponse | SearchDocResponse)[]>([]);
  const [expandedTerms, setExpandedTerms] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [loadingDocId, setLoadingDocId] = useState<string | null>(null);

  const executeSearch = async (searchTerm?: string) => {
    const q = (searchTerm !== undefined ? searchTerm : query).trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);
    setExpandedTerms(null);

    try {
      if (searchMethod === 'keyword') {
        const keywordData = await searchKeywordRegulations(q, topK, origin, useLLMExpansion, settings);
        setResults(keywordData);
        // Extract any expanded terms from the response items
        const allExpanded = Array.from(
          new Set(keywordData.flatMap(r => r.expanded_terms || []).filter(Boolean))
        );
        if (allExpanded.length > 0) {
          setExpandedTerms(allExpanded);
        }
      } else if (searchMethod === 'docs') {
        const docsData = await searchDocsRegulations(q, topK, origin, settings);
        setResults(docsData);
      } else {
        const semanticData = await searchRegulations(q, topK, origin, settings);
        setResults(semanticData);
      }

      // Record in Query Memory
      recordQuery({
        query: q,
        type: 'search',
        searchMethod,
        origin,
        top_k: topK,
        resultsCount: results.length,
        answerSnippet: `Retrieved results via /search/${searchMethod === 'keyword' ? 'keyword' : searchMethod === 'docs' ? 'docs' : ''}`,
        retrievedChunks: results.map(r => ({
          chunk_id: r.chunk_id,
          document_id: r.document_id,
          source: r.source,
          path: r.path,
          score: r.score,
        })),
        isPinned: false,
        isActiveInContext: false,
      });
    } catch (err: any) {
      setError(err.message || 'Error executing search');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyChunkId = (chunkId: string) => {
    navigator.clipboard.writeText(chunkId);
    setCopiedId(chunkId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleOpenDoc = async (item: SearchResponse | KeywordSearchResponse | SearchDocResponse) => {
    // If it already has markdown_doc, open directly
    if ('markdown_doc' in item && item.markdown_doc) {
      onViewDoc(item as SearchDocResponse);
      return;
    }

    // Otherwise fetch the full doc representation via /search/docs for this document
    setLoadingDocId(item.chunk_id);
    try {
      const docResults = await searchDocsRegulations(item.chunk_id, 1, origin, settings);
      if (docResults.length > 0) {
        onViewDoc(docResults[0]);
      } else {
        // Fallback: construct document viewer with available chunk text
        onViewDoc({
          ...item,
          markdown_doc: `# ${item.document_id}\n\n${item.path.join(' > ')}\n\n---\n\n${item.text}`
        });
      }
    } catch (e: any) {
      onViewDoc({
        ...item,
        markdown_doc: `# ${item.document_id}\n\n${item.path.join(' > ')}\n\n---\n\n${item.text}`
      });
    } finally {
      setLoadingDocId(null);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-61px)] bg-slate-950 overflow-y-auto">
      {/* Search Header Container */}
      <div className="p-6 bg-slate-900/60 border-b border-slate-800/80 shrink-0">
        <div className="max-w-5xl mx-auto space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-bold text-slate-100 tracking-tight">
                Regulation Search & Document Explorer
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Execute keyword (BM25 FTS5) or semantic vector queries across EU Formex & EASA regulations
              </p>
            </div>

            {/* Search Method Tabs */}
            <div className="flex items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-lg shrink-0">
              <button
                type="button"
                onClick={() => setSearchMethod('keyword')}
                className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  searchMethod === 'keyword'
                    ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="GET /search/keyword: SQLite FTS5 BM25 search. Best for acronyms (ATSEP, FTL), clauses, and exact terms."
              >
                <Key className="w-3.5 h-3.5" />
                <span>Keyword & Acronym (BM25)</span>
              </button>

              <button
                type="button"
                onClick={() => setSearchMethod('semantic')}
                className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  searchMethod === 'semantic'
                    ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="GET /search: Dense semantic vector search. Best for natural language questions."
              >
                <Hash className="w-3.5 h-3.5" />
                <span>Semantic Vector</span>
              </button>

              <button
                type="button"
                onClick={() => setSearchMethod('docs')}
                className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  searchMethod === 'docs'
                    ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="GET /search/docs: Returns full markdown representations of matched regulations."
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Full Docs</span>
              </button>
            </div>
          </div>

          {/* Search Bar & Controls */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-3 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && executeSearch()}
                placeholder={
                  searchMethod === 'keyword'
                    ? "Enter acronym or keyword (e.g. ATSEP, AMC-20, CAT.OP.MPA, FTL)..."
                    : "Enter natural language query to search regulations..."
                }
                className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none font-sans"
              />
            </div>

            <div className="flex items-center gap-2">
              {/* Origin Segmented Control */}
              <div className="flex items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-lg">
                <button
                  type="button"
                  onClick={() => setOrigin('all')}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                    origin === 'all'
                      ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setOrigin('easa')}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                    origin === 'easa'
                      ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  EASA
                </button>
                <button
                  type="button"
                  onClick={() => setOrigin('eu')}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                    origin === 'eu'
                      ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  EU
                </button>
              </div>

              {/* Top K Dropdown */}
              <select
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="px-3 py-2 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-300 focus:outline-none focus:border-sky-500 font-mono"
              >
                <option value={3}>Top 3</option>
                <option value={5}>Top 5</option>
                <option value={8}>Top 8</option>
                <option value={10}>Top 10</option>
              </select>

              <button
                type="button"
                onClick={() => executeSearch()}
                disabled={loading || !query.trim()}
                className="px-4 py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>{loading ? 'Searching...' : 'Search'}</span>
              </button>
            </div>
          </div>

          {/* Keyword Search Specific Options: LLM Query Expansion Toggle */}
          {searchMethod === 'keyword' && (
            <div className="flex items-center justify-between pt-1 text-xs">
              <label className="flex items-center gap-2 cursor-pointer text-slate-300 hover:text-white select-none">
                <input
                  type="checkbox"
                  checked={useLLMExpansion}
                  onChange={(e) => setUseLLMExpansion(e.target.checked)}
                  className="w-3.5 h-3.5 rounded text-sky-600 focus:ring-sky-500 bg-slate-900 border-slate-700"
                />
                <span className="flex items-center gap-1 text-slate-400">
                  <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                  <span>Enable LLM query expansion (<code className="font-mono text-[11px] text-sky-300">use_llm=true</code>)</span>
                </span>
              </label>

              <span className="text-[11px] text-slate-500 font-mono">
                API Endpoint: GET /search/keyword
              </span>
            </div>
          )}

          {/* Display LLM Expanded Terms from server if returned */}
          {expandedTerms && expandedTerms.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 p-2 bg-sky-950/30 border border-sky-800/40 rounded-lg text-xs">
              <span className="text-sky-400 font-medium flex items-center gap-1">
                <Sparkles className="w-3 h-3" />
                <span>LLM Expanded Terms:</span>
              </span>
              {expandedTerms.map((term, idx) => (
                <span key={idx} className="px-2 py-0.5 rounded bg-sky-900/40 border border-sky-700/50 font-mono text-[11px] text-sky-200">
                  {term}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main Results View */}
      <div className="flex-1 p-6 max-w-5xl mx-auto w-full space-y-4">
        {/* Error Bar */}
        {error && (
          <div className="p-3 bg-rose-950/30 border border-rose-800/50 rounded-lg text-xs text-rose-300 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
            <div>
              <span className="font-semibold">API Error:</span> {error}
            </div>
          </div>
        )}

        {/* Results Metadata Header */}
        {hasSearched && !loading && (
          <div className="flex items-center justify-between text-xs text-slate-400 pb-1">
            <div>
              <span>Found <strong className="text-slate-200 font-mono tabular-nums">{results.length}</strong> matching chunks</span>
              <span className="mx-2">·</span>
              <span>Method: <strong className="text-slate-200 uppercase font-mono">{searchMethod}</strong></span>
              <span className="mx-2">·</span>
              <span>Origin: <strong className="text-slate-200 uppercase">{origin}</strong></span>
            </div>

            {targetedChunks.length > 0 && (
              <div className="flex items-center gap-2 text-amber-400 font-mono text-xs">
                <Layers className="w-3.5 h-3.5" />
                <span>{targetedChunks.length} chunk(s) targeted for LLM</span>
              </div>
            )}
          </div>
        )}

        {/* Initial Empty State before search */}
        {!hasSearched && !loading && (
          <div className="p-16 text-center bg-slate-900/30 border border-slate-800/80 rounded-xl space-y-3">
            <Search className="w-10 h-10 text-slate-600 mx-auto" />
            <h3 className="text-base font-semibold text-slate-200">Regulatory Search Engine</h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
              Use <strong>Keyword & Acronym (BM25)</strong> to find specific codes like <code className="text-sky-300 font-mono">ATSEP</code>, <code className="text-sky-300 font-mono">AMC-20</code>, <code className="text-sky-300 font-mono">CAT.OP.MPA</code>, or <strong>Semantic Vector</strong> for natural language questions.
            </p>
          </div>
        )}

        {/* No results state */}
        {hasSearched && results.length === 0 && !loading && (
          <div className="p-12 text-center bg-slate-900/30 border border-slate-800/80 rounded-xl space-y-3">
            <BookOpen className="w-8 h-8 text-slate-600 mx-auto" />
            <h3 className="text-sm font-semibold text-slate-300">No matching regulations found</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              The API returned 0 matching chunks. Try adjusting your query or switching between Keyword (BM25) and Semantic search modes.
            </p>
          </div>
        )}

        {/* Results List */}
        {results.length > 0 && (
          <div className="space-y-3">
            {results.map((doc) => {
              const isTargeted = targetedChunks.includes(doc.chunk_id);
              const scorePercent = typeof doc.score === 'number' ? Math.round(doc.score * 100) : 0;

              return (
                <div
                  key={doc.chunk_id}
                  className={`p-4 sm:p-5 bg-slate-900 border rounded-xl transition-all ${
                    isTargeted
                      ? 'border-amber-500/60 shadow-[0_0_12px_rgba(245,158,11,0.1)]'
                      : 'border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Card Header */}
                  <div className="flex flex-wrap items-start justify-between gap-3 mb-2.5">
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-mono text-sky-400 uppercase tracking-wider font-semibold">
                          {doc.source}
                        </span>
                        <span aria-hidden="true" className="text-slate-600">·</span>
                        <span className="font-mono text-slate-400">{doc.document_id}</span>
                        <span aria-hidden="true" className="text-slate-600">·</span>
                        <span className="font-mono text-slate-500">{doc.chunk_id}</span>
                      </div>
                      <h3 className="text-sm font-semibold text-slate-100">
                        {doc.path[doc.path.length - 1] || doc.chunk_id}
                      </h3>
                    </div>

                    {/* Score & Target Button */}
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-md">
                        <span className="text-[11px] text-slate-500">Score</span>
                        <span className="font-mono text-xs font-semibold text-emerald-400 tabular-nums">
                          {doc.score.toFixed(2)}
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={() => onToggleTargetChunk(doc.chunk_id)}
                        className={`px-2.5 py-1 text-xs rounded-md border transition-colors flex items-center gap-1 font-medium ${
                          isTargeted
                            ? 'bg-amber-950/80 border-amber-700 text-amber-300'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                        }`}
                        title={isTargeted ? 'Remove from targeted LLM context' : 'Target this chunk in /llm/ask'}
                      >
                        <Layers className="w-3 h-3" />
                        <span>{isTargeted ? 'Targeted' : 'Target'}</span>
                      </button>
                    </div>
                  </div>

                  {/* Hierarchical Breadcrumb */}
                  {doc.path && doc.path.length > 0 && (
                    <div className="text-xs text-slate-400 mb-3 bg-slate-950/40 p-1.5 rounded border border-slate-800/40 overflow-x-auto whitespace-nowrap">
                      {doc.path.map((step, idx) => (
                        <React.Fragment key={idx}>
                          {idx > 0 && <span className="mx-1 text-slate-600">/</span>}
                          <span className={idx === doc.path.length - 1 ? 'text-slate-300 font-medium' : 'text-slate-500'}>
                            {step}
                          </span>
                        </React.Fragment>
                      ))}
                    </div>
                  )}

                  {/* Text Snippet */}
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed font-sans bg-slate-950/30 p-3 rounded-lg border border-slate-800/60 mb-3 whitespace-pre-wrap">
                    {doc.text}
                  </p>

                  {/* Card Actions */}
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800/60 text-xs">
                    <button
                      type="button"
                      onClick={() => handleCopyChunkId(doc.chunk_id)}
                      className="flex items-center gap-1 text-slate-400 hover:text-slate-200 font-mono text-[11px]"
                    >
                      {copiedId === doc.chunk_id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedId === doc.chunk_id ? 'Copied ID' : 'Copy ID'}</span>
                    </button>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onAskAboutChunk(doc.chunk_id, doc.path[doc.path.length - 1] || doc.chunk_id)}
                        className="flex items-center gap-1 px-2.5 py-1 text-sky-400 hover:text-sky-300 bg-sky-950/40 hover:bg-sky-900/40 border border-sky-800/40 rounded transition-colors"
                      >
                        <span>Ask LLM</span>
                        <ArrowUpRight className="w-3 h-3" />
                      </button>

                      <button
                        type="button"
                        onClick={() => handleOpenDoc(doc)}
                        disabled={loadingDocId === doc.chunk_id}
                        className="flex items-center gap-1 px-2.5 py-1 text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors"
                      >
                        <FileText className="w-3 h-3 text-sky-400" />
                        <span>{loadingDocId === doc.chunk_id ? 'Loading...' : 'Read Full Document'}</span>
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
