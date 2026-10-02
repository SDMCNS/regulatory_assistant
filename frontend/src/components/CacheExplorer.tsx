import React, { useState, useEffect } from 'react';
import { keys, get, del } from 'idb-keyval';
import { Database, Trash2, Search, FileText, DatabaseZap, ChevronDown, ChevronRight, FileText as FileTextIcon, ArrowUpRight } from 'lucide-react';
import { SearchDocResponse, KeywordSearchResponse, SearchResponse, DocSection } from '../types';
import { parseDocumentSections } from '../utils/sectionParser';
import { marked } from 'marked';

interface CacheExplorerProps {
  onViewDoc: (doc: SearchDocResponse) => void;
  onAskAboutChunk: (chunkId: string, title: string) => void;
}

export const CacheExplorer: React.FC<CacheExplorerProps> = ({ onViewDoc, onAskAboutChunk }) => {
  const [cacheKeys, setCacheKeys] = useState<string[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedData, setSelectedData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [collapsedChunks, setCollapsedChunks] = useState<Set<string>>(new Set());

  const toggleCollapse = (chunkId: string) => {
    setCollapsedChunks(prev => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  };

  const loadKeys = async () => {
    try {
      const allKeys = await keys();
      const filtered = allKeys
        .map(String)
        .filter(k => k.startsWith('aerolex_doc_cache_') || k.startsWith('aerolex_search_cache_') || k.startsWith('aerolex_eu_user_query_memory_v2'));
      setCacheKeys(filtered);
    } catch (e) {
      console.error('Failed to load cache keys', e);
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

  const handleSelectKey = async (key: string) => {
    setSelectedKey(key);
    setIsLoading(true);
    try {
      const data = await get(key);
      setSelectedData(data);
    } catch (e) {
      console.error('Failed to load data for key', key, e);
      setSelectedData(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteKey = async (key: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await del(key);
      if (selectedKey === key) {
        setSelectedKey(null);
        setSelectedData(null);
      }
      loadKeys();
    } catch (err) {
      console.error('Failed to delete key', err);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm("Are you sure you want to clear ALL cached documents and searches?")) return;
    try {
      const allKeys = await keys();
      for (const k of allKeys) {
        const ks = String(k);
        if (ks.startsWith('aerolex_doc_cache_') || ks.startsWith('aerolex_search_cache_')) {
          await del(k);
        }
      }
      setSelectedKey(null);
      setSelectedData(null);
      loadKeys();
    } catch (err) {
      console.error('Failed to clear cache', err);
    }
  };

  const renderSearchChunks = (results: (SearchResponse | KeywordSearchResponse | SearchDocResponse)[]) => {
    if (!Array.isArray(results)) return <pre className="text-xs text-slate-300">{JSON.stringify(results, null, 2)}</pre>;
    
    return (
      <div className="space-y-3">
        {results.map((doc, idx) => (
          <div key={doc.chunk_id || idx} className="p-4 sm:p-5 bg-slate-900 border border-slate-800 rounded-xl hover:border-slate-700 transition-all">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-2.5">
              <div className="space-y-1 min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs">
                  <button 
                    onClick={() => toggleCollapse(doc.chunk_id)}
                    className="p-0.5 hover:bg-slate-800 rounded transition-colors text-slate-400 hover:text-slate-200"
                  >
                    {collapsedChunks.has(doc.chunk_id) ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                  <span className="font-mono text-sky-400 uppercase tracking-wider font-semibold">{doc.source}</span>
                  <span className="text-slate-600">·</span>
                  <span className="font-mono text-slate-400">{doc.document_id}</span>
                  <span className="text-slate-600">·</span>
                  <span className="font-mono text-slate-500">{doc.chunk_id}</span>
                </div>
                <h3 className="text-sm font-semibold text-slate-100 pl-6 cursor-pointer hover:text-sky-300 transition-colors" onClick={() => toggleCollapse(doc.chunk_id)}>
                  {doc.path?.[doc.path.length - 1] || doc.chunk_id}
                </h3>
              </div>
              {doc.score !== undefined && (
                <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-md">
                  <span className="text-[11px] text-slate-500">Score</span>
                  <span className="font-mono text-xs font-semibold text-emerald-400 tabular-nums">
                    {doc.score.toFixed(2)}
                  </span>
                </div>
              )}
            </div>

            {!collapsedChunks.has(doc.chunk_id) && (
              <>
                {doc.path && doc.path.length > 0 && (
                  <div className="text-xs text-slate-400 mb-3 bg-slate-950/40 p-1.5 rounded border border-slate-800/40 ml-6 whitespace-nowrap overflow-x-auto">
                    {doc.path.join(' / ')}
                  </div>
                )}
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed font-sans bg-slate-950/30 p-3 rounded-lg border border-slate-800/60 mb-3 whitespace-pre-wrap ml-6">
                  {doc.text}
                </p>
              </>
            )}
            
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/60 mt-3 justify-end text-xs">
              <button
                onClick={() => onAskAboutChunk(doc.chunk_id, doc.path?.[doc.path.length - 1] || doc.chunk_id)}
                className="flex items-center gap-1 px-2.5 py-1 text-sky-400 hover:text-sky-300 bg-sky-950/40 hover:bg-sky-900/40 border border-sky-800/40 rounded transition-colors"
              >
                <span>Ask LLM</span>
                <ArrowUpRight className="w-3 h-3" />
              </button>
              <button
                onClick={() => onViewDoc(doc as SearchDocResponse)}
                className="flex items-center gap-1 px-2.5 py-1 text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded transition-colors"
              >
                <FileTextIcon className="w-3 h-3 text-sky-400" />
                <span>Read Full Document</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderDocument = (doc: SearchDocResponse) => {
    if (!doc.markdown_doc) return <pre className="text-xs text-slate-300">{JSON.stringify(doc, null, 2)}</pre>;
    const sections = parseDocumentSections(doc.markdown_doc);
    
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div>
            <h3 className="font-semibold text-slate-100">{doc.document_id}</h3>
            <p className="text-xs text-slate-400 mt-1">Source: {doc.source} · {sections.length} sections extracted</p>
          </div>
          <button
            onClick={() => onViewDoc(doc)}
            className="flex items-center gap-1 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold transition-colors"
          >
            <FileTextIcon className="w-4 h-4" />
            <span>Open in Full Viewer</span>
          </button>
        </div>
        
        <div className="space-y-3">
          {sections.map(sec => {
            let renderedHtml = '';
            try { renderedHtml = marked.parse(sec.markdown) as string; } 
            catch(e) { renderedHtml = `<pre>${sec.markdown}</pre>`; }
            
            return (
              <div key={sec.id} className="border border-slate-800 bg-slate-900/60 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 bg-slate-800/40 border-b border-slate-800/80">
                  <h4 className="text-sm font-semibold text-slate-200 truncate">{sec.title}</h4>
                  <span className="text-[11px] text-slate-500 font-mono">{sec.wordCount} words</span>
                </div>
                <div className="p-4 bg-slate-950/40">
                  <div 
                    className="prose prose-invert prose-slate max-w-none text-sm leading-relaxed 
                      prose-headings:text-slate-100 prose-headings:font-semibold 
                      prose-h1:text-lg prose-h2:text-base prose-h3:text-sm prose-h4:text-xs prose-h4:uppercase prose-h4:text-sky-400
                      prose-p:text-slate-300 prose-p:my-2 prose-code:text-sky-300 prose-code:bg-slate-800"
                    dangerouslySetInnerHTML={{ __html: renderedHtml }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderContent = () => {
    if (!selectedKey || !selectedData) return null;
    
    if (selectedKey.startsWith('aerolex_search_cache_')) {
      return renderSearchChunks(selectedData);
    } else if (selectedKey.startsWith('aerolex_doc_cache_')) {
      return renderDocument(selectedData);
    } else {
      // Memory or other
      return (
        <pre className="text-xs font-mono text-slate-300 bg-slate-950 p-4 rounded-lg overflow-x-auto border border-slate-800">
          {JSON.stringify(selectedData, null, 2)}
        </pre>
      );
    }
  };

  return (
    <div className="flex-1 flex flex-col md:flex-row h-full overflow-hidden bg-slate-900">
      {/* Sidebar: Key List */}
      <div className="w-full md:w-1/3 max-w-sm flex flex-col border-r border-slate-800 bg-slate-950/50">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sky-400 font-semibold">
            <Database className="w-5 h-5" />
            <h2>Persistent Cache</h2>
          </div>
          <button 
            onClick={handleClearAll}
            className="p-1.5 hover:bg-rose-500/20 text-rose-400 rounded-md transition-colors"
            title="Clear Cache"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2">
          {cacheKeys.length === 0 ? (
            <p className="p-4 text-center text-sm text-slate-500">No cached items found.</p>
          ) : (
            <div className="space-y-1">
              {cacheKeys.map(key => {
                const isDoc = key.startsWith('aerolex_doc_cache_');
                const isSearch = key.startsWith('aerolex_search_cache_');
                const isMemory = key.startsWith('aerolex_eu_user_query_memory_v2');
                
                let icon = <DatabaseZap className="w-4 h-4 text-slate-500" />;
                if (isDoc) icon = <FileText className="w-4 h-4 text-emerald-400" />;
                if (isSearch) icon = <Search className="w-4 h-4 text-sky-400" />;

                let displayName = key.replace('aerolex_', '');
                if (isDoc) displayName = key.replace('aerolex_doc_cache_', '');
                if (isSearch) displayName = key.replace('aerolex_search_cache_', '');
                
                return (
                  <button
                    key={key}
                    onClick={() => handleSelectKey(key)}
                    className={`w-full text-left flex items-center gap-2 p-2 rounded text-sm transition-colors group ${
                      selectedKey === key ? 'bg-slate-800 border-slate-700' : 'hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="shrink-0">{icon}</div>
                    <div className="truncate flex-1 font-mono text-xs text-slate-300">
                      {displayName}
                    </div>
                    <button
                      onClick={(e) => handleDeleteKey(key, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 transition-opacity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Main Area: Content Viewer */}
      <div className="flex-1 flex flex-col bg-slate-900 overflow-hidden">
        <div className="p-4 border-b border-slate-800 bg-slate-900 sticky top-0 z-10 flex items-center justify-between shadow-sm">
          <h2 className="font-semibold text-slate-200">
            {selectedKey ? selectedKey : 'Select an item to view'}
          </h2>
          {selectedKey && (
            <span className="text-xs font-mono text-slate-500 bg-slate-950 px-2 py-1 rounded">
              {isLoading ? 'Loading...' : `${JSON.stringify(selectedData).length} bytes`}
            </span>
          )}
        </div>
        
        <div className="flex-1 overflow-auto p-4 bg-slate-950/20">
          {!selectedKey ? (
            <div className="h-full flex items-center justify-center text-slate-500">
              <div className="text-center">
                <Database className="w-12 h-12 mx-auto mb-4 opacity-20" />
                <p>View cached full documents and search results.</p>
                <p className="text-sm mt-2 opacity-70">Saves API roundtrips and LLM costs.</p>
              </div>
            </div>
          ) : isLoading ? (
             <div className="flex items-center gap-2 text-sky-500">
               <div className="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
               <span className="text-sm">Reading from IndexedDB...</span>
             </div>
          ) : (
            renderContent()
          )}
        </div>
      </div>
    </div>
  );
};
