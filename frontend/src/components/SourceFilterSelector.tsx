import React from 'react';
import { BookOpen, Check, X, CheckCheck, RefreshCw, Layers } from 'lucide-react';

export interface SourceOption {
  id: string;
  label: string;
  shortLabel?: string;
  badge?: string;
  description: string;
}

export const ALL_SOURCES: SourceOption[] = [
  { id: 'easa', label: 'EASA', shortLabel: 'EASA', badge: 'Rules & CS', description: 'EASA Easy Access Rules, Certification Specifications, AMC & GM' },
  { id: 'eu', label: 'EU (EUR-Lex)', shortLabel: 'EU', badge: 'Regulations', description: 'European Union Aviation Regulations, Directives & Decisions' },
  { id: 'faa', label: 'FAA', shortLabel: 'FAA', badge: '14 CFR', description: 'FAA Title 14 CFR Regulations and Advisory Circulars' },
  { id: 'icao', label: 'ICAO', shortLabel: 'ICAO', badge: 'Standards & SARPs', description: 'ICAO Chicago Convention, Annexes (1-19), Doc Manuals & PANS-ATM' },
  { id: 'skybrary', label: 'SKYbrary', shortLabel: 'SKYbrary', badge: 'Safety Library', description: 'SKYbrary Bookshelf, Safety Articles & Accident Reports' },
  { id: 'manual', label: 'Manuals', shortLabel: 'Manuals', badge: 'OEM / Ops', description: 'Internal Company Operations & Maintenance Manuals' },
  { id: 'note', label: 'Notes', shortLabel: 'Notes', badge: 'Engineering', description: 'Internal Engineering Project Notes & Meeting Journals' },
  { id: 'user', label: 'User Docs', shortLabel: 'User', badge: 'Uploads', description: 'Custom User Uploaded Aviation Documents' },
];

export const ALL_SOURCE_IDS = ALL_SOURCES.map(s => s.id);

interface SourceFilterSelectorProps {
  selectedSources: string[];
  onChange: (sources: string[]) => void;
  compact?: boolean;
  className?: string;
  label?: string;
}

