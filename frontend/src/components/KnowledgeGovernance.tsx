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
  ArrowUpRight,
  CheckSquare,
  Square,
  MinusSquare,
  Layers,
  SlidersHorizontal,
  FolderCheck,
  FolderX,
  BookOpen,
  Tag,
  Sparkles,
  Calendar,
  Zap,
  Sliders
} from 'lucide-react';
import {
  AppSettings,
  RegulationItem,
  GovernanceStats,
  UploadAnalysisResponse,
  IngestConfirmRequest,
  IngestionResultResponse,
  ComparisonMatchItem,
  CategoryStatsItem,
  SkybraryTopicItem,
  SkybraryTopicGovernanceResponse,
  CandidateTitleItem,
  ObsolescenceCandidateFinding,
  AiObsolescenceScanResponse
} from '../types';
import {
  getRegulationsCatalog,
  getGovernanceStats,
  deactivateDocument,
  activateDocument,
  batchDeactivateDocuments,
  batchActivateDocuments,
  deactivateCategory,
  activateCategory,
  getSkybraryTopics,
  deactivateSkybraryTopic,
  activateSkybraryTopic,
  analyzeDocumentUpload,
  confirmDocumentIngestion,
  scanObsolescenceWithAI,
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
  const [selectedSubtopic, setSelectedSubtopic] = useState<string>('all');

  // Deactivate Modal state
  const [selectedDoc, setSelectedDoc] = useState<RegulationItem | null>(null);
  const [deactivateReason, setDeactivateReason] = useState('');
  const [supersededBy, setSupersededBy] = useState('');
  const [showDeactivateModal, setShowDeactivateModal] = useState(false);

  // Multi-select Batch state
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [showBatchDeactivateModal, setShowBatchDeactivateModal] = useState(false);
  const [batchDeactivateReason, setBatchDeactivateReason] = useState('');
  const [batchSupersededBy, setBatchSupersededBy] = useState('');

  // Category Management & Category Deactivation state
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [showCategoryDeactivateModal, setShowCategoryDeactivateModal] = useState(false);
  const [targetCategory, setTargetCategory] = useState<string>('');
  const [categoryDeactivateReason, setCategoryDeactivateReason] = useState('');
  const [categorySupersededBy, setCategorySupersededBy] = useState('');

  // SKYbrary Subtopics Governance state
  const [skybraryTopics, setSkybraryTopics] = useState<SkybraryTopicItem[]>([]);
  const [showSkybraryTopicModal, setShowSkybraryTopicModal] = useState(false);
  const [skybraryTopicFilterSearch, setSkybraryTopicFilterSearch] = useState('');
  const [showSkybraryDeactivateModal, setShowSkybraryDeactivateModal] = useState(false);
  const [targetSkybraryTopic, setTargetSkybraryTopic] = useState<string>('');
  const [skybraryDeactivateReason, setSkybraryDeactivateReason] = useState('');
  const [skybrarySupersededBy, setSkybrarySupersededBy] = useState('');

  // Date & Obsolescence Pattern Filter state
  const [yearPreset, setYearPreset] = useState<'all' | 'legacy_pre_2015' | 'aging_2015_2019' | 'review_2020_2024' | 'recent_2025' | 'custom'>('all');
  const [customYearMin, setCustomYearMin] = useState<string>('');
  const [customYearMax, setCustomYearMax] = useState<string>('');
  const [patternFilter, setPatternFilter] = useState<string>('all');
  const [showAdvancedFilters, setShowAdvancedFilters] = useState<boolean>(true);

  // AI Obsolescence Review state
  const [showAiScanModal, setShowAiScanModal] = useState<boolean>(false);
  const [aiScanning, setAiScanning] = useState<boolean>(false);
  const [aiScanResponse, setAiScanResponse] = useState<AiObsolescenceScanResponse | null>(null);
  const [aiScanConfidenceFilter, setAiScanConfidenceFilter] = useState<'all' | 'HIGH' | 'MEDIUM' | 'LOW'>('all');
  const [aiScanSelectedDocIds, setAiScanSelectedDocIds] = useState<Set<string>>(new Set());
  const [aiScanFocus, setAiScanFocus] = useState<string>('all');

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

  const fetchSkybraryTopics = useCallback(async () => {
    try {
      const data = await getSkybraryTopics(settings);
      setSkybraryTopics(data || []);
    } catch (err: any) {
      console.error('Failed to load skybrary topics:', err);
    }
  }, [settings]);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRegulationsCatalog({
        origin: originFilter !== 'all' ? originFilter : undefined,
        subtopic: originFilter === 'skybrary' && selectedSubtopic !== 'all' ? selectedSubtopic : undefined,
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
  }, [originFilter, selectedSubtopic, statusFilter, searchQuery, settings]);

  useEffect(() => {
    fetchStats();
    fetchSkybraryTopics();
    fetchDocs();
  }, [fetchStats, fetchSkybraryTopics, fetchDocs]);

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

  // --- Multi-select Batch Handlers ---
  const handleToggleSelectDoc = (docId: string) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  // Filter documents by Date Preset and Obsolescence Pattern
  const displayedDocuments = useMemo(() => {
    return documents.filter((doc) => {
      // 1. Year Filter
      if (yearPreset === 'legacy_pre_2015') {
        const prim = doc.primary_year;
        const anyLegacy = (doc.detected_years || []).some(y => y <= 2014);
        if (!( (prim !== null && prim !== undefined && prim <= 2014) || anyLegacy )) return false;
      } else if (yearPreset === 'aging_2015_2019') {
        const prim = doc.primary_year;
        const anyAging = (doc.detected_years || []).some(y => y >= 2015 && y <= 2019);
        if (!( (prim !== null && prim !== undefined && prim >= 2015 && prim <= 2019) || anyAging )) return false;
      } else if (yearPreset === 'review_2020_2024') {
        const prim = doc.primary_year;
        const anyReview = (doc.detected_years || []).some(y => y >= 2020 && y <= 2024);
        if (!( (prim !== null && prim !== undefined && prim >= 2020 && prim <= 2024) || anyReview )) return false;
      } else if (yearPreset === 'recent_2025') {
        const prim = doc.primary_year;
        const anyRecent = (doc.detected_years || []).some(y => y >= 2025);
        if (!( (prim !== null && prim !== undefined && prim >= 2025) || anyRecent )) return false;
      } else if (yearPreset === 'custom') {
        const min = customYearMin ? parseInt(customYearMin, 10) : null;
        const max = customYearMax ? parseInt(customYearMax, 10) : null;
        if (min !== null && !isNaN(min)) {
          const prim = doc.primary_year;
          const anyMin = (doc.detected_years || []).some(y => y >= min);
          if (!( (prim !== null && prim !== undefined && prim >= min) || anyMin )) return false;
        }
        if (max !== null && !isNaN(max)) {
          const prim = doc.primary_year;
          const anyMax = (doc.detected_years || []).some(y => y <= max);
          if (!( (prim !== null && prim !== undefined && prim <= max) || anyMax )) return false;
        }
      }

      // 2. Pattern Flag Filter
      if (patternFilter !== 'all') {
        const flags = doc.obsolescence_flags || [];
        if (!flags.includes(patternFilter)) return false;
      }

      return true;
    });
  }, [documents, yearPreset, customYearMin, customYearMax, patternFilter]);

  const flaggedDocsInView = useMemo(() => {
    return displayedDocuments.filter(d => (d.obsolescence_flags || []).length > 0);
  }, [displayedDocuments]);

  const allVisibleSelected = useMemo(() => {
    return displayedDocuments.length > 0 && displayedDocuments.every((d) => selectedDocIds.has(d.document_id));
  }, [displayedDocuments, selectedDocIds]);

  const someVisibleSelected = useMemo(() => {
    return displayedDocuments.some((d) => selectedDocIds.has(d.document_id)) && !allVisibleSelected;
  }, [displayedDocuments, selectedDocIds, allVisibleSelected]);

  const handleToggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedDocIds((prev) => {
        const next = new Set(prev);
        displayedDocuments.forEach((d) => next.delete(d.document_id));
        return next;
      });
    } else {
      setSelectedDocIds((prev) => {
        const next = new Set(prev);
        displayedDocuments.forEach((d) => next.add(d.document_id));
        return next;
      });
    }
  };

  const handleSelectAllFlagged = () => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      flaggedDocsInView.forEach((d) => next.add(d.document_id));
      return next;
    });
  };

  const handleClearSelection = () => {
    setSelectedDocIds(new Set());
  };

  // --- AI Obsolescence Scan Handlers ---
  const handleLaunchAiScan = async (targetDocs?: RegulationItem[]) => {
    let candidates: RegulationItem[] = [];
    if (targetDocs && targetDocs.length > 0) {
      candidates = targetDocs;
    } else if (selectedDocIds.size > 0) {
      candidates = displayedDocuments.filter((d) => selectedDocIds.has(d.document_id));
    } else {
      candidates = displayedDocuments.slice(0, 80);
    }

    if (candidates.length === 0) {
      setError('No documents available in the current view to analyze with AI.');
      return;
    }

    setAiScanning(true);
    setShowAiScanModal(true);
    try {
      const payloadDocs: CandidateTitleItem[] = candidates.map((d) => ({
        document_id: d.document_id,
        title: d.title,
        origin: d.origin,
        subtopic: d.subtopic,
        year: d.primary_year
      }));

      const res = await scanObsolescenceWithAI(payloadDocs, aiScanFocus, settings);
      setAiScanResponse(res);
      // Pre-select HIGH confidence findings by default
      const preselected = new Set<string>();
      (res.findings || []).forEach((f) => {
        if (f.confidence === 'HIGH') {
          preselected.add(f.document_id);
        }
      });
      setAiScanSelectedDocIds(preselected);
    } catch (err: any) {
      setError(err.message || 'Failed to complete AI obsolescence review.');
    } finally {
      setAiScanning(false);
    }
  };

  const handleTransferAiSelectionToTable = () => {
    const updated = new Set(selectedDocIds);
    aiScanSelectedDocIds.forEach((id) => updated.add(id));
    setSelectedDocIds(updated);
    setShowAiScanModal(false);
    setSuccessMsg(`Added ${aiScanSelectedDocIds.size} AI-flagged candidate documents to batch selection.`);
  };

  const handleBatchSuppressFromAiScan = () => {
    if (aiScanSelectedDocIds.size === 0) return;
    setSelectedDocIds(new Set(aiScanSelectedDocIds));
    setShowAiScanModal(false);
    setBatchDeactivateReason('Identified as obsolete / superseded during AI regulatory review');
    setBatchSupersededBy('');
    setShowBatchDeactivateModal(true);
  };

  const handleOpenBatchDeactivateModal = () => {
    if (selectedDocIds.size === 0) return;
    setBatchDeactivateReason('');
    setBatchSupersededBy('');
    setShowBatchDeactivateModal(true);
  };

  const handleConfirmBatchDeactivate = async () => {
    if (selectedDocIds.size === 0) return;
    if (!batchDeactivateReason.trim()) {
      alert('Please provide a common reason for deactivation of the selected documents.');
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const docIdsList = Array.from(selectedDocIds);
      const res = await batchDeactivateDocuments(
        docIdsList,
        batchDeactivateReason.trim(),
        batchSupersededBy.trim() || undefined,
        settings
      );
      setSuccessMsg(res.message || `Successfully deactivated ${res.deactivated_documents} documents (${res.deactivated_chunks} chunks).`);
      setShowBatchDeactivateModal(false);
      setSelectedDocIds(new Set());
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || 'Failed to batch deactivate documents.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleBatchActivate = async () => {
    if (selectedDocIds.size === 0) return;
    if (!window.confirm(`Reactivate all ${selectedDocIds.size} selected document(s) and restore their chunks into the active search index?`)) {
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const docIdsList = Array.from(selectedDocIds);
      const res = await batchActivateDocuments(docIdsList, settings);
      setSuccessMsg(res.message || `Successfully reactivated ${res.activated_documents} documents (${res.activated_chunks} chunks).`);
      setSelectedDocIds(new Set());
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || 'Failed to batch reactivate documents.');
    } finally {
      setActionLoading(false);
    }
  };

  // --- Category Handlers ---
  const CATEGORY_META: Record<string, { label: string; desc: string }> = {
    easa: { label: 'EASA Easy Access', desc: 'European Union Aviation Safety Agency regulations and CSs' },
    faa: { label: 'FAA Title 14 CFR', desc: 'US Code of Federal Regulations aeronautics parts' },
    eu: { label: 'EU Formex Acts', desc: 'Official Journal of the EU aviation legislation' },
    skybrary: { label: 'SKYbrary Bookshelf', desc: 'Operational safety reference library and guidelines' },
    manual: { label: 'Company SOPs & Manuals', desc: 'Flight ops, ground ops, and maintenance manuals' },
    note: { label: 'Notes & Journals', desc: 'Internal working memos, safety bulletins, journals' },
    user: { label: 'User Documents', desc: 'User-uploaded regulatory and organizational documents' },
  };

  const handleOpenCategoryDeactivateModal = (category: string) => {
    setTargetCategory(category);
    setCategoryDeactivateReason('');
    setCategorySupersededBy('');
    setShowCategoryDeactivateModal(true);
  };

  const handleConfirmCategoryDeactivate = async () => {
    if (!targetCategory) return;
    if (!categoryDeactivateReason.trim()) {
      alert(`Please provide a common reason for deactivating category '${targetCategory.toUpperCase()}'.`);
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const res = await deactivateCategory(
        targetCategory,
        categoryDeactivateReason.trim(),
        categorySupersededBy.trim() || undefined,
        settings
      );
      setSuccessMsg(res.message || `Category '${targetCategory.toUpperCase()}' suppressed: ${res.deactivated_documents} documents deactivated.`);
      setShowCategoryDeactivateModal(false);
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || `Failed to deactivate category '${targetCategory}'.`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCategoryActivate = async (category: string) => {
    const catLabel = category.toUpperCase();
    if (!window.confirm(`Reactivate ALL documents in category '${catLabel}' and restore their clauses into the active search index?`)) {
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const res = await activateCategory(category, settings);
      setSuccessMsg(res.message || `Category '${catLabel}' activated: ${res.activated_documents} documents reactivated.`);
      await Promise.all([fetchStats(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || `Failed to activate category '${category}'.`);
    } finally {
      setActionLoading(false);
    }
  };

  // --- SKYbrary Subtopic Handlers ---
  const handleOpenSkybraryDeactivateModal = (topic: string) => {
    setTargetSkybraryTopic(topic);
    setSkybraryDeactivateReason('');
    setSkybrarySupersededBy('');
    setShowSkybraryDeactivateModal(true);
  };

  const handleConfirmSkybraryDeactivate = async () => {
    if (!targetSkybraryTopic) return;
    if (!skybraryDeactivateReason.trim()) {
      alert(`Please supply a common reason for suppressing SKYbrary subtopic '${targetSkybraryTopic}'.`);
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const res = await deactivateSkybraryTopic(
        targetSkybraryTopic,
        skybraryDeactivateReason.trim(),
        skybrarySupersededBy.trim() || undefined,
        settings
      );
      setSuccessMsg(res.message || `SKYbrary subtopic '${targetSkybraryTopic}' suppressed: ${res.deactivated_documents} documents deactivated.`);
      setShowSkybraryDeactivateModal(false);
      await Promise.all([fetchStats(), fetchSkybraryTopics(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || `Failed to deactivate SKYbrary subtopic '${targetSkybraryTopic}'.`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSkybraryActivate = async (topic: string) => {
    if (!window.confirm(`Reactivate all documents in SKYbrary subtopic '${topic}' and restore them into the active search index?`)) {
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      const res = await activateSkybraryTopic(topic, settings);
      setSuccessMsg(res.message || `SKYbrary subtopic '${topic}' reactivated: ${res.reactivated_documents} documents restored.`);
      await Promise.all([fetchStats(), fetchSkybraryTopics(), fetchDocs()]);
    } catch (err: any) {
      setError(err.message || `Failed to activate SKYbrary subtopic '${topic}'.`);
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

  const filteredSkybraryTopics = useMemo(() => {
    if (!skybraryTopicFilterSearch.trim()) return skybraryTopics;
    const q = skybraryTopicFilterSearch.toLowerCase();
    return skybraryTopics.filter((t) => t.topic.toLowerCase().includes(q));
  }, [skybraryTopics, skybraryTopicFilterSearch]);

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
            onClick={() => setShowCategoryModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-950/80 hover:bg-indigo-900/80 text-indigo-300 border border-indigo-700/60 shadow-sm transition-colors"
            title="Inspect category metrics and suppress or activate entire regulatory categories"
          >
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            <span>Category Controls</span>
          </button>
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
          <div className="flex items-center gap-2">
            <select
              value={originFilter}
              onChange={(e) => {
                setOriginFilter(e.target.value);
                if (e.target.value !== 'skybrary') {
                  setSelectedSubtopic('all');
                }
              }}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">All Origins</option>
              <option value="skybrary">SKYbrary Bookshelf</option>
              <option value="easa">EASA Easy Access</option>
              <option value="faa">FAA Title 14 CFR</option>
              <option value="eu">EU Formex Acts</option>
              <option value="manual">Company SOPs & Manuals</option>
              <option value="note">Notes & Journals</option>
              <option value="user">User Documents</option>
            </select>

            {/* SKYbrary Subtopic Granularity Dropdown & Controls */}
            {originFilter === 'skybrary' ? (
              <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
                <div className="flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-amber-400" />
                  <select
                    value={selectedSubtopic}
                    onChange={(e) => setSelectedSubtopic(e.target.value)}
                    className="bg-slate-950 border border-amber-800/60 text-amber-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-amber-500 max-w-[220px] truncate"
                    title="Filter by SKYbrary subtopic / bookshelf category"
                  >
                    <option value="all">All Subtopics ({skybraryTopics.length})</option>
                    {skybraryTopics.map((t) => (
                      <option key={t.topic} value={t.topic}>
                        {t.topic} ({t.active}/{t.total})
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="button"
                  onClick={() => setShowSkybraryTopicModal(true)}
                  className="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-amber-950/70 hover:bg-amber-900/80 text-amber-300 border border-amber-800/60 transition-colors flex items-center gap-1 shadow-sm"
                  title="View all 85 SKYbrary subtopics, metrics, and perform bulk topic suppression"
                >
                  <Tag className="w-3 h-3 text-amber-400" />
                  <span>Subtopic Manager</span>
                </button>

                {selectedSubtopic !== 'all' && (
                  <div className="flex items-center gap-1.5 pl-2 border-l border-slate-800">
                    <button
                      type="button"
                      onClick={() => handleOpenSkybraryDeactivateModal(selectedSubtopic)}
                      disabled={actionLoading}
                      className="px-2.5 py-1 text-xs font-medium rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800/80 transition-colors flex items-center gap-1 shadow-sm"
                      title={`Suppress all documents in SKYbrary subtopic '${selectedSubtopic}'`}
                    >
                      <FolderX className="w-3.5 h-3.5 text-rose-400" />
                      <span>Suppress Subtopic</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSkybraryActivate(selectedSubtopic)}
                      disabled={actionLoading}
                      className="px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-800/80 transition-colors flex items-center gap-1 shadow-sm"
                      title={`Activate all documents in SKYbrary subtopic '${selectedSubtopic}'`}
                    >
                      <FolderCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Activate Subtopic</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              /* Non-Skybrary Category Actions */
              originFilter !== 'all' && (
                <div className="flex items-center gap-1.5 pl-2 border-l border-slate-800">
                  <button
                    type="button"
                    onClick={() => handleOpenCategoryDeactivateModal(originFilter)}
                    disabled={actionLoading}
                    className="px-2.5 py-1 text-xs font-medium rounded-lg bg-rose-950/70 hover:bg-rose-900/80 text-rose-300 border border-rose-800/60 transition-colors flex items-center gap-1 shadow-sm"
                    title={`Suppress all documents in category '${originFilter.toUpperCase()}'`}
                  >
                    <FolderX className="w-3.5 h-3.5 text-rose-400" />
                    <span>Suppress Category</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleCategoryActivate(originFilter)}
                    disabled={actionLoading}
                    className="px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-950/70 hover:bg-emerald-900/80 text-emerald-300 border border-emerald-800/60 transition-colors flex items-center gap-1 shadow-sm"
                    title={`Activate all documents in category '${originFilter.toUpperCase()}'`}
                  >
                    <FolderCheck className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Activate Category</span>
                  </button>
                  {stats?.category_stats?.[originFilter] && (
                    <span className="text-[11px] font-mono text-slate-400 px-2 py-0.5 rounded bg-slate-950 border border-slate-800">
                      {stats.category_stats[originFilter].active} / {stats.category_stats[originFilter].total} active
                    </span>
                  )}
                </div>
              )
            )}
          </div>
        </div>

        {/* Obsolescence & Date Intelligence Filters Bar */}
        <div className="mt-3 pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Year & Pattern Filter Controls */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 text-slate-400 font-medium mr-1">
              <Calendar className="w-3.5 h-3.5 text-amber-400" />
              <span>Title Date:</span>
            </div>

            {/* Year Presets */}
            <div className="inline-flex rounded-lg bg-slate-950 p-0.5 border border-slate-800">
              <button
                type="button"
                onClick={() => setYearPreset('all')}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                  yearPreset === 'all'
                    ? 'bg-slate-800 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                All Years
              </button>
              <button
                type="button"
                onClick={() => setYearPreset('review_2020_2024')}
                className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all flex items-center gap-1 ${
                  yearPreset === 'review_2020_2024'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-sm'
                    : 'text-amber-400/80 hover:text-amber-300 hover:bg-amber-950/30'
                }`}
                title="Filter for titles dating between 2020 - 2024 (documents that at least need review)"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                <span>2020–2024 Review</span>
              </button>
              <button
                type="button"
                onClick={() => setYearPreset('aging_2015_2019')}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                  yearPreset === 'aging_2015_2019'
                    ? 'bg-slate-800 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Filter for regulations from 2015 - 2019"
              >
                2015–2019
              </button>
              <button
                type="button"
                onClick={() => setYearPreset('legacy_pre_2015')}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                  yearPreset === 'legacy_pre_2015'
                    ? 'bg-slate-800 text-rose-300 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Filter for legacy regulations prior to 2015 (high obsolescence probability)"
              >
                Pre-2015 Legacy
              </button>
              <button
                type="button"
                onClick={() => setYearPreset('recent_2025')}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                  yearPreset === 'recent_2025'
                    ? 'bg-slate-800 text-emerald-300 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Filter for recent regulations (2025+)"
              >
                2025+
              </button>
              <button
                type="button"
                onClick={() => setYearPreset('custom')}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                  yearPreset === 'custom'
                    ? 'bg-slate-800 text-indigo-300 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Custom Range
              </button>
            </div>

            {/* Custom Range Inputs */}
            {yearPreset === 'custom' && (
              <div className="flex items-center gap-1 bg-slate-950 px-2 py-0.5 rounded-lg border border-slate-800">
                <input
                  type="number"
                  placeholder="Min (e.g. 2018)"
                  value={customYearMin}
                  onChange={(e) => setCustomYearMin(e.target.value)}
                  className="w-20 bg-transparent text-slate-200 text-[11px] font-mono outline-none placeholder:text-slate-600"
                />
                <span className="text-slate-500 text-[10px]">–</span>
                <input
                  type="number"
                  placeholder="Max (e.g. 2024)"
                  value={customYearMax}
                  onChange={(e) => setCustomYearMax(e.target.value)}
                  className="w-20 bg-transparent text-slate-200 text-[11px] font-mono outline-none placeholder:text-slate-600"
                />
              </div>
            )}

            {/* Pattern Filter Dropdown */}
            <div className="flex items-center gap-1.5 ml-1">
              <span className="text-slate-500 text-[11px]">Pattern:</span>
              <select
                value={patternFilter}
                onChange={(e) => setPatternFilter(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
              >
                <option value="all">All Regulatory Patterns</option>
                <option value="KNOWN_REPEALED">⚠️ Known Repealed (EC 216/2008, etc.)</option>
                <option value="SUPERSEDED_KEYWORD">🔄 'Superseded / Replaced' in Title</option>
                <option value="DRAFT">📝 Draft / Working Document</option>
                <option value="EARLY_REVISION">📌 Early Revision (Issue/Amdt 0-1)</option>
                <option value="COVID_TEMPORARY">⏱️ COVID / Temporary Exemption</option>
                <option value="OLD_SKYBRARY">📚 Old SKYbrary Article (&lt;2018)</option>
              </select>
            </div>
          </div>

          {/* Quick Selection & AI Obsolescence Scanner */}
          <div className="flex items-center gap-2">
            {flaggedDocsInView.length > 0 && (
              <button
                type="button"
                onClick={handleSelectAllFlagged}
                className="px-2.5 py-1 rounded-lg bg-amber-950/50 hover:bg-amber-900/60 text-amber-300 border border-amber-800/60 text-[11px] font-medium transition-colors flex items-center gap-1.5"
                title={`Select all ${flaggedDocsInView.length} documents with obsolescence/review flags in view`}
              >
                <Zap className="w-3 h-3 text-amber-400" />
                <span>Select Flagged ({flaggedDocsInView.length})</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => handleLaunchAiScan()}
              disabled={aiScanning || displayedDocuments.length === 0}
              className="px-3 py-1 rounded-lg bg-gradient-to-r from-indigo-900/80 to-purple-900/80 hover:from-indigo-800 hover:to-purple-800 text-indigo-100 border border-indigo-700/60 text-[11px] font-semibold transition-all shadow-sm flex items-center gap-1.5 disabled:opacity-50"
              title="Use LLM to scan current view for obsolete, repealed, and superseded regulatory titles"
            >
              <Sparkles className="w-3.5 h-3.5 text-indigo-300 animate-pulse" />
              <span>
                {aiScanning
                  ? 'AI Scanning...'
                  : selectedDocIds.size > 0
                  ? `AI Review Selected (${selectedDocIds.size})`
                  : `✨ AI Obsolescence Review (${Math.min(displayedDocuments.length, 80)})`}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Document Table View */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
            <p className="text-xs">Loading regulations catalog with governance states...</p>
          </div>
        ) : displayedDocuments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2 border border-dashed border-slate-800 rounded-xl p-8">
            <ShieldAlert className="w-8 h-8 text-slate-600" />
            <p className="text-sm font-medium text-slate-300">No regulations match the selected filters or date ranges.</p>
            <p className="text-xs text-slate-500">Try adjusting your search query, status filter, date range, or pattern recognition filter.</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {/* Table Selection Header */}
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800/80 text-xs text-slate-400">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleToggleSelectAllVisible}
                  className="flex items-center gap-2 hover:text-white transition-colors"
                  title={allVisibleSelected ? 'Deselect all visible documents' : 'Select all visible documents'}
                >
                  {allVisibleSelected ? (
                    <CheckSquare className="w-4 h-4 text-indigo-400" />
                  ) : someVisibleSelected ? (
                    <MinusSquare className="w-4 h-4 text-indigo-400" />
                  ) : (
                    <Square className="w-4 h-4 text-slate-500" />
                  )}
                  <span className="font-medium">
                    {allVisibleSelected ? 'Deselect All Visible' : 'Select All Visible'} ({displayedDocuments.length})
                  </span>
                </button>

                {selectedDocIds.size > 0 && (
                  <span className="text-indigo-400 font-semibold font-mono">
                    • {selectedDocIds.size} selected
                  </span>
                )}
              </div>

              <div className="flex items-center gap-3">
                {selectedDocIds.size > 0 && (
                  <button
                    type="button"
                    onClick={handleClearSelection}
                    className="text-[11px] text-slate-500 hover:text-slate-300 underline transition-colors"
                  >
                    Clear selection
                  </button>
                )}
                <span>
                  Showing <strong className="text-slate-200">{displayedDocuments.length}</strong> of {documents.length} regulations
                </span>
              </div>
            </div>

            {displayedDocuments.map((doc) => {
              const isActive = doc.is_active !== false;
              const isSelected = selectedDocIds.has(doc.document_id);
              return (
                <div
                  key={doc.document_id}
                  className={`p-4 rounded-xl border transition-all ${
                    isSelected
                      ? 'ring-1 ring-indigo-500 bg-slate-900/90 border-indigo-500/60 shadow-md shadow-indigo-950/40'
                      : isActive
                      ? 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700'
                      : 'bg-rose-950/20 border-rose-900/40 hover:border-rose-800/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      {/* Row Checkbox */}
                      <button
                        type="button"
                        onClick={() => handleToggleSelectDoc(doc.document_id)}
                        className="mt-0.5 text-slate-500 hover:text-indigo-400 transition-colors shrink-0"
                        title={isSelected ? 'Deselect' : 'Select for batch action'}
                      >
                        {isSelected ? (
                          <CheckSquare className="w-4 h-4 text-indigo-400" />
                        ) : (
                          <Square className="w-4 h-4 text-slate-600 hover:text-slate-400" />
                        )}
                      </button>

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

                        {/* Year Badge */}
                        {doc.primary_year && (
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                              doc.primary_year >= 2020 && doc.primary_year <= 2024
                                ? 'bg-amber-950/80 text-amber-300 border-amber-700/80'
                                : doc.primary_year < 2015
                                ? 'bg-rose-950/70 text-rose-300 border-rose-800/60'
                                : doc.primary_year >= 2025
                                ? 'bg-emerald-950/70 text-emerald-300 border-emerald-800/60'
                                : 'bg-slate-800 text-slate-300 border-slate-700'
                            }`}
                            title={
                              doc.primary_year >= 2020 && doc.primary_year <= 2024
                                ? 'Title dated 2020-2024: Indicates title at least needs review'
                                : `Title detected year: ${doc.primary_year}`
                            }
                          >
                            Year: {doc.primary_year}
                            {doc.primary_year >= 2020 && doc.primary_year <= 2024 && ' • Needs Review'}
                          </span>
                        )}

                        {/* Obsolescence Pattern Flags */}
                        {doc.obsolescence_flags && doc.obsolescence_flags.map((flag) => {
                          if (flag.startsWith('YEAR_') || flag === 'RECENT_2025_PLUS' || flag === 'REVIEW_2020_2024' || flag === 'AGING_2015_2019' || flag === 'LEGACY_PRE_2015') {
                            return null; // Shown in year badge above
                          }
                          return (
                            <span
                              key={flag}
                              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border flex items-center gap-1 ${
                                flag === 'KNOWN_REPEALED'
                                  ? 'bg-red-950/90 text-red-300 border-red-700'
                                  : flag === 'SUPERSEDED_KEYWORD'
                                  ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                                  : flag === 'COVID_TEMPORARY'
                                  ? 'bg-orange-950/80 text-orange-300 border-orange-800'
                                  : flag === 'DRAFT'
                                  ? 'bg-yellow-950/80 text-yellow-300 border-yellow-800'
                                  : 'bg-purple-950/80 text-purple-300 border-purple-800'
                              }`}
                              title={`Pattern flag: ${flag}`}
                            >
                              <AlertTriangle className="w-2.5 h-2.5 shrink-0" />
                              <span>{flag.replace(/_/g, ' ')}</span>
                            </span>
                          );
                        })}

                        {/* Subtopic Badge */}
                        {doc.subtopic && (
                          <span
                            className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-950/70 text-amber-300 border border-amber-800/60 flex items-center gap-1 max-w-[240px] truncate"
                            title={`SKYbrary Subtopic: ${doc.subtopic}`}
                          >
                            <Tag className="w-2.5 h-2.5 text-amber-400 shrink-0" />
                            <span className="truncate">{doc.subtopic}</span>
                          </span>
                        )}

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

      {/* Floating Batch Action Bar */}
      {selectedDocIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-slate-900/95 border border-indigo-500/60 shadow-2xl shadow-indigo-950/80 rounded-2xl px-5 py-3 flex items-center gap-4 backdrop-blur-md animate-in slide-in-from-bottom-5 duration-200">
          <div className="flex items-center gap-2 pr-3 border-r border-slate-700">
            <CheckSquare className="w-4 h-4 text-indigo-400 shrink-0" />
            <span className="text-xs font-semibold text-white whitespace-nowrap">
              <span className="text-indigo-400 font-bold font-mono">{selectedDocIds.size}</span> document{selectedDocIds.size > 1 ? 's' : ''} selected
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleOpenBatchDeactivateModal}
              disabled={actionLoading}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
              title="Deactivate and suppress all selected documents with a common reason"
            >
              <Archive className="w-3.5 h-3.5" />
              <span>Batch Suppress ({selectedDocIds.size})</span>
            </button>
            <button
              onClick={handleBatchActivate}
              disabled={actionLoading}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
              title="Reactivate all selected documents"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Batch Reactivate ({selectedDocIds.size})</span>
            </button>
            <button
              onClick={handleClearSelection}
              className="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors flex items-center gap-1"
            >
              <X className="w-3.5 h-3.5" />
              <span>Deselect</span>
            </button>
          </div>
        </div>
      )}

      {/* Batch Deactivate Modal */}
      {showBatchDeactivateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2 text-rose-400">
                <AlertTriangle className="w-5 h-5" />
                <h2 className="text-base font-bold text-white">Batch Deactivate / Suppress Documents</h2>
              </div>
              <button
                onClick={() => setShowBatchDeactivateModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl">
                <div className="text-xs text-slate-400">Batch Target:</div>
                <div className="text-sm font-semibold text-white mt-0.5">
                  <span className="text-rose-400 font-bold">{selectedDocIds.size}</span> documents selected for deactivation
                </div>
                <div className="text-[11px] font-mono text-slate-500 mt-1 max-h-24 overflow-y-auto space-y-0.5">
                  {Array.from(selectedDocIds).slice(0, 10).map((id) => (
                    <div key={id} className="truncate">• {id}</div>
                  ))}
                  {selectedDocIds.size > 10 && (
                    <div className="text-slate-400 italic">...and {selectedDocIds.size - 10} more</div>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Common Reason for Batch Deactivation <span className="text-rose-400">*</span>
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Batch superseded by updated regulation package, obsolete advisory guidance, or periodic archive..."
                  value={batchDeactivateReason}
                  onChange={(e) => setBatchDeactivateReason(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Superseding Document / Package Reference <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Regulation (EU) 2024/..., or Updated Manual Suite 2026"
                  value={batchSupersededBy}
                  onChange={(e) => setBatchSupersededBy(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-900/40 text-xs text-rose-300 flex items-start gap-2">
                <Info className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
                <span>
                  <strong>Batch Knowledge Forgetting:</strong> All chunks belonging to these {selectedDocIds.size} documents will be set to <code className="text-rose-200">is_active = 0</code>. They will be suppressed immediately from all RAG vector and keyword search operations.
                </span>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowBatchDeactivateModal(false)}
                disabled={actionLoading}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmBatchDeactivate}
                disabled={actionLoading || !batchDeactivateReason.trim()}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm Batch Deactivation ({selectedDocIds.size})</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Category Deactivate Modal */}
      {showCategoryDeactivateModal && targetCategory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2 text-rose-400">
                <FolderX className="w-5 h-5" />
                <h2 className="text-base font-bold text-white">Suppress Entire Category</h2>
              </div>
              <button
                onClick={() => setShowCategoryDeactivateModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
                <div className="text-xs text-slate-400">Target Category:</div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-mono uppercase font-bold border ${originColor(targetCategory)}`}>
                    {targetCategory}
                  </span>
                  <span className="text-sm font-semibold text-white">
                    {CATEGORY_META[targetCategory]?.label || targetCategory}
                  </span>
                </div>
                {stats?.category_stats?.[targetCategory] && (
                  <div className="text-xs text-slate-400 mt-1">
                    Affects: <strong className="text-rose-400 font-mono">{stats.category_stats[targetCategory].active}</strong> active documents out of {stats.category_stats[targetCategory].total} total
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Reason for Category Suppression <span className="text-rose-400">*</span>
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Scope adjustment: deactivating all FAA CFR provisions for EU-only compliance assessment..."
                  value={categoryDeactivateReason}
                  onChange={(e) => setCategoryDeactivateReason(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Superseding Category Reference <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. EASA Easy Access Suite"
                  value={categorySupersededBy}
                  onChange={(e) => setCategorySupersededBy(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-900/50 text-xs text-rose-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
                <span>
                  <strong>Full Category Suppression:</strong> Every document under <strong>{targetCategory.toUpperCase()}</strong> will be deactivated and tombstoned with this reason. All associated clauses will be excluded from RAG searches until reactivated.
                </span>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowCategoryDeactivateModal(false)}
                disabled={actionLoading}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmCategoryDeactivate}
                disabled={actionLoading || !categoryDeactivateReason.trim()}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Suppress All in {targetCategory.toUpperCase()}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Category Management Modal */}
      {showCategoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150 my-8">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2 text-indigo-400">
                <Layers className="w-5 h-5" />
                <div>
                  <h2 className="text-base font-bold text-white">Category-Level Knowledge Governance</h2>
                  <p className="text-[11px] text-slate-400">
                    Suppress or activate whole bodies of regulation in a single operation
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowCategoryModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              {Object.entries(CATEGORY_META).map(([catKey, meta]) => {
                const catStat = stats?.category_stats?.[catKey] || { total: 0, active: 0, deactivated: 0 };

                return (
                  <div
                    key={catKey}
                    className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-bold border ${originColor(catKey)}`}>
                          {catKey}
                        </span>
                        <h4 className="text-sm font-semibold text-white">{meta.label}</h4>
                      </div>
                      <p className="text-xs text-slate-400">{meta.desc}</p>
                      <div className="flex items-center gap-3 mt-2 text-[11px] font-mono">
                        <span className="text-slate-300">Total: <strong>{catStat.total}</strong></span>
                        <span className="text-emerald-400">Active: <strong>{catStat.active}</strong></span>
                        <span className="text-rose-400">Suppressed: <strong>{catStat.deactivated}</strong></span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          setOriginFilter(catKey);
                          setShowCategoryModal(false);
                        }}
                        className="px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
                        title={`Filter main table by ${meta.label}`}
                      >
                        Inspect
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setShowCategoryModal(false);
                          handleOpenCategoryDeactivateModal(catKey);
                        }}
                        disabled={actionLoading || catStat.active === 0}
                        className="px-2.5 py-1 text-xs font-medium rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800/80 transition-colors flex items-center gap-1 disabled:opacity-40"
                        title="Deactivate all documents in this category"
                      >
                        <FolderX className="w-3.5 h-3.5 text-rose-400" />
                        <span>Suppress All</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          handleCategoryActivate(catKey);
                        }}
                        disabled={actionLoading || catStat.deactivated === 0}
                        className="px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-800/80 transition-colors flex items-center gap-1 disabled:opacity-40"
                        title="Reactivate all documents in this category"
                      >
                        <FolderCheck className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Activate All</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setShowCategoryModal(false)}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SKYbrary Subtopic Deactivate Modal */}
      {showSkybraryDeactivateModal && targetSkybraryTopic && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2 text-rose-400">
                <FolderX className="w-5 h-5" />
                <h2 className="text-base font-bold text-white">Suppress SKYbrary Subtopic</h2>
              </div>
              <button
                onClick={() => setShowSkybraryDeactivateModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
                <div className="text-xs text-slate-400">Target Subtopic:</div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-amber-950/80 text-amber-300 border border-amber-800/60">
                    {targetSkybraryTopic}
                  </span>
                  <span className="text-xs text-slate-400">in SKYbrary Bookshelf</span>
                </div>
                {(() => {
                  const topicStat = skybraryTopics.find((t) => t.topic.toLowerCase() === targetSkybraryTopic.toLowerCase());
                  if (topicStat) {
                    return (
                      <div className="text-xs text-slate-400 mt-1">
                        Affects: <strong className="text-rose-400 font-mono">{topicStat.active}</strong> active documents out of {topicStat.total} total
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Common Reason for Subtopic Suppression <span className="text-rose-400">*</span>
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Obsolete accident investigation guidance, archived advisory topic, or scope reduction..."
                  value={skybraryDeactivateReason}
                  onChange={(e) => setSkybraryDeactivateReason(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Superseding Topic / Guidance Reference <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Modern SKYbrary 2026 Bookshelf Update"
                  value={skybrarySupersededBy}
                  onChange={(e) => setSkybrarySupersededBy(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-900/50 text-xs text-rose-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
                <span>
                  <strong>Full Subtopic Suppression:</strong> All documents classified under <strong>{targetSkybraryTopic}</strong> will be tombstoned and deactivated (<code className="text-rose-200">is_active = 0</code>). All of their clauses will be excluded from RAG and BM25 searches.
                </span>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowSkybraryDeactivateModal(false)}
                disabled={actionLoading}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmSkybraryDeactivate}
                disabled={actionLoading || !skybraryDeactivateReason.trim()}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {actionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Suppress All in {targetSkybraryTopic}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SKYbrary Topics Manager Modal */}
      {showSkybraryTopicModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150 my-8 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-2.5 text-amber-400">
                <BookOpen className="w-5 h-5" />
                <div>
                  <h2 className="text-base font-bold text-white">SKYbrary Subtopics Knowledge Governance</h2>
                  <p className="text-[11px] text-slate-400">
                    Granularly filter, inspect, suppress, or activate documents by subtopic domain ({skybraryTopics.length} distinct subtopics)
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowSkybraryTopicModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Search filter for subtopics */}
            <div className="py-3 shrink-0">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
                <input
                  type="text"
                  placeholder="Filter SKYbrary subtopics (e.g. Accident Reports, Human Factors, Weather, Runway...)"
                  value={skybraryTopicFilterSearch}
                  onChange={(e) => setSkybraryTopicFilterSearch(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>

            <div className="space-y-2.5 overflow-y-auto flex-1 pr-1">
              {filteredSkybraryTopics.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs">
                  No SKYbrary subtopics match "{skybraryTopicFilterSearch}".
                </div>
              ) : (
                filteredSkybraryTopics.map((topicItem) => {
                  const isCurrentFilter = originFilter === 'skybrary' && selectedSubtopic.toLowerCase() === topicItem.topic.toLowerCase();

                  return (
                    <div
                      key={topicItem.topic}
                      className={`p-3.5 rounded-xl border transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                        isCurrentFilter
                          ? 'bg-amber-950/20 border-amber-800/80'
                          : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Tag className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                          <h4 className="text-sm font-semibold text-white truncate">{topicItem.topic}</h4>
                        </div>
                        <div className="flex items-center gap-3 text-[11px] font-mono">
                          <span className="text-slate-300">Total: <strong>{topicItem.total.toLocaleString()}</strong> docs</span>
                          <span className="text-emerald-400">Active: <strong>{topicItem.active.toLocaleString()}</strong></span>
                          <span className="text-rose-400">Suppressed: <strong>{topicItem.deactivated.toLocaleString()}</strong></span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => {
                            setOriginFilter('skybrary');
                            setSelectedSubtopic(topicItem.topic);
                            setShowSkybraryTopicModal(false);
                          }}
                          className={`px-2.5 py-1 text-xs font-medium rounded-lg border transition-colors ${
                            isCurrentFilter
                              ? 'bg-amber-600 text-white border-amber-500'
                              : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                          }`}
                          title={`Filter catalog table to '${topicItem.topic}'`}
                        >
                          {isCurrentFilter ? 'Active Filter' : 'Filter in Table'}
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            setShowSkybraryTopicModal(false);
                            handleOpenSkybraryDeactivateModal(topicItem.topic);
                          }}
                          disabled={actionLoading || topicItem.active === 0}
                          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800/80 transition-colors flex items-center gap-1 disabled:opacity-40"
                          title={`Suppress all ${topicItem.active} active documents in this subtopic`}
                        >
                          <FolderX className="w-3.5 h-3.5 text-rose-400" />
                          <span>Suppress Topic</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            handleSkybraryActivate(topicItem.topic);
                          }}
                          disabled={actionLoading || topicItem.deactivated === 0}
                          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-800/80 transition-colors flex items-center gap-1 disabled:opacity-40"
                          title={`Reactivate all ${topicItem.deactivated} suppressed documents in this subtopic`}
                        >
                          <FolderCheck className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Activate Topic</span>
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800 flex justify-end shrink-0">
              <button
                onClick={() => setShowSkybraryTopicModal(false)}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
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
                      accept=".pdf,.xml,.txt,.md,.docx,.doc,.html"
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
                        Supports PDF, Word (.DOC / .DOCX), XML (EASA, EU Formex, FAA CFR), Markdown, TXT, HTML.
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-950 text-sky-300 border border-sky-800">EASA / FAA / EU XML</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-950 text-blue-300 border border-blue-800">Word .DOC / .DOCX</span>
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
                      {analysisResult.extracted_metadata.author && (
                        <span>Author: <strong className="text-white">{analysisResult.extracted_metadata.author}</strong></span>
                      )}
                      {analysisResult.extracted_metadata.is_word && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-900/60 text-blue-200 border border-blue-700/60 font-mono">
                          {analysisResult.extracted_metadata.word_format?.toUpperCase() || 'WORD'}
                        </span>
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

      {/* AI Obsolescence Review Modal */}
      {showAiScanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/70">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-900/30">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span>AI Obsolescence & Superseding Review</span>
                    {aiScanResponse && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800 font-mono">
                        {aiScanResponse.flagged_count} candidates found
                      </span>
                    )}
                  </h3>
                  <p className="text-xs text-slate-400">
                    Autonomous regulatory analysis identifying repealed EU/UK frameworks, expired exemptions, and outdated titles
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowAiScanModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scan Configuration & Controls Bar */}
            <div className="px-6 py-3 bg-slate-950/40 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-medium">Scan Focus:</span>
                <select
                  value={aiScanFocus}
                  onChange={(e) => setAiScanFocus(e.target.value)}
                  disabled={aiScanning}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 focus:outline-none focus:border-indigo-500 font-mono text-xs"
                >
                  <option value="general">General Obsolescence & Repeals</option>
                  <option value="dates_2020_2024">Aging Titles (2020–2024 & Older Review Window)</option>
                  <option value="repealed_eu">Repealed EU Frameworks (Basic Regs, EC 216/2008)</option>
                  <option value="covid_exemptions">COVID-19 Emergency & Temporary Exemptions</option>
                </select>
              </div>

              <button
                type="button"
                onClick={() => handleLaunchAiScan()}
                disabled={aiScanning}
                className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50 shadow-sm"
              >
                {aiScanning ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Analyzing Regulations...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Re-scan Current View</span>
                  </>
                )}
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {aiScanning ? (
                <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
                  <div className="relative">
                    <div className="w-16 h-16 rounded-full border-4 border-indigo-500/20 border-t-indigo-500 animate-spin"></div>
                    <Sparkles className="w-7 h-7 text-indigo-400 absolute inset-0 m-auto animate-pulse" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-200">
                      Analyzing Regulatory Corpus with AI
                    </h4>
                    <p className="text-xs text-slate-400 mt-1 max-w-sm">
                      Evaluating document titles, years, legal structure, and basic regulation repeal lineage...
                    </p>
                  </div>
                </div>
              ) : !aiScanResponse || aiScanResponse.findings.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center border border-dashed border-slate-800 rounded-2xl p-8 space-y-3">
                  <ShieldCheck className="w-12 h-12 text-emerald-400" />
                  <div>
                    <h4 className="text-sm font-bold text-slate-200">No Obsolete Regulations Found</h4>
                    <p className="text-xs text-slate-400 mt-1 max-w-md">
                      The titles analyzed appear active, current, and consistent with known aviation regulatory frameworks.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* AI Summary Banner */}
                  {aiScanResponse.summary && (
                    <div className="p-3.5 rounded-xl bg-indigo-950/40 border border-indigo-800/60 text-xs text-indigo-200 leading-relaxed flex items-start gap-2.5">
                      <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold text-white">AI Legal Analysis: </span>
                        {aiScanResponse.summary}
                      </div>
                    </div>
                  )}

                  {/* Summary Metric Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                      <div className="text-slate-500 text-[10px]">Scanned Documents</div>
                      <div className="text-lg font-bold font-mono text-slate-200 mt-0.5">
                        {aiScanResponse.total_scanned}
                      </div>
                    </div>
                    <div className="p-3 bg-rose-950/30 border border-rose-900/40 rounded-xl">
                      <div className="text-rose-400/90 text-[10px]">Obsolete Candidates</div>
                      <div className="text-lg font-bold font-mono text-rose-300 mt-0.5">
                        {aiScanResponse.flagged_count}
                      </div>
                    </div>
                    <div className="p-3 bg-red-950/40 border border-red-800/60 rounded-xl">
                      <div className="text-red-400 text-[10px]">High Confidence</div>
                      <div className="text-lg font-bold font-mono text-red-300 mt-0.5">
                        {aiScanResponse.high_confidence_count}
                      </div>
                    </div>
                    <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-xl">
                      <div className="text-amber-400 text-[10px]">Medium / Review</div>
                      <div className="text-lg font-bold font-mono text-amber-300 mt-0.5">
                        {aiScanResponse.medium_confidence_count}
                      </div>
                    </div>
                  </div>

                  {/* Confidence Filter & Quick Selection Toolbar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-800/70 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 font-medium text-[11px]">Filter:</span>
                      <div className="inline-flex rounded-lg bg-slate-950 p-0.5 border border-slate-800">
                        <button
                          type="button"
                          onClick={() => setAiScanConfidenceFilter('ALL')}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            aiScanConfidenceFilter === 'ALL'
                              ? 'bg-slate-800 text-white'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          All ({aiScanResponse.findings.length})
                        </button>
                        <button
                          type="button"
                          onClick={() => setAiScanConfidenceFilter('HIGH')}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            aiScanConfidenceFilter === 'HIGH'
                              ? 'bg-red-900/60 text-red-300 font-semibold'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          High Confidence ({aiScanResponse.high_confidence_count})
                        </button>
                        <button
                          type="button"
                          onClick={() => setAiScanConfidenceFilter('MEDIUM_PLUS')}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                            aiScanConfidenceFilter === 'MEDIUM_PLUS'
                              ? 'bg-amber-900/60 text-amber-300 font-semibold'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          Medium + High ({aiScanResponse.high_confidence_count + aiScanResponse.medium_confidence_count})
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const allIds = new Set(
                            aiScanResponse.findings
                              .filter((f) => {
                                if (aiScanConfidenceFilter === 'HIGH') return f.confidence === 'HIGH';
                                if (aiScanConfidenceFilter === 'MEDIUM_PLUS') return f.confidence === 'HIGH' || f.confidence === 'MEDIUM';
                                return true;
                              })
                              .map((f) => f.document_id)
                          );
                          setAiScanSelectedDocIds(allIds);
                        }}
                        className="text-[11px] text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
                      >
                        Select All In View
                      </button>
                      <span className="text-slate-700">•</span>
                      <button
                        type="button"
                        onClick={() => {
                          const highIds = new Set(
                            aiScanResponse.findings
                              .filter((f) => f.confidence === 'HIGH')
                              .map((f) => f.document_id)
                          );
                          setAiScanSelectedDocIds(highIds);
                        }}
                        className="text-[11px] text-red-400 hover:text-red-300 font-medium transition-colors"
                      >
                        Select High Only
                      </button>
                      <span className="text-slate-700">•</span>
                      <button
                        type="button"
                        onClick={() => setAiScanSelectedDocIds(new Set())}
                        className="text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
                      >
                        Clear
                      </button>
                    </div>
                  </div>

                  {/* Findings Cards List */}
                  <div className="space-y-2.5">
                    {aiScanResponse.findings
                      .filter((f) => {
                        if (aiScanConfidenceFilter === 'HIGH') return f.confidence === 'HIGH';
                        if (aiScanConfidenceFilter === 'MEDIUM_PLUS') return f.confidence === 'HIGH' || f.confidence === 'MEDIUM';
                        return true;
                      })
                      .map((finding) => {
                        const isChecked = aiScanSelectedDocIds.has(finding.document_id);
                        return (
                          <div
                            key={finding.document_id}
                            className={`p-3.5 rounded-xl border transition-all ${
                              isChecked
                                ? 'bg-slate-900/90 border-indigo-500/70 shadow-md ring-1 ring-indigo-500/50'
                                : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              {/* Selection Checkbox */}
                              <button
                                type="button"
                                onClick={() => {
                                  setAiScanSelectedDocIds((prev) => {
                                    const next = new Set(prev);
                                    if (next.has(finding.document_id)) {
                                      next.delete(finding.document_id);
                                    } else {
                                      next.add(finding.document_id);
                                    }
                                    return next;
                                  });
                                }}
                                className="mt-0.5 text-slate-500 hover:text-indigo-400 transition-colors shrink-0"
                              >
                                {isChecked ? (
                                  <CheckSquare className="w-4 h-4 text-indigo-400" />
                                ) : (
                                  <Square className="w-4 h-4 text-slate-600 hover:text-slate-400" />
                                )}
                              </button>

                              <div className="flex-1 min-w-0">
                                {/* Badges Header */}
                                <div className="flex items-center gap-2 flex-wrap mb-1">
                                  {/* Status Badge */}
                                  <span
                                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                      finding.likely_status === 'REPEALED'
                                        ? 'bg-red-950/90 text-red-300 border-red-700'
                                        : finding.likely_status === 'SUPERSEDED'
                                        ? 'bg-rose-950/90 text-rose-300 border-rose-700'
                                        : finding.likely_status === 'EXPIRED'
                                        ? 'bg-orange-950/90 text-orange-300 border-orange-700'
                                        : finding.likely_status === 'DRAFT'
                                        ? 'bg-yellow-950/90 text-yellow-300 border-yellow-700'
                                        : 'bg-amber-950/90 text-amber-300 border-amber-700'
                                    }`}
                                  >
                                    {(finding.likely_status || 'OBSOLETE').replace(/_/g, ' ')}
                                  </span>

                                  {/* Confidence Badge */}
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase border ${
                                      finding.confidence === 'HIGH'
                                        ? 'bg-red-950/60 text-red-400 border-red-800'
                                        : finding.confidence === 'MEDIUM'
                                        ? 'bg-amber-950/60 text-amber-400 border-amber-800'
                                        : 'bg-slate-800 text-slate-400 border-slate-700'
                                    }`}
                                  >
                                    {finding.confidence} Confidence
                                  </span>

                                  {finding.detected_year && (
                                    <span
                                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                                        finding.detected_year >= 2020 && finding.detected_year <= 2024
                                          ? 'bg-amber-950/80 text-amber-300 border-amber-800'
                                          : 'bg-slate-800 text-slate-300 border-slate-700'
                                      }`}
                                    >
                                      Year: {finding.detected_year}
                                    </span>
                                  )}

                                  {finding.origin && (
                                    <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-slate-900 text-slate-400 border border-slate-800">
                                      {finding.origin}
                                    </span>
                                  )}
                                </div>

                                {/* Title & Doc ID */}
                                <h4 className="text-xs font-semibold text-slate-100 leading-snug">
                                  {finding.title}
                                </h4>
                                <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                                  ID: {finding.document_id}
                                </div>

                                {/* Analysis Explanation */}
                                <p className="text-xs text-slate-300 bg-slate-900/70 p-2.5 rounded-lg border border-slate-800/80 mt-2 leading-relaxed">
                                  {finding.reason}
                                </p>

                                {/* Superseded Successor Reference */}
                                {finding.superseded_by && (
                                  <div className="mt-2 text-[11px] text-emerald-300 font-mono flex items-center gap-1.5 bg-emerald-950/30 px-2 py-1 rounded border border-emerald-900/50">
                                    <ArrowRight className="w-3 h-3 text-emerald-400 shrink-0" />
                                    <span>Superseded by successor: <strong className="text-white">{finding.superseded_by}</strong></span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-between bg-slate-950/80 shrink-0">
              <div className="text-xs text-slate-400">
                <strong className="text-indigo-400 font-mono">{aiScanSelectedDocIds.size}</strong> candidate(s) selected
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowAiScanModal(false)}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                >
                  Close
                </button>

                {aiScanSelectedDocIds.size > 0 && (
                  <>
                    <button
                      type="button"
                      onClick={handleTransferAiSelectionToTable}
                      className="px-4 py-2 text-xs font-medium rounded-lg bg-indigo-950 hover:bg-indigo-900 text-indigo-200 border border-indigo-700/80 transition-colors flex items-center gap-1.5"
                      title="Add selected candidate document IDs to the batch selection on the main table"
                    >
                      <Check className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Transfer Selection to Table</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleBatchSuppressFromAiScan}
                      className="px-4 py-2 text-xs font-semibold rounded-lg bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-colors flex items-center gap-1.5"
                      title="Open batch deactivation modal pre-filled with candidate justifications"
                    >
                      <Archive className="w-3.5 h-3.5" />
                      <span>Batch Suppress Candidates ({aiScanSelectedDocIds.size})</span>
                    </button>
                  </>
                )}
              </div>
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
