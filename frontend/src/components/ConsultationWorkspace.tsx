/**
 * ConsultationWorkspace.tsx - Document Consultation Workspace
 * 
 * Supports uploading consultation document(s) (PDF, Word .doc/.docx, XML) alongside
 * stakeholder feedback comments CSV.
 * Features:
 * - Common Themes Identification & Filtering
 * - Regulatory Stance & Sentiment Analysis
 * - Comment Validity & Actionability Assessment
 * - Stakeholder Grouping & Sector Cross-Tabulation
 * - Side-by-side Alignment with Consulted Document Draft Text
 * - Human Reviewer Deliberation Workbench (Review status & Analyst Notes)
 * - AI Assistance to formulate arguments (strictly assisting, not replacing the human)
 * - Review Matrix CSV/JSON Export
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Users,
  MessageSquare,
  FileText,
  Upload,
  Filter,
  Search,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  ThumbsUp,
  Download,
  Sparkles,
  RefreshCw,
  FolderOpen,
  ArrowRight,
  Shield,
  Layers,
  ChevronRight,
  Plus,
  Trash2,
  FileCheck,
  Building,
  Plane,
  X,
  ExternalLink
} from 'lucide-react';
import {
  ConsultationSession,
  ConsultationSessionSummary,
  ConsultationComment,
  listConsultationSessions,
  getConsultationSession,
  createConsultationSession,
  updateCommentReview,
  assistCommentFormulation,
  loadSampleConsultation,
  deleteConsultationSession,
  getExportConsultationUrl
} from '../services/consultationService';

export const ConsultationWorkspace: React.FC = () => {
  const [sessions, setSessions] = useState<ConsultationSessionSummary[]>([]);
  const [currentSession, setCurrentSession] = useState<ConsultationSession | null>(null);
  const [selectedCommentId, setSelectedCommentId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [selectedTheme, setSelectedTheme] = useState<string>('all');
  const [selectedGroup, setSelectedGroup] = useState<string>('all');
  const [selectedSentiment, setSelectedSentiment] = useState<string>('all');
  const [selectedValidity, setSelectedValidity] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');

  // Review Workbench State
  const [humanStatus, setHumanStatus] = useState<string>('Pending Review');
  const [humanNotes, setHumanNotes] = useState<string>('');
  const [savingNotes, setSavingNotes] = useState<boolean>(false);
  const [assistingAI, setAssistingAI] = useState<boolean>(false);

  // Upload Modal State
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [uploadTitle, setUploadTitle] = useState<string>('');
  const [uploadDescription, setUploadDescription] = useState<string>('');
  const [uploadDomain, setUploadDomain] = useState<string>('Aviation Safety / Regulatory Affairs');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [submittingUpload, setSubmittingUpload] = useState<boolean>(false);

  // Active Inspector Tab
  const [inspectorTab, setInspectorTab] = useState<'deliberation' | 'document'>('deliberation');

  // Load Sessions Catalog
  const refreshSessions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const list = await listConsultationSessions();
      setSessions(list);
      if (list.length > 0) {
        const full = await getConsultationSession(list[0].consultation_id);
        setCurrentSession(full);
        if (full.comments.length > 0) {
          setSelectedCommentId(full.comments[0].comment_id);
        }
      } else {
        // Auto-seed sample NPA if database is empty
        const sample = await loadSampleConsultation();
        setCurrentSession(sample);
        setSessions([
          {
            consultation_id: sample.consultation_id,
            title: sample.title,
            description: sample.description,
            domain: sample.domain,
            status: sample.status,
            created_at: sample.created_at,
            updated_at: sample.updated_at,
            comment_count: sample.comments.length,
            metrics: sample.metrics,
          }
        ]);
        if (sample.comments.length > 0) {
          setSelectedCommentId(sample.comments[0].comment_id);
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed loading consultation workspace.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // Selected Comment sync
  const selectedComment = useMemo(() => {
    if (!currentSession || !selectedCommentId) return null;
    return currentSession.comments.find(c => c.comment_id === selectedCommentId) || null;
  }, [currentSession, selectedCommentId]);

  useEffect(() => {
    if (selectedComment) {
      setHumanStatus(selectedComment.human_review_status || 'Pending Review');
      setHumanNotes(selectedComment.human_notes || '');
    }
  }, [selectedComment]);

  // Switch Active Session
  const handleSelectSession = async (cid: string) => {
    try {
      setLoading(true);
      const full = await getConsultationSession(cid);
      setCurrentSession(full);
      setSelectedCommentId(full.comments.length > 0 ? full.comments[0].comment_id : null);
    } catch (err: any) {
      setError(err.message || 'Failed loading selected session.');
    } finally {
      setLoading(false);
    }
  };

  // Filtered Comments
  const filteredComments = useMemo(() => {
    if (!currentSession) return [];
    return currentSession.comments.filter(c => {
      // Text search
      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase();
        const matchesText =
          c.comment_text.toLowerCase().includes(term) ||
          c.stakeholder_name.toLowerCase().includes(term) ||
          c.target_section.toLowerCase().includes(term) ||
          (c.proposed_text && c.proposed_text.toLowerCase().includes(term));
        if (!matchesText) return false;
      }
      // Theme
      if (selectedTheme !== 'all') {
        if (!c.themes.includes(selectedTheme)) return false;
      }
      // Stakeholder Group
      if (selectedGroup !== 'all') {
        if (c.stakeholder_group !== selectedGroup) return false;
      }
      // Sentiment
      if (selectedSentiment !== 'all') {
        if (c.sentiment !== selectedSentiment) return false;
      }
      // Validity
      if (selectedValidity !== 'all') {
        if (c.validity !== selectedValidity) return false;
      }
      // Status
      if (selectedStatus !== 'all') {
        if (c.human_review_status !== selectedStatus) return false;
      }
      return true;
    });
  }, [currentSession, searchTerm, selectedTheme, selectedGroup, selectedSentiment, selectedValidity, selectedStatus]);

  // Save Review Status & Notes
  const handleSaveReview = async () => {
    if (!selectedComment || !currentSession) return;
    try {
      setSavingNotes(true);
      await updateCommentReview(selectedComment.comment_id, humanStatus, humanNotes);
      // Update local state
      setCurrentSession(prev => {
        if (!prev) return null;
        return {
          ...prev,
          comments: prev.comments.map(c =>
            c.comment_id === selectedComment.comment_id
              ? { ...c, human_review_status: humanStatus, human_notes: humanNotes }
              : c
          )
        };
      });
    } catch (err: any) {
      alert(`Failed saving notes: ${err.message}`);
    } finally {
      setSavingNotes(false);
    }
  };

  // Trigger AI Deliberation Assistance
  const handleAssistFormulation = async () => {
    if (!selectedComment || !currentSession) return;
    try {
      setAssistingAI(true);
      const notes = await assistCommentFormulation(
        selectedComment.comment_id,
        currentSession.consultation_id
      );
      // Update local state
      setCurrentSession(prev => {
        if (!prev) return null;
        return {
          ...prev,
          comments: prev.comments.map(c =>
            c.comment_id === selectedComment.comment_id
              ? { ...c, ai_assistance_notes: notes }
              : c
          )
        };
      });
    } catch (err: any) {
      alert(`Failed generating assistance: ${err.message}`);
    } finally {
      setAssistingAI(false);
    }
  };

  // Handle Upload Submission
  const handleCreateConsultation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadTitle.trim() || !csvFile) {
      alert('Please provide a consultation title and a stakeholder feedback CSV file.');
      return;
    }

    try {
      setSubmittingUpload(true);
      const formData = new FormData();
      formData.append('title', uploadTitle.trim());
      formData.append('description', uploadDescription.trim());
      formData.append('domain', uploadDomain.trim());
      formData.append('feedback_csv', csvFile);
      if (docFile) {
        formData.append('consultation_doc', docFile);
      }

      const created = await createConsultationSession(formData);
      setIsUploadModalOpen(false);
      setUploadTitle('');
      setUploadDescription('');
      setCsvFile(null);
      setDocFile(null);

      await refreshSessions();
      await handleSelectSession(created.consultation_id);
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setSubmittingUpload(false);
    }
  };

  // Delete Session
  const handleDeleteSession = async (cid: string) => {
    if (!confirm('Are you sure you want to delete this consultation session? This cannot be undone.')) {
      return;
    }
    try {
      await deleteConsultationSession(cid);
      await refreshSessions();
    } catch (err: any) {
      alert(`Failed to delete session: ${err.message}`);
    }
  };

  // Stance Colors & Icons
  const renderSentimentBadge = (sentiment: string) => {
    switch (sentiment) {
      case 'Strongly Critical':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-950/80 text-rose-300 border border-rose-800/80">
            <AlertTriangle className="w-3 h-3 text-rose-400" />
            Strongly Critical
          </span>
        );
      case 'Concerned':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-950/80 text-amber-300 border border-amber-800/80">
            <AlertTriangle className="w-3 h-3 text-amber-400" />
            Concerned
          </span>
        );
      case 'Supportive':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
            <ThumbsUp className="w-3 h-3 text-emerald-400" />
            Supportive
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-sky-950/80 text-sky-300 border border-sky-800/80">
            <HelpCircle className="w-3 h-3 text-sky-400" />
            Neutral / Inquiring
          </span>
        );
    }
  };

  // Validity Tag Colors
  const renderValidityBadge = (validity: string) => {
    switch (validity) {
      case 'Actionable Proposal':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-teal-950 text-teal-300 border border-teal-800">
            <FileCheck className="w-3 h-3 text-teal-400" />
            Actionable Proposal
          </span>
        );
      case 'Substantive Technical Concern':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-indigo-950 text-indigo-300 border border-indigo-800">
            <Layers className="w-3 h-3 text-indigo-400" />
            Technical Concern
          </span>
        );
      case 'Clarification Request':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-blue-950 text-blue-300 border border-blue-800">
            <HelpCircle className="w-3 h-3 text-blue-400" />
            Clarification
          </span>
        );
      case 'Editorial / Minor':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
            Editorial
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
            General Opinion
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* 1. Header Toolbar */}
      <header className="px-6 py-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between gap-4 shrink-0 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-950/80 border border-cyan-800/80 flex items-center justify-center text-cyan-400 shadow-sm">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight text-white">Document Consultation Workspace</h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800">
                Rulemaking Deliberation
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Stakeholder feedback synthesis, common themes, and decision support (assists human reviewers; does not resolve comments)
            </p>
          </div>
        </div>

        {/* Action Controls & Session Picker */}
        <div className="flex items-center gap-2">
          {/* Consultation Session Selector */}
          <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5">
            <FolderOpen className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={currentSession?.consultation_id || ''}
              onChange={(e) => handleSelectSession(e.target.value)}
              className="bg-transparent text-xs text-slate-200 focus:outline-none cursor-pointer max-w-xs truncate"
            >
              {sessions.map(s => (
                <option key={s.consultation_id} value={s.consultation_id} className="bg-slate-900 text-white">
                  {s.title} ({s.comment_count} comments)
                </option>
              ))}
            </select>
          </div>

          {/* New Consultation Upload Button */}
          <button
            onClick={() => setIsUploadModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Consultation</span>
          </button>

          {/* Export Matrix Button */}
          {currentSession && (
            <a
              href={getExportConsultationUrl(currentSession.consultation_id, 'csv')}
              download
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
              title="Export complete consultation review matrix as CSV"
            >
              <Download className="w-3.5 h-3.5 text-slate-300" />
              <span>Export CSV</span>
            </a>
          )}
        </div>
      </header>

      {/* 2. Top Analytics Metrics Strip */}
      {currentSession && (
        <section className="px-6 py-3 bg-slate-900/40 border-b border-slate-800/80 grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
          {/* Card 1: Total Comments */}
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-[11px] font-medium text-slate-400">Total Feedback Submissions</div>
              <div className="text-xl font-bold text-white mt-0.5">{currentSession.comments.length}</div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-sky-950 border border-sky-800 flex items-center justify-center text-sky-400">
              <MessageSquare className="w-4 h-4" />
            </div>
          </div>

          {/* Card 2: Regulatory Stance Breakdown */}
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl">
            <div className="text-[11px] font-medium text-slate-400 mb-1 flex items-center justify-between">
              <span>Regulatory Stance</span>
              <span className="text-[10px] text-slate-500">Sentiment</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-800 flex overflow-hidden">
              <div
                style={{ width: `${((currentSession.metrics.sentiment_distribution['Strongly Critical'] || 0) / (currentSession.comments.length || 1)) * 100}%` }}
                className="bg-rose-500 transition-all"
                title={`Critical: ${currentSession.metrics.sentiment_distribution['Strongly Critical'] || 0}`}
              />
              <div
                style={{ width: `${((currentSession.metrics.sentiment_distribution['Concerned'] || 0) / (currentSession.comments.length || 1)) * 100}%` }}
                className="bg-amber-500 transition-all"
                title={`Concerned: ${currentSession.metrics.sentiment_distribution['Concerned'] || 0}`}
              />
              <div
                style={{ width: `${((currentSession.metrics.sentiment_distribution['Neutral / Inquiring'] || 0) / (currentSession.comments.length || 1)) * 100}%` }}
                className="bg-sky-500 transition-all"
                title={`Inquiring: ${currentSession.metrics.sentiment_distribution['Neutral / Inquiring'] || 0}`}
              />
              <div
                style={{ width: `${((currentSession.metrics.sentiment_distribution['Supportive'] || 0) / (currentSession.comments.length || 1)) * 100}%` }}
                className="bg-emerald-500 transition-all"
                title={`Supportive: ${currentSession.metrics.sentiment_distribution['Supportive'] || 0}`}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mt-1">
              <span className="text-rose-400">{currentSession.metrics.sentiment_distribution['Strongly Critical'] || 0} Crit</span>
              <span className="text-amber-400">{currentSession.metrics.sentiment_distribution['Concerned'] || 0} Conc</span>
              <span className="text-sky-400">{currentSession.metrics.sentiment_distribution['Neutral / Inquiring'] || 0} Inq</span>
              <span className="text-emerald-400">{currentSession.metrics.sentiment_distribution['Supportive'] || 0} Supp</span>
            </div>
          </div>

          {/* Card 3: Actionable Proposals */}
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-[11px] font-medium text-slate-400">Actionable Proposals Rate</div>
              <div className="text-xl font-bold text-teal-300 mt-0.5">
                {currentSession.metrics.actionable_proposal_pct}%
              </div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-teal-950 border border-teal-800 flex items-center justify-center text-teal-400">
              <FileCheck className="w-4 h-4" />
            </div>
          </div>

          {/* Card 4: Stakeholder Groups Represented */}
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-[11px] font-medium text-slate-400">Stakeholder Sectors</div>
              <div className="text-xl font-bold text-purple-300 mt-0.5">
                {Object.keys(currentSession.metrics.stakeholder_groups || {}).length} Sectors
              </div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-purple-950 border border-purple-800 flex items-center justify-center text-purple-400">
              <Building className="w-4 h-4" />
            </div>
          </div>
        </section>
      )}

      {/* 3. Interactive Common Themes Filter Chips */}
      {currentSession && currentSession.metrics.theme_distribution && (
        <section className="px-6 py-2 bg-slate-900/20 border-b border-slate-800 flex items-center gap-2 overflow-x-auto shrink-0 scrollbar-thin">
          <span className="text-xs font-semibold text-slate-400 flex items-center gap-1 whitespace-nowrap">
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
            Common Themes:
          </span>
          <button
            onClick={() => setSelectedTheme('all')}
            className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              selectedTheme === 'all'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            All Themes ({currentSession.comments.length})
          </button>
          {Object.entries(currentSession.metrics.theme_distribution).map(([theme, count]) => (
            <button
              key={theme}
              onClick={() => setSelectedTheme(selectedTheme === theme ? 'all' : theme)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                selectedTheme === theme
                  ? 'bg-cyan-500 text-white shadow-sm'
                  : 'bg-slate-900 text-slate-300 border border-slate-800 hover:border-slate-700'
              }`}
            >
              <span>{theme}</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-800 text-slate-400">
                {count}
              </span>
            </button>
          ))}
        </section>
      )}

      {/* 4. Filter & Search Control Bar */}
      <section className="px-6 py-2.5 bg-slate-900/60 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2 flex-1 min-w-[240px] max-w-md">
          <div className="relative w-full">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search comments, stakeholders, or article references..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2.5 top-2 text-slate-500 hover:text-slate-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Dropdown Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Stakeholder Sector Filter */}
          <select
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="all">All Stakeholder Sectors</option>
            {currentSession &&
              Object.keys(currentSession.metrics.stakeholder_groups || {}).map(g => (
                <option key={g} value={g}>{g}</option>
              ))}
          </select>

          {/* Sentiment Filter */}
          <select
            value={selectedSentiment}
            onChange={(e) => setSelectedSentiment(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="all">All Regulatory Stances</option>
            <option value="Strongly Critical">Strongly Critical</option>
            <option value="Concerned">Concerned</option>
            <option value="Neutral / Inquiring">Neutral / Inquiring</option>
            <option value="Supportive">Supportive</option>
          </select>

          {/* Validity Filter */}
          <select
            value={selectedValidity}
            onChange={(e) => setSelectedValidity(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="all">All Validity Categories</option>
            <option value="Actionable Proposal">Actionable Proposals</option>
            <option value="Substantive Technical Concern">Technical Concerns</option>
            <option value="Clarification Request">Clarification Requests</option>
            <option value="Editorial / Minor">Editorial / Minor</option>
            <option value="General Opinion / Policy Grievance">General Opinion</option>
          </select>

          {/* Review Status Filter */}
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="all">All Review Statuses</option>
            <option value="Pending Review">Pending Review</option>
            <option value="Under Technical Assessment">Under Technical Assessment</option>
            <option value="In Consideration">In Consideration</option>
            <option value="Flagged for Legal Review">Flagged for Legal Review</option>
            <option value="Draft Response Prepared">Draft Response Prepared</option>
          </select>

          {(selectedTheme !== 'all' || selectedGroup !== 'all' || selectedSentiment !== 'all' || selectedValidity !== 'all' || selectedStatus !== 'all' || searchTerm) && (
            <button
              onClick={() => {
                setSelectedTheme('all');
                setSelectedGroup('all');
                setSelectedSentiment('all');
                setSelectedValidity('all');
                setSelectedStatus('all');
                setSearchTerm('');
              }}
              className="text-xs text-cyan-400 hover:underline px-2"
            >
              Reset Filters
            </button>
          )}
        </div>
      </section>

      {/* 5. Main Split Deliberation Workspace */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Pane: Comment Triage Stream */}
        <div className="w-1/2 md:w-5/12 lg:w-4/12 border-r border-slate-800 flex flex-col bg-slate-950 overflow-hidden">
          <div className="p-3 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 shrink-0">
            <span>Showing <strong className="text-white">{filteredComments.length}</strong> of {currentSession?.comments.length || 0} feedback comments</span>
            <span className="font-mono text-[11px] text-slate-500">Click to deliberate</span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60 p-2 space-y-2">
            {filteredComments.map((comment) => {
              const isSelected = comment.comment_id === selectedCommentId;
              return (
                <div
                  key={comment.comment_id}
                  onClick={() => setSelectedCommentId(comment.comment_id)}
                  className={`p-3.5 rounded-xl cursor-pointer transition-all border ${
                    isSelected
                      ? 'bg-slate-900 border-cyan-500 shadow-md ring-1 ring-cyan-500/50'
                      : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-900/80 hover:border-slate-700'
                  }`}
                >
                  {/* Top metadata */}
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-mono text-[11px] font-bold text-cyan-400 shrink-0">
                        {comment.comment_id}
                      </span>
                      <span className="text-xs font-semibold text-white truncate" title={comment.stakeholder_name}>
                        {comment.stakeholder_name}
                      </span>
                    </div>
                    {renderSentimentBadge(comment.sentiment)}
                  </div>

                  {/* Sector & Provision Target */}
                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-mono">
                      {comment.stakeholder_group}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/80">
                      {comment.target_section}
                    </span>
                    {renderValidityBadge(comment.validity)}
                  </div>

                  {/* Comment Body Excerpt */}
                  <p className="text-xs text-slate-300 line-clamp-3 leading-relaxed mb-2">
                    {comment.comment_text}
                  </p>

                  {/* Proposed Alternative Text Callout (if present) */}
                  {comment.proposed_text && (
                    <div className="p-2 bg-teal-950/40 border border-teal-900/50 rounded-lg text-[11px] text-teal-200 mb-2 line-clamp-2">
                      <strong className="text-teal-300">Proposed Change: </strong>
                      {comment.proposed_text}
                    </div>
                  )}

                  {/* Themes & Review Status */}
                  <div className="flex items-center justify-between pt-1 border-t border-slate-800/60 text-[10px]">
                    <div className="flex flex-wrap items-center gap-1 text-slate-400">
                      {comment.themes.slice(0, 2).map(t => (
                        <span key={t} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                          {t}
                        </span>
                      ))}
                    </div>
                    <span className={`px-2 py-0.5 rounded font-medium ${
                      comment.human_review_status === 'Draft Response Prepared'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : comment.human_review_status === 'In Consideration'
                        ? 'bg-amber-950 text-amber-300 border border-amber-800'
                        : 'bg-slate-800 text-slate-400'
                    }`}>
                      {comment.human_review_status}
                    </span>
                  </div>
                </div>
              );
            })}

            {filteredComments.length === 0 && (
              <div className="p-8 text-center text-slate-500">
                <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-xs">No feedback comments match the selected filters.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Pane: Deep Consultation Inspector & Deliberation Workbench */}
        <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
          {selectedComment ? (
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Comment Header */}
              <div className="p-4 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between gap-4 shrink-0">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-cyan-400">
                      {selectedComment.comment_id}
                    </span>
                    <h2 className="text-sm font-bold text-white">
                      {selectedComment.stakeholder_name}
                    </h2>
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300">
                      {selectedComment.stakeholder_group}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                    <span>Target Provision: <strong className="text-cyan-300 font-mono">{selectedComment.target_section}</strong></span>
                    <span>•</span>
                    <span>Regulatory Stance: {renderSentimentBadge(selectedComment.sentiment)}</span>
                    <span>•</span>
                    <span>Validity: {renderValidityBadge(selectedComment.validity)}</span>
                  </div>
                </div>

                {/* Sub-tabs: Deliberation vs Document Text */}
                <div className="flex items-center p-1 bg-slate-950 border border-slate-800 rounded-lg">
                  <button
                    onClick={() => setInspectorTab('deliberation')}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      inspectorTab === 'deliberation'
                        ? 'bg-slate-800 text-cyan-400 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Deliberation & Context
                  </button>
                  <button
                    onClick={() => setInspectorTab('document')}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      inspectorTab === 'document'
                        ? 'bg-slate-800 text-cyan-400 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Consulted Document Full Text
                  </button>
                </div>
              </div>

              {/* Inspector Content */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {inspectorTab === 'deliberation' ? (
                  <>
                    {/* Section 1: Side-by-side Feedback & Document Provision */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {/* Left: Stakeholder Feedback Card */}
                      <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
                        <div className="flex items-center justify-between text-xs font-semibold text-slate-200 border-b border-slate-800 pb-2">
                          <span className="flex items-center gap-1.5 text-cyan-400">
                            <MessageSquare className="w-4 h-4" />
                            Stakeholder Submission
                          </span>
                          <span className="text-[11px] font-normal text-slate-400">{selectedComment.stakeholder_name}</span>
                        </div>

                        <div>
                          <label className="text-[11px] font-medium text-slate-400 block mb-1">Feedback Comment</label>
                          <div className="text-xs text-slate-200 leading-relaxed bg-slate-950 p-3 rounded-lg border border-slate-800">
                            {selectedComment.comment_text}
                          </div>
                        </div>

                        {selectedComment.proposed_text && (
                          <div>
                            <label className="text-[11px] font-medium text-teal-400 block mb-1">
                              Proposed Alternative Drafting Text
                            </label>
                            <div className="text-xs text-teal-200 leading-relaxed bg-teal-950/40 p-3 rounded-lg border border-teal-800/80 font-mono">
                              {selectedComment.proposed_text}
                            </div>
                          </div>
                        )}

                        {selectedComment.rationale && (
                          <div>
                            <label className="text-[11px] font-medium text-slate-400 block mb-1">Stated Justification / Rationale</label>
                            <div className="text-xs text-slate-300 leading-relaxed bg-slate-950 p-3 rounded-lg border border-slate-800 italic">
                              {selectedComment.rationale}
                            </div>
                          </div>
                        )}

                        {/* Validity Analysis Summary */}
                        <div className="p-3 bg-slate-950 border border-slate-800/80 rounded-lg text-xs space-y-1">
                          <div className="font-semibold text-slate-300 flex items-center justify-between">
                            <span>Comment Actionability Assessment:</span>
                            {renderValidityBadge(selectedComment.validity)}
                          </div>
                          <p className="text-slate-400 text-[11px]">
                            {selectedComment.validity_rationale}
                          </p>
                        </div>
                      </div>

                      {/* Right: Consulted Document Provision Excerpt */}
                      <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
                        <div className="flex items-center justify-between text-xs font-semibold text-slate-200 border-b border-slate-800 pb-2">
                          <span className="flex items-center gap-1.5 text-indigo-400">
                            <FileText className="w-4 h-4" />
                            Consulted Document Provision
                          </span>
                          <span className="font-mono text-[11px] text-indigo-300 font-bold">
                            {selectedComment.target_section}
                          </span>
                        </div>

                        {selectedComment.matched_section_content ? (
                          <div>
                            <div className="text-xs font-semibold text-white mb-1.5">
                              {selectedComment.matched_section_title}
                            </div>
                            <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-950 p-3.5 rounded-lg border border-slate-800 font-sans max-h-80 overflow-y-auto">
                              {selectedComment.matched_section_content}
                            </div>
                          </div>
                        ) : (
                          <div className="p-8 text-center text-slate-500 bg-slate-950 rounded-lg border border-slate-800">
                            <FileText className="w-6 h-6 mx-auto mb-2 opacity-40" />
                            <p className="text-xs">No direct section excerpt matched for target '{selectedComment.target_section}'.</p>
                            <p className="text-[11px] text-slate-600 mt-1">Switch to 'Consulted Document Full Text' tab to inspect the complete proposal.</p>
                          </div>
                        )}

                        <div className="p-3 bg-slate-950 border border-slate-800/80 rounded-lg text-[11px] text-slate-400 space-y-1">
                          <div className="font-semibold text-slate-300">Drafter Note:</div>
                          <p>
                            Evaluate the operational delta between the proposed text and the stakeholder's requested amendment.
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Section 2: Human Reviewer Deliberation Workbench */}
                    <div className="p-5 bg-slate-900 border border-cyan-900/40 rounded-2xl space-y-4 shadow-sm">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-lg bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400">
                            <Shield className="w-4 h-4" />
                          </div>
                          <div>
                            <h3 className="text-sm font-bold text-white">Human Reviewer Deliberation Workbench</h3>
                            <p className="text-[11px] text-slate-400">
                              Assign triage status and formulate review considerations. AI assists formulation; final policy resolution remains with human authority.
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleAssistFormulation}
                            disabled={assistingAI}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-colors disabled:opacity-50"
                          >
                            {assistingAI ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Sparkles className="w-3.5 h-3.5" />
                            )}
                            <span>Assist Formulation</span>
                          </button>

                          <button
                            onClick={handleSaveReview}
                            disabled={savingNotes}
                            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors disabled:opacity-50"
                          >
                            {savingNotes ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3.5 h-3.5" />
                            )}
                            <span>Save Deliberation</span>
                          </button>
                        </div>
                      </div>

                      {/* Review Status Selector */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <label className="text-xs font-medium text-slate-300 block mb-1.5">
                            Deliberation / Triage Status
                          </label>
                          <select
                            value={humanStatus}
                            onChange={(e) => setHumanStatus(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                          >
                            <option value="Pending Review">Pending Review</option>
                            <option value="Under Technical Assessment">Under Technical Assessment</option>
                            <option value="In Consideration">In Consideration</option>
                            <option value="Flagged for Legal Review">Flagged for Legal Review</option>
                            <option value="Draft Response Prepared">Draft Response Prepared</option>
                          </select>
                        </div>

                        <div className="md:col-span-2">
                          <label className="text-xs font-medium text-slate-300 block mb-1.5">
                            Human Analyst Notes & Response Considerations
                          </label>
                          <textarea
                            rows={3}
                            placeholder="Record review notes, policy justifications, or drafting counter-proposals for the review committee..."
                            value={humanNotes}
                            onChange={(e) => setHumanNotes(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                          />
                        </div>
                      </div>

                      {/* AI Formulation Briefing (if generated) */}
                      {selectedComment.ai_assistance_notes && (
                        <div className="p-4 bg-indigo-950/30 border border-indigo-900/60 rounded-xl space-y-2">
                          <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-300">
                            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                            <span>AI Formulation Briefing & Counter-Arguments (Advisory Only)</span>
                          </div>
                          <div className="text-xs text-indigo-100 whitespace-pre-wrap leading-relaxed font-sans bg-slate-950/80 p-3 rounded-lg border border-indigo-900/40">
                            {selectedComment.ai_assistance_notes}
                          </div>
                          <div className="text-[10px] text-indigo-400 italic">
                            Deliberation notes are provided as objective regulatory considerations to assist human drafting.
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  /* Full Consulted Document Viewer Tab */
                  <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                      <div>
                        <h3 className="text-sm font-bold text-white">Consulted Document Text & Provisions</h3>
                        <p className="text-xs text-slate-400">
                          {currentSession.documents[0]?.title || 'Consultation Draft'}
                        </p>
                      </div>
                      <span className="text-xs font-mono text-slate-400">
                        {currentSession.documents[0]?.word_count.toLocaleString() || 0} words
                      </span>
                    </div>

                    <div className="space-y-6">
                      {currentSession.documents[0]?.sections.map((sec, idx) => (
                        <div key={idx} className="p-4 bg-slate-950 border border-slate-800/80 rounded-xl space-y-2">
                          <h4 className="text-xs font-bold text-cyan-300 font-mono">
                            {sec.title}
                          </h4>
                          <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
                            {sec.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 p-8">
              <MessageSquare className="w-12 h-12 mb-3 opacity-30" />
              <p className="text-sm font-semibold">Select a feedback comment to begin deliberation</p>
              <p className="text-xs text-slate-600 mt-1">Review stakeholder feedback side-by-side with original draft text</p>
            </div>
          )}
        </div>
      </main>

      {/* 6. Upload Consultation Modal */}
      {isUploadModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-bold text-white">Create Document Consultation Workspace</h3>
              </div>
              <button
                onClick={() => setIsUploadModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateConsultation} className="p-6 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">
                  Consultation Title <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. NPA 2024-08: Cybersecurity Oversight in ATM/ANS"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-slate-300 block mb-1">
                    Regulatory Domain
                  </label>
                  <input
                    type="text"
                    value={uploadDomain}
                    onChange={(e) => setUploadDomain(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-300 block mb-1">
                    Description / Scope
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. EASA Notice of Proposed Amendment comment review"
                    value={uploadDescription}
                    onChange={(e) => setUploadDescription(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              {/* Stakeholder Feedback CSV Input */}
              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                <label className="text-xs font-semibold text-white flex items-center gap-1.5">
                  <FileText className="w-4 h-4 text-cyan-400" />
                  Stakeholder Feedback CSV <span className="text-rose-400">*</span>
                </label>
                <p className="text-[11px] text-slate-400">
                  CSV file containing comments. Supports standard columns: Stakeholder, Category, Article/Section, Comment, Proposed Change, Rationale.
                </p>
                <input
                  type="file"
                  required
                  accept=".csv"
                  onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                  className="block w-full text-xs text-slate-400 file:mr-4 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-cyan-950 file:text-cyan-300 hover:file:bg-cyan-900 cursor-pointer"
                />
              </div>

              {/* Consultation Document Input */}
              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                <label className="text-xs font-semibold text-white flex items-center gap-1.5">
                  <FileText className="w-4 h-4 text-indigo-400" />
                  Document(s) to be Consulted <span className="text-slate-500">(Optional)</span>
                </label>
                <p className="text-[11px] text-slate-400">
                  The draft regulation, NPA, or policy paper. Supports PDF, Word (.doc / .docx), XML, and TXT.
                </p>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,.xml,.txt,.md,.html"
                  onChange={(e) => setDocFile(e.target.files?.[0] || null)}
                  className="block w-full text-xs text-slate-400 file:mr-4 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-950 file:text-indigo-300 hover:file:bg-indigo-900 cursor-pointer"
                />
              </div>

              {/* Submit Buttons */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
                <button
                  type="button"
                  onClick={async () => {
                    setIsUploadModalOpen(false);
                    await loadSampleConsultation();
                    await refreshSessions();
                  }}
                  className="text-xs text-indigo-400 hover:underline flex items-center gap-1"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Load Pre-Configured Sample (NPA 2024-05)
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsUploadModalOpen(false)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingUpload}
                    className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors disabled:opacity-50"
                  >
                    {submittingUpload ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Upload className="w-3.5 h-3.5" />
                    )}
                    <span>Analyze & Launch Workspace</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
