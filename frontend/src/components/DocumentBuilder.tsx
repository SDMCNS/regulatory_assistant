/**
 * DocumentBuilder Component
 * 
 * Enables users to author and publish custom or company regulatory manuals,
 * enforcing the exact same hierarchical structure (Subparts, Sections, Articles,
 * Markdown tables, and normative modal verbs) and sequential chunking
 * (chunk_id, section_path, embedding_text, previous_chunk_id, next_chunk_id)
 * as EASA Easy Access Rules and FAA Title 14 CFR documents.
 */

import React, { useState, useMemo } from 'react';
import {
  FileText,
  Plus,
  Trash2,
  ArrowUp,
  ArrowDown,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Eye,
  BookOpen,
  Table,
  ListOrdered,
  ShieldCheck,
  Scale,
  RefreshCw,
  Copy,
  Split,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal,
  Bookmark,
  Send,
  FilePlus2
} from 'lucide-react';
import {
  AppSettings,
  ManualDocumentRequest,
  ManualSectionInput,
  SearchDocResponse,
} from '../types';
import { createManualDocument } from '../services/apiClient';

interface DocumentBuilderProps {
  settings: AppSettings;
  onViewDoc: (doc: SearchDocResponse) => void;
  onOpenWorkspaceWithDocs: (docIds: string[], initialQuery?: string) => void;
  onSendToAssistant?: (prompt: string, chunkIds: string[]) => void;
}

