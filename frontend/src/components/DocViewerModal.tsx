/**
 * Modal to view full markdown document and metadata from /search/docs
 */

import React, { useMemo } from 'react';
import { X, Copy, Check, FileText, ExternalLink, BookmarkPlus } from 'lucide-react';
import { SearchDocResponse } from '../types';
import { marked } from 'marked';

interface DocViewerModalProps {
  doc: SearchDocResponse | null;
  onClose: () => void;
  onAskAboutChunk?: (chunkId: string, docTitle: string) => void;
}

export const DocViewerModal: React.FC<DocViewerModalProps> = ({
  doc,
  onClose,
  onAskAboutChunk,
}) => {
  const [copied, setCopied] = React.useState(false);

  const renderedMarkdown = useMemo(() => {
    if (!doc?.markdown_doc) return '';
    try {
      return marked.parse(doc.markdown_doc);
    } catch (e) {
      return `<pre class="whitespace-pre-wrap">${doc.markdown_doc}</pre>`;
    }
  }, [doc]);

  if (!doc) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(doc.markdown_doc || doc.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative flex flex-col w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90 shrink-0">
          <div className="flex items-center gap-3 min-w-0 pr-4">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20 shrink-0">
              <FileText className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span className="font-mono text-sky-400 uppercase tracking-wider">{doc.source}</span>
                <span aria-hidden="true">·</span>
                <span className="font-mono">{doc.document_id}</span>
                <span aria-hidden="true">·</span>
                <span className="font-mono text-emerald-400">Score: {(doc.score * 100).toFixed(1)}%</span>
              </div>
              <h2 className="text-base font-semibold text-slate-100 truncate">
                {doc.path[doc.path.length - 1] || doc.chunk_id}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {onAskAboutChunk && (
              <button
                onClick={() => {
                  onAskAboutChunk(doc.chunk_id, doc.path[doc.path.length - 1] || doc.chunk_id);
                  onClose();
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-sky-300 bg-sky-950/60 hover:bg-sky-900/60 border border-sky-800/60 rounded-md transition-colors whitespace-nowrap"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Ask LLM</span>
              </button>
            )}

            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-md transition-colors whitespace-nowrap"
              title="Copy markdown text"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
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
        <div className="px-6 py-2 bg-slate-950/50 border-b border-slate-800/80 text-xs text-slate-400 overflow-x-auto whitespace-nowrap shrink-0">
          <span className="text-slate-500 mr-2">Path:</span>
          {doc.path.map((segment, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && <span className="mx-1 text-slate-600">/</span>}
              <span className={idx === doc.path.length - 1 ? 'text-slate-200 font-medium' : 'text-slate-400'}>
                {segment}
              </span>
            </React.Fragment>
          ))}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Matched Chunk Highlight Box */}
          <div className="p-4 bg-sky-950/20 border border-sky-800/40 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-sky-400">
                Matched Search Chunk ({doc.chunk_id})
              </span>
            </div>
            <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed font-sans">
              {doc.text}
            </p>
          </div>

          {/* Full Markdown Document */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
              Full Regulatory Document Representation
            </h3>
            <div 
              className="prose prose-invert prose-slate max-w-none text-sm leading-relaxed 
                prose-headings:text-slate-100 prose-headings:font-semibold 
                prose-h1:text-lg prose-h2:text-base prose-h3:text-sm prose-h4:text-xs prose-h4:uppercase prose-h4:tracking-wider prose-h4:text-sky-400
                prose-p:text-slate-300 prose-p:my-2
                prose-ul:text-slate-300 prose-li:my-1
                prose-strong:text-slate-100 prose-code:text-sky-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                prose-blockquote:border-sky-500/50 prose-blockquote:bg-sky-950/20 prose-blockquote:text-slate-300 prose-blockquote:py-1 prose-blockquote:px-4"
              dangerouslySetInnerHTML={{ __html: renderedMarkdown }}
            />
          </div>

          {/* Metadata Accordion / Block */}
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
