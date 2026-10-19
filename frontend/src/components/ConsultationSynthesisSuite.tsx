/**
 * ConsultationSynthesisSuite.tsx - Comprehensive Multi-Level Synthesis Suite
 * 
 * Provides structured, objective synthesis of stakeholder comments and concerns
 * vs the consulted document text:
 * 1. General Assessment of Stakeholder Sentiment Overall & Macro Consultation Dynamics
 * 2. Per Stakeholder Type Synthesis vs Consulted Text
 * 3. Per Category / Thematic Synthesis vs Consulted Text
 * 4. Per Consulted Section Synthesis
 * 5. Per Comment vs Consulted Text Comparative Matrix
 * 6. Live AI Deep Narrative Synthesis (Local LLM or Gemini)
 */

import React, { useState, useMemo } from 'react';
import {
  Users,
  MessageSquare,
  FileText,
  AlertTriangle,
  HelpCircle,
  ThumbsUp,
  Sparkles,
  RefreshCw,
  ArrowRight,
  Shield,
  Layers,
  Building,
  Plane,
  X,
  ExternalLink,
  Scale,
  GitCompare,
  TrendingUp,
  Download,
  Search,
  Check,
  Copy,
  BookOpen,
  Sliders,
  Filter,
  Compass
} from 'lucide-react';
import {
  ConsultationSession,
  ConsultationSynthesisBundle,
  DeepSynthesisResult,
  generateDeepSynthesis,
  getExportSynthesisReportUrl
} from '../services/consultationService';

interface ConsultationSynthesisSuiteProps {
  session: ConsultationSession;
  synthesisBundle: ConsultationSynthesisBundle | null;
  loading: boolean;
  onRefreshSynthesis: () => void;
  onSelectCommentForTriage?: (commentId: string) => void;
}

