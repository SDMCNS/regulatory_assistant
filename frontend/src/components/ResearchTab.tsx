import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  Search, 
  Loader2, 
  FileText, 
  Activity, 
  Layers, 
  List,
  ChevronDown, 
  ChevronUp,
  ChevronRight, 
  CheckCircle2, 
  XCircle, 
  Copy, 
  Check, 
  Download, 
  Sparkles, 
  BookOpen, 
  ShieldCheck, 
  RefreshCw,
  ExternalLink,
  Info,
  Compass,
  RotateCcw,
  CheckCheck,
  Trash2,
  X,
  AlertTriangle,
  Ban,
  ShieldAlert,
  Cpu,
  Columns
} from 'lucide-react';
import { marked } from 'marked';
import { AppSettings, SearchDocResponse, ResearchJobSummary, ResearchJobDetail, DocSection } from '../types';
import { parseReportSections, getSectionStyle, countCitations, normalizeChunkCitations, findChunkExcerpt } from '../utils/sectionParser';
import { 
  createResearchJob, 
  listResearchJobs, 
  getResearchJob, 
  deleteResearchJob, 
  getDocumentMarkdown 
} from '../services/apiClient';

interface ResearchTabProps {
  settings: AppSettings;
  onViewDoc?: (doc: SearchDocResponse) => void;
  onAskAboutChunk?: (chunkId: string, docTitle: string) => void;
  onOpenWorkspaceWithDocs?: (documentIds: string[], initialQuery?: string) => void;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export const ResearchTab: React.FC<ResearchTabProps> = ({ 
  settings, 
  onViewDoc,
  onAskAboutChunk,
  onOpenWorkspaceWithDocs
}) => {
  const [query, setQuery] = useState('');
  const [recursionLevel, setRecursionLevel] = useState<number>(2);
  const [jobs, setJobs] = useState<ResearchJobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState<ResearchJobDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [activeChunkModal, setActiveChunkModal] = useState<{ id: string; text: string } | null>(null);
  const [loadingDocId, setLoadingDocId] = useState<string | null>(null);
  const [cacheNotification, setCacheNotification] = useState<string | null>(null);

  // Fetch jobs list from SQLite backend
  const fetchJobs = useCallback(async (autoSelectFirst = false) => {
    try {
      setIsRefreshing(true);
      const data = await listResearchJobs(settings);
      setJobs(data);
      
      // Auto-select first job if available and none selected
      if (data.length > 0 && autoSelectFirst) {
        setSelectedJobId(data[0].job_id);
      }
    } catch (e) {
      console.error('Failed to fetch research jobs', e);
    } finally {
      setIsRefreshing(false);
    }
  }, [settings]);

  // Load selected job details
  const loadJobDetail = useCallback(async (jobId: string) => {
    try {
      setIsLoadingDetail(true);
      const detail = await getResearchJob(jobId, settings);
      setSelectedJobDetail(detail);
    } catch (e) {
      console.error(`Failed to load job details for ${jobId}`, e);
    } finally {
      setIsLoadingDetail(false);
    }
  }, [settings]);

  // Initial load
  useEffect(() => {
    fetchJobs(true);
  }, []);

  // When selectedJobId changes, load detail
  useEffect(() => {
    if (selectedJobId) {
      loadJobDetail(selectedJobId);
    } else {
      setSelectedJobDetail(null);
    }
  }, [selectedJobId, loadJobDetail]);

  // Polling: poll every 4s if any job is PENDING or RUNNING
  useEffect(() => {
    const hasActiveJob = jobs.some(j => j.status === 'PENDING' || j.status === 'RUNNING') ||
      (selectedJobDetail && (selectedJobDetail.status === 'PENDING' || selectedJobDetail.status === 'RUNNING'));

    if (!hasActiveJob) return;

    const interval = setInterval(async () => {
      try {
        const updatedList = await listResearchJobs(settings);
        setJobs(updatedList);
        if (selectedJobId) {
          const detail = await getResearchJob(selectedJobId, settings);
          setSelectedJobDetail(detail);
        }
      } catch (err) {
        console.warn('Polling error for research jobs:', err);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [jobs, selectedJobId, selectedJobDetail, settings]);

  const handleSubmit = async (e?: React.FormEvent, forceRefresh = false, overrideQuery?: string) => {
    if (e) e.preventDefault();
    const targetQuery = overrideQuery !== undefined ? overrideQuery : query;
    if (!targetQuery.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setCacheNotification(null);
    try {
      const res = await createResearchJob(targetQuery.trim(), recursionLevel, forceRefresh, settings);
      if (overrideQuery === undefined) {
        setQuery('');
      }
      
      if (res.cached) {
        setCacheNotification('Loaded from preserved research archive (Result already verified).');
      }

      await fetchJobs(false);
      setSelectedJobId(res.job_id);
    } catch (e: any) {
      console.error('Failed to submit research job', e);
      alert(`Could not start research job: ${e.message || e}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRetryJob = (failedJob: ResearchJobDetail) => {
    handleSubmit(undefined, true, failedJob.query);
  };

  const handleDeleteJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this preserved research job?')) return;
    try {
      await deleteResearchJob(jobId, settings);
      if (selectedJobId === jobId) {
        setSelectedJobId(null);
        setSelectedJobDetail(null);
      }
      fetchJobs(false);
    } catch (err) {
      console.error('Failed to delete job', err);
    }
  };

  const handleOpenDoc = async (documentId: string) => {
    if (!onViewDoc) return;
    try {
      setLoadingDocId(documentId);
      const res = await getDocumentMarkdown(documentId, settings);
      const docItem: SearchDocResponse = {
        chunk_id: documentId,
        score: 1.0,
        source: 'Consulted Regulation',
        document_id: documentId,
        path: [documentId],
        text: '',
        metadata: { title: res.document_id },
        markdown_doc: res.markdown_doc
      };
      onViewDoc(docItem);
    } catch (e) {
      console.error('Failed to fetch document markdown', e);
      alert(`Could not load document: ${documentId}`);
    } finally {
      setLoadingDocId(null);
    }
  };

  const filteredJobs = useMemo(() => {
    if (!searchFilter.trim()) return jobs;
    const filter = searchFilter.toLowerCase();
    return jobs.filter(j => j.query.toLowerCase().includes(filter) || j.status.toLowerCase().includes(filter));
  }, [jobs, searchFilter]);

  return (
    <div className="flex h-[calc(100vh-61px)] bg-slate-950 text-slate-200 overflow-hidden font-sans">
      {/* Left Sidebar: Preserved Research Jobs */}
      <aside className="w-84 border-r border-slate-800/80 flex flex-col bg-slate-900/60 backdrop-blur shrink-0">
        <div className="p-3.5 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Layers className="w-4 h-4" />
            </span>
            <div>
              <h2 className="text-xs font-semibold text-white tracking-wide uppercase">Preserved Research</h2>
              <p className="text-[10px] text-slate-500">{jobs.length} archived report{jobs.length === 1 ? '' : 's'}</p>
            </div>
          </div>
          <button
            onClick={() => fetchJobs(false)}
            title="Refresh jobs list"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>

        {/* Filter input */}
        <div className="px-3 pt-2.5 pb-1.5">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search preserved research..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full bg-slate-950/70 border border-slate-800 rounded-md pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        {/* Jobs list */}
        <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
          {filteredJobs.map(job => {
            const isSelected = selectedJobId === job.job_id;
            return (
              <div
                key={job.job_id}
                onClick={() => {
                  setSelectedJobId(job.job_id);
                  setCacheNotification(null);
                }}
                className={`group relative p-3 rounded-lg border cursor-pointer transition-all duration-150 ${
                  isSelected
                    ? 'bg-indigo-950/40 border-indigo-500/70 shadow-sm shadow-indigo-950/50'
                    : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-850 hover:border-slate-700/80'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-medium border ${
                      job.recursion_level === 1 
                        ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60' 
                        : job.recursion_level === 2
                        ? 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60'
                        : 'bg-purple-950/60 text-purple-300 border-purple-800/60'
                    }`}>
                      Depth {job.recursion_level}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {new Date(job.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                    </span>
                    {job.provider === 'gemini' ? (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-700/60 flex items-center gap-1 font-semibold" title="Google Gemini Cloud">
                        <Sparkles className="w-2.5 h-2.5 text-indigo-400" />
                        Gemini
                      </span>
                    ) : job.provider ? (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1" title="Local LM Studio">
                        <Cpu className="w-2.5 h-2.5 text-slate-400" />
                        Local
                      </span>
                    ) : null}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {job.status === 'COMPLETED' ? (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Preserved</span>
                      </span>
                    ) : job.status === 'FAILED' ? (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-rose-400">
                        <XCircle className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Failed</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-sky-400">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span className="hidden sm:inline">Running</span>
                      </span>
                    )}

                    <button
                      onClick={(e) => handleDeleteJob(job.job_id, e)}
                      title="Delete preserved job"
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 hover:bg-slate-800 rounded transition-all"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                <p className="text-xs font-medium text-slate-200 line-clamp-2 leading-relaxed mb-2">
                  {job.query}
                </p>

                <div className="text-[10px] font-mono text-slate-400 truncate flex items-center gap-1.5 bg-slate-950/50 px-2 py-1 rounded border border-slate-800/60">
                  <Activity className="w-2.5 h-2.5 text-indigo-400 shrink-0" />
                  <span className="truncate">{job.progress || job.status}</span>
                </div>
              </div>
            );
          })}

          {filteredJobs.length === 0 && (
            <div className="text-center py-10 px-4 text-slate-500">
              <Compass className="w-8 h-8 mx-auto mb-2 text-slate-600 opacity-60" />
              <p className="text-xs font-medium text-slate-400">No research jobs yet</p>
              <p className="text-[11px] mt-1 text-slate-600">Submit a regulatory query to start research</p>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-slate-950 overflow-y-auto">
        {/* Research Input Form */}
        <section className="p-6 border-b border-slate-800/80 bg-slate-900/30 shrink-0">
          <form onSubmit={(e) => handleSubmit(e, false)} className="max-w-4xl mx-auto space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h1 className="text-xl font-bold text-white flex items-center gap-2.5">
                  <span className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-400 shadow-sm shadow-indigo-500/10">
                    <Sparkles className="w-5 h-5" />
                  </span>
                  Deep Regulatory Research
                </h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  Autonomous recursive exploration across official EASA & EU Aviation Regulations. Results are permanently preserved.
                </p>
              </div>

              <div className="flex items-center gap-2.5 flex-wrap">
                {/* Active LLM Provider Indicator */}
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium shadow-sm ${
                    settings.researchProvider === 'gemini'
                      ? 'bg-indigo-950/70 border-indigo-700/60 text-indigo-300'
                      : 'bg-slate-950/80 border-slate-800 text-slate-400'
                  }`}
                  title={
                    settings.researchProvider === 'gemini'
                      ? `Using Google Gemini Cloud (${settings.geminiModel || 'gemini-3.5-flash'}) for deep research`
                      : 'Using Local LM Studio Engine for deep research'
                  }
                >
                  {settings.researchProvider === 'gemini' ? (
                    <>
                      <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      <span>Gemini Cloud: <span className="font-mono text-[11px] text-indigo-200">{settings.geminiModel || 'gemini-3.5-flash'}</span></span>
                    </>
                  ) : (
                    <>
                      <Cpu className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>Local LM Studio</span>
                    </>
                  )}
                </div>

                {/* Depth Selector */}
                <div className="flex items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-lg">
                  {[
                    { level: 1, label: 'Fast (1x)', desc: 'Single-order synthesis' },
                    { level: 2, label: 'Thorough (2x)', desc: 'Two-stage gap analysis' },
                    { level: 3, label: 'Exhaustive (3x)', desc: 'Three recursive loops' }
                  ].map(({ level, label, desc }) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => setRecursionLevel(level)}
                      title={desc}
                      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                        recursionLevel === level
                          ? 'bg-indigo-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Query Input Box */}
            <div className="relative">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    handleSubmit(e, false);
                  }
                }}
                rows={2}
                placeholder="Enter regulatory inquiry for autonomous deep research (e.g., certification requirements, operational rules, AMC/GM standards)..."
                className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl p-3.5 pr-32 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-inner transition-all resize-none"
              />

              <div className="absolute right-3 bottom-3 flex items-center gap-2">
                <button
                  type="submit"
                  disabled={!query.trim() || isSubmitting}
                  className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 shadow-lg shadow-indigo-900/40 hover:shadow-indigo-800/60"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Processing...</span>
                    </>
                  ) : (
                    <>
                      <Search className="w-3.5 h-3.5" />
                      <span>Start Research</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {cacheNotification && (
              <div className="flex items-center justify-between gap-2 p-2.5 bg-emerald-950/60 border border-emerald-800/70 rounded-lg text-xs text-emerald-300">
                <div className="flex items-center gap-2">
                  <CheckCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>{cacheNotification}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setCacheNotification(null)}
                  className="text-emerald-400 hover:text-white text-xs px-2 py-0.5 rounded hover:bg-emerald-900"
                >
                  Dismiss
                </button>
              </div>
            )}
          </form>
        </section>

        {/* Report Content View */}
        <section className="flex-1 p-6">
          <div className="max-w-4xl mx-auto">
            {isLoadingDetail && !selectedJobDetail ? (
              <div className="border border-slate-800 rounded-2xl p-12 bg-slate-900/30 flex flex-col items-center justify-center min-h-[350px]">
                <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-3" />
                <p className="text-sm text-slate-400">Loading research job details...</p>
              </div>
            ) : selectedJobDetail ? (
              <ResearchReportViewer
                job={selectedJobDetail}
                onOpenChunkModal={(id, text) => setActiveChunkModal({ id, text })}
                onOpenDoc={handleOpenDoc}
                loadingDocId={loadingDocId}
                onRetry={() => handleRetryJob(selectedJobDetail)}
                onForceRerun={() => handleSubmit(undefined, true, selectedJobDetail.query)}
                onOpenWorkspaceWithDocs={onOpenWorkspaceWithDocs}
              />
            ) : (
              <div className="border border-slate-800/80 rounded-2xl p-12 bg-slate-900/20 text-center flex flex-col items-center justify-center min-h-[400px]">
                <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-4 shadow-xl">
                  <Compass className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold text-white mb-2">No Research Job Selected</h3>
                <p className="text-xs text-slate-400 max-w-md mb-6 leading-relaxed">
                  Select a preserved research job from the sidebar or enter an inquiry above to begin autonomous recursive exploration.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-lg text-left">
                  <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] font-mono text-indigo-400 font-bold block mb-1">01 / RETRIEVE</span>
                    <p className="text-[11px] text-slate-400">Hybrid vector and BM25 search across regulatory chunks.</p>
                  </div>
                  <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] font-mono text-indigo-400 font-bold block mb-1">02 / EXTRACT</span>
                    <p className="text-[11px] text-slate-400">Synthesizes regulatory facts with exact source chunk IDs.</p>
                  </div>
                  <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] font-mono text-indigo-400 font-bold block mb-1">03 / PRESERVE</span>
                    <p className="text-[11px] text-slate-400">Archived in database for immediate instant reuse.</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Full Chunk Inspector Modal */}
      {activeChunkModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
                  <FileText className="w-4 h-4" />
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-white">Cited Regulatory Chunk</h3>
                  <p className="text-[11px] font-mono text-indigo-400 truncate max-w-md">{activeChunkModal.id}</p>
                </div>
              </div>
              <button
                onClick={() => setActiveChunkModal(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto bg-slate-950 p-4 rounded-xl border border-slate-800/80 text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap selection:bg-indigo-600">
              {activeChunkModal.text}
            </div>

            <div className="flex items-center justify-between pt-4 mt-2 border-t border-slate-800">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(activeChunkModal.text);
                  alert('Chunk text copied to clipboard!');
                }}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition-colors"
              >
                <Copy className="w-3.5 h-3.5" />
                Copy Text
              </button>

              <button
                onClick={() => setActiveChunkModal(null)}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Configure marked with custom link renderer for chunk citations
marked.use({
  renderer: {
    link({ href, title, text }: any) {
      if (href && href.startsWith('chunk:')) {
        const chunkId = href.replace(/^chunk:/, '').trim();
        const safeId = escapeHtml(chunkId);
        const safeText = escapeHtml(text || 'Citation');

        return `<span class="chunk-cite-badge group relative inline-flex items-center mx-1 align-baseline cursor-pointer" data-chunk-id="${safeId}">` +
          `<button type="button" class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono font-medium text-indigo-300 bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/60 hover:border-indigo-500 shadow-sm transition-all select-none">` +
          `<svg class="w-3 h-3 text-indigo-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>` +
          `<span>${safeText}</span>` +
          `</button>` +
          `</span>`;
      }
      return false;
    }
  }
});

function renderMarkdownWithCitations(markdown: string): string {
  if (!markdown) return '';
  const preprocessed = normalizeChunkCitations(markdown);

  try {
    return marked.parse(preprocessed) as string;
  } catch (e) {
    return `<pre class="whitespace-pre-wrap">${escapeHtml(markdown)}</pre>`;
  }
}

interface ResearchReportViewerProps {
  job: ResearchJobDetail;
  onOpenChunkModal: (id: string, text: string) => void;
  onOpenDoc: (documentId: string) => void;
  loadingDocId: string | null;
  onRetry: () => void;
  onForceRerun: () => void;
  onOpenWorkspaceWithDocs?: (documentIds: string[], initialQuery?: string) => void;
}

const ResearchReportViewer: React.FC<ResearchReportViewerProps> = ({
  job,
  onOpenChunkModal,
  onOpenDoc,
  loadingDocId,
  onRetry,
  onForceRerun,
  onOpenWorkspaceWithDocs
}) => {
  // ALL HOOKS MUST BE UNCONDITIONALLY CALLED AT THE TOP LEVEL BEFORE ANY RETURN
  const [viewMode, setViewMode] = useState<'sections' | 'continuous'>('sections');
  const [sectionFilter, setSectionFilter] = useState('');
  const [openSectionIds, setOpenSectionIds] = useState<Record<string, boolean>>({});
  const [copiedSectionId, setCopiedSectionId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showRegs, setShowRegs] = useState(false);
  const [showAudit, setShowAudit] = useState(true);
  const [auditTab, setAuditTab] = useState<'all' | 'negated' | 'validated'>('all');
  const [hoveredTooltip, setHoveredTooltip] = useState<{
    chunkId: string;
    excerpt: string;
    top: number;
    left: number;
    showBelow: boolean;
  } | null>(null);

  // Parse structured report sections
  const sections = useMemo<DocSection[]>(() => {
    if (!job.report_markdown) return [];
    return parseReportSections(job.report_markdown);
  }, [job.report_markdown]);

  // Initial open state: expand all sections by default so report is immediately readable
  useEffect(() => {
    if (sections.length > 0) {
      const initialOpen: Record<string, boolean> = {};
      sections.forEach(s => {
        initialOpen[s.id] = true;
      });
      setOpenSectionIds(initialOpen);
    }
  }, [job.job_id, sections]);

  // Dismiss tooltip on scroll to prevent stale floating positions
  useEffect(() => {
    const handleScroll = () => setHoveredTooltip(null);
    window.addEventListener('scroll', handleScroll, true);
    return () => window.removeEventListener('scroll', handleScroll, true);
  }, []);

  const totalWords = useMemo(() => sections.reduce((acc, s) => acc + s.wordCount, 0), [sections]);
  const totalCitations = useMemo(() => Object.keys(job.referenced_chunks || {}).length, [job.referenced_chunks]);

  const filteredSections = useMemo(() => {
    if (!sectionFilter.trim()) return sections;
    const q = sectionFilter.toLowerCase();
    return sections.filter(s => s.title.toLowerCase().includes(q) || s.markdown.toLowerCase().includes(q));
  }, [sections, sectionFilter]);

  const continuousHtml = useMemo(() => {
    if (!job.report_markdown) return '';
    return renderMarkdownWithCitations(job.report_markdown);
  }, [job.report_markdown]);

  const handleExpandAll = () => {
    const allOpen: Record<string, boolean> = {};
    sections.forEach(s => {
      allOpen[s.id] = true;
    });
    setOpenSectionIds(allOpen);
  };

  const handleCollapseAll = () => {
    setOpenSectionIds({});
  };

  const toggleSection = (id: string) => {
    setOpenSectionIds(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  const handleCopySection = (sec: DocSection, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(sec.markdown);
    setCopiedSectionId(sec.id);
    setTimeout(() => setCopiedSectionId(null), 2000);
  };

  const handleCopyMarkdown = () => {
    if (!job.report_markdown) return;
    navigator.clipboard.writeText(job.report_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    if (!job.report_markdown) return;
    const blob = new Blob([job.report_markdown], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `Regulatory_Research_${job.job_id.slice(0, 8)}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleMouseOver = (e: React.MouseEvent) => {
    const badge = (e.target as HTMLElement).closest('.chunk-cite-badge');
    if (badge) {
      const chunkId = badge.getAttribute('data-chunk-id');
      if (chunkId) {
        const excerpt = findChunkExcerpt(chunkId, job.referenced_chunks, job.evaluation_summary);
        const rect = badge.getBoundingClientRect();
        const showBelow = rect.top < 180;
        const top = showBelow ? rect.bottom + 8 : rect.top - 8;
        const tooltipWidth = 320;
        const left = Math.max(16 + tooltipWidth / 2, Math.min(window.innerWidth - 16 - tooltipWidth / 2, rect.left + rect.width / 2));

        setHoveredTooltip({
          chunkId,
          excerpt,
          top,
          left,
          showBelow
        });
      }
    }
  };

  const handleMouseOut = (e: React.MouseEvent) => {
    const relatedTarget = e.relatedTarget as HTMLElement | null;
    if (!relatedTarget || !relatedTarget.closest('.chunk-cite-badge')) {
      setHoveredTooltip(null);
    }
  };

  const handleContainerClick = (e: React.MouseEvent) => {
    const badge = (e.target as HTMLElement).closest('.chunk-cite-badge');
    if (badge) {
      e.preventDefault();
      e.stopPropagation();
      const chunkId = badge.getAttribute('data-chunk-id');
      if (chunkId) {
        const excerpt = findChunkExcerpt(chunkId, job.referenced_chunks, job.evaluation_summary);
        onOpenChunkModal(chunkId, excerpt);
      }
    }
  };

  // Conditional Rendering AFTER all hooks have executed
  if (job.status !== 'COMPLETED') {
    return (
      <div className="border border-slate-800 rounded-2xl p-8 bg-slate-900/40 backdrop-blur flex flex-col items-center justify-center min-h-[380px] shadow-xl">
        {job.status === 'FAILED' ? (
          <div className="text-center max-w-md">
            <div className="w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/30 flex items-center justify-center mx-auto mb-4 text-rose-400 shadow-lg shadow-rose-950/50">
              <XCircle className="w-7 h-7" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Research Operation Failed</h3>
            <p className="text-xs text-rose-400 font-mono bg-rose-950/40 p-3 rounded-lg border border-rose-900/60 mb-4 break-words">
              {job.progress}
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={onRetry}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg flex items-center gap-2 shadow-lg shadow-indigo-900/40 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Retry Research
              </button>
            </div>
          </div>
        ) : (
          <div className="text-center max-w-lg w-full">
            <div className="w-14 h-14 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center mx-auto mb-4 text-indigo-400 shadow-lg shadow-indigo-950/50 relative">
              <Activity className="w-7 h-7 animate-pulse" />
              <div className="absolute inset-0 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
            </div>

            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800 uppercase tracking-wider font-semibold inline-block mb-2">
              Recursion Level {job.recursion_level} In Progress
            </span>

            <h3 className="text-base font-semibold text-white mb-2">{job.query}</h3>
            
            <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3 mb-6 inline-block w-full">
              <div className="flex items-center justify-center gap-2 text-xs font-mono text-indigo-300">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400 shrink-0" />
                <span className="truncate">{job.progress || 'Processing regulatory chunks...'}</span>
              </div>
            </div>

            <div className="w-full max-w-md mx-auto bg-slate-900 border border-slate-800 rounded-full h-2 overflow-hidden mb-4">
              <div className="bg-gradient-to-r from-sky-500 via-indigo-500 to-purple-500 h-full w-2/3 rounded-full animate-pulse" />
            </div>

            <p className="text-[11px] text-slate-500 flex items-center justify-center gap-1.5">
              <Info className="w-3.5 h-3.5" />
              <span>Jobs run asynchronously in the background. You can safely switch tabs while this completes.</span>
            </p>
          </div>
        )}
      </div>
    );
  }

  const consultedCount = job.consulted_regulations?.length || 0;

  return (
    <div className="space-y-5 animate-in fade-in slide-in-from-bottom-3 duration-300">
      {/* Report Header Card */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl backdrop-blur flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1 font-semibold">
              <CheckCircle2 className="w-3 h-3" />
              Preserved Report
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800 font-semibold">
              Depth Level {job.recursion_level}
            </span>
            <span className="text-xs text-slate-500">
              {new Date(job.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
            {job.provider === 'gemini' ? (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-700/80 flex items-center gap-1 font-semibold">
                <Sparkles className="w-3 h-3 text-indigo-400" />
                Google Gemini Cloud ({job.model || 'gemini-3.8-flash'})
              </span>
            ) : job.provider ? (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1 font-medium">
                <Cpu className="w-3 h-3 text-slate-400" />
                Local LM Studio ({job.model || 'Local Model'})
              </span>
            ) : null}
            {job.evaluation_summary && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 flex items-center gap-1 font-medium" title="Scientific audit of retrieved chunks">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                Evidence Audit: {job.evaluation_summary.validated_count} Validated · {job.evaluation_summary.negated_count} Negated
              </span>
            )}
          </div>

          <h2 className="text-lg font-bold text-white leading-snug">{job.query}</h2>

          <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
            <span className="flex items-center gap-1.5 font-medium">
              <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
              <span>{consultedCount} Regulations Consulted</span>
            </span>
            {consultedCount > 0 && onOpenWorkspaceWithDocs && (
              <button
                type="button"
                onClick={() => {
                  const docIds = Array.from(new Set((job.consulted_regulations || []).map(r => r.document_id).filter(Boolean)));
                  onOpenWorkspaceWithDocs(docIds, job.query);
                }}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/70 hover:border-indigo-500 text-indigo-300 text-[11px] font-medium shadow-sm transition-all"
                title="Open all consulted regulatory sources in dedicated overlap workspace"
              >
                <Columns className="w-3 h-3 text-indigo-400" />
                <span>Open in Workspace</span>
              </button>
            )}
            <span aria-hidden="true" className="text-slate-700">·</span>
            <span className="flex items-center gap-1.5 font-medium">
              <FileText className="w-3.5 h-3.5 text-sky-400" />
              <span>{totalCitations} Cited Chunks</span>
            </span>
            <span aria-hidden="true" className="text-slate-700">·</span>
            <span className="flex items-center gap-1.5 font-medium">
              <Layers className="w-3.5 h-3.5 text-purple-400" />
              <span>{sections.length} Sections</span>
            </span>
            <span aria-hidden="true" className="text-slate-700">·</span>
            <span className="font-mono text-slate-400">
              {totalWords.toLocaleString()} words
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
          <button
            onClick={onForceRerun}
            title="Re-run deep research from scratch on this query"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 border border-slate-700 transition-colors shadow-sm"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
            <span>Re-run</span>
          </button>

          <button
            onClick={handleCopyMarkdown}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 border border-slate-700 transition-colors shadow-sm"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
            <span>{copied ? 'Copied!' : 'Copy'}</span>
          </button>

          <button
            onClick={handleDownloadMarkdown}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition-colors shadow-sm"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download</span>
          </button>
        </div>
      </div>

      {/* Sections Viewer Controls & Filter Bar */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 shadow-lg backdrop-blur">
        {/* View Mode Toggle */}
        <div className="flex items-center p-0.5 bg-slate-950 border border-slate-800 rounded-lg text-xs shrink-0">
          <button
            onClick={() => setViewMode('sections')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
              viewMode === 'sections' 
                ? 'bg-indigo-600 text-white font-medium shadow-sm' 
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="View segmented by sections"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Sections ({sections.length})</span>
          </button>
          <button
            onClick={() => setViewMode('continuous')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
              viewMode === 'continuous' 
                ? 'bg-indigo-600 text-white font-medium shadow-sm' 
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="View as continuous document"
          >
            <List className="w-3.5 h-3.5" />
            <span>Continuous</span>
          </button>
        </div>

        {/* Section Filter Input */}
        {viewMode === 'sections' && (
          <div className="relative flex-1 max-w-md">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter report sections..."
              value={sectionFilter}
              onChange={(e) => setSectionFilter(e.target.value)}
              className="w-full bg-slate-950/70 border border-slate-800 rounded-lg pl-8 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors shadow-inner"
            />
            {sectionFilter && (
              <button
                onClick={() => setSectionFilter('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
                title="Clear filter"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        )}

        {/* Expand / Collapse All buttons */}
        {viewMode === 'sections' && (
          <div className="flex items-center gap-2 shrink-0 text-xs">
            <button
              onClick={handleExpandAll}
              className="px-2.5 py-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
            >
              Expand All
            </button>
            <span className="text-slate-700">|</span>
            <button
              onClick={handleCollapseAll}
              className="px-2.5 py-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
            >
              Collapse All
            </button>
          </div>
        )}
      </div>

      {/* Main Report View: Sections or Continuous */}
      {viewMode === 'sections' ? (
        <div 
          className="space-y-3"
          onMouseOver={handleMouseOver}
          onMouseOut={handleMouseOut}
          onClick={handleContainerClick}
        >
          {filteredSections.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded-xl bg-slate-900/30">
              No report sections match "{sectionFilter}".
            </div>
          ) : (
            filteredSections.map((sec) => {
              const isOpen = openSectionIds[sec.id] ?? false;
              const style = getSectionStyle(sec.type);
              const citeCount = sec.citationCount ?? countCitations(sec.markdown);

              return (
                <div
                  key={sec.id}
                  id={`sec-card-${sec.id}`}
                  className={`border rounded-xl transition-all duration-200 overflow-hidden ${
                    isOpen 
                      ? 'border-slate-700/80 bg-slate-900/70 shadow-lg shadow-black/20' 
                      : 'border-slate-800/80 bg-slate-900/40 hover:border-slate-700/60'
                  }`}
                >
                  {/* Card Header */}
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
                          <ChevronUp className="w-4 h-4 text-indigo-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>

                      {/* Section Type Badge */}
                      <span className={`px-2 py-0.5 text-[11px] font-medium border rounded-md shrink-0 ${style.badgeClass}`}>
                        {style.label}
                      </span>

                      {/* Section Title */}
                      <h3 className="text-sm font-semibold text-slate-200 truncate flex-1">
                        {sec.title}
                      </h3>
                    </div>

                    {/* Right Meta & Actions */}
                    <div className="flex items-center gap-2.5 shrink-0">
                      {citeCount > 0 && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono font-medium bg-indigo-950/80 text-indigo-300 border border-indigo-800/60 rounded-md">
                          <FileText className="w-3 h-3 text-indigo-400" />
                          <span>{citeCount} cite{citeCount > 1 ? 's' : ''}</span>
                        </span>
                      )}

                      <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
                        {sec.wordCount} words
                      </span>

                      <button
                        onClick={(e) => handleCopySection(sec, e)}
                        title="Copy section markdown"
                        className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md transition-colors"
                      >
                        {copiedSectionId === sec.id ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Section Content Body */}
                  {isOpen && (
                    <div className="px-6 py-5 border-t border-slate-800/80 bg-slate-950/40">
                      <div
                        className="prose prose-invert prose-indigo max-w-none 
                          prose-headings:text-indigo-100 prose-headings:font-bold 
                          prose-h1:text-xl prose-h1:border-b prose-h1:border-slate-800 prose-h1:pb-2.5 prose-h1:mb-4
                          prose-h2:text-base prose-h2:mt-5 prose-h2:mb-2.5 prose-h2:text-indigo-200
                          prose-h3:text-sm prose-h3:mt-3.5 prose-h3:mb-2 prose-h3:text-slate-200
                          prose-p:text-slate-300 prose-p:leading-relaxed prose-p:text-sm
                          prose-li:text-slate-300 prose-li:text-sm
                          prose-strong:text-white prose-strong:font-semibold
                          prose-table:text-xs prose-th:text-slate-200 prose-td:text-slate-300
                          prose-hr:border-slate-800 prose-hr:my-4"
                        dangerouslySetInnerHTML={{ __html: renderMarkdownWithCitations(sec.markdown) }}
                      />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      ) : (
        /* Continuous Document View */
        <div 
          onMouseOver={handleMouseOver} 
          onMouseOut={handleMouseOut} 
          onClick={handleContainerClick}
          className="bg-slate-900/50 border border-slate-800/80 rounded-2xl p-8 shadow-xl backdrop-blur"
        >
          <div
            className="prose prose-invert prose-indigo max-w-none 
              prose-headings:text-indigo-100 prose-headings:font-bold 
              prose-h1:text-2xl prose-h1:border-b prose-h1:border-slate-800 prose-h1:pb-3 prose-h1:mb-6
              prose-h2:text-lg prose-h2:mt-6 prose-h2:mb-3 prose-h2:text-indigo-200
              prose-h3:text-base prose-h3:mt-4 prose-h3:mb-2 prose-h3:text-slate-200
              prose-p:text-slate-300 prose-p:leading-relaxed prose-p:text-sm
              prose-li:text-slate-300 prose-li:text-sm
              prose-strong:text-white prose-strong:font-semibold
              prose-table:text-xs prose-th:text-slate-200 prose-td:text-slate-300
              prose-hr:border-slate-800 prose-hr:my-6"
            dangerouslySetInnerHTML={{ __html: continuousHtml }}
          />
        </div>
      )}

      {/* Collapsible Scientific Evidence & Negation Audit Accordion */}
      <div className="border border-slate-800/80 rounded-2xl bg-slate-900/40 backdrop-blur overflow-hidden shadow-xl">
        <button
          onClick={() => setShowAudit(!showAudit)}
          className="w-full flex items-center justify-between p-4 bg-slate-900/70 hover:bg-slate-850 transition-colors text-left"
        >
          <div className="flex items-center gap-2.5">
            <span className="p-1 rounded-md bg-indigo-500/10 text-indigo-400">
              <ShieldAlert className="w-4 h-4" />
            </span>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-200 uppercase tracking-wide">
                  Scientific Evidence & Negation Audit
                </span>
                {job.evaluation_summary && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800 font-medium">
                    {job.evaluation_summary.validated_count} Validated · {job.evaluation_summary.negated_count} Negated
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Critique, falsification, and boundary verification of retrieved chunks (excluding out-of-scope rules like VTOL)
              </p>
            </div>
          </div>
          {showAudit ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>

        {showAudit && (
          <div className="p-5 border-t border-slate-800/80 space-y-4">
            {job.evaluation_summary ? (
              <>
                {/* Scope & Boundary Pills */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
                  <div className="space-y-1.5">
                    <div className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Target Governing Domains</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {job.evaluation_summary.target_domains && job.evaluation_summary.target_domains.length > 0 ? (
                        job.evaluation_summary.target_domains.map((td, i) => (
                          <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60">
                            {td}
                          </span>
                        ))
                      ) : (
                        <span className="text-[10px] text-slate-500">Autonomous domain inference</span>
                      )}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <div className="text-[11px] font-semibold text-rose-400 flex items-center gap-1.5">
                      <Ban className="w-3.5 h-3.5" />
                      <span>Explicit Falsification Boundaries (Out of Scope)</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {job.evaluation_summary.excluded_domains && job.evaluation_summary.excluded_domains.length > 0 ? (
                        job.evaluation_summary.excluded_domains.map((ed, i) => (
                          <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/60 line-through">
                            {ed}
                          </span>
                        ))
                      ) : (
                        <span className="text-[10px] text-slate-500">None declared</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Audit Tabs */}
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setAuditTab('all')}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                        auditTab === 'all'
                          ? 'bg-indigo-600 text-white'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      All ({job.evaluation_summary.total_evaluated})
                    </button>
                    <button
                      type="button"
                      onClick={() => setAuditTab('negated')}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium flex items-center gap-1 transition-colors ${
                        auditTab === 'negated'
                          ? 'bg-rose-600 text-white'
                          : 'text-rose-400 hover:text-rose-300'
                      }`}
                    >
                      <Ban className="w-3 h-3" />
                      <span>Negated ({job.evaluation_summary.negated_count})</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setAuditTab('validated')}
                      className={`px-2.5 py-1 text-xs rounded-md font-medium flex items-center gap-1 transition-colors ${
                        auditTab === 'validated'
                          ? 'bg-emerald-600 text-white'
                          : 'text-emerald-400 hover:text-emerald-300'
                      }`}
                    >
                      <CheckCircle2 className="w-3 h-3" />
                      <span>Validated ({job.evaluation_summary.validated_count})</span>
                    </button>
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Audit Ledger
                  </span>
                </div>

                {/* Evaluated Chunks Cards */}
                <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
                  {/* Negated Chunks */}
                  {(auditTab === 'all' || auditTab === 'negated') &&
                    Object.entries(job.evaluation_summary.negated_chunks || {}).map(([cid, reason]) => (
                      <div
                        key={cid}
                        className="p-3 rounded-xl bg-rose-950/20 border border-rose-900/40 hover:border-rose-800/60 transition-colors space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded font-bold uppercase bg-rose-950 text-rose-300 border border-rose-800 flex items-center gap-1">
                              <Ban className="w-3 h-3" />
                              REJECTED / OUT OF SCOPE
                            </span>
                            <button
                              type="button"
                              onClick={() => {
                                const text = findChunkExcerpt(cid, job.referenced_chunks, job.evaluation_summary);
                                onOpenChunkModal(cid, text);
                              }}
                              className="text-xs font-mono text-slate-300 font-semibold hover:text-indigo-400 hover:underline text-left"
                              title="Click to inspect chunk text"
                            >
                              {cid}
                            </button>
                          </div>
                          <span className="text-[10px] font-mono text-rose-400/80">
                            Purged from Report Facts & Citations
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed pl-1 border-l-2 border-rose-800/80">
                          <strong className="text-rose-300">Critique & Falsification:</strong> {reason}
                        </p>
                      </div>
                    ))}

                  {/* Validated Chunks */}
                  {(auditTab === 'all' || auditTab === 'validated') &&
                    Object.entries(job.evaluation_summary.validated_chunks || {}).map(([cid, valueSummary]) => (
                      <div
                        key={cid}
                        className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-900/40 hover:border-emerald-800/60 transition-colors space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded font-bold uppercase bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" />
                              VALIDATED RELEVANCE
                            </span>
                            <button
                              type="button"
                              onClick={() => {
                                const text = findChunkExcerpt(cid, job.referenced_chunks, job.evaluation_summary);
                                onOpenChunkModal(cid, text);
                              }}
                              className="text-xs font-mono text-slate-300 font-semibold hover:text-indigo-400 hover:underline text-left"
                              title="Click to inspect chunk text"
                            >
                              {cid}
                            </button>
                          </div>
                          <span className="text-[10px] font-mono text-emerald-400/80">
                            Retained for Synthesis
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed pl-1 border-l-2 border-emerald-800/80">
                          <strong className="text-emerald-300">Genuine Regulatory Value:</strong> {valueSummary}
                        </p>
                      </div>
                    ))}

                  {job.evaluation_summary.total_evaluated === 0 && (
                    <div className="text-center py-6 text-xs text-slate-500">
                      No candidate chunks evaluated in this run.
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-2">
                <p>
                  This research report was preserved prior to the activation of the Scientific Adversarial Negation Gate.
                </p>
                <p className="text-slate-500 text-[11px]">
                  Click <strong className="text-slate-300">"Re-run"</strong> at the top to re-execute with autonomous chunk questioning, VTOL/out-of-scope falsification, and to-and-fro query refinement.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Collapsible Consulted Regulations Accordion */}
      <div className="border border-slate-800/80 rounded-2xl bg-slate-900/40 backdrop-blur overflow-hidden shadow-xl">
        <button
          onClick={() => setShowRegs(!showRegs)}
          className="w-full flex items-center justify-between p-4 bg-slate-900/70 hover:bg-slate-850 transition-colors text-left"
        >
          <div className="flex items-center gap-2.5">
            <span className="p-1 rounded-md bg-sky-500/10 text-sky-400">
              <ShieldCheck className="w-4 h-4" />
            </span>
            <span className="text-xs font-semibold text-slate-200 uppercase tracking-wide">
              Consulted Regulatory Sources ({consultedCount})
            </span>
          </div>
          {showRegs ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>

        {showRegs && (
          <div className="p-5 border-t border-slate-800/80 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <div>
                <h4 className="text-xs font-semibold text-slate-200">
                  Examine Consulted Regulatory Sources in Dedicated Workspace
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Cross-reference consulted regulations, run FTS overlap searches, and compare requirement chunks side-by-side.
                </p>
              </div>
              {onOpenWorkspaceWithDocs && consultedCount > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    const docIds = Array.from(new Set((job.consulted_regulations || []).map(r => r.document_id).filter(Boolean)));
                    onOpenWorkspaceWithDocs(docIds, job.query);
                  }}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md transition-all shrink-0"
                >
                  <Columns className="w-3.5 h-3.5" />
                  <span>Open All in Workspace</span>
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {job.consulted_regulations?.map((reg, idx) => (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition-colors flex items-start justify-between gap-3 group"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold uppercase ${
                        (reg.source || '').toLowerCase().includes('easa')
                          ? 'bg-sky-950 text-sky-400 border border-sky-800'
                          : 'bg-indigo-950 text-indigo-400 border border-indigo-800'
                      }`}>
                        {reg.source || 'Regulation'}
                      </span>
                      <span className="text-[10px] font-mono text-slate-500 truncate">{reg.document_id}</span>
                    </div>

                    <h4 className="text-xs font-medium text-slate-200 line-clamp-2 leading-snug">
                      {reg.document_title || reg.title || reg.document_id}
                    </h4>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {onOpenWorkspaceWithDocs && (
                      <button
                        type="button"
                        onClick={() => onOpenWorkspaceWithDocs([reg.document_id], job.query)}
                        title="Open this regulation in Workspace"
                        className="p-2 text-slate-400 hover:text-indigo-300 hover:bg-slate-900 rounded-lg transition-colors border border-transparent hover:border-slate-800"
                      >
                        <Columns className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {onOpenDoc && (
                      <button
                        onClick={() => onOpenDoc(reg.document_id)}
                        disabled={loadingDocId === reg.document_id}
                        title="Inspect full regulation document"
                        className="p-2 text-slate-400 hover:text-indigo-300 hover:bg-slate-900 rounded-lg transition-colors border border-transparent hover:border-slate-800"
                      >
                        {loadingDocId === reg.document_id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                        ) : (
                          <ExternalLink className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Floating Fixed Portal Tooltip for Citation Badges */}
      {hoveredTooltip && (
        <div
          style={{
            top: `${hoveredTooltip.top}px`,
            left: `${hoveredTooltip.left}px`,
          }}
          className={`fixed z-[9999] w-80 p-3.5 bg-slate-900/98 backdrop-blur-md border border-indigo-500/60 rounded-xl shadow-2xl text-left pointer-events-none -translate-x-1/2 transition-all duration-150 animate-in fade-in zoom-in-95 ${
            hoveredTooltip.showBelow ? 'translate-y-0' : '-translate-y-full'
          }`}
        >
          <div className="flex items-center justify-between pb-1.5 mb-2 border-b border-slate-800 text-[10px] font-mono text-indigo-300 font-semibold gap-2">
            <span className="truncate">ID: {hoveredTooltip.chunkId}</span>
            <span className="text-[9px] bg-indigo-950 text-indigo-400 px-1.5 py-0.5 rounded border border-indigo-800 shrink-0">Chunk</span>
          </div>
          <div className="line-clamp-6 text-slate-300 text-xs leading-relaxed font-normal">
            {hoveredTooltip.excerpt}
          </div>
          <div className="flex items-center justify-between mt-2.5 pt-1.5 border-t border-slate-800/60 text-[10px] text-indigo-400 font-mono">
            <span>Click to view full chunk</span>
            <span className="text-slate-500">AeroLex Reference</span>
          </div>
          {/* Arrow pointing to badge */}
          <div
            className={`absolute left-1/2 -translate-x-1/2 border-4 border-transparent ${
              hoveredTooltip.showBelow
                ? 'bottom-full -mb-px border-b-slate-900'
                : 'top-full -mt-px border-t-slate-900'
            }`}
          />
        </div>
      )}
    </div>
  );
};
