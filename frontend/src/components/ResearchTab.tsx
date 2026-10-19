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
import { 
  AppSettings, 
  SearchDocResponse, 
  ResearchJobSummary, 
  ResearchJobDetail, 
  DocSection, 
  ChunkContextSummaryResponse,
  ResearchGap,
  SkybraryReadingMaterial,
  UserNoteReadingMaterial
} from '../types';
import { parseReportSections, getSectionStyle, countCitations, normalizeChunkCitations, findChunkExcerpt } from '../utils/sectionParser';
import { 
  downloadResearchReportHtml, 
  downloadResearchReportMarkdown 
} from '../utils/reportHtmlGenerator';
import { 
  createResearchJob, 
  listResearchJobs, 
  getResearchJob, 
  deleteResearchJob, 
  getDocumentMarkdown,
  getChunkContextSummary,
  generateComprehensiveReport
} from '../services/apiClient';
import { SourceFilterSelector, ALL_SOURCE_IDS } from './SourceFilterSelector';

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
  const [selectedSources, setSelectedSources] = useState<string[]>(() => ALL_SOURCE_IDS);
  const [jobs, setJobs] = useState<ResearchJobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState<ResearchJobDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [activeChunkModal, setActiveChunkModal] = useState<{ id: string; text: string; initialTab?: 'focal' | 'context' } | null>(null);
  const [modalTab, setModalTab] = useState<'focal' | 'context'>('focal');
  const [chunkContexts, setChunkContexts] = useState<Record<string, ChunkContextSummaryResponse>>({});
  const [loadingContextId, setLoadingContextId] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [copiedContextKey, setCopiedContextKey] = useState<string | null>(null);
  const [loadingDocId, setLoadingDocId] = useState<string | null>(null);
  const [cacheNotification, setCacheNotification] = useState<string | null>(null);
  const [isGeneratingComprehensive, setIsGeneratingComprehensive] = useState(false);

  const handleGenerateComprehensive = async (jobId: string) => {
    try {
      setIsGeneratingComprehensive(true);
      await generateComprehensiveReport(jobId, settings);
      const detail = await getResearchJob(jobId, settings);
      setSelectedJobDetail(detail);
      const updatedList = await listResearchJobs(settings);
      setJobs(updatedList);
    } catch (err: any) {
      alert(`Failed to start comprehensive report: ${err.message}`);
    } finally {
      setIsGeneratingComprehensive(false);
    }
  };

  const handleFetchChunkContext = async (chunkId: string) => {
    if (chunkContexts[chunkId]) return;
    setLoadingContextId(chunkId);
    setContextError(null);
    try {
      const activeQ = selectedJobDetail?.query || 'General aviation regulatory requirements and compliance';
      const res = await getChunkContextSummary(chunkId, activeQ, 2, settings);
      setChunkContexts(prev => ({ ...prev, [chunkId]: res }));
    } catch (err: any) {
      console.error('Failed to fetch surrounding chunk context in research:', err);
      setContextError(err.message || 'Failed to synthesize surrounding context');
    } finally {
      setLoadingContextId(null);
    }
  };

  const handleOpenChunkModal = (id: string, text: string, initialTab: 'focal' | 'context' = 'focal') => {
    setActiveChunkModal({ id, text, initialTab });
    setModalTab(initialTab);
    if (initialTab === 'context') {
      handleFetchChunkContext(id);
    }
  };

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

  // Polling: poll every 4s if any job is PENDING or RUNNING (including comprehensive report generation)
  useEffect(() => {
    const hasActiveJob = jobs.some(j => j.status === 'PENDING' || j.status === 'RUNNING' || j.comprehensive_status === 'RUNNING') ||
      (selectedJobDetail && (
        selectedJobDetail.status === 'PENDING' || 
        selectedJobDetail.status === 'RUNNING' || 
        selectedJobDetail.comprehensive_status === 'RUNNING'
      ));

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
      const isAllSources = ALL_SOURCE_IDS.every(s => selectedSources.includes(s));
      const originsToSend = isAllSources ? undefined : selectedSources;
      const res = await createResearchJob(targetQuery.trim(), recursionLevel, forceRefresh, settings, originsToSend);
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
    if (failedJob.origins && failedJob.origins.length > 0) {
      setSelectedSources(failedJob.origins);
    }
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

                <p className="text-xs font-medium text-slate-200 line-clamp-2 leading-relaxed mb-1.5">
                  {job.query}
                </p>

                {job.origins && job.origins.length > 0 && job.origins.length < 7 && (
                  <div className="flex items-center gap-1 mb-1.5 flex-wrap">
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 font-medium">
                      {job.origins.map(o => o.toUpperCase()).join(' · ')}
                    </span>
                  </div>
                )}

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

            {/* Source Selection & Exclusion Filter */}
            <SourceFilterSelector
              selectedSources={selectedSources}
              onChange={setSelectedSources}
            />

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
                onOpenChunkModal={(id, text, initialTab) => handleOpenChunkModal(id, text, initialTab)}
                onOpenDoc={handleOpenDoc}
                loadingDocId={loadingDocId}
                onRetry={() => handleRetryJob(selectedJobDetail)}
                onForceRerun={() => handleSubmit(undefined, true, selectedJobDetail.query)}
                onOpenWorkspaceWithDocs={onOpenWorkspaceWithDocs}
                onGenerateComprehensive={handleGenerateComprehensive}
                isGeneratingComprehensive={isGeneratingComprehensive}
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
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700/90 rounded-2xl max-w-3xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[88vh]">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-3">
              <div className="flex items-center gap-2.5">
                <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
                  <FileText className="w-4 h-4" />
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-white">Cited Regulatory Chunk Inspector</h3>
                  <p className="text-[11px] font-mono text-indigo-400 truncate max-w-md">{activeChunkModal.id}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveChunkModal(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* View Mode Tabs */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setModalTab('focal')}
                  className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                    modalTab === 'focal'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  Focal Provision Text
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setModalTab('context');
                    handleFetchChunkContext(activeChunkModal.id);
                  }}
                  className={`px-3 py-1.5 text-xs rounded-lg font-medium flex items-center gap-1.5 transition-colors ${
                    modalTab === 'context'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-purple-300 hover:text-purple-100 hover:bg-purple-950/40'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Surrounding Sequence &amp; Context</span>
                  {chunkContexts[activeChunkModal.id] && (
                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-purple-900/80 text-purple-200 ml-1">
                      {chunkContexts[activeChunkModal.id].surrounding_chunks?.length || 0}
                    </span>
                  )}
                </button>
              </div>

              {modalTab === 'context' && !chunkContexts[activeChunkModal.id] && loadingContextId !== activeChunkModal.id && (
                <button
                  type="button"
                  onClick={() => handleFetchChunkContext(activeChunkModal.id)}
                  className="text-[11px] text-purple-400 hover:text-purple-300 flex items-center gap-1"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Fetch Sequence</span>
                </button>
              )}
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {modalTab === 'focal' ? (
                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap selection:bg-indigo-600 h-full">
                  {activeChunkModal.text}
                </div>
              ) : (
                /* Context & Sequence View */
                <div className="space-y-4">
                  {loadingContextId === activeChunkModal.id ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center bg-slate-950/60 rounded-xl border border-purple-900/30">
                      <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mb-3" />
                      <span className="text-sm font-semibold text-purple-200">Retrieving surrounding regulatory provisions...</span>
                      <p className="text-xs text-slate-400 max-w-sm mt-1">
                        Expanding chunk sequence (window ±2) and synthesizing context &amp; practical implications with LLM.
                      </p>
                    </div>
                  ) : contextError && !chunkContexts[activeChunkModal.id] ? (
                    <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-900/50 text-xs text-rose-300 space-y-2">
                      <div className="flex items-center gap-2 font-semibold">
                        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                        <span>Could not fetch surrounding context</span>
                      </div>
                      <p className="text-slate-400">{contextError}</p>
                      <button
                        type="button"
                        onClick={() => handleFetchChunkContext(activeChunkModal.id)}
                        className="px-3 py-1 bg-rose-900/60 hover:bg-rose-800 text-rose-200 rounded text-xs transition-colors"
                      >
                        Retry Analysis
                      </button>
                    </div>
                  ) : chunkContexts[activeChunkModal.id] ? (
                    <>
                      {/* LLM Synthesis Summary */}
                      <div className="p-4 rounded-xl bg-gradient-to-br from-purple-950/40 via-indigo-950/20 to-slate-950 border border-purple-800/40 shadow-md space-y-2.5">
                        <div className="flex items-center justify-between gap-2 pb-2 border-b border-purple-800/30">
                          <div className="flex items-center gap-2">
                            <span className="p-1 rounded-md bg-purple-500/10 text-purple-400">
                              <Sparkles className="w-3.5 h-3.5" />
                            </span>
                            <h4 className="text-xs font-semibold text-purple-200 uppercase tracking-wider">
                              Surrounding Context &amp; Practical Implications
                            </h4>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(chunkContexts[activeChunkModal.id].summary);
                              setCopiedContextKey(`summary_${activeChunkModal.id}`);
                              setTimeout(() => setCopiedContextKey(null), 2000);
                            }}
                            className="text-[11px] text-purple-300 hover:text-white px-2 py-0.5 rounded bg-purple-950/60 border border-purple-800/40 hover:bg-purple-900/60 flex items-center gap-1 transition-colors"
                          >
                            {copiedContextKey === `summary_${activeChunkModal.id}` ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                            <span>{copiedContextKey === `summary_${activeChunkModal.id}` ? 'Copied' : 'Copy Synthesis'}</span>
                          </button>
                        </div>
                        <div className="text-slate-200 leading-relaxed font-sans text-xs whitespace-pre-wrap bg-slate-950/60 p-3 rounded-lg border border-purple-900/30">
                          {chunkContexts[activeChunkModal.id].summary}
                        </div>
                      </div>

                      {/* Surrounding Provision Sequence */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs font-semibold text-slate-300 px-1">
                          <span className="flex items-center gap-1.5">
                            <Layers className="w-3.5 h-3.5 text-indigo-400" />
                            Chronological Provision Sequence ({chunkContexts[activeChunkModal.id].surrounding_chunks?.length || 0})
                          </span>
                          <span className="text-[11px] text-slate-500 font-mono">
                            Doc: {chunkContexts[activeChunkModal.id].document_id}
                          </span>
                        </div>

                        <div className="space-y-2.5">
                          {chunkContexts[activeChunkModal.id].surrounding_chunks?.map((sc) => {
                            const isTarget = sc.is_target || sc.position === 'target';
                            return (
                              <div
                                key={sc.chunk_id}
                                className={`p-3 rounded-xl border transition-colors ${
                                  isTarget
                                    ? 'bg-indigo-950/30 border-indigo-500/70 shadow-md ring-1 ring-indigo-500/30'
                                    : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                                        isTarget
                                          ? 'bg-indigo-600 text-white'
                                          : 'bg-slate-800 text-slate-300'
                                      }`}
                                    >
                                      {isTarget
                                        ? 'Focal Provision (Current Chunk)'
                                        : sc.position === 'before'
                                        ? 'Preceding Provision'
                                        : 'Subsequent Provision'}
                                    </span>
                                    <span className="text-xs font-mono text-slate-300 font-medium">
                                      {sc.chunk_id}
                                    </span>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      navigator.clipboard.writeText(sc.text);
                                      setCopiedContextKey(`chunk_${sc.chunk_id}`);
                                      setTimeout(() => setCopiedContextKey(null), 2000);
                                    }}
                                    className="text-[11px] text-slate-400 hover:text-white px-2 py-0.5 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 flex items-center gap-1 transition-colors"
                                  >
                                    {copiedContextKey === `chunk_${sc.chunk_id}` ? (
                                      <Check className="w-3 h-3 text-emerald-400" />
                                    ) : (
                                      <Copy className="w-3 h-3" />
                                    )}
                                    <span>{copiedContextKey === `chunk_${sc.chunk_id}` ? 'Copied' : 'Copy'}</span>
                                  </button>
                                </div>
                                {sc.section_path && sc.section_path.length > 0 && (
                                  <div className="text-[10px] text-slate-500 mb-2 truncate">
                                    {sc.section_path.join(' > ')}
                                  </div>
                                )}
                                <div className="text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap bg-slate-950 p-2.5 rounded-lg border border-slate-850">
                                  {sc.text}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </>
                  ) : null}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between pt-3 mt-3 border-t border-slate-800">
              <div className="flex items-center gap-2">
                {modalTab === 'focal' ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(activeChunkModal.text);
                        setCopiedContextKey('focal_main');
                        setTimeout(() => setCopiedContextKey(null), 2000);
                      }}
                      className="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition-colors"
                    >
                      {copiedContextKey === 'focal_main' ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      <span>{copiedContextKey === 'focal_main' ? 'Copied to Clipboard' : 'Copy Provision'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setModalTab('context');
                        handleFetchChunkContext(activeChunkModal.id);
                      }}
                      className="flex items-center gap-1.5 text-xs text-purple-300 hover:text-white px-3 py-1.5 rounded-lg bg-purple-950/60 border border-purple-800/60 hover:bg-purple-900/60 transition-colors"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                      <span>Get Surrounding Context</span>
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setModalTab('focal')}
                    className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition-colors"
                  >
                    <span>View Focal Provision</span>
                  </button>
                )}
              </div>

              <button
                type="button"
                onClick={() => setActiveChunkModal(null)}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-sm"
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
  onOpenChunkModal: (id: string, text: string, initialTab?: 'focal' | 'context') => void;
  onOpenDoc: (documentId: string) => void;
  loadingDocId: string | null;
  onRetry: () => void;
  onForceRerun: () => void;
  onOpenWorkspaceWithDocs?: (documentIds: string[], initialQuery?: string) => void;
  onGenerateComprehensive?: (jobId: string) => void;
  isGeneratingComprehensive?: boolean;
}

const ResearchReportViewer: React.FC<ResearchReportViewerProps> = ({
  job,
  onOpenChunkModal,
  onOpenDoc,
  loadingDocId,
  onRetry,
  onForceRerun,
  onOpenWorkspaceWithDocs,
  onGenerateComprehensive,
  isGeneratingComprehensive
}) => {
  // ALL HOOKS MUST BE UNCONDITIONALLY CALLED AT THE TOP LEVEL BEFORE ANY RETURN
  const [reportType, setReportType] = useState<'initial' | 'comprehensive'>('initial');
  const [showSkybrary, setShowSkybrary] = useState(true);
  const [showUserNotes, setShowUserNotes] = useState(true);
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

  // Determine active markdown (initial vs comprehensive)
  const activeMarkdown = useMemo(() => {
    if (reportType === 'comprehensive' && job.comprehensive_report_markdown) {
      return job.comprehensive_report_markdown;
    }
    return job.report_markdown || '';
  }, [reportType, job.comprehensive_report_markdown, job.report_markdown]);

  // Parse structured report sections
  const sections = useMemo<DocSection[]>(() => {
    if (!activeMarkdown) return [];
    return parseReportSections(activeMarkdown);
  }, [activeMarkdown]);

  // Initial open state: expand all sections by default so report is immediately readable
  useEffect(() => {
    if (sections.length > 0) {
      const initialOpen: Record<string, boolean> = {};
      sections.forEach(s => {
        initialOpen[s.id] = true;
      });
      setOpenSectionIds(initialOpen);
    }
  }, [job.job_id, sections, reportType]);

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
    if (!activeMarkdown) return '';
    return renderMarkdownWithCitations(activeMarkdown);
  }, [activeMarkdown]);

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
    if (!activeMarkdown) return;
    navigator.clipboard.writeText(activeMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [downloadToast, setDownloadToast] = useState<string | null>(null);

  const handleDownloadHtml = () => {
    if (!activeMarkdown) return;
    downloadResearchReportHtml(job, reportType);
    setDownloadToast('Report downloaded as interactive HTML with citation mouse-overs!');
    setTimeout(() => setDownloadToast(null), 3500);
  };

  const handleDownloadMarkdown = () => {
    if (!activeMarkdown) return;
    downloadResearchReportMarkdown(job, reportType);
    setDownloadToast('Report downloaded as Markdown (.md)!');
    setTimeout(() => setDownloadToast(null), 3500);
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
            {job.origins && job.origins.length > 0 && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-sky-300 border border-slate-700 flex items-center gap-1 font-medium" title={`Sources considered: ${job.origins.join(', ')}`}>
                <BookOpen className="w-3 h-3 text-sky-400" />
                Sources: {job.origins.map(o => o.toUpperCase()).join(' · ')}
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

          {/* Version Switcher if Comprehensive Report is Available */}
          {job.comprehensive_report_markdown && (
            <div className="pt-2 flex items-center gap-2">
              <span className="text-[11px] text-slate-400 font-medium">Report Version:</span>
              <div className="inline-flex items-center p-0.5 bg-slate-950 border border-slate-800 rounded-lg text-xs">
                <button
                  type="button"
                  onClick={() => setReportType('initial')}
                  className={`px-2.5 py-1 rounded-md font-medium transition-all ${
                    reportType === 'initial'
                      ? 'bg-slate-800 text-sky-300 shadow-sm border border-slate-700'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Initial Report
                </button>
                <button
                  type="button"
                  onClick={() => setReportType('comprehensive')}
                  className={`px-2.5 py-1 rounded-md font-medium flex items-center gap-1.5 transition-all ${
                    reportType === 'comprehensive'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Sparkles className="w-3 h-3 text-amber-300" />
                  <span>Comprehensive (Gaps Resolved)</span>
                </button>
              </div>
            </div>
          )}
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

          {/* Hooked Download Button: Downloads well-formatted HTML with citation mouse-overs */}
          <div className="relative inline-flex items-center rounded-lg shadow-sm">
            <button
              onClick={handleDownloadHtml}
              title="Download well-formatted interactive HTML report with citation mouse-overs"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-l-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download HTML</span>
            </button>
            <button
              type="button"
              onClick={() => setShowDownloadMenu(prev => !prev)}
              title="Choose report download format (.html or .md)"
              className="px-1.5 py-1.5 rounded-r-lg bg-indigo-700 hover:bg-indigo-600 border-l border-indigo-500/40 text-white transition-colors"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>

            {showDownloadMenu && (
              <div 
                className="absolute right-0 top-full mt-1.5 w-64 p-1.5 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-50 animate-in fade-in zoom-in-95"
                onMouseLeave={() => setShowDownloadMenu(false)}
              >
                <button
                  type="button"
                  onClick={() => {
                    handleDownloadHtml();
                    setShowDownloadMenu(false);
                  }}
                  className="w-full flex items-start gap-2.5 p-2 rounded-lg text-left hover:bg-indigo-950/60 border border-transparent hover:border-indigo-800 transition-colors"
                >
                  <span className="p-1 rounded bg-indigo-500/20 text-indigo-400 mt-0.5">
                    <FileText className="w-3.5 h-3.5" />
                  </span>
                  <div>
                    <div className="text-xs font-semibold text-white flex items-center gap-1.5">
                      <span>HTML Report (.html)</span>
                      <span className="text-[9px] bg-indigo-600 text-white px-1 py-0.2 rounded font-mono font-bold">Recommended</span>
                    </div>
                    <div className="text-[11px] text-slate-400 mt-0.5">Interactive executive view with citation mouse-overs & appendices</div>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    handleDownloadMarkdown();
                    setShowDownloadMenu(false);
                  }}
                  className="w-full flex items-start gap-2.5 p-2 rounded-lg text-left hover:bg-slate-800/80 border border-transparent hover:border-slate-700 transition-colors mt-1"
                >
                  <span className="p-1 rounded bg-slate-800 text-slate-400 mt-0.5">
                    <Copy className="w-3.5 h-3.5" />
                  </span>
                  <div>
                    <div className="text-xs font-semibold text-slate-200">Raw Markdown (.md)</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">Plain text markdown document</div>
                  </div>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Download Confirmation Toast */}
      {downloadToast && (
        <div className="flex items-center gap-2 p-2.5 px-3.5 rounded-xl bg-emerald-950/90 border border-emerald-600/70 text-emerald-200 text-xs font-medium shadow-lg animate-in fade-in slide-in-from-top-1">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{downloadToast}</span>
        </div>
      )}

      {/* Research Gaps Self-Critique & Sub-Research Activities Panel */}
      {job.research_gaps && job.research_gaps.length > 0 && (
        <div className="border border-indigo-500/40 rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-purple-950/30 backdrop-blur overflow-hidden shadow-xl">
          <div className="p-4 bg-slate-900/70 border-b border-indigo-900/40 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2.5">
              <span className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                <Sparkles className="w-4 h-4 text-amber-300" />
              </span>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-xs font-bold text-white tracking-wide uppercase">
                    Report Self-Critique & Identified Regulatory Gaps
                  </h3>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-700/60 font-semibold">
                    {job.research_gaps.length} Sub-Research Job{job.research_gaps.length === 1 ? '' : 's'} Available
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  The research engine reviewed its report and identified aspects that could benefit from dedicated sub-research.
                </p>
              </div>
            </div>

            {/* Action Button */}
            <div className="flex items-center gap-2">
              {job.comprehensive_status === 'COMPLETED' ? (
                <button
                  type="button"
                  onClick={() => setReportType('comprehensive')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-sm ${
                    reportType === 'comprehensive'
                      ? 'bg-emerald-600 text-white shadow-emerald-950/50'
                      : 'bg-emerald-950/80 text-emerald-300 border border-emerald-700 hover:bg-emerald-900'
                  }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-300" />
                  <span>{reportType === 'comprehensive' ? 'Viewing Comprehensive Report' : 'View Comprehensive Report'}</span>
                </button>
              ) : (job.comprehensive_status === 'RUNNING' || isGeneratingComprehensive) ? (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-950/90 border border-indigo-600/70 text-indigo-200 text-xs font-semibold shadow-sm animate-pulse">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                  <span>Investigating Gaps & Synthesizing...</span>
                </div>
              ) : onGenerateComprehensive ? (
                <button
                  type="button"
                  onClick={() => onGenerateComprehensive(job.job_id)}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-all shadow-md shadow-indigo-900/50 hover:shadow-indigo-800/60"
                  title="Run targeted sub-research jobs addressing identified gaps and synthesize a master report"
                >
                  <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                  <span>Produce Comprehensive Report</span>
                </button>
              ) : null}
            </div>
          </div>

          {/* Gaps Grid */}
          <div className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {job.research_gaps.map((gap, i) => (
                <div key={gap.gap_id || i} className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/90 flex flex-col justify-between space-y-2.5">
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/60 font-semibold uppercase">
                        Sub-Job {i + 1}
                      </span>
                    </div>
                    <h4 className="text-xs font-semibold text-slate-100">{gap.topic}</h4>
                    <p className="text-[11px] text-slate-300 leading-relaxed mt-1">
                      {gap.description}
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-800/60 space-y-1">
                    <div className="text-[10px] text-slate-400 font-medium">Target Sub-Query:</div>
                    <div className="text-[11px] font-mono text-cyan-300 bg-slate-900/80 px-2 py-1 rounded border border-cyan-900/40 break-words">
                      {gap.sub_query}
                    </div>
                    {gap.rationale && (
                      <p className="text-[10px] text-slate-400 italic pt-0.5">
                        {gap.rationale}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

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
                {job.evaluation_summary?.surrounding_context_expanded && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-800 font-medium flex items-center gap-1 shadow-sm">
                    <Sparkles className="w-3 h-3 text-purple-400" />
                    Surrounding Sequence Context Active
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
                                onOpenChunkModal(cid, text, 'focal');
                              }}
                              className="text-xs font-mono text-slate-300 font-semibold hover:text-indigo-400 hover:underline text-left"
                              title="Click to inspect chunk text"
                            >
                              {cid}
                            </button>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                const text = findChunkExcerpt(cid, job.referenced_chunks, job.evaluation_summary);
                                onOpenChunkModal(cid, text, 'context');
                              }}
                              className="text-[11px] font-medium text-purple-300 hover:text-white px-2 py-0.5 rounded bg-purple-950/70 border border-purple-800/70 hover:bg-purple-900/80 flex items-center gap-1 transition-colors shadow-sm"
                              title="Inspect surrounding sequence and LLM context synthesis"
                            >
                              <Sparkles className="w-3 h-3 text-purple-400" />
                              <span>Surrounding Context</span>
                            </button>
                            <span className="text-[10px] font-mono text-emerald-400/80">
                              Retained for Synthesis
                            </span>
                          </div>
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

      {/* Collapsible Additional Potential Reading Materials (SKYbrary Bookshelf) */}
      <div className="border border-sky-900/50 rounded-2xl bg-gradient-to-br from-slate-900/90 via-sky-950/20 to-slate-900/90 backdrop-blur overflow-hidden shadow-xl">
        <button
          onClick={() => setShowSkybrary(!showSkybrary)}
          className="w-full flex items-center justify-between p-4 bg-slate-900/80 hover:bg-slate-850 transition-colors text-left"
        >
          <div className="flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-sky-500/15 text-sky-400 border border-sky-500/30">
              <BookOpen className="w-4 h-4" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-100 uppercase tracking-wide">
                  Additional Potential Reading Materials · SKYbrary Bookshelf
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-sky-950 text-sky-300 border border-sky-800/80 font-semibold">
                  {job.skybrary_reading_materials?.length || 0} Curated Resource{(job.skybrary_reading_materials?.length || 0) === 1 ? '' : 's'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                External aviation safety articles, operational guidance, and best-practice materials matched to this finished report.
              </p>
            </div>
          </div>
          {showSkybrary ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>

        {showSkybrary && (
          <div className="p-5 border-t border-sky-900/40 space-y-4">
            {job.skybrary_reading_materials && job.skybrary_reading_materials.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {job.skybrary_reading_materials.map((item, idx) => {
                  const matchPercent = Math.round(item.relevance_score * 100);
                  return (
                    <div
                      key={item.document_id || idx}
                      className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-sky-700/60 transition-all duration-200 flex flex-col justify-between space-y-3 group hover:shadow-lg hover:shadow-sky-950/30"
                    >
                      <div className="space-y-2">
                        {/* Header Badges */}
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[9px] font-mono px-2 py-0.5 rounded-full font-bold uppercase bg-sky-950 text-sky-300 border border-sky-800/80">
                              {item.category || 'SKYbrary Guidance'}
                            </span>
                            {item.author && (
                              <span className="text-[10px] text-slate-400 truncate max-w-[140px]" title={item.author}>
                                {item.author}
                              </span>
                            )}
                          </div>

                          {/* Relevance Score Badge with visual bar */}
                          <div className="flex items-center gap-1.5">
                            <div className="w-12 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  matchPercent >= 85
                                    ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                                    : 'bg-gradient-to-r from-sky-500 to-indigo-500'
                                }`}
                                style={{ width: `${matchPercent}%` }}
                              />
                            </div>
                            <span
                              className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${
                                matchPercent >= 85
                                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/80'
                                  : 'bg-sky-950 text-sky-300 border border-sky-800/80'
                              }`}
                            >
                              {matchPercent}% Match
                            </span>
                          </div>
                        </div>

                        {/* Document Title */}
                        <h4 className="text-sm font-semibold text-white group-hover:text-sky-300 transition-colors leading-snug">
                          {item.title}
                        </h4>

                        {/* Match Rationale */}
                        {item.match_rationale && (
                          <p className="text-xs text-slate-300 leading-relaxed pl-2 border-l-2 border-sky-500/50 bg-sky-950/20 py-1 pr-1 rounded-r">
                            <strong className="text-sky-400 text-[11px] uppercase tracking-wide block mb-0.5 font-semibold">
                              Why Recommended:
                            </strong>
                            {item.match_rationale}
                          </p>
                        )}

                        {/* Key Excerpt */}
                        {item.key_excerpt && (
                          <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800/80 text-[11px] text-slate-400 italic leading-relaxed line-clamp-3">
                            "{item.key_excerpt}"
                          </div>
                        )}
                      </div>

                      {/* Card Action Buttons */}
                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-1.5">
                          {onOpenDoc && (
                            <button
                              type="button"
                              onClick={() => onOpenDoc(item.document_id)}
                              disabled={loadingDocId === item.document_id}
                              title="Inspect full text in regulatory document reader"
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors border border-slate-700/80"
                            >
                              {loadingDocId === item.document_id ? (
                                <Loader2 className="w-3 h-3 animate-spin text-sky-400" />
                              ) : (
                                <ExternalLink className="w-3 h-3 text-sky-400" />
                              )}
                              <span>Read In-App</span>
                            </button>
                          )}

                          {onOpenWorkspaceWithDocs && (
                            <button
                              type="button"
                              onClick={() => onOpenWorkspaceWithDocs([item.document_id], job.query)}
                              title="Open this SKYbrary document in workspace side-by-side"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 text-xs font-medium transition-colors border border-slate-800"
                            >
                              <Columns className="w-3 h-3 text-indigo-400" />
                              <span>Workspace</span>
                            </button>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5">
                          {item.pdf_url && (
                            <a
                              href={item.pdf_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Open or download official publication PDF"
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-sky-950/80 hover:bg-sky-900 text-sky-300 text-xs font-medium transition-colors border border-sky-800/80"
                            >
                              <Download className="w-3 h-3" />
                              <span>PDF</span>
                            </a>
                          )}

                          {item.summary_url && (
                            <a
                              href={item.summary_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Visit official SKYbrary portal article"
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-850 text-slate-300 hover:text-white text-xs font-medium transition-colors border border-slate-800"
                            >
                              <ExternalLink className="w-3 h-3" />
                              <span>SKYbrary Portal</span>
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-6 rounded-xl bg-slate-950/60 border border-slate-800 text-center space-y-2">
                <p className="text-xs text-slate-400">
                  No dedicated SKYbrary bookshelf items have been matched for this research run yet.
                </p>
                <p className="text-[11px] text-slate-500">
                  Re-running or producing a comprehensive report will automatically search the SKYbrary knowledge corpus for relevant operational guidance.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Collapsible Additional Potential Reading Materials (User Notes & Internal Documentation) */}
      <div className="border border-amber-900/50 rounded-2xl bg-gradient-to-br from-slate-900/90 via-amber-950/20 to-slate-900/90 backdrop-blur overflow-hidden shadow-xl">
        <button
          onClick={() => setShowUserNotes(!showUserNotes)}
          className="w-full flex items-center justify-between p-4 bg-slate-900/80 hover:bg-slate-850 transition-colors text-left"
        >
          <div className="flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-amber-500/15 text-amber-400 border border-amber-500/30">
              <FileText className="w-4 h-4" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-100 uppercase tracking-wide">
                  Internal Documentation & Project Notes · Relevant Follow-up Reading
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800/80 font-semibold">
                  {job.user_notes_reading_materials?.length || 0} Matched Note{(job.user_notes_reading_materials?.length || 0) === 1 ? '' : 's'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Internal team journals, meeting minutes, and project documentation matched to this inquiry for contextual background.
              </p>
            </div>
          </div>
          {showUserNotes ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>

        {showUserNotes && (
          <div className="p-5 border-t border-amber-900/40 space-y-4">
            {job.user_notes_reading_materials && job.user_notes_reading_materials.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {job.user_notes_reading_materials.map((item, idx) => {
                  const matchPercent = Math.round(item.relevance_score * 100);
                  return (
                    <div
                      key={item.document_id || idx}
                      className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-amber-700/60 transition-all duration-200 flex flex-col justify-between space-y-3 group hover:shadow-lg hover:shadow-amber-950/30"
                    >
                      <div className="space-y-2">
                        {/* Header Badges */}
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-[9px] font-mono px-2 py-0.5 rounded-full font-bold uppercase bg-amber-950 text-amber-300 border border-amber-800/80">
                              {item.note_type || 'Internal Note'}
                            </span>
                            {item.project && (
                              <span className="text-[9px] font-mono px-2 py-0.5 rounded-full font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                                {item.project}
                              </span>
                            )}
                            {item.author && (
                              <span className="text-[10px] text-slate-400 truncate max-w-[140px]" title={item.author}>
                                {item.author}
                              </span>
                            )}
                          </div>

                          {/* Relevance Score Badge */}
                          <div className="flex items-center gap-1.5">
                            <div className="w-12 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  matchPercent >= 80
                                    ? 'bg-gradient-to-r from-amber-500 to-emerald-400'
                                    : 'bg-gradient-to-r from-amber-500 to-orange-400'
                                }`}
                                style={{ width: `${matchPercent}%` }}
                              />
                            </div>
                            <span
                              className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${
                                matchPercent >= 80
                                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/80'
                                  : 'bg-amber-950 text-amber-300 border border-amber-800/80'
                              }`}
                            >
                              {matchPercent}% Match
                            </span>
                          </div>
                        </div>

                        {/* Title */}
                        <h4 className="text-sm font-semibold text-white group-hover:text-amber-300 transition-colors leading-snug">
                          {item.title}
                        </h4>

                        {/* Match Rationale */}
                        {item.match_rationale && (
                          <p className="text-xs text-slate-300 leading-relaxed pl-2 border-l-2 border-amber-500/50 bg-amber-950/20 py-1 pr-1 rounded-r">
                            <strong className="text-amber-400 text-[11px] uppercase tracking-wide block mb-0.5 font-semibold">
                              Relevance Context:
                            </strong>
                            {item.match_rationale}
                          </p>
                        )}

                        {/* Key Excerpt */}
                        {item.key_excerpt && (
                          <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800/80 text-[11px] text-slate-400 italic leading-relaxed line-clamp-3">
                            "{item.key_excerpt}"
                          </div>
                        )}
                      </div>

                      {/* Card Action Buttons */}
                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-1.5">
                          {onOpenDoc && (
                            <button
                              type="button"
                              onClick={() => onOpenDoc(item.document_id)}
                              disabled={loadingDocId === item.document_id}
                              title="Inspect full text in document reader"
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors border border-slate-700/80"
                            >
                              {loadingDocId === item.document_id ? (
                                <Loader2 className="w-3 h-3 animate-spin text-amber-400" />
                              ) : (
                                <ExternalLink className="w-3 h-3 text-amber-400" />
                              )}
                              <span>Read In-App</span>
                            </button>
                          )}

                          {onOpenWorkspaceWithDocs && (
                            <button
                              type="button"
                              onClick={() => onOpenWorkspaceWithDocs([item.document_id], job.query)}
                              title="Open this note in workspace alongside regulations"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-850 text-slate-400 hover:text-slate-200 text-xs font-medium transition-colors border border-slate-800"
                            >
                              <Columns className="w-3 h-3 text-amber-400" />
                              <span>Workspace</span>
                            </button>
                          )}
                        </div>

                        {item.date && (
                          <span className="text-[10px] text-slate-500 font-mono">
                            {item.date}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-6 rounded-xl bg-slate-950/60 border border-slate-800 text-center space-y-2">
                <p className="text-xs text-slate-400">
                  No internal project notes or user documentation matched this regulatory query.
                </p>
                <p className="text-[11px] text-slate-500">
                  Author notes in the Notes & Journals tab to link internal project progress and meeting minutes with regulatory inquiries.
                </p>
              </div>
            )}
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