export const ConsultationSynthesisSuite: React.FC<ConsultationSynthesisSuiteProps> = ({
  session,
  synthesisBundle,
  loading,
  onRefreshSynthesis,
  onSelectCommentForTriage
}) => {
  // Active synthesis sub-tab
  const [activeTab, setActiveTab] = useState<'overall' | 'stakeholder_type' | 'category' | 'section' | 'comment'>('overall');

  // Selected item within each sub-tab
  const [selectedGroup, setSelectedGroup] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedSection, setSelectedSection] = useState<string>('');

  // Comment Matrix search & filters
  const [matrixSearch, setMatrixSearch] = useState<string>('');
  const [matrixFilterGroup, setMatrixFilterGroup] = useState<string>('all');
  const [matrixFilterSentiment, setMatrixFilterSentiment] = useState<string>('all');

  // AI Deep Synthesis Modal State
  const [isAiModalOpen, setIsAiModalOpen] = useState<boolean>(false);
  const [aiScope, setAiScope] = useState<'overall' | 'stakeholder_type' | 'category' | 'section' | 'comment'>('overall');
  const [aiTargetId, setAiTargetId] = useState<string | undefined>(undefined);
  const [aiTargetTitle, setAiTargetTitle] = useState<string>('General Consultation');
  const [aiProvider, setAiProvider] = useState<'local' | 'gemini'>('local');
  const [aiLoading, setAiLoading] = useState<boolean>(false);
  const [aiResult, setAiResult] = useState<DeepSynthesisResult | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  // Sync initial selection defaults
  React.useEffect(() => {
    if (synthesisBundle) {
      if (!selectedGroup && synthesisBundle.stakeholder_type_synthesis.length > 0) {
        setSelectedGroup(synthesisBundle.stakeholder_type_synthesis[0].stakeholder_group);
      }
      if (!selectedCategory && synthesisBundle.category_synthesis.length > 0) {
        setSelectedCategory(synthesisBundle.category_synthesis[0].category_name);
      }
      if (!selectedSection && synthesisBundle.section_synthesis.length > 0) {
        setSelectedSection(synthesisBundle.section_synthesis[0].section_title);
      }
    }
  }, [synthesisBundle, selectedGroup, selectedCategory, selectedSection]);

  // Open AI Modal Helper
  const handleOpenAiModal = (
    scope: 'overall' | 'stakeholder_type' | 'category' | 'section' | 'comment',
    targetId?: string,
    targetTitle?: string
  ) => {
    setAiScope(scope);
    setAiTargetId(targetId);
    setAiTargetTitle(targetTitle || (scope === 'overall' ? 'General Consultation Sentiment & Synthesis' : targetId || 'Target'));
    setAiResult(null);
    setIsAiModalOpen(true);
  };

  // Run AI Synthesis
  const handleExecuteAiSynthesis = async () => {
    try {
      setAiLoading(true);
      const res = await generateDeepSynthesis(session.consultation_id, aiScope, aiTargetId, aiProvider);
      setAiResult(res);
    } catch (err: any) {
      alert(`AI Synthesis failed: ${err.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const handleCopyText = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Helper for Sentiment Score Badges
  const renderSentimentScoreBadge = (score: number | null | undefined) => {
    if (score == null || typeof score !== 'number' || isNaN(score)) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-800 text-slate-400 border border-slate-700">
          N/A
        </span>
      );
    }
    if (score <= -0.4) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-rose-950/80 text-rose-300 border border-rose-800">
          <AlertTriangle className="w-3 h-3 text-rose-400" />
          {score.toFixed(2)} Strongly Critical
        </span>
      );
    }
    if (score < 0.1) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-amber-950/80 text-amber-300 border border-amber-800">
          <AlertTriangle className="w-3 h-3 text-amber-400" />
          {score.toFixed(2)} Concerned
        </span>
      );
    }
    if (score < 0.4) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-sky-950/80 text-sky-300 border border-sky-800">
          <HelpCircle className="w-3 h-3 text-sky-400" />
          {score > 0 ? `+${score.toFixed(2)}` : score.toFixed(2)} Neutral / Qualified
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
        <ThumbsUp className="w-3 h-3 text-emerald-400" />
        +{score.toFixed(2)} Supportive
      </span>
    );
  };

  // Current active data slices
  const currentStakeholderSynth = useMemo(() => {
    if (!synthesisBundle) return null;
    return synthesisBundle.stakeholder_type_synthesis.find(s => s.stakeholder_group === selectedGroup) || synthesisBundle.stakeholder_type_synthesis[0] || null;
  }, [synthesisBundle, selectedGroup]);

  const currentCategorySynth = useMemo(() => {
    if (!synthesisBundle) return null;
    return synthesisBundle.category_synthesis.find(c => c.category_name === selectedCategory) || synthesisBundle.category_synthesis[0] || null;
  }, [synthesisBundle, selectedCategory]);

  const currentSectionSynth = useMemo(() => {
    if (!synthesisBundle) return null;
    return synthesisBundle.section_synthesis.find(s => s.section_title === selectedSection) || synthesisBundle.section_synthesis[0] || null;
  }, [synthesisBundle, selectedSection]);

  const filteredCommentSynthesis = useMemo(() => {
    if (!synthesisBundle) return [];
    return synthesisBundle.comment_synthesis.filter(c => {
      if (matrixSearch.trim()) {
        const term = matrixSearch.toLowerCase();
        const match =
          c.comment_id.toLowerCase().includes(term) ||
          c.stakeholder_name.toLowerCase().includes(term) ||
          c.target_section.toLowerCase().includes(term) ||
          c.comment_text.toLowerCase().includes(term) ||
          c.stakeholder_concern.toLowerCase().includes(term);
        if (!match) return false;
      }
      if (matrixFilterGroup !== 'all' && c.stakeholder_group !== matrixFilterGroup) return false;
      if (matrixFilterSentiment !== 'all' && c.sentiment !== matrixFilterSentiment) return false;
      return true;
    });
  }, [synthesisBundle, matrixSearch, matrixFilterGroup, matrixFilterSentiment]);

  if (loading && !synthesisBundle) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-400 space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
        <p className="text-sm font-medium">Computing multi-level consultation synthesis...</p>
        <p className="text-xs text-slate-500">Cross-referencing stakeholder concerns with consulted document provisions.</p>
      </div>
    );
  }

  if (!synthesisBundle) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-400 space-y-3">
        <AlertTriangle className="w-8 h-8 text-amber-400" />
        <p className="text-sm font-medium">Synthesis data unavailable for this session.</p>
        <button
          onClick={onRefreshSynthesis}
          className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold"
        >
          Generate Synthesis
        </button>
      </div>
    );
  }

  const overall = synthesisBundle.overall_assessment;

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-950 font-sans">
      {/* 1. Synthesis Sub-Navigation Strip */}
      <nav className="px-6 py-2.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between gap-3 shrink-0 backdrop-blur z-10">
        <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5">
          <button
            onClick={() => setActiveTab('overall')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === 'overall'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Scale className="w-3.5 h-3.5" />
            <span>General Sentiment & Macro</span>
          </button>

          <button
            onClick={() => setActiveTab('stakeholder_type')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === 'stakeholder_type'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Per Stakeholder Type</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300">
              {synthesisBundle.stakeholder_type_synthesis.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('category')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === 'category'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Per Category / Theme</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300">
              {synthesisBundle.category_synthesis.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('section')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === 'section'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Per Consulted Section</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300">
              {synthesisBundle.section_synthesis.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('comment')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === 'comment'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <GitCompare className="w-3.5 h-3.5" />
            <span>Per Comment Matrix</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300">
              {synthesisBundle.comment_synthesis.length}
            </span>
          </button>
        </div>

        {/* Global Action Tools */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => handleOpenAiModal(
              activeTab === 'comment' ? 'overall' : activeTab,
              activeTab === 'stakeholder_type' ? selectedGroup : activeTab === 'category' ? selectedCategory : activeTab === 'section' ? selectedSection : undefined,
              activeTab === 'stakeholder_type' ? `Stakeholder Sector: ${selectedGroup}` : activeTab === 'category' ? `Theme: ${selectedCategory}` : activeTab === 'section' ? `Section: ${selectedSection}` : 'Macro Consultation Assessment'
            )}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white shadow-sm transition-all"
            title="Generate AI narrative synthesis for this level"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Deep AI Synthesis</span>
          </button>

          <a
            href={getExportSynthesisReportUrl(session.consultation_id, 'markdown')}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
            title="Download full executive synthesis report in Markdown"
          >
            <Download className="w-3.5 h-3.5 text-slate-300" />
            <span>Export Report</span>
          </a>

          <button
            onClick={onRefreshSynthesis}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Recalculate synthesis metrics"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </nav>

      {/* 2. Main Content Panels */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* ============================================================== */}
        {/* SUB-TAB 1: GENERAL ASSESSMENT OF STAKEHOLDER SENTIMENT OVERALL */}
        {/* ============================================================== */}
        {activeTab === 'overall' && (
          <div className="space-y-6 max-w-7xl mx-auto">
            {/* Top Macro Banner */}
            <div className="p-6 bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 rounded-2xl shadow-lg relative overflow-hidden">
              <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-slate-800/80 pb-6">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                      MACRO CONSULTATION DELIBERATION
                    </span>
                    <span className="text-xs text-slate-400">
                      {session.domain}
                    </span>
                  </div>
                  <h2 className="text-xl font-bold text-white tracking-tight">
                    General Assessment of Stakeholder Sentiment Overall
                  </h2>
                  <p className="text-xs text-slate-400 mt-1 max-w-3xl">
                    Macro synthesis of {overall.total_comments} stakeholder comments submitted by {overall.total_stakeholders} distinct organizations vs draft provisions in '{session.title}'.
                  </p>
                </div>

                {/* Net Sentiment Metric Box */}
                <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl flex items-center gap-4 shrink-0">
                  <div className="text-right">
                    <div className="text-[11px] font-medium text-slate-400">Net Stakeholder Stance</div>
                    <div className="text-sm font-bold text-white mt-0.5 max-w-[200px] truncate" title={overall.overall_sentiment_label}>
                      {overall.overall_sentiment_label}
                    </div>
                  </div>
                  <div className="w-14 h-14 rounded-xl bg-slate-900 border border-slate-700/80 flex flex-col items-center justify-center font-mono font-bold">
                    <span className={`text-lg ${(overall.overall_sentiment_score ?? 0) <= -0.4 ? 'text-rose-400' : (overall.overall_sentiment_score ?? 0) < 0.1 ? 'text-amber-400' : 'text-emerald-400'}`}>
                      {overall.overall_sentiment_score != null && !isNaN(overall.overall_sentiment_score)
                        ? (overall.overall_sentiment_score > 0 ? `+${overall.overall_sentiment_score.toFixed(2)}` : overall.overall_sentiment_score.toFixed(2))
                        : '0.00'}
                    </span>
                    <span className="text-[9px] text-slate-500 uppercase">Score</span>
                  </div>
                </div>
              </div>

              {/* Sentiment Breakdown Bar & KPIs */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
                {/* Sentiment Distribution Card */}
                <div className="md:col-span-2 p-4 bg-slate-950/50 border border-slate-800/80 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between text-xs font-medium text-slate-300">
                    <span>Sentiment Breakdown (% of Submissions)</span>
                    <span className="text-slate-400 font-mono">{overall.total_comments} Total Comments</span>
                  </div>

                  {/* Multi-color Progress Bar */}
                  <div className="h-3 w-full rounded-full bg-slate-800 flex overflow-hidden">
                    <div
                      style={{ width: `${overall.sentiment_breakdown_pct['Strongly Critical'] || 0}%` }}
                      className="bg-rose-500 transition-all hover:opacity-90"
                      title={`Strongly Critical: ${overall.sentiment_breakdown_pct['Strongly Critical'] || 0}%`}
                    />
                    <div
                      style={{ width: `${overall.sentiment_breakdown_pct['Concerned'] || 0}%` }}
                      className="bg-amber-500 transition-all hover:opacity-90"
                      title={`Concerned: ${overall.sentiment_breakdown_pct['Concerned'] || 0}%`}
                    />
                    <div
                      style={{ width: `${overall.sentiment_breakdown_pct['Neutral / Inquiring'] || 0}%` }}
                      className="bg-sky-500 transition-all hover:opacity-90"
                      title={`Neutral / Inquiring: ${overall.sentiment_breakdown_pct['Neutral / Inquiring'] || 0}%`}
                    />
                    <div
                      style={{ width: `${overall.sentiment_breakdown_pct['Supportive'] || 0}%` }}
                      className="bg-emerald-500 transition-all hover:opacity-90"
                      title={`Supportive: ${overall.sentiment_breakdown_pct['Supportive'] || 0}%`}
                    />
                  </div>

                  <div className="grid grid-cols-4 gap-2 text-[11px] font-mono text-center pt-1">
                    <div className="p-1.5 rounded bg-rose-950/40 text-rose-300 border border-rose-900/50">
                      <strong>{overall.sentiment_breakdown_pct['Strongly Critical'] || 0}%</strong>
                      <span className="block text-[10px] text-slate-400 font-sans">Critical</span>
                    </div>
                    <div className="p-1.5 rounded bg-amber-950/40 text-amber-300 border border-amber-900/50">
                      <strong>{overall.sentiment_breakdown_pct['Concerned'] || 0}%</strong>
                      <span className="block text-[10px] text-slate-400 font-sans">Concerned</span>
                    </div>
                    <div className="p-1.5 rounded bg-sky-950/40 text-sky-300 border border-sky-900/50">
                      <strong>{overall.sentiment_breakdown_pct['Neutral / Inquiring'] || 0}%</strong>
                      <span className="block text-[10px] text-slate-400 font-sans">Neutral</span>
                    </div>
                    <div className="p-1.5 rounded bg-emerald-950/40 text-emerald-300 border border-emerald-900/50">
                      <strong>{overall.sentiment_breakdown_pct['Supportive'] || 0}%</strong>
                      <span className="block text-[10px] text-slate-400 font-sans">Supportive</span>
                    </div>
                  </div>
                </div>

                {/* KPI Card: Actionability Rate */}
                <div className="p-4 bg-slate-950/50 border border-slate-800/80 rounded-xl flex flex-col justify-between">
                  <div className="text-xs font-medium text-slate-400">Actionable Drafting Proposals</div>
                  <div className="my-2">
                    <span className="text-3xl font-extrabold text-teal-300 font-mono">
                      {overall.actionable_rate}%
                    </span>
                    <span className="text-xs text-slate-400 ml-2">concrete amendments</span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    High actionability indicates industry is constructive, offering specific legal draft revisions.
                  </p>
                </div>

                {/* KPI Card: Sector Coalitions */}
                <div className="p-4 bg-slate-950/50 border border-slate-800/80 rounded-xl flex flex-col justify-between">
                  <div className="text-xs font-medium text-slate-400">Sectors & Coalitions</div>
                  <div className="my-2">
                    <span className="text-3xl font-extrabold text-purple-300 font-mono">
                      {overall.stakeholder_coalition_dynamics.length}
                    </span>
                    <span className="text-xs text-slate-400 ml-2">active sectoral blocs</span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Airlines, Aerodromes, Pilot Unions, and Regulators cross-tabulated.
                  </p>
                </div>
              </div>
            </div>

            {/* Executive Synthesis Narrative */}
            <div className="p-6 bg-slate-900 border border-slate-800 rounded-2xl space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-bold text-white">
                    Executive Synthesis & Core Regulatory Tension
                  </h3>
                </div>
                <button
                  onClick={() => handleOpenAiModal('overall', undefined, 'Macro Consultation Assessment')}
                  className="text-xs text-cyan-400 hover:underline flex items-center gap-1"
                >
                  <Sparkles className="w-3 h-3" />
                  Request LLM Analytical Narrative
                </button>
              </div>

              <div className="text-xs text-slate-200 leading-relaxed whitespace-pre-line bg-slate-950 p-4 rounded-xl border border-slate-800/80 font-sans">
                {overall.executive_summary}
              </div>
            </div>

            {/* 3-Column Split: Friction Zones | Consensus Areas | Coalition Dynamics */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

              {/* Column 1: Top Regulatory Friction Zones */}
              <div className="p-5 bg-slate-900 border border-rose-950/50 rounded-2xl space-y-4">
                <div className="flex items-center gap-2 text-rose-400 font-bold text-xs uppercase tracking-wider border-b border-slate-800 pb-2">
                  <AlertTriangle className="w-4 h-4" />
                  <span>Top Regulatory Friction Zones</span>
                </div>

                <div className="space-y-3">
                  {overall.top_friction_zones.map((fz, idx) => (
                    <div key={idx} className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-white">{fz.topic}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-950 text-rose-300 border border-rose-800 shrink-0">
                          {fz.affected_articles}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-300 leading-relaxed">
                        {fz.core_issue}
                      </p>
                      <div className="pt-1.5 border-t border-slate-900 flex flex-wrap gap-1">
                        {fz.contesting_groups.map(g => (
                          <span key={g} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 font-mono">
                            {g}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Column 2: Areas of Broad Consensus */}
              <div className="p-5 bg-slate-900 border border-emerald-950/50 rounded-2xl space-y-4">
                <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs uppercase tracking-wider border-b border-slate-800 pb-2">
                  <Check className="w-4 h-4" />
                  <span>Areas of Broad Consensus</span>
                </div>

                <div className="space-y-3">
                  {overall.areas_of_broad_consensus.map((c, idx) => (
                    <div key={idx} className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl flex items-start gap-2.5">
                      <div className="w-5 h-5 rounded-full bg-emerald-950 border border-emerald-800 flex items-center justify-center text-emerald-400 shrink-0 mt-0.5">
                        <Check className="w-3 h-3" />
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {c}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Column 3: Stakeholder Coalition Dynamics */}
              <div className="p-5 bg-slate-900 border border-purple-950/50 rounded-2xl space-y-4">
                <div className="flex items-center gap-2 text-purple-400 font-bold text-xs uppercase tracking-wider border-b border-slate-800 pb-2">
                  <Users className="w-4 h-4" />
                  <span>Stakeholder Coalition Dynamics</span>
                </div>

                <div className="space-y-3">
                  {overall.stakeholder_coalition_dynamics.map((co, idx) => (
                    <div key={idx} className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
                      <div className="text-xs font-bold text-purple-300">
                        {co.group}
                      </div>
                      <p className="text-[11px] text-slate-300 leading-relaxed">
                        <strong>Stance:</strong> {co.stance}
                      </p>
                      <div className="p-2 bg-slate-900 rounded text-[11px] text-amber-300/90 border border-slate-800">
                        <strong className="text-amber-400">Inter-sector Friction: </strong>
                        {co.friction_with}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

            </div>

            {/* Strategic Roadmap for Rulemaker */}
            <div className="p-6 bg-slate-900 border border-cyan-900/50 rounded-2xl space-y-4">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-xs uppercase tracking-wider border-b border-slate-800 pb-2">
                <Compass className="w-4 h-4" />
                <span>Recommended Rulemaker Deliberation Roadmap</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {overall.rulemaker_action_roadmap.map((step, idx) => (
                  <div key={idx} className="p-4 bg-slate-950 border border-slate-800 rounded-xl flex items-start gap-3">
                    <div className="w-6 h-6 rounded-lg bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400 font-mono font-bold text-xs shrink-0 mt-0.5">
                      {idx + 1}
                    </div>
                    <p className="text-xs text-slate-200 leading-relaxed">
                      {step}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* SUB-TAB 2: PER STAKEHOLDER TYPE SYNTHESIS VS CONSULTED TEXT     */}
        {/* ============================================================== */}
        {activeTab === 'stakeholder_type' && (
          <div className="flex flex-col lg:flex-row gap-6 max-w-7xl mx-auto items-start">
            {/* Left Selector: Stakeholder Groups */}
            <div className="w-full lg:w-80 shrink-0 space-y-2">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider px-1 mb-2">
                Select Stakeholder Group ({synthesisBundle.stakeholder_type_synthesis.length})
              </div>

              {synthesisBundle.stakeholder_type_synthesis.map(st => {
                const isSelected = st.stakeholder_group === (currentStakeholderSynth?.stakeholder_group || '');
                return (
                  <div
                    key={st.stakeholder_group}
                    onClick={() => setSelectedGroup(st.stakeholder_group)}
                    className={`p-3.5 rounded-xl cursor-pointer transition-all border ${
                      isSelected
                        ? 'bg-slate-900 border-cyan-500 shadow-md ring-1 ring-cyan-500/50'
                        : 'bg-slate-900/40 border-slate-800 hover:bg-slate-900/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-bold text-white truncate" title={st.stakeholder_group}>
                        {st.stakeholder_group}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300 shrink-0">
                        {st.comment_count} comments
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 truncate max-w-[150px]">
                        {st.stakeholders.join(', ')}
                      </span>
                      {renderSentimentScoreBadge(st.average_sentiment_score)}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Right Main Pane: Stakeholder Group Synthesis Detail */}
            {currentStakeholderSynth && (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
                {/* Header Strip */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Building className="w-4 h-4 text-purple-400" />
                      <h2 className="text-lg font-bold text-white">
                        {currentStakeholderSynth.stakeholder_group}
                      </h2>
                    </div>
                    <div className="text-xs text-slate-400 flex flex-wrap items-center gap-2">
                      <span>Represented submitters: <strong className="text-slate-200">{currentStakeholderSynth.stakeholders.join(', ')}</strong></span>
                      <span>•</span>
                      <span>{currentStakeholderSynth.comment_count} total comments</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {renderSentimentScoreBadge(currentStakeholderSynth.average_sentiment_score)}
                    <button
                      onClick={() => handleOpenAiModal('stakeholder_type', currentStakeholderSynth.stakeholder_group, `Stakeholder Group: ${currentStakeholderSynth.stakeholder_group}`)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Deep AI Synthesis</span>
                    </button>
                  </div>
                </div>

                {/* Stance Narrative Card */}
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                  <div className="text-xs font-semibold text-slate-300">
                    Collective Sector Stance vs Consulted Text
                  </div>
                  <p className="text-xs text-slate-200 leading-relaxed">
                    {currentStakeholderSynth.collective_stance_summary}
                  </p>
                </div>

                {/* Primary Targets & Dominant Themes */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl">
                    <span className="text-[11px] font-semibold text-slate-400 block mb-2">Primary Consulted Sections Targeted:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {currentStakeholderSynth.primary_targeted_sections.map(sec => (
                        <span key={sec} className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/80">
                          {sec}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl">
                    <span className="text-[11px] font-semibold text-slate-400 block mb-2">Dominant Thematic Concerns:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {currentStakeholderSynth.dominant_themes.map(th => (
                        <span key={th} className="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-300">
                          {th}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Core Concerns vs Draft Text Table */}
                <div className="space-y-3">
                  <div className="text-xs font-bold text-white uppercase tracking-wider flex items-center justify-between">
                    <span>Core Concerns vs Draft Text ({currentStakeholderSynth.core_concerns_vs_consulted_text.length})</span>
                    <span className="text-[10px] text-slate-400 font-mono">Specific submissions</span>
                  </div>

                  <div className="divide-y divide-slate-800 border border-slate-800 rounded-xl overflow-hidden bg-slate-950">
                    {currentStakeholderSynth.core_concerns_vs_consulted_text.map((c, idx) => (
                      <div key={idx} className="p-4 space-y-2 hover:bg-slate-900/40 transition-colors">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-white">{c.stakeholder}</span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800">
                              Target: {c.target}
                            </span>
                          </div>
                          <span className={`text-[11px] font-medium ${c.stance.includes('Critical') ? 'text-rose-400' : c.stance.includes('Concerned') ? 'text-amber-400' : 'text-emerald-400'}`}>
                            {c.stance}
                          </span>
                        </div>

                        <p className="text-xs text-slate-300 leading-relaxed">
                          <strong>Concern: </strong>{c.concern}
                        </p>

                        {c.proposed_change && c.proposed_change !== 'No text proposed' && (
                          <div className="p-2.5 bg-teal-950/30 border border-teal-900/50 rounded-lg text-xs font-mono text-teal-200">
                            <strong className="text-teal-300">Requested Alternative: </strong>{c.proposed_change}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Cross-Sector Conflicts & Drafter Advice */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-950 border border-amber-950/60 rounded-xl space-y-1.5">
                    <div className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>Cross-Sector Alignment & Conflicts</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {currentStakeholderSynth.cross_sector_alignment_and_conflicts}
                    </p>
                  </div>

                  <div className="p-4 bg-slate-950 border border-indigo-950/60 rounded-xl space-y-1.5">
                    <div className="text-xs font-bold text-indigo-400 flex items-center gap-1.5">
                      <Shield className="w-3.5 h-3.5" />
                      <span>Rulemaker Deliberation Advice</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {currentStakeholderSynth.rulemaker_deliberation_advice}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================== */}
        {/* SUB-TAB 3: PER CATEGORY / THEMATIC SYNTHESIS VS CONSULTED TEXT */}
        {/* ============================================================== */}
        {activeTab === 'category' && (
          <div className="flex flex-col lg:flex-row gap-6 max-w-7xl mx-auto items-start">
            {/* Left Selector: Categories */}
            <div className="w-full lg:w-80 shrink-0 space-y-2">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider px-1 mb-2">
                Select Thematic Category ({synthesisBundle.category_synthesis.length})
              </div>

              {synthesisBundle.category_synthesis.map(cat => {
                const isSelected = cat.category_name === (currentCategorySynth?.category_name || '');
                return (
                  <div
                    key={cat.category_name}
                    onClick={() => setSelectedCategory(cat.category_name)}
                    className={`p-3.5 rounded-xl cursor-pointer transition-all border ${
                      isSelected
                        ? 'bg-slate-900 border-cyan-500 shadow-md ring-1 ring-cyan-500/50'
                        : 'bg-slate-900/40 border-slate-800 hover:bg-slate-900/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-bold text-white truncate" title={cat.category_name}>
                        {cat.category_name}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300 shrink-0">
                        {cat.comment_count} comments
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 truncate max-w-[150px]">
                        {cat.participating_groups.join(', ')}
                      </span>
                      {renderSentimentScoreBadge(cat.average_sentiment_score)}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Right Main Pane: Category Synthesis Detail */}
            {currentCategorySynth && (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Layers className="w-4 h-4 text-cyan-400" />
                      <h2 className="text-lg font-bold text-white">
                        {currentCategorySynth.category_name}
                      </h2>
                    </div>
                    <div className="text-xs text-slate-400 flex flex-wrap items-center gap-2">
                      <span>Implicated Articles: <strong className="text-cyan-300 font-mono">{currentCategorySynth.implicated_sections.join(', ')}</strong></span>
                      <span>•</span>
                      <span>Participating sectors: <strong className="text-slate-200">{currentCategorySynth.participating_groups.join(', ')}</strong></span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {renderSentimentScoreBadge(currentCategorySynth.average_sentiment_score)}
                    <button
                      onClick={() => handleOpenAiModal('category', currentCategorySynth.category_name, `Theme: ${currentCategorySynth.category_name}`)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Deep AI Synthesis</span>
                    </button>
                  </div>
                </div>

                {/* Conflict Summary vs Draft Text */}
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                  <div className="text-xs font-semibold text-slate-300">
                    Thematic Conflict Summary vs Consulted Draft Text
                  </div>
                  <p className="text-xs text-slate-200 leading-relaxed">
                    {currentCategorySynth.thematic_conflict_summary}
                  </p>
                </div>

                {/* Policy Trade-offs & Drafting Remedies */}
                <div className="p-4 bg-slate-950 border border-cyan-900/60 rounded-xl space-y-3">
                  <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                    <Scale className="w-4 h-4 text-cyan-400" />
                    <span>Policy Trade-offs & Drafting Remedies for the Rulemaker</span>
                  </div>

                  <div className="space-y-2">
                    {currentCategorySynth.policy_tradeoffs_and_remedies.map((rem, idx) => (
                      <div key={idx} className="flex items-start gap-2.5 text-xs text-slate-200 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                        <span className="w-5 h-5 rounded-full bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400 font-mono text-[10px] shrink-0">
                          {idx + 1}
                        </span>
                        <span className="leading-relaxed">{rem}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Stakeholder Positions Table */}
                <div className="space-y-3">
                  <div className="text-xs font-bold text-white uppercase tracking-wider">
                    Stakeholder Submissions on this Category ({currentCategorySynth.stakeholder_positions.length})
                  </div>

                  <div className="divide-y divide-slate-800 border border-slate-800 rounded-xl overflow-hidden bg-slate-950">
                    {currentCategorySynth.stakeholder_positions.map((pos, idx) => (
                      <div key={idx} className="p-4 space-y-2 hover:bg-slate-900/40 transition-colors">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-white">{pos.stakeholder}</span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 font-mono">{pos.group}</span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800">{pos.target_section}</span>
                          </div>
                          <span className={`text-[11px] font-medium ${pos.sentiment.includes('Critical') ? 'text-rose-400' : pos.sentiment.includes('Concerned') ? 'text-amber-400' : 'text-emerald-400'}`}>
                            {pos.sentiment}
                          </span>
                        </div>

                        <p className="text-xs text-slate-300 leading-relaxed">
                          <strong>Argument: </strong>{pos.argument}
                        </p>

                        {pos.proposal && pos.proposal !== 'No drafting text proposed' && (
                          <div className="p-2.5 bg-teal-950/30 border border-teal-900/50 rounded-lg text-xs font-mono text-teal-200">
                            <strong className="text-teal-300">Proposed Drafting: </strong>{pos.proposal}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================== */}
        {/* SUB-TAB 4: PER CONSULTED SECTION SYNTHESIS                     */}
        {/* ============================================================== */}
        {activeTab === 'section' && (
          <div className="flex flex-col lg:flex-row gap-6 max-w-7xl mx-auto items-start">
            {/* Left Selector: Consulted Sections */}
            <div className="w-full lg:w-80 shrink-0 space-y-2">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider px-1 mb-2">
                Consulted Document Sections ({synthesisBundle.section_synthesis.length})
              </div>

              {synthesisBundle.section_synthesis.map(sec => {
                const isSelected = sec.section_title === (currentSectionSynth?.section_title || '');
                return (
                  <div
                    key={sec.section_title}
                    onClick={() => setSelectedSection(sec.section_title)}
                    className={`p-3.5 rounded-xl cursor-pointer transition-all border ${
                      isSelected
                        ? 'bg-slate-900 border-cyan-500 shadow-md ring-1 ring-cyan-500/50'
                        : 'bg-slate-900/40 border-slate-800 hover:bg-slate-900/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-bold text-white truncate" title={sec.section_title}>
                        {sec.section_title}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300 shrink-0">
                        {sec.comment_count} comments
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 truncate max-w-[150px]">
                        {sec.commenting_groups.join(', ') || 'No feedback'}
                      </span>
                      {renderSentimentScoreBadge(sec.average_sentiment_score)}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Right Main Pane: Section Synthesis Detail */}
            {currentSectionSynth && (
              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <FileText className="w-4 h-4 text-cyan-400" />
                      <h2 className="text-lg font-bold text-white">
                        {currentSectionSynth.section_title}
                      </h2>
                    </div>
                    <div className="text-xs text-slate-400 flex flex-wrap items-center gap-2">
                      <span>Commenting Sectors: <strong className="text-slate-200">{currentSectionSynth.commenting_groups.join(', ') || 'None'}</strong></span>
                      <span>•</span>
                      <span>{currentSectionSynth.comment_count} total comments</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {renderSentimentScoreBadge(currentSectionSynth.average_sentiment_score)}
                    <button
                      onClick={() => handleOpenAiModal('section', currentSectionSynth.section_title, `Section: ${currentSectionSynth.section_title}`)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Deep AI Synthesis</span>
                    </button>
                  </div>
                </div>

                {/* Consulted Draft Legal Text Excerpt */}
                {currentSectionSynth.section_excerpt && (
                  <div className="p-4 bg-slate-950 border border-indigo-950/60 rounded-xl space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold text-indigo-300">
                      <span>Draft Legal Text Excerpt Under Consultation</span>
                      <button
                        onClick={() => handleCopyText(currentSectionSynth.section_excerpt)}
                        className="text-[11px] text-indigo-400 hover:text-indigo-200 flex items-center gap-1"
                      >
                        {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                        <span>Copy Draft Text</span>
                      </button>
                    </div>
                    <p className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto p-2 bg-slate-900/60 rounded border border-slate-800">
                      {currentSectionSynth.section_excerpt}
                    </p>
                  </div>
                )}

                {/* Synthesized Feedback Narrative */}
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
                  <div className="text-xs font-semibold text-slate-300">Synthesized Feedback Analysis vs Section Text</div>
                  <p className="text-xs text-slate-200 leading-relaxed">
                    {currentSectionSynth.synthesized_feedback_vs_text}
                  </p>
                </div>

                {/* Contentious vs Supported Provisions Split */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Contentious Provisions */}
                  <div className="p-4 bg-slate-950 border border-rose-950/60 rounded-xl space-y-2">
                    <div className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>Contentious Provisions & Objections ({currentSectionSynth.contentious_provisions.length})</span>
                    </div>
                    <div className="space-y-1.5">
                      {currentSectionSynth.contentious_provisions.length > 0 ? (
                        currentSectionSynth.contentious_provisions.map((cp, idx) => (
                          <div key={idx} className="p-2.5 rounded bg-rose-950/30 border border-rose-900/40 text-[11px] text-rose-200 leading-relaxed">
                            {cp}
                          </div>
                        ))
                      ) : (
                        <p className="text-[11px] text-slate-500 italic">No contentious provisions reported.</p>
                      )}
                    </div>
                  </div>

                  {/* Supported Provisions */}
                  <div className="p-4 bg-slate-950 border border-emerald-950/60 rounded-xl space-y-2">
                    <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                      <Check className="w-3.5 h-3.5" />
                      <span>Supported Provisions & Endorsements</span>
                    </div>
                    <div className="space-y-1.5">
                      {currentSectionSynth.supported_provisions.map((sp, idx) => (
                        <div key={idx} className="p-2.5 rounded bg-emerald-950/30 border border-emerald-900/40 text-[11px] text-emerald-200 leading-relaxed">
                          {sp}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Suggested Amendments from Industry */}
                {currentSectionSynth.suggested_amendments.length > 0 && (
                  <div className="space-y-3">
                    <div className="text-xs font-bold text-white uppercase tracking-wider">
                      Proposed Drafting Amendments from Stakeholders ({currentSectionSynth.suggested_amendments.length})
                    </div>

                    <div className="space-y-2.5">
                      {currentSectionSynth.suggested_amendments.map((am, idx) => (
                        <div key={idx} className="p-3.5 bg-slate-950 border border-teal-950/60 rounded-xl space-y-2">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-bold text-teal-300">{am.stakeholder}</span>
                            <span className="font-mono text-[10px] text-cyan-400">{am.target_clause}</span>
                          </div>
                          <div className="p-2.5 bg-teal-950/40 border border-teal-800/60 rounded-lg text-xs font-mono text-teal-100">
                            {am.proposed_text}
                          </div>
                          <p className="text-[11px] text-slate-400 italic">
                            <strong>Rationale: </strong>{am.rationale}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Deliberation Guidance */}
                <div className="p-4 bg-slate-950 border border-cyan-900/60 rounded-xl space-y-1.5">
                  <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                    <Compass className="w-3.5 h-3.5" />
                    <span>Rulemaker Deliberation Guidance for this Section</span>
                  </div>
                  <p className="text-xs text-slate-200 leading-relaxed">
                    {currentSectionSynth.deliberation_guidance}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================== */}
        {/* SUB-TAB 5: PER COMMENT VS CONSULTED TEXT COMPARATIVE MATRIX    */}
        {/* ============================================================== */}
        {activeTab === 'comment' && (
          <div className="space-y-6 max-w-7xl mx-auto">
            {/* Filter & Search Bar */}
            <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl flex flex-wrap items-center justify-between gap-3">
              <div className="relative flex-1 min-w-[280px] max-w-md">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter matrix by comment ID, submitter, provision, or concern..."
                  value={matrixSearch}
                  onChange={(e) => setMatrixSearch(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <select
                  value={matrixFilterGroup}
                  onChange={(e) => setMatrixFilterGroup(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
                >
                  <option value="all">All Sectors</option>
                  {synthesisBundle.stakeholder_type_synthesis.map(st => (
                    <option key={st.stakeholder_group} value={st.stakeholder_group}>{st.stakeholder_group}</option>
                  ))}
                </select>

                <select
                  value={matrixFilterSentiment}
                  onChange={(e) => setMatrixFilterSentiment(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
                >
                  <option value="all">All Regulatory Stances</option>
                  <option value="Strongly Critical">Strongly Critical</option>
                  <option value="Concerned">Concerned</option>
                  <option value="Neutral / Inquiring">Neutral / Inquiring</option>
                  <option value="Supportive">Supportive</option>
                </select>

                <span className="text-xs text-slate-400 font-mono ml-2">
                  Showing {filteredCommentSynthesis.length} of {synthesisBundle.comment_synthesis.length}
                </span>
              </div>
            </div>

            {/* Synthesis Cards Stream */}
            <div className="space-y-4">
              {filteredCommentSynthesis.map((c) => (
                <div key={c.comment_id} className="p-5 bg-slate-900 border border-slate-800 rounded-2xl space-y-4 shadow-sm hover:border-slate-700 transition-colors">
                  {/* Top Header */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-bold text-cyan-400">{c.comment_id}</span>
                      <span className="text-xs font-bold text-white">{c.stakeholder_name}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-mono">{c.stakeholder_group}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                        {c.target_section}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {renderSentimentScoreBadge(c.sentiment_score)}
                      <button
                        onClick={() => handleOpenAiModal('comment', c.comment_id, `Comment ${c.comment_id}: ${c.stakeholder_name}`)}
                        className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1 transition-colors"
                      >
                        <Sparkles className="w-3 h-3" />
                        <span>AI Synthesis</span>
                      </button>
                      {onSelectCommentForTriage && (
                        <button
                          onClick={() => onSelectCommentForTriage(c.comment_id)}
                          className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center gap-1 transition-colors"
                        >
                          <span>Deliberate</span>
                          <ArrowRight className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* 2-Column Comparative Layout: Draft Stipulation vs Stakeholder Concern */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* Left: Draft Legal Stipulation */}
                    <div className="p-3.5 bg-slate-950 border border-indigo-950/50 rounded-xl space-y-1.5">
                      <div className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                        <FileText className="w-3 h-3" />
                        <span>Consulted Draft Text Stipulation ({c.target_section})</span>
                      </div>
                      <p className="text-xs text-slate-300 font-mono leading-relaxed bg-slate-900/60 p-2.5 rounded border border-slate-800 max-h-36 overflow-y-auto">
                        {c.text_stipulation}
                      </p>
                    </div>

                    {/* Right: Stakeholder Submission & Proposed Alternative */}
                    <div className="p-3.5 bg-slate-950 border border-cyan-950/50 rounded-xl space-y-1.5">
                      <div className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                        <MessageSquare className="w-3 h-3" />
                        <span>Stakeholder Feedback & Proposed Alternative</span>
                      </div>
                      <p className="text-xs text-slate-200 leading-relaxed bg-slate-900/60 p-2.5 rounded border border-slate-800">
                        {c.comment_text}
                      </p>
                      {c.proposed_text && (
                        <div className="p-2 bg-teal-950/40 border border-teal-800/60 rounded text-[11px] font-mono text-teal-200">
                          <strong className="text-teal-300">Proposed: </strong>{c.proposed_text}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Divergence & Operational Impact */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs space-y-1">
                      <strong className="text-amber-400 block">Regulatory Divergence Analysis:</strong>
                      <p className="text-slate-300 text-[11px] leading-relaxed">
                        {c.divergence_analysis}
                      </p>
                    </div>

                    <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs space-y-1">
                      <strong className="text-purple-400 block">Operational & Safety Feasibility Impact:</strong>
                      <p className="text-slate-300 text-[11px] leading-relaxed">
                        {c.operational_and_safety_impact}
                      </p>
                    </div>
                  </div>

                  {/* Drafting Alternatives */}
                  <div className="p-3.5 bg-slate-950 border border-cyan-900/40 rounded-xl space-y-2">
                    <strong className="text-cyan-300 text-xs block">Actionable Drafting Alternatives for Counsel:</strong>
                    <div className="space-y-1.5">
                      {c.drafting_options.map((opt, oIdx) => (
                        <div key={oIdx} className="text-[11px] text-slate-300 flex items-start gap-2 bg-slate-900/50 p-2 rounded border border-slate-800/80">
                          <ArrowRight className="w-3 h-3 text-cyan-400 shrink-0 mt-0.5" />
                          <span>{opt}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}

              {filteredCommentSynthesis.length === 0 && (
                <div className="p-12 text-center text-slate-500 bg-slate-900/40 border border-slate-800 rounded-2xl">
                  <Search className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  <p className="text-xs">No comments match the search/filter criteria.</p>
                </div>
              )}
            </div>
          </div>
        )}

      </div>

      {/* 3. Deep AI Narrative Synthesis Modal */}
      {isAiModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-3xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">AI Deep Consultation Synthesis</h3>
                  <p className="text-[11px] text-slate-400">{aiTargetTitle}</p>
                </div>
              </div>
              <button
                onClick={() => setIsAiModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-4 flex-1 font-sans">
              {/* Controls bar */}
              <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-xs text-slate-300">
                  <span>Inference Provider:</span>
                  <select
                    value={aiProvider}
                    onChange={(e) => setAiProvider(e.target.value as any)}
                    className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-white focus:outline-none focus:border-cyan-500 cursor-pointer"
                  >
                    <option value="local">Local LLM (LM Studio - Gemma 3 / Qwen)</option>
                    <option value="gemini">Google Gemini Pro / Flash</option>
                  </select>
                </div>

                <button
                  onClick={handleExecuteAiSynthesis}
                  disabled={aiLoading}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm transition-colors disabled:opacity-50"
                >
                  {aiLoading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5" />
                  )}
                  <span>{aiResult ? 'Regenerate Analysis' : 'Run Synthesis'}</span>
                </button>
              </div>

              {/* Output Content */}
              {aiLoading ? (
                <div className="p-16 flex flex-col items-center justify-center text-slate-400 space-y-3">
                  <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
                  <p className="text-sm font-semibold text-white">Synthesizing stakeholder arguments vs consulted provisions...</p>
                  <p className="text-xs text-slate-500">Evaluating legal tensions, operational constraints, and drafting remedies.</p>
                </div>
              ) : aiResult ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800 pb-2">
                    <span className="font-semibold text-cyan-400">Target: {aiResult.target_summary}</span>
                    <button
                      onClick={() => handleCopyText(aiResult.synthesis_narrative)}
                      className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copied ? 'Copied' : 'Copy Synthesis'}</span>
                    </button>
                  </div>

                  <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 leading-relaxed font-sans whitespace-pre-wrap max-h-96 overflow-y-auto">
                    {aiResult.synthesis_narrative}
                  </div>
                </div>
              ) : (
                <div className="p-12 text-center text-slate-500 space-y-2">
                  <Scale className="w-10 h-10 mx-auto opacity-30 text-cyan-400" />
                  <p className="text-sm font-semibold text-slate-300">Ready to synthesize {aiTargetTitle}</p>
                  <p className="text-xs text-slate-500">
                    Click 'Run Synthesis' to generate an objective legal, operational, and stakeholder friction brief.
                  </p>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
              <span className="text-[11px] text-slate-500">
                Rulemaking decision-support system. Final policy resolution remains strictly with human authority.
              </span>
              <button
                onClick={() => setIsAiModalOpen(false)}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white transition-colors"
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
