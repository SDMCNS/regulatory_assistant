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
  ExternalLink,
  Scale,
  GitCompare,
  BarChart3,
  CheckSquare,
  Edit3,
  FileSpreadsheet,
  Network,
  ChevronDown,
  AlertCircle,
  Building2,
  Sliders,
  Compass,
  Check
} from 'lucide-react';
import {
  ConsultationSession,
  ConsultationSessionSummary,
  ConsultationComment,
  ConsultationSynthesisBundle,
  ConsultationTemplateField,
  InspectFileResponse,
  RequiredTextBlock,
  OrganisationAnalysis,
  listConsultationSessions,
  getConsultationSession,
  createConsultationSession,
  updateCommentReview,
  assistCommentFormulation,
  loadSampleConsultation,
  deleteConsultationSession,
  getExportConsultationUrl,
  getConsultationSynthesis,
  getExportSynthesisReportUrl,
  inspectFeedbackFile,
  updateSessionTextBlock,
} from '../services/consultationService';
import { ConsultationSynthesisSuite } from './ConsultationSynthesisSuite';
import { StakeholderSpiderModal } from './StakeholderSpiderModal';

export const STANDARD_TEMPLATE_FIELDS: ConsultationTemplateField[] = [
  { key: 'comment_id', label: 'ID', required: false, type: 'string', description: 'Unique comment identifier or submission reference', aliases: ['id'] },
  { key: 'document_title', label: 'Please select the document title from the drop down below', required: false, type: 'string', description: 'Target consulted document or regulation title', aliases: ['document_title'] },
  { key: 'chapter_section', label: 'Chapter/Section', required: true, type: 'string', description: 'Target clause, article, chapter, or AMC/GM section', aliases: ['chapter/section', 'chapter_section', 'section'] },
  { key: 'page', label: 'Page', required: false, type: 'string', description: 'Page number in draft document', aliases: ['page'] },
  { key: 'original_text', label: 'Original text in document', required: false, type: 'string', description: 'Quoted draft text cited by the stakeholder', aliases: ['original text in document', 'original_text'] },
  { key: 'comment_text', label: 'Comment', required: true, type: 'string', description: 'Substantive feedback, technical critique, or objection', aliases: ['comment', 'comment_text'] },
  { key: 'comment_type', label: 'Type of Comment', required: false, type: 'string', description: 'Classification (e.g. Technical, Legal, Editorial, General)', aliases: ['type of comment'] },
  { key: 'importance', label: 'Importance', required: false, type: 'string', description: 'Priority rating (High, Medium, Low, Critical)', aliases: ['importance'] },
  { key: 'proposed_text', label: 'Proposed new text (required in case of change request)', required: false, type: 'string', description: 'Requested amendment or replacement drafting text', aliases: ['proposed new text'] },
  { key: 'stakeholder_category', label: 'Stakeholder Category', required: false, type: 'string', description: 'Sector category (Airline, ANSP, OEM, Association, Authority)', aliases: ['stakeholder category', 'category'] },
  { key: 'organisation_name', label: 'Organisation Name', required: false, type: 'string', description: 'Name of the submitting organisation or entity', aliases: ['organisation name', 'stakeholder'] },
  { key: 'af_cba', label: 'AF / CBA (Internal)', required: false, type: 'string', description: 'Internal reference field only (not an Assessment Factor; ignored for evaluation)', aliases: ['af / cba', 'af', 'cba'] },
  { key: 'response_to_comment', label: 'Response to comment', required: false, type: 'string', description: 'Draft or official regulatory authority response', aliases: ['response to comment'] },
  { key: 'rationale_and_changes', label: 'Rationale and resulting changes (if applicable)', required: false, type: 'string', description: 'Legal and technical justification for text modifications', aliases: ['rationale and resulting changes'] },
  { key: 'overall_id', label: 'Overall ID#', required: false, type: 'string', description: 'Master cross-consultation tracking ID', aliases: ['overall id#', 'overall id'] },
];

