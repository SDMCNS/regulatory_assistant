/**
 * TopBar Component adhering to the Universal Frontend Design Constitution
 * One-row, 3-zone contract: Brand Title — Clean Nav Links — Primary Actions
 */

import React from 'react';
import { Sliders, ShieldCheck, AlertCircle, RefreshCw, Zap } from 'lucide-react';
import { ConnectionStatus } from '../types';

export type ActiveTab = 'assistant' | 'search' | 'memory' | 'extract' | 'cache';

interface TopBarProps {
  activeTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
  connectionStatus: ConnectionStatus;
  onOpenSettings: () => void;
  onPingConnection: () => void;
  isPinging: boolean;
  activeMemoryCount: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  activeTab,
  onSelectTab,
  connectionStatus,
  onOpenSettings,
  onPingConnection,
  isPinging,
  activeMemoryCount,
}) => {
  return (
    <header className="flex items-center justify-between px-6 py-3.5 bg-slate-950/90 border-b border-slate-800/80 backdrop-blur sticky top-0 z-40">
      {/* Zone 1: Single text element wordmark */}
      <div className="flex items-center gap-3">
        <a 
          href="#" 
          onClick={(e) => { e.preventDefault(); onSelectTab('assistant'); }} 
          className="text-lg font-bold tracking-tight text-white flex items-center gap-2 hover:opacity-90 transition-opacity"
        >
          <span className="w-2.5 h-2.5 rounded-full bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.8)]" />
          <span>AeroLex EU</span>
        </a>
        <span className="hidden sm:inline text-xs text-slate-500 font-mono">
          EASA & EU Formex
        </span>
      </div>

      {/* Zone 2: Clean text navigation links / segmented controls */}
      <nav className="flex items-center gap-1 p-1 bg-slate-900 border border-slate-800 rounded-lg">
        <button
          onClick={() => onSelectTab('assistant')}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
            activeTab === 'assistant'
              ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Ask Assistant
        </button>

        <button
          onClick={() => onSelectTab('search')}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
            activeTab === 'search'
              ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Regulation Search
        </button>

        <button
          onClick={() => onSelectTab('memory')}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
            activeTab === 'memory'
              ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>Query Memory</span>
          {activeMemoryCount > 0 && (
            <span className="px-1.5 py-0.2 font-mono text-[10px] rounded bg-sky-950 text-sky-400 border border-sky-800/60">
              {activeMemoryCount}
            </span>
          )}
        </button>

        <button
          onClick={() => onSelectTab('extract')}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap hidden md:block ${
            activeTab === 'extract'
              ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Schema Extractor
        </button>

        <button
          onClick={() => onSelectTab('cache')}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap hidden lg:block ${
            activeTab === 'cache'
              ? 'bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Local Cache
        </button>
      </nav>

      {/* Zone 3: 1-2 primary actions */}
      <div className="flex items-center gap-2">
        {/* Fast API Status Indicator */}
        <button
          onClick={onPingConnection}
          disabled={isPinging}
          title={`Click to re-ping API (${connectionStatus.message})`}
          className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-mono transition-colors ${
            connectionStatus.state === 'connected'
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-400 hover:bg-emerald-900/40'
              : connectionStatus.state === 'cors_issue'
              ? 'bg-amber-950/40 border-amber-800/60 text-amber-400 hover:bg-amber-900/40'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-850'
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${
            connectionStatus.state === 'connected'
              ? 'bg-emerald-500 animate-pulse'
              : connectionStatus.state === 'cors_issue'
              ? 'bg-amber-500'
              : 'bg-slate-500'
          }`} />
          <span>
            {connectionStatus.state === 'connected'
              ? `FastAPI (${connectionStatus.latencyMs ?? 0}ms)`
              : connectionStatus.state === 'cors_issue'
              ? 'CORS Alert'
              : 'Local Offline'}
          </span>
          <RefreshCw className={`w-3 h-3 text-slate-500 ml-0.5 ${isPinging ? 'animate-spin' : ''}`} />
        </button>

        {/* Settings Button */}
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-lg transition-colors whitespace-nowrap"
        >
          <Sliders className="w-3.5 h-3.5 text-sky-400" />
          <span className="hidden sm:inline">Settings</span>
        </button>
      </div>
    </header>
  );
};