// Preset starter templates
const PRESET_TEMPLATES: {
  id: string;
  name: string;
  description: string;
  data: ManualDocumentRequest;
}[] = [
  {
    id: 'flight_ops_a',
    name: 'Operator Flight Operations Manual (Part A)',
    description: 'General flight operations, standard operating procedures, and crew responsibilities.',
    data: {
      title: 'Operations Manual Part A — General Flight Operations',
      document_id: 'MANUAL_OPS_PART_A',
      source: 'Operator Flight Operations',
      date: '2026-03-01',
      language: 'eng',
      stakeholder: 'airline',
      description: 'Standard Operating Procedures, Pre-flight Briefing requirements, and Dispatch Minima for commercial air transport operations.',
      sections: [
        {
          section_number: '1.1',
          title: 'Scope, Applicability and Operational Control',
          subpart: 'Subpart A — General Requirements',
          subject_group: 'OPERATIONAL CONTROL',
          text: 'This Manual applies to all multi-engine commercial air transport flights conducted by the operator.\n\n(a) The Pilot-in-Command (PIC) shall have operational control over the safety of the aircraft during flight time.\n(b) The operator shall maintain active flight following and continuous radio communication throughout the cruise phase.\n(c) No flight shall commence unless the dispatcher and PIC have jointly certified the operational flight plan (OFP).'
        },
        {
          section_number: '1.2',
          title: 'Pre-flight Briefing and Fuel Planning Standards',
          subpart: 'Subpart A — General Requirements',
          subject_group: 'FLIGHT CREW PROCEDURES',
          text: 'The PIC shall ensure that all flight crew members receive a comprehensive pre-flight briefing covering weather, NOTAMs, aircraft status, and contingency plans.\n\n| Fuel Requirement | Minimum Required Reserves | Operational Margin |\n| :--- | :--- | :--- |\n| Taxi Fuel | Standard APU + 15 min taxi | 250 kg |\n| Trip Fuel | Destination routing + winds | FMC calculated |\n| Contingency Fuel | 5% of trip fuel or 5 min holding | 15 min holding min |\n| Alternate Fuel | Missed approach + climb to alternate | Fuel to furthest alternate |\n| Final Reserve | 30 minutes at 1,500 ft holding speed | Mandatory non-usable |\n\n(d) The aircraft shall not depart if final reserve fuel is compromised under any expected routing scenario.'
        },
        {
          section_number: '1.3',
          title: 'All-Weather Operations and Low Visibility Procedures (LVP)',
          subpart: 'Subpart B — All-Weather Operations',
          subject_group: 'AERODROME OPERATING MINIMA',
          text: 'Low visibility takeoff and Category II/III precision approaches are governed by the following criteria:\n\n(a) CAT II operations shall not be initiated unless the RVR is at least 300 meters and decision height (DH) is 100 feet.\n(b) Autoland systems must be verified operational prior to commencing the final descent segment.\n(c) Should visual contact not be established at or before the decision height, the flight crew shall immediately initiate a missed approach.'
        }
      ]
    }
  },
  {
    id: 'sms_manual',
    name: 'Safety Management System (SMS) Manual',
    description: 'Corporate aviation safety policy, hazard identification, and risk mitigation matrices.',
    data: {
      title: 'Aviation Safety Management System (SMS) Standard Manual',
      document_id: 'MANUAL_SMS_POLICY',
      source: 'Corporate Safety & Quality Assurance',
      date: '2026-02-15',
      language: 'eng',
      stakeholder: 'airline',
      description: 'Framework for hazard reporting, root-cause safety investigation, and ALARP risk mitigation.',
      sections: [
        {
          section_number: '2.1',
          title: 'Safety Policy Objectives and Accountable Executive Commitment',
          subpart: 'Subpart 1 — Safety Policy & Objectives',
          subject_group: 'LEADERSHIP RESPONSIBILITIES',
          text: 'The Accountable Executive shall ensure adequate financial and human resources are allocated for the management of aviation safety.\n\n(a) The organization maintains a Just Culture policy wherein non-intentional errors reported promptly shall not incur disciplinary action.\n(b) Gross negligence, willful violation, or substance impairment is prohibited and shall not be shielded under Just Culture provisions.'
        },
        {
          section_number: '2.2',
          title: 'Hazard Identification and Risk Severity Assessment',
          subpart: 'Subpart 2 — Safety Risk Management',
          subject_group: 'RISK TOLERABILITY',
          text: 'All identified hazards must be evaluated against the standard corporate 5x5 Risk Tolerability Matrix:\n\n| Severity Level | Definition | Acceptable Response Time |\n| :--- | :--- | :--- |\n| 5 — Catastrophic | Aircraft hull loss, multiple fatalities | Immediate grounding / cessation |\n| 4 — Hazardous | Serious injury, major equipment damage | 24-hour mitigation required |\n| 3 — Major | Significant operational disruption | 7-day corrective action plan |\n| 2 — Minor | Operating nuisance, minor damage | 30-day review cycle |\n| 1 — Negligible | Inconsequential event | Trend monitoring only |\n\n(c) Any risk ranked in the intolerable red zone (Severity 4-5 with Likelihood C-E) shall mandate immediate mitigation before operation resumes.'
        }
      ]
    }
  },
  {
    id: 'blank',
    name: 'Custom Blank Regulation / Manual',
    description: 'Start from an empty template and create custom clauses from scratch.',
    data: {
      title: '',
      document_id: '',
      source: 'Manual Document',
      date: new Date().toISOString().slice(0, 10),
      language: 'eng',
      stakeholder: 'general',
      description: '',
      sections: [
        {
          section_number: '1.1',
          title: 'General Provision',
          subpart: 'Subpart A — General',
          subject_group: '',
          text: 'The operator or organization shall ensure compliance with the following requirements...'
        }
      ]
    }
  }
];

