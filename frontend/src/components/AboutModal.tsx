/**
 * AboutModal: Explains what AeroLex EU does, how it works, and its regulatory intelligence capabilities.
 * Features the official SESAR Deployment Manager branding.
 */

import React from 'react';
import { 
  X, 
  ShieldCheck, 
  Search, 
  Sparkles, 
  BookOpen, 
  Layers, 
  Users, 
  Cpu, 
  FileCheck, 
  CheckCircle2, 
  ExternalLink,
  Zap,
  Lock,
  Compass
} from 'lucide-react';
import sesarLogo from '../assets/sesar_logo.png';

interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AboutModal: React.FC<AboutModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        className="relative flex flex-col w-full max-w-2xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden transition-colors"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with SESAR Branding */}
        <div className="flex items-start justify-between p-6 border-b border-slate-800 bg-slate-900/90 shrink-0">
          <div className="flex items-center gap-4">
            <div className="p-2.5 bg-white rounded-xl shadow-md border border-slate-200/40 flex items-center justify-center shrink-0">
              <img 
                src={sesarLogo} 
                alt="SESAR Deployment Manager Logo" 
                className="h-10 sm:h-12 w-auto object-contain"
              />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-100 tracking-tight">AeroLex EU</h2>
                <span className="px-2 py-0.5 text-[10px] font-mono font-medium rounded-full bg-sky-950 text-sky-400 border border-sky-800/60">
                  v2.4
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Aviation Regulatory Intelligence & Consultation Synthesis Platform
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
            aria-label="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Modal Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-slate-300 text-xs leading-relaxed">
          
          {/* Executive Overview */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center gap-2 text-sky-400 font-semibold text-sm">
              <Compass className="w-4 h-4 shrink-0" />
              <span>What is AeroLex EU?</span>
            </div>
            <p className="text-slate-300">
              AeroLex EU is an enterprise-grade, offline-first regulatory intelligence and compliance workstation purpose-built for civil aviation authorities, airspace managers, flight operations compliance auditors, and SESAR deployment stakeholders.
            </p>
            <p className="text-slate-400">
              It transforms multi-thousand page regulatory corpuses and complex public consultation packages into an interactive, verifiable knowledge base with sub-millisecond search and total citation integrity.
            </p>
          </div>

          {/* How It Works */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-slate-200 font-semibold text-sm">
              <Zap className="w-4 h-4 text-amber-400 shrink-0" />
              <span>How It Works: Core Architecture</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Feature 1: Hybrid Retrieval */}
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Search className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                  <span>Hybrid Retrieval (BM25 + FAISS)</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Dual-track retrieval unites SQLite FTS5 BM25 with dense vector embeddings using Reciprocal Rank Fusion (RRF), ensuring exact acronyms and clause identifiers match alongside semantic intent.
                </p>
              </div>

              {/* Feature 2: Deep Research */}
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                  <span>Adversarial Deep Research</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  A multi-turn recursive reasoning engine that validates, cross-checks, and actively tests candidate clauses against counter-evidence before generating cited regulatory briefs.
                </p>
              </div>

              {/* Feature 3: Consultation Intelligence */}
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Users className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  <span>Consultation Stakeholder Synthesis</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Parses Excel, CSV, and Word stakeholder responses, mapping direction of travel, inter-stakeholder tension tradeoffs, and tacit acquiescence across clauses.
                </p>
              </div>

              {/* Feature 4: Normative Requirement Lens */}
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <FileCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  <span>Normative Requirement Lens</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Real-time modal verb parsing separates legal mandates (SHALL / MUST), prohibitions (SHALL NOT), recommendations (SHOULD), and advisory guidance (MAY / GM).
                </p>
              </div>

              {/* Feature 5: Sequential Context Expansion */}
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Layers className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                  <span>Surrounding Context Expansion</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Expands retrieved provisions with preceding and subsequent articles in regulatory order, preserving legal qualifiers, scopes, and exceptions.
                </p>
              </div>

              {/* Feature 6: Offline & Sovereign AI */}
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Lock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  <span>Air-Gapped & Sovereign Execution</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Operates 100% locally with LM Studio on your device for zero data leakage, or seamlessly scales with Google Gemini Cloud for high-throughput synthesis.
                </p>
              </div>
            </div>
          </div>

          {/* Supported Regulatory Frameworks */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-slate-200 font-semibold text-sm">
              <BookOpen className="w-4 h-4 text-teal-400 shrink-0" />
              <span>Supported Aviation Frameworks</span>
            </div>

            <div className="flex flex-wrap gap-2 text-[11px] font-mono">
              <span className="px-2.5 py-1 rounded-lg bg-sky-950/50 text-sky-300 border border-sky-800/50">
                EASA Easy Access Rules
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-indigo-950/50 text-indigo-300 border border-indigo-800/50">
                EU Formex Aviation Acts
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-emerald-950/50 text-emerald-300 border border-emerald-800/50">
                FAA Title 14 CFR
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-cyan-950/50 text-cyan-300 border border-cyan-800/50">
                SKYbrary Knowledge Base
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-amber-950/50 text-amber-300 border border-amber-800/50">
                Stakeholder Public Consultations
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-purple-950/50 text-purple-300 border border-purple-800/50">
                Custom Operations Manuals (SOPs)
              </span>
            </div>
          </div>

          {/* Commitment to Data Integrity */}
          <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 text-[11px] text-slate-400 space-y-1">
            <div className="font-semibold text-slate-300 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Traceability Guarantee</span>
            </div>
            <p>
              Every synthesis response, research finding, and consultation summary is anchored directly to its originating official clause ID, document title, and source standard.
            </p>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-900/90 shrink-0">
          <div className="text-[11px] text-slate-500 font-mono">
            SESAR Deployment Manager • Civil Aviation Modernization
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-white bg-sky-600 hover:bg-sky-500 rounded-lg transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
