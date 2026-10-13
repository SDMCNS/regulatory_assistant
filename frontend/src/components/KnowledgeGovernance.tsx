import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  Search,
  Filter,
  RefreshCw,
  Archive,
  ArrowRight,
  AlertTriangle,
  History,
  CheckCircle,
  FileText,
  X,
  ExternalLink,
  Info,
  UploadCloud,
  Upload,
  Check,
  Copy,
  AlertCircle,
  ArrowUpRight
} from 'lucide-react';
import {
  AppSettings,
  RegulationItem,
  GovernanceStats,
  UploadAnalysisResponse,
  IngestConfirmRequest,
  IngestionResultResponse,
  ComparisonMatchItem
} from '../types';
import {
  getRegulationsCatalog,
  getGovernanceStats,
  deactivateDocument,
  activateDocument,
  analyzeDocumentUpload,
  confirmDocumentIngestion,
  loadSettings
} from '../services/apiClient';

interface KnowledgeGovernanceProps {
  settings?: AppSettings;
  onOpenInWorkspace?: (docId: string) => void;
}

export const KnowledgeGovernance: React.FC<KnowledgeGovernanceProps> = ({
  settings = loadSettings(),
  onOpenInWorkspace
}) => {
  const [stats, setStats] = useState<GovernanceStats | null>(null);
  const [documents, setDocuments] = useState<RegulationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'deactivated'>('all');
  const [originFilter, setOriginFilter] = useState<string>('all');

  // Deactivate Modal state
  const [selectedDoc, setSelectedDoc] = useState<RegulationItem | null>(null);
  const [deactivateReason, setDeactivateReason] = useState('');
  const [supersededBy, setSupersededBy] = useState('');
  const [showDeactivateModal, setShowDeactivateModal] = useState(false);

  // Audit Log Drawer state
  const [showLogs, setShowLogs] = useState(false);

  // Upload & Executive Comparison state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [analyzingFile, setAnalyzingFile] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<UploadAnalysisResponse | null>(null);
  const [executiveAction, setExecutiveAction] = useState<'none' | 'supersede' | 'suppress'>('none');
  const [targetDocId, setTargetDocId] = useState<string>('');
  const [customTitle, setCustomTitle] = useState<string>('');
  const [customDate, setCustomDate] = useState<string>('');
  const [confirmingIngest, setConfirmingIngest] = useState(false);
  const [ingestSuccess, setIngestSuccess] = useState<IngestionResultResponse | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const data = await getGovernanceStats(settings);
      setStats(data);
    } catch (err: any) {
      console.error('Failed to load governance stats:', err);
    }
  }, [settings]);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRegulationsCatalog({
        origin: originFilter !== 'all' ? originFilter : undefined,
        status: statusFilter,
        query: searchQuery.trim() || undefined,
        limit: 500
      }, settings);
      setDocuments(data.regulations || []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch regulations catalog.');
    } finally {
      setLoading(false);
    }
  }, [originFilter, statusFilter, searchQuery, settings]);

  useEffect(() => {
    fetchStats();
    fetchDocs();
  }, [fetchStats, fetchDocs]);

  const handleOpenDeactivateModal = (doc: RegulationItem) => {
    setSelectedDoc(doc);
    setDeactivateReason('');
    setSupersededBy('');
    setShowDeactivateModal(true);
  };

  const handleConfirmDeactivate = async () => {
    if (!selectedDoc) return;
    if (!deactivateReason.trim()) {
      alert('Please provide a reason for deactivation / knowledge forgetting.');
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const res = await deactivateDocument(
        selectedDoc.document_id,
        deactivateReason.trim(),
        supersededBy.trim() || undefined,
        settings
      );
      setSuccessMsg(res.message || `Document '${selectedDoc.document_id}' successfully deactivated.`);
      setShowDeactivateModal(false);
      setSelectedDoc(null);
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || 'Failed to deactivate document.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReactivate = async (doc: RegulationItem) => {
    if (!window.confirm(`Reactivate '${doc.title || doc.document_id}' and restore all ${doc.chunk_count} chunks to the active search index?`)) {
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const res = await activateDocument(doc.document_id, settings);
      setSuccessMsg(res.message || `Document '${doc.document_id}' reactivated.`);
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || 'Failed to reactivate document.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenUploadModal = () => {
    setUploadFile(null);
    setAnalysisResult(null);
    setIngestSuccess(null);
    setAnalyzingFile(false);
    setConfirmingIngest(false);
    setExecutiveAction('none');
    setTargetDocId('');
    setCustomTitle('');
    setCustomDate('');
    setShowUploadModal(true);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadFile(file);
    setAnalysisResult(null);
    setIngestSuccess(null);
    setAnalyzingFile(true);
    setError(null);
    try {
      const res = await analyzeDocumentUpload(file, settings);
      setAnalysisResult(res);
      setExecutiveAction((res.suggested_action as any) || 'none');
      setTargetDocId(res.suggested_target_doc_id || (res.matches?.[0]?.document_id || ''));
      setCustomTitle(res.extracted_metadata?.title || '');
      setCustomDate(res.extracted_metadata?.date || '');
    } catch (err: any) {
      setError(err.message || 'Failed to analyze uploaded document.');
    } finally {
      setAnalyzingFile(false);
    }
  };

  const handleConfirmIngestion = async () => {
    if (!analysisResult) return;
    setConfirmingIngest(true);
    setError(null);
    try {
      const payload: IngestConfirmRequest = {
        staging_id: analysisResult.staging_id,
        executive_action: executiveAction,
        target_doc_id: executiveAction !== 'none' ? targetDocId : null,
        custom_title: customTitle.trim() || null,
        custom_date: customDate.trim() || null,
      };
      const res = await confirmDocumentIngestion(payload, settings);
      setIngestSuccess(res);
      setSuccessMsg(res.action_summary || `Document '${res.document_id}' ingested successfully.`);
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || 'Failed to ingest document.');
    } finally {
      setConfirmingIngest(false);
    }
  };

  const originColor = (origin: string) => {
    switch (origin.toLowerCase()) {
      case 'easa': return 'bg-sky-950/80 text-sky-400 border-sky-800/60';
      case 'faa': return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60';
      case 'eu': return 'bg-blue-950/80 text-blue-400 border-blue-800/60';
      case 'skybrary': return 'bg-amber-950/80 text-amber-400 border-amber-800/60';
      case 'manual': return 'bg-teal-950/80 text-teal-400 border-teal-800/60';
      case 'note': return 'bg-purple-950/80 text-purple-400 border-purple-800/60';
      case 'user': return 'bg-cyan-950/80 text-cyan-400 border-cyan-800/60';
      default: return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-hidden">
      {/* Top Header */}
      <header className="px-6 py-4 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-indigo-400" />
            <h1 className="text-lg font-bold tracking-tight text-white">Knowledge Governance & Document Superseding</h1>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-indigo-950/80 text-indigo-400 border border-indigo-800/60">
              Machine Forgetting & Selective Deactivation
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Deactivate obsolete or superseded regulations to guarantee that outdated provisions are disregarded during RAG vector search, BM25 indexing, and LLM synthesis.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleOpenUploadModal}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors"
            title="Upload document, detect XML/Skybrary format, and compare duplicates with executive action"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Upload Document</span>
          </button>
          <button
            onClick={() => setShowLogs(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 border border-slate-700 transition-colors"
          >
            <History className="w-3.5 h-3.5 text-slate-400" />
            <span>Audit Log ({stats?.recent_logs.length || 0})</span>
          </button>
          <button
            onClick={() => { fetchStats(); fetchDocs(); }}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      {/* Alert Banners */}
      {successMsg && (
        <div className="px-6 py-2.5 bg-emerald-950/60 border-b border-emerald-800/60 flex items-center justify-between text-emerald-300 text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successMsg}</span>
          </div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-200">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {error && (
        <div className="px-6 py-2.5 bg-rose-950/60 border-b border-rose-800/60 flex items-center justify-between text-rose-300 text-xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-6 bg-slate-900/40 border-b border-slate-800/60">
        <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Total Instruments</span>
            <FileText className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">
            {stats ? stats.total_documents.toLocaleString() : '—'}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            Across EASA, FAA, EU, Skybrary, SOPs
          </div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-emerald-400">
            <span>Active in RAG</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">
            {stats ? stats.active_documents.toLocaleString() : '—'}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {stats && stats.total_documents > 0
              ? `${((stats.active_documents / stats.total_documents) * 100).toFixed(1)}% currently indexed`
              : 'Indexed for search'}
          </div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-rose-400">
            <span>Deactivated / Superseded</span>
            <Archive className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold text-rose-400 mt-1">
            {stats ? stats.deactivated_documents.toLocaleString() : '—'}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            Tombstoned & excluded from queries
          </div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-amber-400">
            <span>Forgotten Chunks</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400 mt-1">
            {stats ? stats.forgotten_chunks.toLocaleString() : '—'}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {stats && stats.total_chunks > 0
              ? `of ${stats.total_chunks.toLocaleString()} total clauses`
              : 'Omitted from ranking'}
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="px-6 py-3 bg-slate-900/60 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[280px]">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Filter by document title, CELEX, or regulation ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status Segmented Control */}
          <div className="flex items-center p-0.5 bg-slate-950 border border-slate-800 rounded-lg">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                statusFilter === 'all' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              All Statuses
            </button>
            <button
              onClick={() => setStatusFilter('active')}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                statusFilter === 'active' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/60' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Active Only
            </button>
            <button
              onClick={() => setStatusFilter('deactivated')}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                statusFilter === 'deactivated' ? 'bg-rose-950 text-rose-300 border border-rose-800/60' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Deactivated Only
            </button>
          </div>

          {/* Origin Dropdown */}
          <select
            value={originFilter}
            onChange={(e) => setOriginFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Origins</option>
            <option value="easa">EASA Easy Access</option>
            <option value="faa">FAA Title 14 CFR</option>
            <option value="eu">EU Formex Acts</option>
            <option value="skybrary">SKYbrary Bookshelf</option>
            <option value="manual">Company SOPs & Manuals</option>
            <option value="note">Notes & Journals</option>
            <option value="user">User Documents</option>
          </select>
        </div>
      </div>

      {/* Main Document Table View */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
            <p className="text-xs">Loading regulations catalog with governance states...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2 border border-dashed border-slate-800 rounded-xl p-8">
            <ShieldAlert className="w-8 h-8 text-slate-600" />
            <p className="text-sm font-medium text-slate-300">No regulations match the selected filters.</p>
            <p className="text-xs text-slate-500">Try adjusting your search query, status filter, or origin filter.</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            <div className="text-xs text-slate-400 mb-2">
              Showing <span className="text-slate-200 font-semibold">{documents.length}</span> documents
            </div>

            {documents.map((doc) => {
              const isActive = doc.is_active !== false;
              return (
                <div
                  key={doc.document_id}
                  className={`p-4 rounded-xl border transition-colors ${
                    isActive
                      ? 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700'
                      : 'bg-rose-950/20 border-rose-900/40 hover:border-rose-800/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1.5">
                        {/* Status Badge */}
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border ${
                            isActive
                              ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60'
                              : 'bg-rose-950/90 text-rose-300 border-rose-800/80'
                          }`}
                        >
                          {isActive ? (
                            <>
                              <ShieldCheck className="w-3 h-3" />
                              <span>Active in RAG</span>
                            </>
                          ) : (
                            <>
                              <Archive className="w-3 h-3" />
                              <span>Deactivated / Forgotten</span>
                            </>
                          )}
                        </span>

                        {/* Origin Badge */}
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-semibold border ${originColor(doc.origin)}`}>
                          {doc.origin}
                        </span>

                        {/* Chunks Badge */}
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                          {doc.chunk_count} clauses
                        </span>

                        {doc.date && (
                          <span className="text-[11px] text-slate-500 font-mono">
                            {doc.date}
                          </span>
                        )}
                      </div>

                      <h3 className="text-sm font-semibold text-slate-100 leading-snug">
                        {doc.title || doc.document_id}
                      </h3>
                      <p className="text-xs text-slate-500 font-mono mt-0.5 truncate">
                        ID: {doc.document_id}
                      </p>

                      {/* Deactivation & Superseding Banner */}
                      {!isActive && (
                        <div className="mt-2.5 p-2.5 rounded-lg bg-rose-950/40 border border-rose-900/50 text-xs text-rose-200">
                          <div className="flex items-center gap-2 font-medium">
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                            <span>Reason: {doc.deactivation_reason || 'Outdated / Superseded guidance'}</span>
                          </div>
                          {doc.superseded_by && (
                            <div className="mt-1 text-[11px] text-rose-300 flex items-center gap-1.5 font-mono">
                              <ArrowRight className="w-3 h-3 text-rose-400 shrink-0" />
                              <span>Superseded by: <strong className="text-white">{doc.superseded_by}</strong></span>
                            </div>
                          )}
                          {doc.deactivated_at && (
                            <div className="text-[10px] text-rose-400/80 mt-1">
                              Deactivated on: {doc.deactivated_at}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      {onOpenInWorkspace && (
                        <button
                          onClick={() => onOpenInWorkspace(doc.document_id)}
                          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors flex items-center gap-1"
                          title="Open in Workspace"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span className="hidden sm:inline">Workspace</span>
                        </button>
                      )}

                      {isActive ? (
                        <button
                          onClick={() => handleOpenDeactivateModal(doc)}
                          disabled={actionLoading}
                          className="px-3 py-1 text-xs font-medium rounded-lg bg-rose-900/60 hover:bg-rose-800 text-rose-200 border border-rose-700/60 transition-colors flex items-center gap-1.5"
                        >
                          <Archive className="w-3.5 h-3.5" />
                          <span>Deactivate</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReactivate(doc)}
                          disabled={actionLoading}
                          className="px-3 py-1 text-xs font-medium rounded-lg bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-700/60 transition-colors flex items-center gap-1.5"
                        >
                          <ShieldCheck className="w-3.5 h-3.5" />
                          <span>Reactivate</span>
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Deactivate Modal */}
      {showDeactivateModal && selectedDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2 text-rose-400">
                <AlertTriangle className="w-5 h-5" />
                <h2 className="text-base font-bold text-white">Deactivate Regulatory Document</h2>
              </div>
              <button
                onClick={() => setShowDeactivateModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl">
                <div className="text-xs text-slate-400">Target Document:</div>
                <div className="text-sm font-semibold text-white mt-0.5">{selectedDoc.title}</div>
                <div className="text-[11px] font-mono text-slate-500 mt-0.5">{selectedDoc.document_id} • {selectedDoc.chunk_count} clauses</div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Reason for Deactivation / Superseding <span className="text-rose-400">*</span>
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Repealed by Regulation (EU) 2018/1139, obsolete FAA guidance, or revised company manual revision..."
                  value={deactivateReason}
                  onChange={(e) => setDeactivateReason(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Superseding Document ID / Reference <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Regulation (EU) 2018/1139, or AD 2008-10-08"
                  value={supersededBy}
                  onChange={(e) => setSupersededBy(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-900/40 text-xs text-rose-300 flex items-start gap-2">
                <Info className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
                <span>
                  <strong>Knowledge Forgetting Effect:</strong> All {selectedDoc.chunk_count} chunks belonging to this document will be flagged as inactive (<code className="text-rose-200">is_active = 0</code>). They will be disregarded in all future vector semantic and keyword search operations.
                </span>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowDeactivateModal(false)}
                disabled={actionLoading}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeactivate}
                disabled={actionLoading || !deactivateReason.trim()}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm Deactivation</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Document Upload & Executive Comparison Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150 my-8 max-h-[90vh] flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-2.5 text-cyan-400">
                <UploadCloud className="w-5 h-5" />
                <div>
                  <h2 className="text-base font-bold text-white">Upload & Compare Regulatory Document</h2>
                  <p className="text-[11px] text-slate-400">
                    Automatic XML/Skybrary workflow routing, duplicate/update detection, & executive superseding control
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowUploadModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="mt-4 space-y-4 overflow-y-auto flex-1 pr-1">
              {/* Step 1: File Selection Area */}
              {!analysisResult && !ingestSuccess && (
                <div className="space-y-4">
                  <div className="p-8 border-2 border-dashed border-slate-700/80 hover:border-cyan-500/80 rounded-2xl bg-slate-950/60 transition-colors text-center relative group">
                    <input
                      type="file"
                      accept=".pdf,.xml,.txt,.md,.docx,.html"
                      onChange={handleFileSelect}
                      disabled={analyzingFile}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
                    />
                    <div className="flex flex-col items-center justify-center gap-2 pointer-events-none">
                      <div className="w-12 h-12 rounded-xl bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400 group-hover:scale-105 transition-transform">
                        {analyzingFile ? (
                          <RefreshCw className="w-6 h-6 animate-spin text-cyan-300" />
                        ) : (
                          <Upload className="w-6 h-6" />
                        )}
                      </div>
                      <div className="text-sm font-semibold text-white">
                        {analyzingFile ? 'Analyzing & comparing document...' : 'Choose or drop a regulatory document'}
                      </div>
                      <p className="text-xs text-slate-400 max-w-md">
                        Supports PDF, XML (EASA, EU Formex, FAA CFR), Markdown, TXT, HTML.
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-950 text-sky-300 border border-sky-800">EASA / FAA / EU XML</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950 text-indigo-300 border border-indigo-800">Skybrary Chunker Workflow</span>
                      </div>
                    </div>
                  </div>

                  {analyzingFile && (
                    <div className="p-3 bg-cyan-950/40 border border-cyan-800/60 rounded-xl flex items-center gap-3 text-xs text-cyan-300">
                      <RefreshCw className="w-4 h-4 animate-spin shrink-0 text-cyan-400" />
                      <span>
                        Inspecting document namespaces, parsing text, calculating SHA-256 fingerprint, and comparing against existing regulations...
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Step 2: Analysis Results & Executive Control */}
              {analysisResult && !ingestSuccess && (
                <div className="space-y-4">
                  {/* Format & Workflow Classification Banner */}
                  <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400">Classified Workflow & Destination</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-cyan-950 text-cyan-300 border border-cyan-800">
                        {analysisResult.workflow}
                      </span>
                    </div>
                    <div className="text-xs text-slate-300">
                      <strong>Detection:</strong> {analysisResult.detection_reason}
                    </div>
                    <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400">
                      <span>Source: <strong className="text-white">{analysisResult.category}</strong></span>
                      <span>•</span>
                      <span>Origin: <strong className="text-white">{analysisResult.origin}</strong></span>
                      <span>•</span>
                      <span>Format: <strong className="text-white">{analysisResult.format}</strong></span>
                    </div>
                  </div>

                  {/* Metadata & Title Overrides */}
                  <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                    <div className="text-xs font-semibold text-slate-200">Extracted Document Attributes</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-slate-400 mb-1">
                          Document Title <span className="text-slate-500">(editable)</span>
                        </label>
                        <input
                          type="text"
                          value={customTitle}
                          onChange={(e) => setCustomTitle(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-slate-400 mb-1">
                          Publication Date <span className="text-slate-500">(YYYY-MM-DD, optional)</span>
                        </label>
                        <input
                          type="text"
                          placeholder="e.g. 2024-05-15"
                          value={customDate}
                          onChange={(e) => setCustomDate(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                        />
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                      {analysisResult.extracted_metadata.word_count && (
                        <span>Words: <strong className="text-white">{analysisResult.extracted_metadata.word_count.toLocaleString()}</strong></span>
                      )}
                      {analysisResult.extracted_metadata.page_count && (
                        <span>Pages: <strong className="text-white">{analysisResult.extracted_metadata.page_count}</strong></span>
                      )}
                      {analysisResult.extracted_metadata.sha256 && (
                        <span className="font-mono truncate max-w-xs" title={analysisResult.extracted_metadata.sha256}>
                          SHA-256: {analysisResult.extracted_metadata.sha256.slice(0, 12)}...
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Duplicate / Update Comparison Findings */}
                  {analysisResult.matches && analysisResult.matches.length > 0 ? (
                    <div className="p-3.5 bg-amber-950/20 border border-amber-900/40 rounded-xl space-y-3">
                      <div className="flex items-center gap-2 text-amber-400">
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                        <span className="text-xs font-bold">
                          Known Predecessor or Duplicate Detected ({analysisResult.matches.length} matches)
                        </span>
                      </div>

                      {/* Matches List */}
                      <div className="space-y-2">
                        {analysisResult.matches.map((match) => (
                          <div
                            key={match.document_id}
                            className={`p-2.5 rounded-lg border text-xs space-y-1 transition-colors ${
                              targetDocId === match.document_id
                                ? 'bg-slate-900 border-amber-500/60'
                                : 'bg-slate-950/80 border-slate-800'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-slate-200">{match.title}</span>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                                  match.match_type === 'exact_duplicate'
                                    ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                    : match.match_type === 'update'
                                    ? 'bg-amber-950 text-amber-300 border border-amber-800'
                                    : 'bg-sky-950 text-sky-300 border border-sky-800'
                                }`}
                              >
                                {match.match_type.replace('_', ' ')}
                              </span>
                            </div>
                            <div className="text-[11px] text-slate-400">
                              {match.comparison_details}
                            </div>
                            <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1">
                              <span>ID: {match.document_id} • Date: {match.date || 'Unknown'}</span>
                              <span>Similarity: {(match.similarity_score * 100).toFixed(0)}%</span>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Executive Action Selector */}
                      <div className="pt-2 border-t border-amber-900/30 space-y-2">
                        <label className="block text-xs font-bold text-white">
                          Executive Control: What should happen to the old document?
                        </label>

                        {analysisResult.matches.length > 1 && (
                          <div className="mb-2">
                            <label className="block text-[11px] text-slate-400 mb-1">Target Document to Supersede / Suppress:</label>
                            <select
                              value={targetDocId}
                              onChange={(e) => setTargetDocId(e.target.value)}
                              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white"
                            >
                              {analysisResult.matches.map((m) => (
                                <option key={m.document_id} value={m.document_id}>
                                  {m.title} ({m.document_id})
                                </option>
                              ))}
                            </select>
                          </div>
                        )}

                        <div className="grid grid-cols-1 gap-2">
                          {/* Option 1: Supersede */}
                          <label
                            className={`p-3 rounded-xl border flex items-start gap-3 cursor-pointer transition-colors ${
                              executiveAction === 'supersede'
                                ? 'bg-amber-950/40 border-amber-500/80 text-amber-200'
                                : 'bg-slate-950 border-slate-800 hover:border-slate-700 text-slate-300'
                            }`}
                          >
                            <input
                              type="radio"
                              name="executive_action"
                              value="supersede"
                              checked={executiveAction === 'supersede'}
                              onChange={() => setExecutiveAction('supersede')}
                              className="mt-0.5 accent-amber-500"
                            />
                            <div>
                              <div className="text-xs font-bold flex items-center gap-1.5">
                                <span>Supersede Old Document</span>
                                <span className="text-[10px] font-normal px-1.5 py-0.2 rounded bg-amber-900/60 text-amber-300">
                                  Recommended for updates
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                Marks old document as superseded by the new one. Outdated provisions are tombstoned from standard search, and only retrieved at a 0.1x fallback weight if no active regulations match.
                              </p>
                            </div>
                          </label>

                          {/* Option 2: Suppress */}
                          <label
                            className={`p-3 rounded-xl border flex items-start gap-3 cursor-pointer transition-colors ${
                              executiveAction === 'suppress'
                                ? 'bg-rose-950/40 border-rose-500/80 text-rose-200'
                                : 'bg-slate-950 border-slate-800 hover:border-slate-700 text-slate-300'
                            }`}
                          >
                            <input
                              type="radio"
                              name="executive_action"
                              value="suppress"
                              checked={executiveAction === 'suppress'}
                              onChange={() => setExecutiveAction('suppress')}
                              className="mt-0.5 accent-rose-500"
                            />
                            <div>
                              <div className="text-xs font-bold flex items-center gap-1.5">
                                <span>Suppress / Deactivate Old Document</span>
                                <span className="text-[10px] font-normal px-1.5 py-0.2 rounded bg-rose-900/60 text-rose-300">
                                  Recommended for duplicates
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                Full machine forgetting. Deactivates and suppresses the predecessor document, completely omitting it from all future search operations.
                              </p>
                            </div>
                          </label>

                          {/* Option 3: Keep Both */}
                          <label
                            className={`p-3 rounded-xl border flex items-start gap-3 cursor-pointer transition-colors ${
                              executiveAction === 'none'
                                ? 'bg-cyan-950/40 border-cyan-500/80 text-cyan-200'
                                : 'bg-slate-950 border-slate-800 hover:border-slate-700 text-slate-300'
                            }`}
                          >
                            <input
                              type="radio"
                              name="executive_action"
                              value="none"
                              checked={executiveAction === 'none'}
                              onChange={() => setExecutiveAction('none')}
                              className="mt-0.5 accent-cyan-500"
                            />
                            <div>
                              <div className="text-xs font-bold">Keep Both Active</div>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                Ingests the new document without changing the status of any existing documents. Both will remain active in the knowledge base.
                              </p>
                            </div>
                          </label>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3.5 bg-emerald-950/20 border border-emerald-900/40 rounded-xl flex items-center gap-3 text-xs text-emerald-300">
                      <CheckCircle className="w-5 h-5 shrink-0 text-emerald-400" />
                      <div>
                        <div className="font-semibold text-emerald-200">No Duplicate or Conflict Detected</div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          This document does not match any existing regulation in the catalog and will be indexed cleanly as a new knowledge instrument.
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Step 3: Ingestion Success Screen */}
              {ingestSuccess && (
                <div className="p-6 bg-slate-950 border border-emerald-800/60 rounded-2xl text-center space-y-4">
                  <div className="w-12 h-12 rounded-full bg-emerald-950 border border-emerald-800 flex items-center justify-center text-emerald-400 mx-auto">
                    <CheckCircle className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-white">Document Ingested Successfully!</h3>
                    <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                      {ingestSuccess.action_summary}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-left p-3 bg-slate-900/80 border border-slate-800 rounded-xl text-xs">
                    <div>
                      <div className="text-[10px] text-slate-500">Document ID</div>
                      <div className="font-mono text-cyan-300 truncate" title={ingestSuccess.document_id}>
                        {ingestSuccess.document_id}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">Origin / Source</div>
                      <div className="font-mono text-white">{ingestSuccess.origin} / {ingestSuccess.source}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">Chunks Indexed</div>
                      <div className="font-mono text-emerald-400">{ingestSuccess.chunks_count} chunks</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-500">FAISS Embeddings</div>
                      <div className="font-mono text-indigo-400">{ingestSuccess.embeddings_count} vectors</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-end gap-2 shrink-0">
              {ingestSuccess ? (
                <>
                  <button
                    onClick={handleOpenUploadModal}
                    className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                  >
                    Upload Another Document
                  </button>
                  <button
                    onClick={() => setShowUploadModal(false)}
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
                  >
                    Done
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => {
                      if (analysisResult) {
                        setAnalysisResult(null);
                        setUploadFile(null);
                      } else {
                        setShowUploadModal(false);
                      }
                    }}
                    disabled={confirmingIngest}
                    className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                  >
                    {analysisResult ? 'Back' : 'Cancel'}
                  </button>
                  {analysisResult && (
                    <button
                      onClick={handleConfirmIngestion}
                      disabled={confirmingIngest || !customTitle.trim()}
                      className="px-4 py-2 text-xs font-semibold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors disabled:opacity-50 flex items-center gap-1.5"
                    >
                      {confirmingIngest && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                      <span>
                        {confirmingIngest ? 'Chunking & Embedding...' : 'Confirm & Ingest Document'}
                      </span>
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Audit Log Drawer */}
      {showLogs && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-900 border-l border-slate-800 w-full max-w-md h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2 text-white">
                <History className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold">Knowledge Governance Audit Log</h3>
              </div>
              <button onClick={() => setShowLogs(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {stats?.recent_logs && stats.recent_logs.length > 0 ? (
                stats.recent_logs.map((log) => (
                  <div key={log.id} className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                        log.action === 'DEACTIVATE' ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      }`}>
                        {log.action}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">{log.performed_at}</span>
                    </div>
                    <div className="font-semibold text-slate-200 mt-1">{log.document_id}</div>
                    {log.reason && <div className="text-slate-400 text-[11px]">Reason: {log.reason}</div>}
                    {log.superseded_by && (
                      <div className="text-indigo-400 text-[11px] font-mono">Superseded by: {log.superseded_by}</div>
                    )}
                  </div>
                ))
              ) : (
                <div className="text-center py-12 text-slate-500 text-xs">
                  No governance actions recorded yet.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
