/**
 * AeroLex EU - Aviation Regulation Assistant
 * Front-end for local LLM & Semantic Search over EASA Easy Access Rules and EU Formex standards
 */

import React, { useState, useEffect, useCallback } from 'react';
import { TopBar, ActiveTab } from './components/TopBar';
import { AskAssistant } from './components/AskAssistant';
import { SearchExplorer } from './components/SearchExplorer';
import { MemoryHub } from './components/MemoryHub';
import { ExtractTool } from './components/ExtractTool';
import { SettingsModal } from './components/SettingsModal';
import { DocViewerModal } from './components/DocViewerModal';
import { AppSettings, ConnectionStatus, SearchDocResponse, DocSection, SearchResponse, KeywordSearchResponse } from './types';
import { DEFAULT_SETTINGS, loadSettings, pingFastApi, saveSettings } from './services/apiClient';
import { getQueryMemory } from './services/memoryService';
import { getChats, createChat, addSectionToChat } from './services/chatService';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('assistant');
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<SearchDocResponse | null>(null);
  const [targetedChunks, setTargetedChunks] = useState<string[]>([]);
  const [activeMemoryCount, setActiveMemoryCount] = useState<number>(0);
  const [isPinging, setIsPinging] = useState(false);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [activeSearchQuery, setActiveSearchQuery] = useState<string>('');

  // Initialize activeChatId
  useEffect(() => {
    const chats = getChats();
    if (chats.length > 0) {
      setActiveChatId(chats[0].id);
    } else {
      const newChat = createChat('Default Chat');
      setActiveChatId(newChat.id);
    }
  }, []);

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    state: 'checking',
    message: 'Testing connection to FastAPI...',
  });

  // Calculate active memory count
  const refreshMemoryCount = useCallback(() => {
    const memory = getQueryMemory();
    const active = memory.filter(m => m.isActiveInContext).length;
    setActiveMemoryCount(active);
  }, []);

  // Ping FastAPI on startup or when settings change
  const checkConnection = useCallback(async (customSettings?: AppSettings) => {
    setIsPinging(true);
    const target = customSettings || settings;
    try {
      const res = await pingFastApi(target.apiUrl, target.apiAuthToken);
      setConnectionStatus(res);
    } catch (e: any) {
      setConnectionStatus({
        state: 'offline',
        message: e.message || 'Cannot reach local FastAPI',
        lastChecked: Date.now()
      });
    } finally {
      setIsPinging(false);
    }
  }, [settings]);

  useEffect(() => {
    checkConnection();
    refreshMemoryCount();
  }, [checkConnection, refreshMemoryCount]);

  const handleSaveSettings = (newSettings: AppSettings) => {
    setSettings(newSettings);
    saveSettings(newSettings);
    checkConnection(newSettings);
  };

  const handleToggleTargetChunk = (chunkId: string) => {
    setTargetedChunks(prev => 
      prev.includes(chunkId) ? prev.filter(id => id !== chunkId) : [...prev, chunkId]
    );
  };

  const handleClearTargetedChunks = () => {
    setTargetedChunks([]);
  };

  const handleAskAboutChunk = (chunkId: string, docTitle: string) => {
    if (!targetedChunks.includes(chunkId)) {
      setTargetedChunks(prev => [...prev, chunkId]);
    }
    setActiveTab('assistant');
  };

  const handleReAskQuery = (query: string, chunkIds?: string[]) => {
    if (chunkIds && chunkIds.length > 0) {
      setTargetedChunks(chunkIds);
    }
    setActiveTab('assistant');
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Bar Header */}
      <TopBar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        connectionStatus={connectionStatus}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onPingConnection={() => checkConnection()}
        isPinging={isPinging}
        activeMemoryCount={activeMemoryCount}
      />

      {/* Main Content Viewport */}
      <main className="flex-1 flex flex-col">
        {activeTab === 'assistant' && (
          <AskAssistant
            settings={settings}
            targetedChunks={targetedChunks}
            onClearTargetedChunks={handleClearTargetedChunks}
            onViewDoc={(doc) => setSelectedDoc(doc)}
            activeChatId={activeChatId}
            onChatChange={setActiveChatId}
          />
        )}

        {activeTab === 'search' && (
          <SearchExplorer
            settings={settings}
            onViewDoc={(doc) => setSelectedDoc(doc)}
            onAskAboutChunk={handleAskAboutChunk}
            targetedChunks={targetedChunks}
            onToggleTargetChunk={handleToggleTargetChunk}
            initialQuery={activeSearchQuery}
            onBookmarkChunk={(chunk) => {
              if (activeChatId) {
                const section: DocSection = {
                  index: 0,
                  id: chunk.chunk_id,
                  type: 'search_chunk',
                  title: chunk.path[chunk.path.length - 1] || chunk.chunk_id,
                  meta: chunk.metadata || {},
                  markdown: chunk.text,
                  wordCount: chunk.text.split(/\s+/).length,
                };
                addSectionToChat(activeChatId, section);
                setActiveTab('assistant');
              }
            }}
          />
        )}

        {activeTab === 'memory' && (
          <MemoryHub
            onReAskQuery={handleReAskQuery}
            onRefreshMemoryCount={refreshMemoryCount}
          />
        )}

        {activeTab === 'extract' && (
          <ExtractTool
            settings={settings}
          />
        )}
      </main>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSaveSettings={handleSaveSettings}
        connectionStatus={connectionStatus}
        onConnectionChange={setConnectionStatus}
      />

      {/* Full Regulatory Document Viewer Modal */}
      <DocViewerModal
        doc={selectedDoc}
        onClose={() => setSelectedDoc(null)}
        onAskAboutChunk={handleAskAboutChunk}
        onBookmarkSection={(section) => {
          if (activeChatId) {
            addSectionToChat(activeChatId, section);
            // Optionally switch to assistant tab
            setActiveTab('assistant');
          }
        }}
        onSearchSection={(sectionMarkdown) => {
          setActiveSearchQuery(sectionMarkdown);
          setActiveTab('search');
        }}
      />
    </div>
  );
}