export const SourceFilterSelector: React.FC<SourceFilterSelectorProps> = ({
  selectedSources,
  onChange,
  compact = false,
  className = '',
  label = 'Sources:'
}) => {
  const isAllSelected = ALL_SOURCES.every(s => selectedSources.includes(s.id));
  const selectedCount = selectedSources.length;
  const excludedCount = ALL_SOURCES.length - selectedCount;

  const handleToggleSource = (id: string) => {
    if (selectedSources.includes(id)) {
      // Trying to exclude this source
      const next = selectedSources.filter(s => s !== id);
      // Ensure at least one source remains selected
      if (next.length === 0) {
        return;
      }
      onChange(next);
    } else {
      // Include this source
      onChange([...selectedSources, id]);
    }
  };

  const handleSelectAll = () => {
    onChange([...ALL_SOURCE_IDS]);
  };

  const handleInvert = () => {
    const inverted = ALL_SOURCES.filter(s => !selectedSources.includes(s.id)).map(s => s.id);
    if (inverted.length > 0) {
      onChange(inverted);
    }
  };

  if (compact) {
    return (
      <div className={`flex items-center gap-1.5 flex-wrap text-xs ${className}`}>
        <span className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400 shrink-0 mr-0.5">
          <BookOpen className="w-3 h-3 text-sky-400" />
          {label}
        </span>

        {/* All Sources quick button */}
        <button
          type="button"
          onClick={handleSelectAll}
          title={isAllSelected ? `All ${ALL_SOURCES.length} sources currently included` : 'Include all sources'}
          className={`px-2 py-0.5 rounded-full text-[11px] font-medium transition-all shrink-0 cursor-pointer flex items-center gap-1 ${
            isAllSelected
              ? 'bg-sky-500/20 text-sky-300 border border-sky-400/50 shadow-sm'
              : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
          }`}
        >
          {isAllSelected && <Check className="w-2.5 h-2.5 text-sky-400" />}
          <span>All</span>
          <span className="text-[9px] opacity-70">({ALL_SOURCES.length})</span>
        </button>

        {/* Individual Source chips */}
        {ALL_SOURCES.map(s => {
          const isIncluded = selectedSources.includes(s.id);
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => handleToggleSource(s.id)}
              title={`${s.description} — Click to ${isIncluded ? 'EXCLUDE' : 'INCLUDE'}`}
              className={`px-2 py-0.5 rounded-full text-[11px] font-medium transition-all shrink-0 cursor-pointer flex items-center gap-1 ${
                isIncluded
                  ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/50 hover:bg-emerald-900/70 shadow-xs'
                  : 'bg-slate-900/40 text-slate-500 line-through hover:line-none hover:text-slate-300 hover:bg-slate-800/60 border border-slate-800/60 opacity-60 hover:opacity-100'
              }`}
            >
              {isIncluded ? (
                <Check className="w-2.5 h-2.5 text-emerald-400" />
              ) : (
                <X className="w-2.5 h-2.5 text-slate-500" />
              )}
              <span>{s.label}</span>
            </button>
          );
        })}

        {/* Count Indicator */}
        <span className="text-[10px] text-slate-400 font-mono ml-1 px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800">
          {isAllSelected ? (
            <span className="text-sky-400">All Included</span>
          ) : (
            <span>
              <span className="text-emerald-400 font-semibold">{selectedCount} inc</span>
              {' • '}
              <span className="text-amber-400/80">{excludedCount} excl</span>
            </span>
          )}
        </span>
      </div>
    );
  }

  // Full / Expanded View (ideal for Deep Research banner)
  return (
    <div className={`p-3 bg-slate-900/80 border border-slate-800/90 rounded-xl space-y-2.5 ${className}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Layers className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-200">
              Regulatory & Documentation Sources
            </span>
            <p className="text-[11px] text-slate-400">
              Select sources to include for retrieval and LLM consideration. Unselected sources are strictly excluded.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status summary pill */}
          <span className="text-xs px-2.5 py-1 rounded-full bg-slate-950 border border-slate-800 font-medium">
            {isAllSelected ? (
              <span className="text-sky-400 flex items-center gap-1.5">
                <CheckCheck className="w-3.5 h-3.5 text-sky-400" />
                All {ALL_SOURCES.length} Sources Included
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="text-emerald-400 font-bold">{selectedCount} Included</span>
                <span className="text-slate-600">•</span>
                <span className="text-rose-400/90 font-medium">{excludedCount} Excluded</span>
              </span>
            )}
          </span>

          {/* Quick Action Buttons */}
          <button
            type="button"
            onClick={handleSelectAll}
            disabled={isAllSelected}
            className="text-[11px] px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-medium flex items-center gap-1"
          >
            <CheckCheck className="w-3 h-3 text-sky-400" />
            <span>Select All</span>
          </button>

          <button
            type="button"
            onClick={handleInvert}
            title="Invert included / excluded sources"
            className="text-[11px] px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 transition-all font-medium flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3 text-indigo-400" />
            <span>Invert</span>
          </button>
        </div>
      </div>

      {/* Sources Grid / Chips */}
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-1.5 pt-1">
        {ALL_SOURCES.map(s => {
          const isIncluded = selectedSources.includes(s.id);
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => handleToggleSource(s.id)}
              className={`p-2 rounded-lg text-left transition-all border flex flex-col justify-between cursor-pointer group relative ${
                isIncluded
                  ? 'bg-emerald-950/40 border-emerald-500/50 hover:bg-emerald-950/60 shadow-sm'
                  : 'bg-slate-950/60 border-slate-800/80 opacity-60 hover:opacity-90 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between w-full mb-1">
                <span className={`text-xs font-bold ${isIncluded ? 'text-emerald-300' : 'text-slate-400'}`}>
                  {s.label}
                </span>
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                  isIncluded ? 'bg-emerald-500 text-slate-950 font-bold' : 'bg-slate-800 text-slate-500'
                }`}>
                  {isIncluded ? <Check className="w-2.5 h-2.5 stroke-[3]" /> : <X className="w-2.5 h-2.5" />}
                </span>
              </div>

              <div className="flex items-center justify-between text-[10px]">
                <span className={`truncate ${isIncluded ? 'text-emerald-400/80' : 'text-slate-500'}`}>
                  {s.badge}
                </span>
                <span className={`text-[9px] font-semibold uppercase px-1 rounded ${
                  isIncluded ? 'bg-emerald-900/60 text-emerald-300' : 'bg-rose-950/50 text-rose-400/80'
                }`}>
                  {isIncluded ? 'Inc' : 'Excl'}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