export const ConsultationWorkspace: React.FC = () => {
  const [sessions, setSessions] = useState<ConsultationSessionSummary[]>([]);
  const [currentSession, setCurrentSession] = useState<ConsultationSession | null>(null);
  const [selectedCommentId, setSelectedCommentId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Workspace Mode: 'triage' | 'synthesis' | 'text_blocks' | 'organisations'
  const [workspaceMode, setWorkspaceMode] = useState<'triage' | 'synthesis' | 'text_blocks' | 'organisations'>('triage');
  const [synthesisBundle, setSynthesisBundle] = useState<ConsultationSynthesisBundle | null>(null);
  const [synthesisLoading, setSynthesisLoading] = useState<boolean>(false);

  // Filters for Triage Stream
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

  // Upload Modal State & 2-Step Grouping Wizard
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [uploadStep, setUploadStep] = useState<1 | 2>(1);
  const [uploadTitle, setUploadTitle] = useState<string>('');
  const [uploadDescription, setUploadDescription] = useState<string>('');
  const [uploadDomain, setUploadDomain] = useState<string>('Aviation Safety / Regulatory Affairs');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [inspectResult, setInspectResult] = useState<InspectFileResponse | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [inspectingFile, setInspectingFile] = useState<boolean>(false);
  const [submittingUpload, setSubmittingUpload] = useState<boolean>(false);

  // Required Text Blocks State
  const [editingBlockId, setEditingBlockId] = useState<string | null>(null);
  const [editingBlockContent, setEditingBlockContent] = useState<string>('');
  const [savingBlock, setSavingBlock] = useState<boolean>(false);
  const [textBlockSearch, setTextBlockSearch] = useState<string>('');
  const [textBlockStatusFilter, setTextBlockStatusFilter] = useState<'all' | 'provided' | 'missing'>('all');

  // Organisations Dynamics State
  const [orgSearch, setOrgSearch] = useState<string>('');
  const [orgCategoryFilter, setOrgCategoryFilter] = useState<string>('all');
  const [showSpiderModal, setShowSpiderModal] = useState<boolean>(false);
  const [spiderInitialOrg, setSpiderInitialOrg] = useState<string | null>(null);

  // Active Inspector Tab
  const [inspectorTab, setInspectorTab] = useState<'deliberation' | 'synthesis' | 'document'>('deliberation');

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
        setCurrentSession(null);
        setSelectedCommentId(null);
        setSynthesisBundle(null);
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

  // Load Synthesis Bundle for active session
  const loadSynthesis = useCallback(async (cid: string) => {
    try {
      setSynthesisLoading(true);
      const bundle = await getConsultationSynthesis(cid);
      setSynthesisBundle(bundle);
    } catch (err: any) {
      console.warn('[Consultation Warning] Failed loading synthesis:', err);
    } finally {
      setSynthesisLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentSession?.consultation_id) {
      loadSynthesis(currentSession.consultation_id);
    }
  }, [currentSession?.consultation_id, loadSynthesis]);

  // Selected Comment sync
  const selectedComment = useMemo(() => {
    if (!currentSession || !selectedCommentId) return null;
    return currentSession.comments.find(c => c.comment_id === selectedCommentId) || null;
  }, [currentSession, selectedCommentId]);

  // Selected Comment Synthesis sync
  const selectedCommentSynthesis = useMemo(() => {
    if (!synthesisBundle || !selectedCommentId) return null;
    return synthesisBundle.comment_synthesis.find(c => c.comment_id === selectedCommentId) || null;
  }, [synthesisBundle, selectedCommentId]);

  // Selected Comment Text Block sync
  const selectedCommentTextBlock = useMemo(() => {
    if (!currentSession?.required_text_blocks || !selectedComment) return null;
    const targetSec = (selectedComment.chapter_section || selectedComment.target_section || '').toLowerCase();
    const targetDoc = (selectedComment.document_title || '').toLowerCase();
    return currentSession.required_text_blocks.find(b => {
      if (targetDoc && b.document_title.toLowerCase() !== targetDoc) return false;
      return b.chapter_section.toLowerCase() === targetSec;
    }) || currentSession.required_text_blocks.find(b => b.chapter_section.toLowerCase() === targetSec) || null;
  }, [currentSession, selectedComment]);

  // Missing Text Blocks Count
  const missingBlocksCount = useMemo(() => {
    return (currentSession?.required_text_blocks || []).filter(b => b.status === 'missing').length;
  }, [currentSession]);

  // Filtered Text Blocks
  const filteredTextBlocks = useMemo(() => {
    if (!currentSession?.required_text_blocks) return [];
    return currentSession.required_text_blocks.filter(b => {
      if (textBlockStatusFilter !== 'all' && b.status !== textBlockStatusFilter) return false;
      if (textBlockSearch.trim()) {
        const q = textBlockSearch.toLowerCase();
        const matches =
          b.document_title.toLowerCase().includes(q) ||
          b.chapter_section.toLowerCase().includes(q) ||
          b.content.toLowerCase().includes(q) ||
          b.referencing_stakeholders.some(s => s.toLowerCase().includes(q));
        if (!matches) return false;
      }
      return true;
    });
  }, [currentSession?.required_text_blocks, textBlockStatusFilter, textBlockSearch]);

  // Filtered Organisations
  const filteredOrganisations = useMemo(() => {
    if (!currentSession?.organisations_analysis) return [];
    return currentSession.organisations_analysis.filter(o => {
      if (orgCategoryFilter !== 'all' && o.stakeholder_category !== orgCategoryFilter) return false;
      if (orgSearch.trim()) {
        const q = orgSearch.toLowerCase();
        const matches =
          o.organisation_name.toLowerCase().includes(q) ||
          o.direction_of_travel.toLowerCase().includes(q) ||
          o.targeted_sections.some(s => s.toLowerCase().includes(q));
        if (!matches) return false;
      }
      return true;
    });
  }, [currentSession?.organisations_analysis, orgCategoryFilter, orgSearch]);

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

  // Inspect file and proceed to step 2 field mapping wizard
  const handleInspectCsv = async () => {
    if (!csvFile) {
      alert('Please select a stakeholder feedback file (CSV/TSV) first.');
      return;
    }
    try {
      setInspectingFile(true);
      const res = await inspectFeedbackFile(csvFile);
      setInspectResult(res);
      setColumnMapping(res.suggested_mapping || {});
      setUploadStep(2);
    } catch (err: any) {
      alert(`Could not inspect file: ${err.message}`);
    } finally {
      setInspectingFile(false);
    }
  };

  // Handle Upload Submission with confirmed column mapping
  const handleCreateConsultation = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!uploadTitle.trim() || !csvFile) {
      alert('Please provide a consultation title and a stakeholder feedback file.');
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
      formData.append('column_mapping', JSON.stringify(columnMapping));
      if (inspectResult?.detected_delimiter) {
        formData.append('delimiter', inspectResult.detected_delimiter);
      }

      const created = await createConsultationSession(formData);
      setIsUploadModalOpen(false);
      setUploadStep(1);
      setInspectResult(null);
      setColumnMapping({});
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

  // Save in-place edited text block
  const handleSaveTextBlock = async (blockId: string) => {
    if (!currentSession) return;
    try {
      setSavingBlock(true);
      await updateSessionTextBlock(
        currentSession.consultation_id,
        blockId,
        editingBlockContent
      );
      // Reload session to refresh comment scores and text matching
      const full = await getConsultationSession(currentSession.consultation_id);
      setCurrentSession(full);
      setEditingBlockId(null);
      setEditingBlockContent('');
    } catch (err: any) {
      alert(`Failed saving text block: ${err.message}`);
    } finally {
      setSavingBlock(false);
    }
  };

  // Delete Session
  const handleDeleteSession = async (cid: string) => {
    if (!confirm('Are you sure you want to delete this consultation session? This cannot be undone.')) {
      return;
    }
    try {
      if (currentSession?.consultation_id === cid) {
        setCurrentSession(null);
        setSelectedCommentId(null);
        setSynthesisBundle(null);
      }
      await deleteConsultationSession(cid);
      await refreshSessions();
    } catch (err: any) {
      alert(`Failed to delete session: ${err.message}`);
    }
  };

  // Safe numeric score formatter
  const formatScore = (val: number | null | undefined, digits = 2, prefix = true): string => {
    if (val == null || typeof val !== 'number' || isNaN(val)) return '0.00';
    const str = val.toFixed(digits);
    return prefix && val > 0 ? `+${str}` : str;
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
          {/* Workspace Mode Toggle */}
          <div className="flex items-center p-1 bg-slate-950 border border-slate-800 rounded-lg">
            <button
              onClick={() => setWorkspaceMode('triage')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                workspaceMode === 'triage'
                  ? 'bg-slate-800 text-cyan-400 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Deliberation & Triage</span>
            </button>

            <button
              onClick={() => setWorkspaceMode('text_blocks')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                workspaceMode === 'text_blocks'
                  ? 'bg-amber-950/80 text-amber-300 border border-amber-800 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Required document text blocks extracted from comment (title, section) references"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Required Text Blocks</span>
              {missingBlocksCount > 0 ? (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-amber-950 text-amber-300 border border-amber-800 animate-pulse">
                  {missingBlocksCount} Missing
                </span>
              ) : (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-emerald-950 text-emerald-400 border border-emerald-800">
                  {currentSession?.required_text_blocks?.length || 0}
                </span>
              )}
            </button>

            <button
              onClick={() => setWorkspaceMode('organisations')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                workspaceMode === 'organisations'
                  ? 'bg-purple-950/80 text-purple-300 border border-purple-800 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Stakeholder direction of travel, organisation stances, and silence accounting"
            >
              <Building2 className="w-3.5 h-3.5" />
              <span>Stakeholders & Silence</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-purple-950 text-purple-300 border border-purple-800">
                {currentSession?.organisations_analysis?.length || 0}
              </span>
            </button>

            <button
              onClick={() => setWorkspaceMode('synthesis')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                workspaceMode === 'synthesis'
                  ? 'bg-cyan-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Scale className="w-3.5 h-3.5" />
              <span>Synthesis Suite</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800">
                Macro & 5 Levels
              </span>
            </button>
          </div>

          {/* Consultation Session Selector */}
          <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5">
            <FolderOpen className="w-3.5 h-3.5 text-slate-400 shrink-0" />
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
            {currentSession && sessions.length > 1 && (
              <button
                onClick={() => handleDeleteSession(currentSession.consultation_id)}
                className="p-1 hover:text-rose-400 text-slate-500 transition-colors"
                title="Delete this consultation session"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* New Consultation Upload Button */}
          <button
            onClick={() => setIsUploadModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Consultation</span>
          </button>

          {/* Export Matrix / Synthesis Report Buttons */}
          {currentSession && (
            <div className="flex items-center gap-1.5">
              <a
                href={getExportSynthesisReportUrl(currentSession.consultation_id, 'markdown')}
                download
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-950 hover:bg-indigo-900 text-indigo-200 border border-indigo-800 transition-colors"
                title="Export comprehensive regulatory consultation synthesis report as Markdown"
              >
                <Download className="w-3.5 h-3.5 text-indigo-300" />
                <span>Export Synthesis</span>
              </a>

              <a
                href={getExportConsultationUrl(currentSession.consultation_id, 'csv')}
                download
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
                title="Export complete consultation review matrix as CSV"
              >
                <Download className="w-3.5 h-3.5 text-slate-300" />
                <span>Export CSV</span>
              </a>
            </div>
          )}
        </div>
      </header>

      {/* 2. Top Analytics Metrics Strip */}
      {currentSession && (
        <section className="px-6 py-3 bg-slate-900/40 border-b border-slate-800/80 grid grid-cols-2 md:grid-cols-5 gap-3 shrink-0">
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
                style={{ width: `${((currentSession?.metrics?.sentiment_distribution?.['Strongly Critical'] || 0) / (currentSession?.comments?.length || 1)) * 100}%` }}
                className="bg-rose-500 transition-all"
                title={`Critical: ${currentSession?.metrics?.sentiment_distribution?.['Strongly Critical'] || 0}`}
              />
              <div
                style={{ width: `${((currentSession?.metrics?.sentiment_distribution?.['Concerned'] || 0) / (currentSession?.comments?.length || 1)) * 100}%` }}
                className="bg-amber-500 transition-all"
                title={`Concerned: ${currentSession?.metrics?.sentiment_distribution?.['Concerned'] || 0}`}
              />
              <div
                style={{ width: `${((currentSession?.metrics?.sentiment_distribution?.['Neutral / Inquiring'] || 0) / (currentSession?.comments?.length || 1)) * 100}%` }}
                className="bg-sky-500 transition-all"
                title={`Inquiring: ${currentSession?.metrics?.sentiment_distribution?.['Neutral / Inquiring'] || 0}`}
              />
              <div
                style={{ width: `${((currentSession?.metrics?.sentiment_distribution?.['Supportive'] || 0) / (currentSession?.comments?.length || 1)) * 100}%` }}
                className="bg-emerald-500 transition-all"
                title={`Supportive: ${currentSession?.metrics?.sentiment_distribution?.['Supportive'] || 0}`}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mt-1">
              <span className="text-rose-400">{currentSession?.metrics?.sentiment_distribution?.['Strongly Critical'] || 0} Crit</span>
              <span className="text-amber-400">{currentSession?.metrics?.sentiment_distribution?.['Concerned'] || 0} Conc</span>
              <span className="text-sky-400">{currentSession?.metrics?.sentiment_distribution?.['Neutral / Inquiring'] || 0} Inq</span>
              <span className="text-emerald-400">{currentSession?.metrics?.sentiment_distribution?.['Supportive'] || 0} Supp</span>
            </div>
          </div>

          {/* Card 3: Actionable Proposals */}
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between">
            <div>
              <div className="text-[11px] font-medium text-slate-400">Actionable Proposals Rate</div>
              <div className="text-xl font-bold text-teal-300 mt-0.5">
                {currentSession?.metrics?.actionable_proposal_pct ?? 0}%
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
                {Object.keys(currentSession?.metrics?.stakeholder_groups || {}).length} Sectors
              </div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-purple-950 border border-purple-800 flex items-center justify-center text-purple-400">
              <Building className="w-4 h-4" />
            </div>
          </div>

          {/* Card 5: Required Document Text Blocks Manifest */}
          <div
            onClick={() => setWorkspaceMode(workspaceMode === 'text_blocks' ? 'triage' : 'text_blocks')}
            className={`p-3 border rounded-xl flex items-center justify-between cursor-pointer transition-all group ${
              workspaceMode === 'text_blocks'
                ? 'bg-amber-950/60 border-amber-500 shadow-sm'
                : 'bg-gradient-to-br from-slate-900 to-amber-950/30 border-amber-900/60 hover:border-amber-500'
            }`}
          >
            <div>
              <div className="text-[11px] font-bold text-amber-300 flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" />
                <span>Required Text Blocks</span>
              </div>
              <div className="text-xs text-slate-200 font-medium mt-0.5">
                {(currentSession.required_text_blocks || []).filter(b => b.status === 'provided').length} / {currentSession.required_text_blocks?.length || 0} Provided
                {missingBlocksCount > 0 ? (
                  <span className="text-amber-400 font-bold ml-1">({missingBlocksCount} Missing)</span>
                ) : (
                  <span className="text-emerald-400 font-bold ml-1">(Complete)</span>
                )}
              </div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-amber-950 border border-amber-800 flex items-center justify-center text-amber-400 group-hover:scale-110 transition-transform">
              <ArrowRight className="w-4 h-4" />
            </div>
          </div>
        </section>
      )}

      {workspaceMode === 'synthesis' && currentSession ? (
        <ConsultationSynthesisSuite
          session={currentSession}
          synthesisBundle={synthesisBundle}
          loading={synthesisLoading}
          onRefreshSynthesis={() => loadSynthesis(currentSession.consultation_id)}
          onSelectCommentForTriage={(cid) => {
            setSelectedCommentId(cid);
            setWorkspaceMode('triage');
            setInspectorTab('synthesis');
          }}
        />
      ) : workspaceMode === 'text_blocks' && currentSession ? (
        /* Required Document Text Blocks View */
        <div className="flex-1 flex flex-col overflow-hidden bg-slate-950 p-6 space-y-5">
          {/* Top Banner */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl flex flex-wrap items-center justify-between gap-4 shrink-0">
            <div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-amber-950 border border-amber-800 flex items-center justify-center text-amber-400">
                  <FileText className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-white">Required Document Text Blocks Manifest</h2>
                  <p className="text-xs text-slate-400">
                    Derived from <span className="text-amber-300 font-mono">Document title</span> and <span className="text-amber-300 font-mono">Chapter/Section</span> references across {currentSession.comments.length} stakeholder feedback submissions.
                  </p>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-2 max-w-3xl leading-relaxed">
                <strong className="text-slate-300">Dual-Context Rulemaking Evaluation:</strong> Each comment is evaluated with <strong>75% weighting on its specific section</strong> and <strong>25% weighting on the whole document</strong>. Provide missing text blocks below to enable embeddings and LLM semantic alignment.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
                Total Required: <strong className="text-white">{currentSession.required_text_blocks?.length || 0}</strong>
              </span>
              <span className="px-3 py-1.5 rounded-xl bg-emerald-950/80 border border-emerald-800 text-xs font-mono text-emerald-300">
                Provided: <strong className="text-emerald-400">{(currentSession.required_text_blocks || []).filter(b => b.status === 'provided').length}</strong>
              </span>
              {missingBlocksCount > 0 && (
                <span className="px-3 py-1.5 rounded-xl bg-amber-950/80 border border-amber-800 text-xs font-mono text-amber-300 animate-pulse">
                  Missing Action Required: <strong className="text-amber-400">{missingBlocksCount}</strong>
                </span>
              )}
            </div>
          </div>

          {/* Search & Filter Controls */}
          <div className="flex items-center justify-between gap-4 shrink-0">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative w-full">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter text blocks by chapter, section, or referencing stakeholder..."
                  value={textBlockSearch}
                  onChange={(e) => setTextBlockSearch(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setTextBlockStatusFilter('all')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
                  textBlockStatusFilter === 'all'
                    ? 'bg-amber-600 text-white'
                    : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                }`}
              >
                All ({currentSession.required_text_blocks?.length || 0})
              </button>
              <button
                onClick={() => setTextBlockStatusFilter('provided')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
                  textBlockStatusFilter === 'provided'
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                }`}
              >
                Provided ({(currentSession.required_text_blocks || []).filter(b => b.status === 'provided').length})
              </button>
              <button
                onClick={() => setTextBlockStatusFilter('missing')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
                  textBlockStatusFilter === 'missing'
                    ? 'bg-amber-600 text-white'
                    : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                }`}
              >
                Missing ({missingBlocksCount})
              </button>
            </div>
          </div>

          {/* Text Blocks List */}
          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {filteredTextBlocks.map((block) => {
              const isEditing = editingBlockId === block.block_id;
              const isProvided = block.status === 'provided';
              return (
                <div
                  key={block.block_id}
                  className={`p-4 bg-slate-900 border rounded-2xl transition-all ${
                    isProvided
                      ? 'border-slate-800/90'
                      : 'border-amber-900/60 bg-gradient-to-r from-slate-900 via-amber-950/10 to-slate-900'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-amber-400">
                          {block.chapter_section}
                        </span>
                        <span className="text-xs text-slate-400">
                          in <strong className="text-slate-300">{block.document_title}</strong>
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11px] text-slate-400">
                        <span>Referenced by <strong>{block.comment_count}</strong> comments</span>
                        {block.critical_comment_count > 0 && (
                          <span className="px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800 font-mono text-[10px]">
                            {block.critical_comment_count} Critical Objections
                          </span>
                        )}
                        <span>•</span>
                        <span>Stakeholders: {block.referencing_stakeholders.join(', ')}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {isProvided ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-300 border border-emerald-800">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          Provided
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950 text-amber-300 border border-amber-800 animate-pulse">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                          User Text Required
                        </span>
                      )}

                      {!isEditing && (
                        <button
                          onClick={() => {
                            setEditingBlockId(block.block_id);
                            setEditingBlockContent(block.content || '');
                          }}
                          className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
                        >
                          <Edit3 className="w-3 h-3 text-amber-400" />
                          <span>{isProvided ? 'Edit Section Text' : 'Provide Text'}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Sample Stakeholder Quoted Snippets */}
                  {block.sample_comment_snippets && block.sample_comment_snippets.length > 0 && (
                    <div className="mb-3 p-2.5 bg-slate-950/80 border border-slate-800/80 rounded-xl text-[11px] text-slate-400">
                      <strong className="text-slate-300">Quoted in Stakeholder Feedback: </strong>
                      <span className="italic">"{block.sample_comment_snippets[0]}"</span>
                    </div>
                  )}

                  {/* Content or Inline Editor */}
                  {isEditing ? (
                    <div className="p-4 bg-slate-950 border border-amber-500/60 rounded-xl space-y-3">
                      <label className="text-xs font-semibold text-white block">
                        Provide / Edit Consulted Text for <span className="font-mono text-amber-300">{block.chapter_section}</span>:
                      </label>
                      <textarea
                        rows={6}
                        value={editingBlockContent}
                        onChange={(e) => setEditingBlockContent(e.target.value)}
                        placeholder="Paste or write the official draft text of this article, section, or requirement..."
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 font-sans leading-relaxed"
                      />
                      <div className="flex items-center justify-between">
                        <p className="text-[11px] text-slate-400">
                          Saving will automatically re-evaluate comment section scores (75% weight) and update embeddings.
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setEditingBlockId(null)}
                            className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            disabled={savingBlock || !editingBlockContent.trim()}
                            onClick={() => handleSaveTextBlock(block.block_id)}
                            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white shadow-sm transition-colors disabled:opacity-50"
                          >
                            {savingBlock ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                            <span>Save & Re-evaluate Comments</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-950 p-3 rounded-xl border border-slate-800 font-sans">
                      {block.content ? (
                        block.content
                      ) : (
                        <span className="text-slate-500 italic">
                          No text provided for this section yet. Click 'Provide Text' above to paste the consulted regulation excerpt.
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {filteredTextBlocks.length === 0 && (
              <div className="p-12 text-center text-slate-500 bg-slate-900/40 rounded-2xl border border-slate-800">
                <FileText className="w-10 h-10 mx-auto mb-2 opacity-30 text-amber-400" />
                <p className="text-sm font-semibold">No text blocks match the search criteria.</p>
              </div>
            )}
          </div>
        </div>
      ) : workspaceMode === 'organisations' && currentSession ? (
        /* Stakeholder Stances & Silence Dynamics View */
        <div className="flex-1 flex flex-col overflow-hidden bg-slate-950 p-6 space-y-5">
          {/* Top Banner */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl flex flex-wrap items-center justify-between gap-4 shrink-0">
            <div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-purple-950 border border-purple-800 flex items-center justify-center text-purple-400">
                  <Building2 className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-white">Stakeholder Stances, Direction of Travel & Silence Accounting</h2>
                  <p className="text-xs text-slate-400">
                    Comprehensive evaluation of individual organisations, collective stakeholder groups, and tacit acquiescence of silent parties.
                  </p>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-2 max-w-3xl leading-relaxed">
                <strong className="text-purple-300">Regulatory Deliberation Principle:</strong> Objections from individual submitters are balanced against the broader participating industry. Silence from other affected sectors on a specific clause is accounted for as tacit acquiescence or non-opposition.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
                Total Organisations: <strong className="text-white">{currentSession.organisations_analysis?.length || 0}</strong>
              </span>
              <span className="px-3 py-1.5 rounded-xl bg-purple-950/80 border border-purple-800 text-xs font-mono text-purple-300">
                Sectors: <strong className="text-purple-300">{Object.keys(currentSession.metrics.stakeholder_groups || {}).length}</strong>
              </span>
              <button
                type="button"
                onClick={() => {
                  setSpiderInitialOrg(null);
                  setShowSpiderModal(true);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs transition-all shadow-md shadow-purple-900/30 cursor-pointer"
                title="Open interactive multi-axis Spider (Radar) diagram and Silence Accounting matrix"
              >
                <Compass className="w-3.5 h-3.5" />
                <span>Visual Spider Map</span>
              </button>
            </div>
          </div>

          {/* Search & Filter Controls */}
          <div className="flex items-center justify-between gap-4 shrink-0">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative w-full">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search organisation name, direction of travel, or targeted section..."
                  value={orgSearch}
                  onChange={(e) => setOrgSearch(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={orgCategoryFilter}
                onChange={(e) => setOrgCategoryFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-purple-500 cursor-pointer"
              >
                <option value="all">All Stakeholder Categories</option>
                {Object.keys(currentSession.metrics.stakeholder_groups || {}).map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Organisation Cards Grid */}
          <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pr-1">
            {filteredOrganisations.map((org) => {
              const score = org.average_weighted_score;
              const isNegative = score != null && score < -0.2;
              const isPositive = score != null && score > 0.2;
              return (
                <div
                  key={org.organisation_name}
                  className="p-4 bg-slate-900 border border-slate-800 rounded-2xl flex flex-col justify-between space-y-3 hover:border-slate-700 transition-colors"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-xs font-bold text-white leading-snug">
                          {org.organisation_name}
                        </h3>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-950 text-slate-400 border border-slate-800 inline-block mt-1">
                          {org.stakeholder_category}
                        </span>
                      </div>
                      <span className={`px-2 py-0.5 rounded font-mono text-xs font-bold shrink-0 ${
                        isNegative
                          ? 'bg-rose-950 text-rose-300 border border-rose-800'
                          : isPositive
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : 'bg-sky-950 text-sky-300 border border-sky-800'
                      }`}>
                        {formatScore(score, 2, true)}
                      </span>
                    </div>

                    <div className="text-[11px] text-slate-400 flex items-center justify-between pt-1 border-t border-slate-800/60 font-mono">
                      <span>75% Sec: <strong className="text-slate-300">{formatScore(org.average_section_score, 2, false)}</strong></span>
                      <span>25% Doc: <strong className="text-slate-300">{formatScore(org.average_document_score, 2, false)}</strong></span>
                      <span>{org.total_comments} comments ({org.critical_comments_count} crit)</span>
                    </div>

                    {/* Direction of Travel */}
                    <div className="p-2.5 bg-slate-950 rounded-xl border border-slate-800/80 space-y-1">
                      <div className="text-[10px] font-semibold text-purple-400 flex items-center gap-1">
                        <Compass className="w-3 h-3" />
                        <span>Direction of Travel</span>
                      </div>
                      <p className="text-xs text-purple-200 font-medium">
                        {org.direction_of_travel}
                      </p>
                    </div>

                    {/* Targeted Sections */}
                    <div>
                      <span className="text-[10px] text-slate-500 font-medium block mb-1">Targeted Provisions:</span>
                      <div className="flex flex-wrap gap-1">
                        {org.targeted_sections.map(sec => (
                          <span key={sec} className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800/80">
                            {sec}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Co-objector Coalition Network */}
                    {org.co_objectors_network && org.co_objectors_network.length > 0 && (
                      <div className="pt-2 border-t border-slate-800/60">
                        <span className="text-[10px] text-slate-500 font-medium block mb-1">Common Objections Aligned With:</span>
                        <div className="flex flex-wrap gap-1">
                          {org.co_objectors_network.map(co => (
                            <span key={co} className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-300">
                              {co}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 mt-2">
                    <button
                      onClick={() => {
                        setSearchTerm(org.organisation_name);
                        setWorkspaceMode('triage');
                      }}
                      className="flex-1 py-1.5 bg-slate-950 hover:bg-slate-800 text-cyan-400 hover:text-cyan-300 rounded-lg text-xs font-semibold flex items-center justify-center gap-1 border border-slate-800 transition-colors cursor-pointer"
                    >
                      <span>View {org.total_comments} Comments</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSpiderInitialOrg(org.organisation_name);
                        setShowSpiderModal(true);
                      }}
                      className="px-2.5 py-1.5 bg-purple-950/60 hover:bg-purple-900/80 text-purple-300 hover:text-purple-200 rounded-lg text-xs font-semibold flex items-center justify-center gap-1 border border-purple-800/60 transition-colors cursor-pointer"
                      title="Plot this stakeholder on the visual spider map"
                    >
                      <Compass className="w-3.5 h-3.5 text-purple-400" />
                      <span>Spider Map</span>
                    </button>
                  </div>
                </div>
              );
            })}

            {filteredOrganisations.length === 0 && (
              <div className="col-span-full p-12 text-center text-slate-500 bg-slate-900/40 rounded-2xl border border-slate-800">
                <Building2 className="w-10 h-10 mx-auto mb-2 opacity-30 text-purple-400" />
                <p className="text-sm font-semibold">No organisations match the filter criteria.</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
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
                      <span className="text-xs font-semibold text-white truncate" title={comment.organisation_name || comment.stakeholder_name}>
                        {comment.organisation_name || comment.stakeholder_name}
                      </span>
                    </div>
                    {renderSentimentBadge(comment.sentiment)}
                  </div>

                  {/* Sector & Provision Target */}
                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-mono">
                      {comment.stakeholder_category || comment.stakeholder_group}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/80">
                      {comment.chapter_section || comment.target_section}
                    </span>
                    {renderValidityBadge(comment.validity)}
                  </div>

                  {/* Direction of travel badge */}
                  {comment.direction_of_travel && (
                    <div className="flex items-center gap-1 mb-2 text-[10px] text-indigo-300 bg-indigo-950/40 border border-indigo-900/40 px-2 py-0.5 rounded">
                      <Compass className="w-3 h-3 text-indigo-400 shrink-0" />
                      <span className="truncate">{comment.direction_of_travel}</span>
                    </div>
                  )}

                  {/* Dual-Context Weighted Score (75% Section / 25% Document) */}
                  {comment.weighted_score != null && !isNaN(comment.weighted_score) && (
                    <div className="flex items-center justify-between text-[10px] font-mono py-1 px-2 rounded bg-slate-950/80 border border-slate-800/80 mb-2">
                      <span className="text-slate-400">Dual-Context Score:</span>
                      <span className={`font-bold ${
                        comment.weighted_score > 0.15 ? 'text-emerald-400' :
                        comment.weighted_score < -0.15 ? 'text-rose-400' : 'text-amber-400'
                      }`}>
                        {formatScore(comment.weighted_score, 2, true)}
                        <span className="text-slate-500 font-normal ml-1">(75% Sec / 25% Doc)</span>
                      </span>
                    </div>
                  )}

                  {/* Support Network & Silence Miniature Indicator */}
                  {comment.support_network && comment.support_network.co_objectors.length > 0 && (
                    <div className="flex items-center justify-between text-[10px] text-amber-400/90 bg-amber-950/30 border border-amber-900/40 px-2 py-0.5 rounded mb-2">
                      <span className="flex items-center gap-1">
                        <Users className="w-3 h-3 text-amber-400" />
                        <span>+{comment.support_network.co_objectors.length} Co-Objector{comment.support_network.co_objectors.length > 1 ? 's' : ''}</span>
                      </span>
                      <span className="text-slate-400 font-mono">
                        {comment.support_network.silence_count} silent ({comment.support_network.silence_rate_pct}%)
                      </span>
                    </div>
                  )}

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

                {/* Sub-tabs: Deliberation vs Synthesis vs Document Text */}
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
                    onClick={() => setInspectorTab('synthesis')}
                    className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      inspectorTab === 'synthesis'
                        ? 'bg-slate-800 text-cyan-400 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Scale className="w-3 h-3" />
                    <span>Comment vs Text Synthesis</span>
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
                    {/* Dual-Context Semantic Evaluation Panel */}
                    <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl space-y-3">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400">
                            <Scale className="w-4 h-4" />
                          </div>
                          <div>
                            <h3 className="text-xs font-bold text-white flex items-center gap-2">
                              <span>Dual-Context Semantic & LLM Evaluation</span>
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                                75% Specific Section / 25% Whole Document
                              </span>
                            </h3>
                            <p className="text-[11px] text-slate-400">
                              Non-deterministic semantic similarity and unified LLM evaluation calibrated against specific provisions and overarching regulatory objectives.
                            </p>
                          </div>
                        </div>

                        {selectedComment.direction_of_travel && (
                          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-indigo-950/80 border border-indigo-800/80 text-xs text-indigo-200">
                            <Compass className="w-3.5 h-3.5 text-indigo-400" />
                            <span className="font-semibold">{selectedComment.direction_of_travel}</span>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {/* Section Score Card (75% weight) */}
                        <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-400 font-medium">Specific Section Score</span>
                            <span className="font-mono text-[10px] font-bold text-indigo-400 bg-indigo-950 px-1.5 py-0.2 rounded">75% Weight</span>
                          </div>
                          <div className="flex items-baseline gap-2">
                            <span className={`text-xl font-bold font-mono ${
                              (selectedComment.section_score ?? 0) > 0.15 ? 'text-emerald-400' :
                              (selectedComment.section_score ?? 0) < -0.15 ? 'text-rose-400' : 'text-amber-400'
                            }`}>
                              {selectedComment.section_score != null && !isNaN(selectedComment.section_score)
                                ? formatScore(selectedComment.section_score, 2, true)
                                : 'N/A'}
                            </span>
                            <span className="text-[11px] text-slate-400 truncate font-mono">
                              {selectedComment.chapter_section || selectedComment.target_section}
                            </span>
                          </div>
                          <p className="text-[10px] text-slate-500">
                            Alignment with targeted clause requirements and technical constraints.
                          </p>
                        </div>

                        {/* Whole Document Score Card (25% weight) */}
                        <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-400 font-medium">Whole Document Score</span>
                            <span className="font-mono text-[10px] font-bold text-cyan-400 bg-cyan-950 px-1.5 py-0.2 rounded">25% Weight</span>
                          </div>
                          <div className="flex items-baseline gap-2">
                            <span className={`text-xl font-bold font-mono ${
                              (selectedComment.document_score ?? 0) > 0.15 ? 'text-emerald-400' :
                              (selectedComment.document_score ?? 0) < -0.15 ? 'text-rose-400' : 'text-amber-400'
                            }`}>
                              {selectedComment.document_score != null && !isNaN(selectedComment.document_score)
                                ? formatScore(selectedComment.document_score, 2, true)
                                : 'N/A'}
                            </span>
                            <span className="text-[11px] text-slate-400 truncate">
                              {selectedComment.document_title || currentSession?.documents?.[0]?.title || 'Consultation Draft'}
                            </span>
                          </div>
                          <p className="text-[10px] text-slate-500">
                            Compatibility with broader safety intent, proportionality, and strategic policy.
                          </p>
                        </div>

                        {/* Combined Weighted Score Card */}
                        <div className="p-3 bg-slate-950 border border-cyan-900/50 rounded-xl space-y-1">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-400 font-medium">Combined Weighted Score</span>
                            <span className="font-mono text-[10px] text-slate-500">Sec*0.75 + Doc*0.25</span>
                          </div>
                          <div className="flex items-baseline gap-2">
                            <span className={`text-xl font-bold font-mono ${
                              (selectedComment.weighted_score ?? 0) > 0.15 ? 'text-emerald-400' :
                              (selectedComment.weighted_score ?? 0) < -0.15 ? 'text-rose-400' : 'text-amber-400'
                            }`}>
                              {selectedComment.weighted_score != null && !isNaN(selectedComment.weighted_score)
                                ? formatScore(selectedComment.weighted_score, 3, true)
                                : 'N/A'}
                            </span>
                            <span className="text-[10px] font-medium text-slate-300">
                              {(selectedComment.weighted_score ?? 0) > 0.2 ? 'Substantially Aligned' :
                               (selectedComment.weighted_score ?? 0) < -0.2 ? 'Substantial Divergence' : 'Moderate Nuance / Neutral'}
                            </span>
                          </div>
                          <p className="text-[10px] text-slate-500">
                            Integrated score synthesizing clause specificity with macro regulatory posture.
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Stakeholder Support Network & Silence Accounting Box */}
                    {selectedComment.support_network && (
                      <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                          <div className="flex items-center gap-2">
                            <div className="w-7 h-7 rounded-lg bg-amber-950 border border-amber-800 flex items-center justify-center text-amber-400">
                              <Network className="w-4 h-4" />
                            </div>
                            <div>
                              <h3 className="text-xs font-bold text-white flex items-center gap-2">
                                <span>Stakeholder Support Network & Silence Accounting</span>
                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                                  {selectedComment.support_network.total_participating_organisations} Participating Organisations
                                </span>
                              </h3>
                              <p className="text-[11px] text-slate-400">
                                Differentiating concerted multi-stakeholder objections from isolated dissent, accounting for non-commenting organisations as tacit regulatory acquiescence.
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Tripartite Breakdown Progress Bar */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-rose-400 font-semibold flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-rose-500 inline-block"></span>
                              Active Co-Objectors: {selectedComment.support_network.support_count} ({selectedComment.support_network.support_rate_pct}%)
                            </span>
                            <span className="text-slate-400 font-medium flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-slate-500 inline-block"></span>
                              Silent Stakeholders (Tacit Acquiescence): {selectedComment.support_network.silence_count} ({selectedComment.support_network.silence_rate_pct}%)
                            </span>
                            <span className="text-emerald-400 font-semibold flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
                              Active Defenders: {selectedComment.support_network.defense_count} ({selectedComment.support_network.defense_rate_pct}%)
                            </span>
                          </div>

                          <div className="h-3 w-full bg-slate-950 rounded-full overflow-hidden flex border border-slate-800">
                            <div
                              style={{ width: `${selectedComment.support_network.support_rate_pct}%` }}
                              className="bg-rose-500 h-full transition-all"
                              title={`Co-Objectors: ${selectedComment.support_network.support_rate_pct}%`}
                            />
                            <div
                              style={{ width: `${selectedComment.support_network.silence_rate_pct}%` }}
                              className="bg-slate-600 h-full transition-all"
                              title={`Silent (Tacit Acquiescence): ${selectedComment.support_network.silence_rate_pct}%`}
                            />
                            <div
                              style={{ width: `${selectedComment.support_network.defense_rate_pct}%` }}
                              className="bg-emerald-500 h-full transition-all"
                              title={`Defenders: ${selectedComment.support_network.defense_rate_pct}%`}
                            />
                          </div>
                        </div>

                        {/* 3 Columns: Co-Objectors, Silent, Defenders */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
                          {/* Co-Objectors */}
                          <div className="p-3 bg-slate-950 border border-rose-950/60 rounded-xl space-y-1.5">
                            <div className="text-[11px] font-bold text-rose-300 flex items-center justify-between">
                              <span>Co-Objecting Stakeholders</span>
                              <span className="text-[10px] font-mono bg-rose-950 px-1.5 py-0.2 rounded text-rose-300">
                                {selectedComment.support_network.co_objectors.length}
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {selectedComment.support_network.co_objectors.length > 0 ? (
                                selectedComment.support_network.co_objectors.map(org => (
                                  <span key={org} className="text-[10px] px-2 py-0.5 rounded bg-rose-950/70 text-rose-200 border border-rose-900/60 font-medium">
                                    {org}
                                  </span>
                                ))
                              ) : (
                                <span className="text-[10px] text-slate-500 italic">No other organisations co-objected on this provision.</span>
                              )}
                            </div>
                          </div>

                          {/* Silent Stakeholders */}
                          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
                            <div className="text-[11px] font-bold text-slate-300 flex items-center justify-between">
                              <span>Silent (Tacit Acquiescence)</span>
                              <span className="text-[10px] font-mono bg-slate-800 px-1.5 py-0.2 rounded text-slate-300">
                                {selectedComment.support_network.silent_organisations.length}
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                              {selectedComment.support_network.silent_organisations.map(org => (
                                <span key={org} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                                  {org}
                                </span>
                              ))}
                            </div>
                            <p className="text-[9px] text-slate-500 italic">
                              Did not submit objections against this specific provision.
                            </p>
                          </div>

                          {/* Defenders */}
                          <div className="p-3 bg-slate-950 border border-emerald-950/60 rounded-xl space-y-1.5">
                            <div className="text-[11px] font-bold text-emerald-300 flex items-center justify-between">
                              <span>Active Defenders</span>
                              <span className="text-[10px] font-mono bg-emerald-950 px-1.5 py-0.2 rounded text-emerald-300">
                                {selectedComment.support_network.defenders.length}
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {selectedComment.support_network.defenders.length > 0 ? (
                                selectedComment.support_network.defenders.map(org => (
                                  <span key={org} className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-200 border border-emerald-900/60 font-medium">
                                    {org}
                                  </span>
                                ))
                              ) : (
                                <span className="text-[10px] text-slate-500 italic">No formal written defense submitted.</span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Regulatory Interpretation */}
                        <div className="p-3 bg-amber-950/20 border border-amber-900/40 rounded-xl text-xs text-amber-200/90 leading-relaxed flex items-start gap-2">
                          <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                          <div>
                            <strong className="text-amber-300">Regulatory Deliberation Weighting: </strong>
                            {selectedComment.support_network.regulatory_interpretation}
                          </div>
                        </div>
                      </div>
                    )}

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

                      {/* Right: Consulted Document Provision Excerpt with In-Place Text Editor */}
                      <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
                        <div className="flex items-center justify-between text-xs font-semibold text-slate-200 border-b border-slate-800 pb-2">
                          <span className="flex items-center gap-1.5 text-indigo-400">
                            <FileText className="w-4 h-4" />
                            Consulted Document Provision
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[11px] text-indigo-300 font-bold">
                              {selectedComment.chapter_section || selectedComment.target_section}
                            </span>
                            {selectedCommentTextBlock ? (
                              <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                                selectedCommentTextBlock.status === 'provided'
                                  ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                                  : 'bg-rose-950 text-rose-300 border-rose-800'
                              }`}>
                                {selectedCommentTextBlock.status === 'provided' ? 'Text Block Provided' : 'Text Block Missing'}
                              </span>
                            ) : null}
                          </div>
                        </div>

                        {selectedComment.document_title && (
                          <div className="text-[11px] text-slate-400">
                            Document: <strong className="text-slate-300">{selectedComment.document_title}</strong>
                            {selectedComment.page && <span> (Page {selectedComment.page})</span>}
                          </div>
                        )}

                        {/* Inline Text Editor or Display */}
                        {editingBlockId === selectedCommentTextBlock?.block_id ? (
                          <div className="space-y-2 bg-slate-950 p-3 rounded-lg border border-cyan-800">
                            <div className="text-[11px] font-bold text-cyan-300 flex items-center justify-between">
                              <span>Editing Required Document Text Block</span>
                              <span className="font-mono text-[10px] text-slate-400">{selectedComment.chapter_section}</span>
                            </div>
                            <textarea
                              rows={8}
                              value={editingBlockContent}
                              onChange={(e) => setEditingBlockContent(e.target.value)}
                              placeholder="Paste or type the official consulted regulatory drafting text for this section..."
                              className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-xs text-white font-mono focus:outline-none focus:border-cyan-500"
                            />
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() => {
                                  setEditingBlockId(null);
                                  setEditingBlockContent('');
                                }}
                                className="px-2.5 py-1 text-xs text-slate-400 hover:text-white"
                              >
                                Cancel
                              </button>
                              <button
                                onClick={() => selectedCommentTextBlock && handleSaveTextBlock(selectedCommentTextBlock.block_id)}
                                disabled={savingBlock}
                                className="flex items-center gap-1 px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-semibold disabled:opacity-50"
                              >
                                {savingBlock && <RefreshCw className="w-3 h-3 animate-spin" />}
                                <span>Save & Re-Score Comments</span>
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {selectedCommentTextBlock?.content || selectedComment.matched_section_content ? (
                              <div>
                                <div className="flex items-center justify-between text-xs font-semibold text-white mb-1.5">
                                  <span>{selectedComment.matched_section_title || selectedCommentTextBlock?.chapter_section}</span>
                                  {selectedCommentTextBlock && (
                                    <button
                                      onClick={() => {
                                        setEditingBlockId(selectedCommentTextBlock.block_id);
                                        setEditingBlockContent(selectedCommentTextBlock.content);
                                      }}
                                      className="text-[10px] text-cyan-400 hover:underline flex items-center gap-1"
                                    >
                                      <Edit3 className="w-3 h-3" />
                                      <span>Edit Section Text</span>
                                    </button>
                                  )}
                                </div>
                                <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-950 p-3.5 rounded-lg border border-slate-800 font-sans max-h-80 overflow-y-auto">
                                  {selectedCommentTextBlock?.content || selectedComment.matched_section_content}
                                </div>
                              </div>
                            ) : (
                              <div className="p-6 text-center text-slate-500 bg-slate-950 rounded-lg border border-slate-800 space-y-3">
                                <FileText className="w-6 h-6 mx-auto opacity-40 text-amber-400" />
                                <div>
                                  <p className="text-xs font-medium text-amber-300">
                                    Section Text Block Missing for '{selectedComment.chapter_section || selectedComment.target_section}'
                                  </p>
                                  <p className="text-[11px] text-slate-400 mt-1">
                                    Stakeholders cited this section. Provide the official text block to ensure accurate dual-context evaluation.
                                  </p>
                                </div>
                                {selectedCommentTextBlock && (
                                  <button
                                    onClick={() => {
                                      setEditingBlockId(selectedCommentTextBlock.block_id);
                                      setEditingBlockContent('');
                                    }}
                                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white inline-flex items-center gap-1.5 shadow-sm"
                                  >
                                    <Edit3 className="w-3.5 h-3.5" />
                                    <span>Provide Section Text In-Place</span>
                                  </button>
                                )}
                              </div>
                            )}
                          </>
                        )}

                        {selectedComment.original_text && (
                          <div className="p-2.5 bg-slate-950 border border-slate-800 rounded-lg text-[11px] space-y-1">
                            <span className="font-semibold text-slate-400">Stakeholder Cited Draft Excerpt:</span>
                            <p className="text-slate-300 italic">"{selectedComment.original_text}"</p>
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

                    {/* Cost/Benefit, Legal Rationale & Response Fields */}
                    {(selectedComment.af_cba || selectedComment.response_to_comment || selectedComment.rationale_and_changes) && (
                      <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
                        <div className="flex items-center gap-2 text-xs font-bold text-white border-b border-slate-800 pb-2">
                          <Building className="w-4 h-4 text-cyan-400" />
                          <span>Internal Reference (AF/CBA) & Formal Consultation Response</span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          {selectedComment.af_cba && (
                            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="text-[11px] font-bold text-slate-300">Internal Ref (AF / CBA)</span>
                                <span className="text-[9px] font-medium text-slate-500 uppercase px-1 rounded bg-slate-900 border border-slate-800">Ignored for Evaluation</span>
                              </div>
                              <p className="text-xs text-slate-400 leading-relaxed">{selectedComment.af_cba}</p>
                            </div>
                          )}

                          {selectedComment.response_to_comment && (
                            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1">
                              <span className="text-[11px] font-bold text-emerald-300 block">Response to Comment</span>
                              <p className="text-xs text-slate-300 leading-relaxed">{selectedComment.response_to_comment}</p>
                            </div>
                          )}

                          {selectedComment.rationale_and_changes && (
                            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1">
                              <span className="text-[11px] font-bold text-amber-300 block">Rationale & Resulting Changes</span>
                              <p className="text-xs text-slate-300 leading-relaxed">{selectedComment.rationale_and_changes}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

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
                ) : inspectorTab === 'synthesis' ? (
                  /* Comment vs Text Synthesis Inspector */
                  <div className="space-y-6">
                    <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between">
                      <div>
                        <div className="text-xs font-bold text-white flex items-center gap-2">
                          <Scale className="w-4 h-4 text-cyan-400" />
                          <span>Synthesis: Comment vs Consulted Draft Provision</span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Rigorous regulatory divergence analysis, operational trade-offs, and drafting alternatives.
                        </p>
                      </div>
                      <button
                        onClick={() => setWorkspaceMode('synthesis')}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white flex items-center gap-1.5 transition-colors"
                      >
                        <GitCompare className="w-3.5 h-3.5" />
                        <span>Full Synthesis Suite</span>
                      </button>
                    </div>

                    {/* Side-by-side Stipulation vs Feedback */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {/* Left: Consulted Draft Text Stipulation */}
                      <div className="p-4 bg-slate-900 border border-indigo-950/60 rounded-xl space-y-2">
                        <div className="text-xs font-bold text-indigo-300 flex items-center justify-between">
                          <span className="flex items-center gap-1.5">
                            <FileText className="w-4 h-4 text-indigo-400" />
                            <span>Consulted Draft Stipulation</span>
                          </span>
                          <span className="font-mono text-[11px] text-indigo-300 font-bold">
                            {selectedComment.target_section}
                          </span>
                        </div>
                        <div className="text-xs text-slate-300 font-mono bg-slate-950 p-3 rounded-lg border border-slate-800 whitespace-pre-wrap max-h-56 overflow-y-auto leading-relaxed">
                          {selectedCommentSynthesis?.text_stipulation || selectedComment.matched_section_content || 'No direct section excerpt matched.'}
                        </div>
                      </div>

                      {/* Right: Stakeholder Submission */}
                      <div className="p-4 bg-slate-900 border border-cyan-950/60 rounded-xl space-y-2">
                        <div className="text-xs font-bold text-cyan-300 flex items-center justify-between">
                          <span className="flex items-center gap-1.5">
                            <MessageSquare className="w-4 h-4 text-cyan-400" />
                            <span>Stakeholder Submission</span>
                          </span>
                          <span className="text-[11px] font-normal text-slate-400">
                            {selectedComment.stakeholder_name}
                          </span>
                        </div>
                        <div className="text-xs text-slate-200 bg-slate-950 p-3 rounded-lg border border-slate-800 leading-relaxed">
                          {selectedComment.comment_text}
                        </div>
                        {selectedComment.proposed_text && (
                          <div className="p-2.5 bg-teal-950/40 border border-teal-800/60 rounded-lg text-xs font-mono text-teal-200">
                            <strong className="text-teal-300">Requested Alternative: </strong>{selectedComment.proposed_text}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Divergence & Operational Impact Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-4 bg-slate-900 border border-amber-950/60 rounded-xl space-y-1.5">
                        <div className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>Regulatory Divergence Analysis</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed bg-slate-950 p-3 rounded-lg border border-slate-800">
                          {selectedCommentSynthesis?.divergence_analysis || 'Stakeholder proposes amendments to draft provisions. Evaluate operational necessity vs baseline safety margins.'}
                        </p>
                      </div>

                      <div className="p-4 bg-slate-900 border border-purple-950/60 rounded-xl space-y-1.5">
                        <div className="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                          <Building className="w-3.5 h-3.5" />
                          <span>Operational & Safety Feasibility Impact</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed bg-slate-950 p-3 rounded-lg border border-slate-800">
                          {selectedCommentSynthesis?.operational_and_safety_impact || 'Assess compliance feasibility and impact on industry workload vs risk mitigations.'}
                        </p>
                      </div>
                    </div>

                    {/* Actionable Drafting Alternatives */}
                    <div className="p-4 bg-slate-900 border border-cyan-900/60 rounded-xl space-y-3">
                      <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                        <Scale className="w-3.5 h-3.5 text-cyan-400" />
                        <span>Actionable Drafting Alternatives for Counsel</span>
                      </div>

                      <div className="space-y-2">
                        {(selectedCommentSynthesis?.drafting_options || [
                          'Drafting Option A: Issue accompanying Guidance Material (GM) clarifying acceptable methods.',
                          'Drafting Option B: Calibrate section wording to address stakeholder operational constraints.'
                        ]).map((opt, oIdx) => (
                          <div key={oIdx} className="text-xs text-slate-200 flex items-start gap-2.5 bg-slate-950 p-3 rounded-lg border border-slate-800">
                            <ArrowRight className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5" />
                            <span className="leading-relaxed">{opt}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  /* Full Consulted Document Viewer Tab */
                  <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                      <div>
                        <h3 className="text-sm font-bold text-white">Consulted Document Text & Provisions</h3>
                        <p className="text-xs text-slate-400">
                          {currentSession?.documents?.[0]?.title || 'Consultation Draft'}
                        </p>
                      </div>
                      <span className="text-xs font-mono text-slate-400">
                        {currentSession?.documents?.[0]?.word_count ? currentSession.documents[0].word_count.toLocaleString() : 0} words
                      </span>
                    </div>

                    <div className="space-y-6">
                      {currentSession?.documents?.[0]?.sections?.map((sec, idx) => (
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
        </>
      )}

      {/* 6. Upload Consultation Modal (2-Step Grouping Wizard) */}
      {isUploadModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-3xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
            {/* Modal Header */}
            <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400">
                  {uploadStep === 1 ? <Upload className="w-4 h-4" /> : <Sliders className="w-4 h-4" />}
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <span>{uploadStep === 1 ? 'Create Consultation Workspace' : 'Confirm Comment Field Grouping'}</span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300 border border-slate-700">
                      Step {uploadStep} of 2
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    {uploadStep === 1
                      ? 'Upload stakeholder comments and optional consulted draft document.'
                      : 'Modify column groupings against the standard 15-field consultation template before ingestion.'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setIsUploadModalOpen(false);
                  setUploadStep(1);
                }}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Step 1: File Upload & Metadata */}
            {uploadStep === 1 ? (
              <div className="p-6 space-y-4 overflow-y-auto flex-1">
                <div>
                  <label className="text-xs font-medium text-slate-300 block mb-1">
                    Consultation Title <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. NPA 2024-05: Aerodrome Ground Safety & Cybersecurity"
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
                      placeholder="e.g. EASA Notice of Proposed Amendment stakeholder consultation"
                      value={uploadDescription}
                      onChange={(e) => setUploadDescription(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>

                {/* Stakeholder Feedback CSV Input */}
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                  <label className="text-xs font-semibold text-white flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <FileSpreadsheet className="w-4 h-4 text-cyan-400" />
                      Stakeholder Feedback Comments File (CSV / TSV) <span className="text-rose-400">*</span>
                    </span>
                    {csvFile && (
                      <span className="text-[10px] font-mono text-cyan-300 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-800">
                        {csvFile.name} ({(csvFile.size / 1024).toFixed(1)} KB)
                      </span>
                    )}
                  </label>
                  <p className="text-[11px] text-slate-400">
                    File structure is flexible. Standard template fields (ID, Document Title, Chapter/Section, Comment, Importance, Proposed Text, Stakeholder Category, Org Name, CBA, etc.) will be previewed in Step 2 for grouping confirmation.
                  </p>
                  <input
                    type="file"
                    required
                    accept=".csv,.tsv,.txt"
                    onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                    className="block w-full text-xs text-slate-400 file:mr-4 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-cyan-950 file:text-cyan-300 hover:file:bg-cyan-900 cursor-pointer"
                  />
                </div>

                {/* Consultation Document Input */}
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                  <label className="text-xs font-semibold text-white flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <FileText className="w-4 h-4 text-indigo-400" />
                      Consulted Document (PDF, Word .doc/.docx, XML, TXT) <span className="text-slate-500 font-normal">(Optional)</span>
                    </span>
                    {docFile && (
                      <span className="text-[10px] font-mono text-indigo-300 bg-indigo-950 px-2 py-0.5 rounded border border-indigo-800">
                        {docFile.name}
                      </span>
                    )}
                  </label>
                  <p className="text-[11px] text-slate-400">
                    The draft regulation or policy paper. Sections referenced in comments that are missing from this document will be compiled into the interactive Required Text Blocks checklist.
                  </p>
                  <input
                    type="file"
                    accept=".pdf,.doc,.docx,.xml,.txt,.md,.html"
                    onChange={(e) => setDocFile(e.target.files?.[0] || null)}
                    className="block w-full text-xs text-slate-400 file:mr-4 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-950 file:text-indigo-300 hover:file:bg-indigo-900 cursor-pointer"
                  />
                </div>

                {/* Modal Footer (Step 1) */}
                <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={async () => {
                      setIsUploadModalOpen(false);
                      await loadSampleConsultation();
                      await refreshSessions();
                    }}
                    className="text-xs text-indigo-400 hover:underline flex items-center gap-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Load Pre-Configured Sample (NPA 2024-05)</span>
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
                      type="button"
                      disabled={inspectingFile || !uploadTitle.trim() || !csvFile}
                      onClick={handleInspectCsv}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors disabled:opacity-50"
                    >
                      {inspectingFile ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Sliders className="w-3.5 h-3.5" />
                      )}
                      <span>{inspectingFile ? 'Inspecting Delimiter & Headers...' : 'Next: Inspect & Group Comment Fields'}</span>
                      {!inspectingFile && <ChevronRight className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              /* Step 2: Interactive Field Grouping Wizard */
              <div className="p-6 space-y-4 overflow-y-auto flex-1 flex flex-col">
                {/* File Inspection Telemetry Strip */}
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400">File:</span>
                    <strong className="text-white font-mono">{csvFile?.name}</strong>
                  </div>
                  <div className="flex items-center gap-3 font-mono text-[11px]">
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-cyan-300">
                      Delimiter: <strong>{inspectResult?.detected_delimiter === '\t' ? 'Tab (\\t)' : inspectResult?.detected_delimiter === ';' ? 'Semicolon (;)' : 'Comma (,)'}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-indigo-300">
                      Rows: <strong>{inspectResult?.row_count ?? 0}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-emerald-300">
                      Columns Found: <strong>{inspectResult?.headers.length ?? 0}</strong>
                    </span>
                  </div>
                </div>

                <div className="text-xs text-slate-300 bg-cyan-950/20 border border-cyan-900/40 p-3 rounded-xl leading-relaxed">
                  <strong className="text-cyan-300">Template Grouping Baseline: </strong>
                  The system has pre-mapped your file columns to the standard 15 consultation fields. Confirm or modify the mappings below. The <strong className="text-white font-mono">Document title</strong> and <strong className="text-white font-mono">Chapter/Section</strong> fields drive the Required Text Blocks manifest.
                </div>

                {/* 15 Standard Template Fields List */}
                <div className="space-y-3 max-h-[50vh] overflow-y-auto p-1 pr-2">
                  {(inspectResult?.template_fields && inspectResult.template_fields.length > 0 ? inspectResult.template_fields : STANDARD_TEMPLATE_FIELDS).map((field, idx) => {
                    const selectedCol = columnMapping[field.key] || '';
                    const sampleVal = selectedCol && inspectResult?.sample_rows?.[0] ? inspectResult.sample_rows[0][selectedCol] : null;

                    return (
                      <div
                        key={field.key}
                        className={`p-3 rounded-xl border transition-colors ${
                          selectedCol
                            ? 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                            : field.required
                            ? 'bg-rose-950/20 border-rose-900/60'
                            : 'bg-slate-950/40 border-slate-900'
                        }`}
                      >
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                          {/* Field metadata */}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono text-slate-500 w-4 shrink-0">#{idx + 1}</span>
                              <span className="text-xs font-bold text-white truncate">{field.label}</span>
                              {field.required && (
                                <span className="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800 shrink-0">
                                  Required
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 mt-0.5 ml-6">{field.description}</p>
                          </div>

                          {/* Column Selector */}
                          <div className="shrink-0 w-full md:w-64">
                            <select
                              value={selectedCol}
                              onChange={(e) => setColumnMapping(prev => ({ ...prev, [field.key]: e.target.value }))}
                              className={`w-full bg-slate-900 border text-xs rounded-lg px-2.5 py-1.5 text-white focus:outline-none ${
                                selectedCol
                                  ? 'border-cyan-700 text-cyan-200'
                                  : field.required
                                  ? 'border-rose-600 text-rose-300'
                                  : 'border-slate-800 text-slate-400'
                              }`}
                            >
                              <option value="">-- (Not in File / Unmapped) --</option>
                              {inspectResult?.headers.map((h) => (
                                <option key={h} value={h}>{h}</option>
                              ))}
                            </select>
                          </div>
                        </div>

                        {/* Sample Data Preview */}
                        {selectedCol && sampleVal !== null && sampleVal !== undefined && (
                          <div className="text-[10px] bg-slate-900/70 p-1.5 rounded-lg border border-slate-800/80 font-mono text-slate-300 truncate mt-1.5 ml-6">
                            <span className="text-slate-500">Row 1 Sample: </span>
                            <span className="text-cyan-300">"{sampleVal}"</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Modal Footer (Step 2) */}
                <div className="pt-4 border-t border-slate-800 flex items-center justify-between mt-auto">
                  <button
                    type="button"
                    onClick={() => setUploadStep(1)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                  >
                    ← Back to File Upload
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setIsUploadModalOpen(false);
                        setUploadStep(1);
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={submittingUpload}
                      onClick={() => handleCreateConsultation()}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors disabled:opacity-50"
                    >
                      {submittingUpload ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      <span>{submittingUpload ? 'Analyzing & Ingesting...' : 'Ingest Feedback with Confirmed Grouping'}</span>
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Interactive Stakeholder Spider Radar & Silence Mapping Modal */}
      {currentSession && (
        <StakeholderSpiderModal
          isOpen={showSpiderModal}
          onClose={() => setShowSpiderModal(false)}
          organisations={currentSession.organisations_analysis || []}
          session={currentSession}
          initialSelectedOrgName={spiderInitialOrg}
        />
      )}
    </div>
  );
};