export const DocumentBuilder: React.FC<DocumentBuilderProps> = ({
  settings,
  onViewDoc,
  onOpenWorkspaceWithDocs,
  onSendToAssistant
}) => {
  // Document level form state
  const [title, setTitle] = useState<string>(PRESET_TEMPLATES[0].data.title);
  const [docId, setDocId] = useState<string>(PRESET_TEMPLATES[0].data.document_id || '');
  const [source, setSource] = useState<string>(PRESET_TEMPLATES[0].data.source || 'Manual');
  const [date, setDate] = useState<string>(PRESET_TEMPLATES[0].data.date || new Date().toISOString().slice(0, 10));
  const [language, setLanguage] = useState<string>(PRESET_TEMPLATES[0].data.language || 'eng');
  const [stakeholder, setStakeholder] = useState<string>(PRESET_TEMPLATES[0].data.stakeholder || 'airline');
  const [description, setDescription] = useState<string>(PRESET_TEMPLATES[0].data.description || '');

  // Sections state
  const [sections, setSections] = useState<ManualSectionInput[]>(PRESET_TEMPLATES[0].data.sections);

  // UI state
  const [activeTab, setActiveTab] = useState<'editor' | 'preview'>('editor');
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [publishResult, setPublishResult] = useState<{
    success: boolean;
    document_id: string;
    title: string;
    chunk_count: number;
    message: string;
  } | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [expandedSectionIdx, setExpandedSectionIdx] = useState<number | null>(0);

  // Load a preset template
  const handleLoadPreset = (presetId: string) => {
    const p = PRESET_TEMPLATES.find(t => t.id === presetId);
    if (!p) return;
    setTitle(p.data.title);
    setDocId(p.data.document_id || '');
    setSource(p.data.source || 'Manual');
    setDate(p.data.date || new Date().toISOString().slice(0, 10));
    setLanguage(p.data.language || 'eng');
    setStakeholder(p.data.stakeholder || 'general');
    setDescription(p.data.description || '');
    setSections(JSON.parse(JSON.stringify(p.data.sections)));
    setPublishResult(null);
    setPublishError(null);
  };

  // Section manipulation
  const handleAddSection = () => {
    const nextNum = sections.length > 0 ? `${sections.length + 1}.1` : '1.1';
    const lastSubpart = sections.length > 0 ? sections[sections.length - 1].subpart : 'Subpart A — General';
    const newSection: ManualSectionInput = {
      section_number: nextNum,
      title: 'New Provision',
      subpart: lastSubpart,
      subject_group: '',
      text: 'The organization shall...'
    };
    setSections([...sections, newSection]);
    setExpandedSectionIdx(sections.length);
  };

  const handleUpdateSection = (index: number, field: keyof ManualSectionInput, value: string) => {
    setSections(prev => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  const handleDeleteSection = (index: number) => {
    if (sections.length <= 1) {
      alert('The document must contain at least one section.');
      return;
    }
    setSections(prev => prev.filter((_, i) => i !== index));
    if (expandedSectionIdx === index) {
      setExpandedSectionIdx(null);
    }
  };

  const handleMoveSection = (index: number, direction: 'up' | 'down') => {
    if ((direction === 'up' && index === 0) || (direction === 'down' && index === sections.length - 1)) {
      return;
    }
    const targetIdx = direction === 'up' ? index - 1 : index + 1;
    setSections(prev => {
      const next = [...prev];
      const temp = next[index];
      next[index] = next[targetIdx];
      next[targetIdx] = temp;
      return next;
    });
    setExpandedSectionIdx(targetIdx);
  };

  // Helper snippet inserters for clause text
  const handleInsertSnippet = (index: number, snippet: string) => {
    setSections(prev => {
      const next = [...prev];
      const current = next[index].text || '';
      next[index] = {
        ...next[index],
        text: current ? `${current}\n\n${snippet}` : snippet
      };
      return next;
    });
  };

  // Simulated chunk calculation
  const simulatedChunks = useMemo(() => {
    const cleanDocId = (docId || '').trim() || `MANUAL_${(title || '').replace(/[^A-Za-z0-9_]+/g, '_').slice(0, 30) || 'UNTITLED'}`;
    return (sections || []).map((sec, idx) => {
      const secNum = sec.section_number || `${idx + 1}`;
      const safeNum = secNum.replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || `${idx + 1}`;
      const chunkId = `${cleanDocId}:sec_${safeNum}`;
      const path = [(title || '').trim() || 'Untitled Document'];
      if (sec.subpart?.trim()) path.push(sec.subpart.trim());
      if (sec.subject_group?.trim()) path.push(sec.subject_group.trim());
      path.push(`${(sec.section_number || '').trim()} ${(sec.title || '').trim()}`.trim());

      const prevSecNum = idx > 0 ? (sections[idx - 1]?.section_number || `${idx}`) : null;
      const prevChunkId = prevSecNum ? `${cleanDocId}:sec_${prevSecNum.replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || idx}` : null;
      
      const nextSecNum = idx < (sections.length - 1) ? (sections[idx + 1]?.section_number || `${idx + 2}`) : null;
      const nextChunkId = nextSecNum ? `${cleanDocId}:sec_${nextSecNum.replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || idx + 2}` : null;

      const embText = `Document: ${(title || '').trim()}\n${sec.subpart ? `Subpart: ${sec.subpart}\n` : ''}${sec.subject_group ? `Subject Group: ${sec.subject_group}\n` : ''}Section: ${sec.section_number || ''} - ${sec.title || ''}\n\n${sec.text || ''}`;

      return {
        chunk_id: chunkId,
        section_number: sec.section_number || `${idx + 1}`,
        section_title: sec.title || 'Untitled Section',
        section_path: path,
        previous_chunk_id: prevChunkId,
        next_chunk_id: nextChunkId,
        embedding_text: embText,
        word_count: (sec.text || '').split(/\s+/).filter(Boolean).length
      };
    });
  }, [title, docId, sections]);

  // Validation
  const validationErrors = useMemo(() => {
    const errors: string[] = [];
    if (!(title || '').trim() || (title || '').trim().length < 3) {
      errors.push('Document title must be at least 3 characters.');
    }
    if (!sections || sections.length === 0) {
      errors.push('Document must have at least one section.');
    }
    (sections || []).forEach((s, idx) => {
      if (!(s.section_number || '').trim()) {
        errors.push(`Section #${idx + 1} is missing a section number (e.g. '1.1').`);
      }
      if (!(s.title || '').trim()) {
        errors.push(`Section #${idx + 1} is missing a section title.`);
      }
      if (!(s.text || '').trim()) {
        errors.push(`Section #${idx + 1} has empty clause text.`);
      }
    });
    return errors;
  }, [title, sections]);

  // Publish handler
  const handlePublish = async () => {
    if (validationErrors.length > 0) {
      alert(`Please resolve validation errors before publishing:\n\n• ${validationErrors.join('\n• ')}`);
      return;
    }

    setIsPublishing(true);
    setPublishError(null);
    setPublishResult(null);

    const payload: ManualDocumentRequest = {
      title: title.trim(),
      document_id: docId.trim() || undefined,
      source: source.trim() || 'Manual',
      date: date.trim() || new Date().toISOString().slice(0, 10),
      language: language.trim() || 'eng',
      stakeholder: stakeholder.trim() || 'general',
      description: description.trim() || undefined,
      sections: sections.map(s => ({
        section_number: s.section_number.trim(),
        title: s.title.trim(),
        subpart: s.subpart?.trim() || undefined,
        subject_group: s.subject_group?.trim() || undefined,
        text: s.text.trim()
      }))
    };

    try {
      const res = await createManualDocument(payload, settings);
      setPublishResult(res);
      setDocId(res.document_id);
    } catch (err: any) {
      console.error('Error publishing manual document:', err);
      setPublishError(err.message || 'Failed to publish document');
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="flex flex-col flex-1 w-full min-h-[500px] h-[calc(100vh-61px)] bg-slate-950 overflow-y-auto">
      {/* Top Header & Preset Starter Bar */}
      <div className="p-6 bg-slate-900/60 border-b border-slate-800/80 shrink-0">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-teal-950/80 border border-teal-800/80 text-teal-400">
                <FilePlus2 className="w-5 h-5" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-white tracking-tight">
                    Regulatory Document Builder
                  </h1>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-teal-950 text-teal-300 border border-teal-800/80 font-semibold">
                    MANUAL INGESTION
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Build and index custom policy manuals, SOPs, or standards enforcing standard EASA / FAA chunking &amp; SQLite FTS5 search.
                </p>
              </div>
            </div>
          </div>

          {/* Quick Preset Selector */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-400 font-medium">Starter Template:</span>
            {PRESET_TEMPLATES.map(p => (
              <button
                key={p.id}
                onClick={() => handleLoadPreset(p.id)}
                className="px-2.5 py-1 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition-colors"
                title={p.description}
              >
                {p.name.split('(')[0].trim()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="p-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-6">
        {/* Success Banner */}
        {publishResult && (
          <div className="p-5 rounded-2xl bg-teal-950/40 border border-teal-600/60 text-teal-100 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-lg animate-in fade-in duration-200">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-teal-900/60 border border-teal-500/60 text-teal-300 shrink-0">
                <CheckCircle2 className="w-6 h-6 text-teal-400" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">
                  Document Published &amp; Fully Indexed!
                </h3>
                <p className="text-xs text-teal-200/90 mt-0.5">
                  "{publishResult.title}" has been structured into {publishResult.chunk_count} discrete chunks and is immediately queryable across SQLite FTS5 and dedicated workspaces.
                </p>
                <div className="text-[11px] font-mono text-teal-400/80 mt-1">
                  Document ID: {publishResult.document_id}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap shrink-0">
              <button
                onClick={() => onViewDoc({
                  chunk_id: `${publishResult.document_id}:sec_1_1`,
                  score: 1.0,
                  source: 'Manual Document',
                  document_id: publishResult.document_id,
                  path: [publishResult.title],
                  text: sections[0]?.text || '',
                  metadata: { title: publishResult.title, document_id: publishResult.document_id, origin: 'manual' },
                  markdown_doc: `# ${publishResult.title}\n\n${sections.map(s => `## ${s.section_number} ${s.title}\n\n${s.text}`).join('\n\n---\n\n')}`
                })}
                className="px-3 py-1.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
              >
                <Eye className="w-3.5 h-3.5" />
                <span>View Full Document</span>
              </button>

              <button
                onClick={() => onOpenWorkspaceWithDocs([publishResult.document_id])}
                className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-850 text-slate-200 border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors"
              >
                <Split className="w-3.5 h-3.5 text-sky-400" />
                <span>Open in Workspace</span>
              </button>
            </div>
          </div>
        )}

        {/* Error Banner */}
        {publishError && (
          <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            <div>
              <span className="font-semibold">Publication Error:</span> {publishError}
            </div>
          </div>
        )}

        {/* Navigation Tabs (Editor vs Live Chunking Simulation) */}
        <div className="flex items-center justify-between gap-4 border-b border-slate-800 pb-3">
          <div className="flex items-center p-1 bg-slate-900 border border-slate-800 rounded-xl text-xs font-medium">
            <button
              onClick={() => setActiveTab('editor')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                activeTab === 'editor'
                  ? 'bg-teal-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Document &amp; Sections Editor ({sections.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('preview')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                activeTab === 'preview'
                  ? 'bg-teal-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Live Chunking &amp; Hierarchy Simulation ({simulatedChunks.length})</span>
            </button>
          </div>

          {/* Publish Action Button */}
          <div className="flex items-center gap-2">
            {validationErrors.length > 0 && (
              <span className="text-xs text-amber-400 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>{validationErrors.length} validation item{validationErrors.length > 1 ? 's' : ''}</span>
              </span>
            )}

            <button
              onClick={handlePublish}
              disabled={isPublishing || validationErrors.length > 0}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:hover:bg-teal-600 text-white font-semibold text-xs shadow-md transition-all"
            >
              {isPublishing ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <ShieldCheck className="w-4 h-4" />
              )}
              <span>{isPublishing ? 'Publishing & Indexing...' : 'Publish & Index Document'}</span>
            </button>
          </div>
        </div>

        {/* TAB 1: DOCUMENT & SECTION EDITOR */}
        {activeTab === 'editor' && (
          <div className="space-y-6">
            {/* Document-level Metadata Card */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4">
              <h2 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-teal-400" />
                <span>Document Header &amp; Metadata</span>
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Title */}
                <div className="md:col-span-2 space-y-1">
                  <label className="text-xs font-medium text-slate-300">
                    Document Title <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g., Easy Access Rules for Ground Operations or Operator OM Part A"
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none transition-colors"
                  />
                </div>

                {/* Custom Document ID */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-300">
                    Document Identifier <span className="text-slate-500 font-normal">(Optional, Auto-generated)</span>
                  </label>
                  <input
                    type="text"
                    value={docId}
                    onChange={(e) => setDocId(e.target.value)}
                    placeholder="e.g., MANUAL_OPS_PART_A"
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none transition-colors"
                  />
                </div>

                {/* Issuing Source */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-300">
                    Source / Issuing Authority
                  </label>
                  <input
                    type="text"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    placeholder="e.g., Corporate Flight Operations, FAA, ICAO"
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none transition-colors"
                  />
                </div>

                {/* Effective Date */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-300">
                    Effective Publication Date
                  </label>
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs text-white focus:outline-none transition-colors"
                  />
                </div>

                {/* Stakeholder Domain */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-300">
                    Primary Stakeholder Domain
                  </label>
                  <select
                    value={stakeholder}
                    onChange={(e) => setStakeholder(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs text-white focus:outline-none transition-colors"
                  >
                    <option value="airline">Airlines &amp; Air Operators</option>
                    <option value="flight_crew">Flight Crew &amp; Pilots</option>
                    <option value="ansp">ANSPs &amp; Air Traffic Management</option>
                    <option value="airport">Aerodromes &amp; Ground Handling</option>
                    <option value="maintenance">Continuing Airworthiness &amp; Part-145</option>
                    <option value="economics">Economic Regulations &amp; Charges</option>
                    <option value="general">General Aviation &amp; Cross-domain</option>
                  </select>
                </div>
              </div>

              {/* Description / Preface */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-300">
                  Scope &amp; Executive Summary <span className="text-slate-500 font-normal">(Optional)</span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Outline the operational scope, regulatory applicability, and mandatory baseline of this document..."
                  rows={2}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none transition-colors"
                />
              </div>
            </div>

            {/* Sections Accordion Header */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <span>Structured Document Sections</span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-teal-950 text-teal-300 border border-teal-800">
                    {sections.length} Clauses
                  </span>
                </h2>
                <p className="text-xs text-slate-400">
                  Each section represents a distinct regulatory clause and chunk unit with full breadcrumb context.
                </p>
              </div>

              <button
                onClick={handleAddSection}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-xs font-semibold transition-colors shadow-sm"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Section</span>
              </button>
            </div>

            {/* Sections List */}
            <div className="space-y-3">
              {(sections || []).map((sec, idx) => {
                const isExpanded = expandedSectionIdx === idx;
                const wordCount = (sec.text || '').split(/\s+/).filter(Boolean).length;

                return (
                  <div
                    key={idx}
                    className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden transition-all shadow-sm"
                  >
                    {/* Section Accordion Title Bar */}
                    <div
                      onClick={() => setExpandedSectionIdx(isExpanded ? null : idx)}
                      className="p-4 flex items-center justify-between gap-3 bg-slate-900/90 hover:bg-slate-850 cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="flex items-center gap-1 text-slate-500">
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); handleMoveSection(idx, 'up'); }}
                            disabled={idx === 0}
                            className="p-1 hover:text-white disabled:opacity-30 rounded hover:bg-slate-800"
                            title="Move section up"
                          >
                            <ArrowUp className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); handleMoveSection(idx, 'down'); }}
                            disabled={idx === sections.length - 1}
                            className="p-1 hover:text-white disabled:opacity-30 rounded hover:bg-slate-800"
                            title="Move section down"
                          >
                            <ArrowDown className="w-3 h-3" />
                          </button>
                        </div>

                        <span className="font-mono text-xs font-bold text-teal-400 bg-teal-950/80 border border-teal-800/80 px-2 py-0.5 rounded-md shrink-0">
                          {sec.section_number || `Sec ${idx + 1}`}
                        </span>

                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold text-slate-100 truncate">
                            {sec.title || 'Untitled Section'}
                          </div>
                          {sec.subpart && (
                            <div className="text-[10px] text-slate-500 truncate">
                              {sec.subpart} {sec.subject_group ? `› ${sec.subject_group}` : ''}
                            </div>
                          )}
                        </div>

                        <span className="text-[11px] font-mono text-slate-500 shrink-0">
                          {wordCount} words
                        </span>
                      </div>

                      <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => handleDeleteSection(idx)}
                          className="p-1.5 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
                          title="Delete section"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>

                        <button
                          type="button"
                          onClick={() => setExpandedSectionIdx(isExpanded ? null : idx)}
                          className="p-1 text-slate-400 hover:text-white"
                        >
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>

                    {/* Section Body (Expanded) */}
                    {isExpanded && (
                      <div className="p-5 border-t border-slate-800 bg-slate-950/50 space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                          {/* Section Number */}
                          <div className="space-y-1">
                            <label className="text-[11px] font-medium text-slate-400">
                              Section / Point Number <span className="text-rose-400">*</span>
                            </label>
                            <input
                              type="text"
                              value={sec.section_number}
                              onChange={(e) => handleUpdateSection(idx, 'section_number', e.target.value)}
                              placeholder="e.g., 1.1 or 21.A.1"
                              className="w-full px-3 py-1.5 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-lg text-xs font-mono text-white focus:outline-none"
                            />
                          </div>

                          {/* Section Title */}
                          <div className="sm:col-span-1 lg:col-span-3 space-y-1">
                            <label className="text-[11px] font-medium text-slate-400">
                              Section Title <span className="text-rose-400">*</span>
                            </label>
                            <input
                              type="text"
                              value={sec.title}
                              onChange={(e) => handleUpdateSection(idx, 'title', e.target.value)}
                              placeholder="e.g., Standard Operating Procedures & Pre-flight Action"
                              className="w-full px-3 py-1.5 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-lg text-xs text-white focus:outline-none"
                            />
                          </div>

                          {/* Subpart */}
                          <div className="sm:col-span-1 lg:col-span-2 space-y-1">
                            <label className="text-[11px] font-medium text-slate-400">
                              Subpart Heading <span className="text-slate-500">(Optional)</span>
                            </label>
                            <input
                              type="text"
                              value={sec.subpart || ''}
                              onChange={(e) => handleUpdateSection(idx, 'subpart', e.target.value)}
                              placeholder="e.g., Subpart A — General Requirements"
                              className="w-full px-3 py-1.5 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-lg text-xs text-slate-300 focus:outline-none"
                            />
                          </div>

                          {/* Subject Group */}
                          <div className="sm:col-span-1 lg:col-span-2 space-y-1">
                            <label className="text-[11px] font-medium text-slate-400">
                              Subject Group / Topic <span className="text-slate-500">(Optional)</span>
                            </label>
                            <input
                              type="text"
                              value={sec.subject_group || ''}
                              onChange={(e) => handleUpdateSection(idx, 'subject_group', e.target.value)}
                              placeholder="e.g., FLIGHT DISPATCH & FUEL PLANNING"
                              className="w-full px-3 py-1.5 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-lg text-xs text-slate-300 focus:outline-none"
                            />
                          </div>
                        </div>

                        {/* Helper Formatting Snippets Toolbar */}
                        <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-800/80 flex-wrap">
                          <span className="text-[11px] text-slate-400 flex items-center gap-1">
                            <Scale className="w-3 h-3 text-emerald-400" /> Insert Template Clause:
                          </span>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <button
                              type="button"
                              onClick={() => handleInsertSnippet(idx, '(a) The operator shall ensure that...')}
                              className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800 hover:bg-emerald-900"
                            >
                              + SHALL Mandate
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInsertSnippet(idx, '(b) It is prohibited to operate...')}
                              className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-950 text-rose-300 border border-rose-800 hover:bg-rose-900"
                            >
                              + PROHIBITED
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInsertSnippet(idx, '(c) The organization should consider...') }
                              className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-950 text-amber-300 border border-amber-800 hover:bg-amber-900"
                            >
                              + SHOULD Recommendation
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInsertSnippet(idx, '| Parameter | Required Standard | Tolerance |\n| :--- | :--- | :--- |\n| Altitude | 10,000 ft | ± 100 ft |\n| Airspeed | 250 KIAS | ± 10 KIAS |') }
                              className="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-950 text-sky-300 border border-sky-800 hover:bg-sky-900 flex items-center gap-1"
                            >
                              <Table className="w-2.5 h-2.5" />
                              <span>+ Markdown Table</span>
                            </button>
                          </div>
                        </div>

                        {/* Clause Body Text */}
                        <div className="space-y-1">
                          <label className="text-[11px] font-medium text-slate-300">
                            Clause Text &amp; Provisions <span className="text-rose-400">*</span>
                          </label>
                          <textarea
                            value={sec.text}
                            onChange={(e) => handleUpdateSection(idx, 'text', e.target.value)}
                            placeholder="Enter the full regulatory clause text, numbered points (a), (b), (c), or markdown tables..."
                            rows={8}
                            className="w-full p-3 bg-slate-950 border border-slate-800 focus:border-teal-500 rounded-xl text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none leading-relaxed"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Bottom Add Section Button */}
            <div className="pt-2 flex justify-center">
              <button
                onClick={handleAddSection}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 text-slate-200 text-xs font-semibold transition-all shadow-sm"
              >
                <Plus className="w-4 h-4 text-teal-400" />
                <span>Add Another Regulatory Provision</span>
              </button>
            </div>
          </div>
        )}

        {/* TAB 2: LIVE CHUNKING & HIERARCHY SIMULATION */}
        {activeTab === 'preview' && (
          <div className="space-y-6">
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Layers className="w-4 h-4 text-teal-400" />
                    <span>Live Ingestion &amp; Chunk Segmentation Simulation</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Demonstrating how your document will be segmented into sequential chunks with breadcrumbs and linked previous/next chunk IDs.
                  </p>
                </div>
                <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-teal-950 text-teal-300 border border-teal-800">
                  {simulatedChunks.length} Chunks Generated
                </span>
              </div>
            </div>

            {/* Simulated Chunks Stream */}
            <div className="space-y-4">
              {simulatedChunks.map((chunk, idx) => (
                <div
                  key={chunk.chunk_id}
                  className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3 shadow-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800/80">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded font-bold bg-teal-950 text-teal-300 border border-teal-800">
                        CHUNK #{idx + 1}
                      </span>
                      <span className="font-mono text-xs text-teal-400 font-semibold">
                        {chunk.chunk_id}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] font-mono text-slate-500">
                      <span>Prev: {chunk.previous_chunk_id ? chunk.previous_chunk_id.split(':').pop() : 'None (Start)'}</span>
                      <span>·</span>
                      <span>Next: {chunk.next_chunk_id ? chunk.next_chunk_id.split(':').pop() : 'None (End)'}</span>
                    </div>
                  </div>

                  {/* Breadcrumb Hierarchy */}
                  <div className="text-xs text-sky-400 font-medium bg-slate-950/70 p-2 rounded-lg border border-slate-800/60 overflow-x-auto whitespace-nowrap">
                    {chunk.section_path.join('  ›  ')}
                  </div>

                  {/* Section Title */}
                  <h4 className="text-sm font-bold text-white">
                    {chunk.section_number} {chunk.section_title}
                  </h4>

                  {/* Embedding representation preview */}
                  <div className="space-y-1">
                    <div className="text-[10px] uppercase font-mono text-slate-500">
                      Embedded &amp; Indexed Representation:
                    </div>
                    <pre className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed max-h-56 overflow-y-auto">
                      {chunk.embedding_text}
                    </pre>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
