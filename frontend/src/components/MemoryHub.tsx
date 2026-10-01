/**
 * MemoryHub Component
 * Comprehensive query memory repository, timeline, context manager, and export tool
 */

import React, { useState } from 'react';
import { 
  Database, Bookmark, BookmarkCheck, Search, Trash2, Download, 
  ExternalLink, Check, Copy, Clock, Layers, Sparkles, Filter 
} from 'lucide-react';
import { QueryMemoryItem } from '../types';
import { 
  getQueryMemory, toggleMemoryContextActive, toggleMemoryPin, 
  deleteMemoryItem, clearMemory, exportMemoryAsMarkdown 
} from '../services/memoryService';

interface MemoryHubProps {
  onReAskQuery: (query: string, chunkIds?: string[]) => void;
  onRefreshMemoryCount?: () => void;
}

export const MemoryHub: React.FC<MemoryHubProps> = ({
  onReAskQuery,
  onRefreshMemoryCount,
}) => {
  const [memoryItems, setMemoryItems] = useState<QueryMemoryItem[]>(() => getQueryMemory());
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'ask' | 'search'>('all');
  const [onlyPinned, setOnlyPinned] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportContent, setExportContent] = useState('');

  const refreshItems = () => {
    const items = getQueryMemory();
    setMemoryItems(items);
    if (onRefreshMemoryCount) onRefreshMemoryCount();
  };

  const handleToggleActive = (id: string) => {
    toggleMemoryContextActive(id);
    refreshItems();
  };

  const handleTogglePin = (id: string) => {
    toggleMemoryPin(id);
    refreshItems();
  };

  const handleDelete = (id: string) => {
    deleteMemoryItem(id);
    refreshItems();
  };

  const handleClear = () => {
    if (window.confirm('Clear all non-pinned queries from memory?')) {
      clearMemory(true);
      refreshItems();
    }
  };

  const handleExport = () => {
    const md = exportMemoryAsMarkdown();
    setExportContent(md);
    setShowExportModal(true);
  };

  const handleDownloadFile = () => {
    const blob = new Blob([exportContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aerolex_eu_query_memory_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Filtered list
  const filteredItems = memoryItems.filter(item => {
    if (onlyPinned && !item.isPinned) return false;
    if (typeFilter !== 'all' && item.type !== typeFilter) return false;
    if (searchTerm.trim()) {
      const s = searchTerm.toLowerCase();
      const inQuery = item.query.toLowerCase().includes(s);
      const inAnswer = (item.answerSnippet || item.fullAnswer || '').toLowerCase().includes(s);
      const inTags = (item.tags || []).some(t => t.toLowerCase().includes(s));
      if (!inQuery && !inAnswer && !inTags) return false;
    }
    return true;
  });

  const activeCount = memoryItems.filter(m => m.isActiveInContext).length;
  const pinnedCount = memoryItems.filter(m => m.isPinned).length;

  return (
    <div className="flex flex-col h-[calc(100vh-61px)] bg-slate-950 overflow-y-auto">
      {/* Header Bar */}
      <div className="p-6 bg-slate-900/60 border-b border-slate-800/80 shrink-0">
        <div className="max-w-5xl mx-auto space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-slate-100 tracking-tight flex items-center gap-2">
                <Database className="w-5 h-5 text-sky-400" />
                <span>User Query Memory Repository</span>
              </h1>
              <p className="text-xs text-slate-400 mt-1">
                Persistent log of your regulatory inquiries with contextual injection controls for the local LLM
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleExport}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors"
              >
                <Download className="w-3.5 h-3.5 text-sky-400" />
                <span>Export Memory Log</span>
              </button>

              <button
                type="button"
                onClick={handleClear}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-rose-300 bg-slate-950 hover:bg-rose-950/30 border border-slate-800 hover:border-rose-900/50 rounded-lg transition-colors"
                title="Clears all queries except pinned ones"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear Unpinned</span>
              </button>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">Total Queries Recorded</div>
              <div className="text-lg font-bold font-mono text-slate-100 tabular-nums">{memoryItems.length}</div>
            </div>

            <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">Active LLM Context Items</div>
              <div className="text-lg font-bold font-mono text-sky-400 tabular-nums">{activeCount}</div>
            </div>

            <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">Pinned Key Inquiries</div>
              <div className="text-lg font-bold font-mono text-amber-400 tabular-nums">{pinnedCount}</div>
            </div>
          </div>

          {/* Search & Filters */}
          <div className="flex flex-col sm:flex-row items-center gap-3">
            <div className="relative flex-1 w-full">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search through past queries, responses, and tags..."
                className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <div className="flex items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-lg">
                <button
                  type="button"
                  onClick={() => setTypeFilter('all')}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    typeFilter === 'all' ? 'bg-slate-800 text-sky-400 font-medium' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  All Types
                </button>
                <button
                  type="button"
                  onClick={() => setTypeFilter('ask')}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    typeFilter === 'ask' ? 'bg-slate-800 text-sky-400 font-medium' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  LLM Q&A
                </button>
                <button
                  type="button"
                  onClick={() => setTypeFilter('search')}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    typeFilter === 'search' ? 'bg-slate-800 text-sky-400 font-medium' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Searches
                </button>
              </div>

              <button
                type="button"
                onClick={() => setOnlyPinned(!onlyPinned)}
                className={`flex items-center gap-1 px-3 py-2 text-xs rounded-lg border transition-colors ${
                  onlyPinned
                    ? 'bg-amber-950/60 border-amber-800 text-amber-300'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <Bookmark className="w-3.5 h-3.5" />
                <span>Pinned</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Memory List */}
      <div className="flex-1 p-6 max-w-5xl mx-auto w-full space-y-3">
        {filteredItems.length === 0 ? (
          <div className="p-12 text-center bg-slate-900/30 border border-slate-800 rounded-xl space-y-2">
            <Clock className="w-8 h-8 text-slate-600 mx-auto" />
            <h3 className="text-sm font-semibold text-slate-300">No matching queries found in memory</h3>
            <p className="text-xs text-slate-500">
              Queries you ask in the Assistant or search in the Explorer are saved here automatically.
            </p>
          </div>
        ) : (
          filteredItems.map((item) => (
            <div
              key={item.id}
              className={`p-4 bg-slate-900 border rounded-xl transition-all ${
                item.isActiveInContext
                  ? 'border-sky-800/80 bg-slate-900/90'
                  : 'border-slate-800/80'
              }`}
            >
              {/* Top Row: Meta and Actions */}
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span className={`px-2 py-0.5 rounded font-mono text-[10px] uppercase font-semibold ${
                    item.type === 'ask' ? 'bg-sky-950 text-sky-400 border border-sky-800/50' : 'bg-slate-800 text-slate-300'
                  }`}>
                    {item.type}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span className="font-mono text-slate-500 tabular-nums">
                    {new Date(item.timestamp).toLocaleString([], {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    })}
                  </span>
                  {item.origin && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span className="uppercase font-mono text-slate-400">{item.origin}</span>
                    </>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {/* Context Toggle */}
                  <button
                    type="button"
                    onClick={() => handleToggleActive(item.id)}
                    className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded border transition-colors ${
                      item.isActiveInContext
                        ? 'bg-sky-950/80 border-sky-700 text-sky-300 font-medium'
                        : 'bg-slate-950 border-slate-800 text-slate-500 hover:text-slate-300'
                    }`}
                    title="Toggle active memory context injection into local LLM"
                  >
                    <Database className="w-3 h-3" />
                    <span>{item.isActiveInContext ? 'Active in LLM Context' : 'Inactive'}</span>
                  </button>

                  {/* Pin Button */}
                  <button
                    type="button"
                    onClick={() => handleTogglePin(item.id)}
                    className={`p-1.5 rounded transition-colors ${
                      item.isPinned
                        ? 'text-amber-400 hover:text-amber-300'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                    title={item.isPinned ? 'Unpin query' : 'Pin query'}
                  >
                    <Bookmark className="w-4 h-4 fill-current" />
                  </button>

                  {/* Re-Ask Button */}
                  <button
                    type="button"
                    onClick={() => onReAskQuery(item.query, item.retrievedChunks?.map(c => c.chunk_id))}
                    className="p-1.5 text-slate-400 hover:text-sky-400 transition-colors"
                    title="Re-run this query in Ask Assistant"
                  >
                    <Sparkles className="w-4 h-4" />
                  </button>

                  {/* Delete Button */}
                  <button
                    type="button"
                    onClick={() => handleDelete(item.id)}
                    className="p-1.5 text-slate-500 hover:text-rose-400 transition-colors"
                    title="Delete query from memory"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Query Content */}
              <h3 className="text-sm font-semibold text-slate-100 mb-2">
                "{item.query}"
              </h3>

              {/* Response Snippet */}
              {(item.answerSnippet || item.fullAnswer) && (
                <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/60 text-xs text-slate-300 leading-relaxed font-sans mb-3">
                  <span className="text-slate-500 font-semibold block mb-0.5 text-[11px] uppercase tracking-wider">
                    Summary / Finding:
                  </span>
                  {item.answerSnippet || item.fullAnswer}
                </div>
              )}

              {/* Retrieved Chunks List */}
              {item.retrievedChunks && item.retrievedChunks.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                  <span className="text-slate-500 text-[11px]">Referenced:</span>
                  {item.retrievedChunks.map((chunk) => (
                    <span
                      key={chunk.chunk_id}
                      className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300"
                    >
                      {chunk.chunk_id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative flex flex-col w-full max-w-2xl max-h-[85vh] bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0">
              <h3 className="text-sm font-semibold text-slate-100">Exported Query Memory Log (Markdown)</h3>
              <button
                type="button"
                onClick={() => setShowExportModal(false)}
                className="text-slate-400 hover:text-slate-200 text-xs"
              >
                Close
              </button>
            </div>

            <div className="flex-1 p-6 overflow-y-auto font-mono text-xs text-slate-300 bg-slate-950">
              <pre className="whitespace-pre-wrap">{exportContent}</pre>
            </div>

            <div className="flex items-center justify-end gap-2 px-6 py-3 border-t border-slate-800 bg-slate-900 shrink-0">
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(exportContent);
                  alert('Copied markdown log to clipboard!');
                }}
                className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg"
              >
                Copy Markdown
              </button>
              <button
                type="button"
                onClick={handleDownloadFile}
                className="px-3 py-1.5 text-xs bg-sky-600 hover:bg-sky-500 text-white rounded-lg flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download .md File</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
