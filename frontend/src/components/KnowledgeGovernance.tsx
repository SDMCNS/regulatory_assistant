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
  Info
} from 'lucide-react';
import { AppSettings, RegulationItem, GovernanceStats } from '../types';
import {
  getRegulationsCatalog,
  getGovernanceStats,
  deactivateDocument,
  activateDocument,
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

  const originColor = (origin: string) => {
    switch (origin.toLowerCase()) {
      case 'easa': return 'bg-sky-950/80 text-sky-400 border-sky-800/60';
      case 'faa': return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60';
      case 'eu': return 'bg-blue-950/80 text-blue-400 border-blue-800/60';
      case 'skybrary': return 'bg-amber-950/80 text-amber-400 border-amber-800/60';
      case 'manual': return 'bg-teal-950/80 text-teal-400 border-teal-800/60';
      case 'note': return 'bg-purple-950/80 text-purple-400 border-purple-800/60';
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
