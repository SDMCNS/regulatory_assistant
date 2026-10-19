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
import { CacheExplorer } from './components/CacheExplorer';
import { SettingsModal } from './components/SettingsModal';
import { AboutModal } from './components/AboutModal';
import { DocViewerModal } from './components/DocViewerModal';
import { ResearchTab } from './components/ResearchTab';
import { RegulationsWorkspace } from './components/RegulationsWorkspace';
import { DocumentBuilder } from './components/DocumentBuilder';
import { NotesTab } from './components/NotesTab';
import { KnowledgeGovernance } from './components/KnowledgeGovernance';
import { ConsultationWorkspace } from './components/ConsultationWorkspace';
import { KnowledgeGraphExplorer } from './components/KnowledgeGraphExplorer';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppSettings, ConnectionStatus, SearchDocResponse, DocSection, SearchResponse, KeywordSearchResponse } from './types';
import { DEFAULT_SETTINGS, loadSettings, pingFastApi, saveSettings } from './services/apiClient';
import { getQueryMemory, initMemory } from './services/memoryService';
import { getChats, createChat, addSectionToChat, initChats } from './services/chatService';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('assistant');
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<SearchDocResponse | null>(null);
  const [targetedChunks, setTargetedChunks] = useState<string[]>([]);
  const [activeMemoryCount, setActiveMemoryCount] = useState<number>(0);
  const [isPinging, setIsPinging] = useState(false);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [activeSearchQuery, setActiveSearchQuery] = useState<string>('');
  const [workspaceInitialDocs, setWorkspaceInitialDocs] = useState<string[]>([]);
  const [workspaceInitialQuery, setWorkspaceInitialQuery] = useState<string>('');
  const [isStoreReady, setIsStoreReady] = useState(false);

  // Initialize activeChatId
  useEffect(() => {
    Promise.all([initChats(), initMemory()]).then(() => {
      setIsStoreReady(true);
      const chats = getChats();
      if (chats.length > 0) {
        setActiveChatId(chats[0].id);
      } else {
        const newChat = createChat('Default Chat');
        setActiveChatId(newChat.id);
      }
    });
  }, []);

  const [chatUpdateTrigger, setChatUpdateTrigger] = useState(0);
  useEffect(() => {
    const handleUpdate = () => setChatUpdateTrigger(prev => prev + 1);
    window.addEventListener('chat_updated', handleUpdate);
    return () => window.removeEventListener('chat_updated', handleUpdate);
  }, []);

  const activeChat = getChats().find(c => c.id === activeChatId);
  const bookmarkedChunkIds = activeChat?.savedSections.map(s => s.id) || [];

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

  // Sync theme with documentElement
  useEffect(() => {
    const isLight = settings.theme === 'light';
    document.documentElement.classList.toggle('light', isLight);
    document.documentElement.classList.toggle('dark', !isLight);
  }, [settings.theme]);

  const handleToggleTheme = () => {
    const nextTheme = settings.theme === 'light' ? 'dark' : 'light';
    const updated: AppSettings = { ...settings, theme: nextTheme };
    handleSaveSettings(updated);
  };

  const [governanceUploadTrigger, setGovernanceUploadTrigger] = useState(0);

  const handleSelectTab = (tab: any) => {
    if (tab === 'governance' && !settings.showGovernanceTab) {
      const updated = { ...settings, showGovernanceTab: true };
      setSettings(updated);
      saveSettings(updated);
    }
    if (tab === 'builder' && !settings.showDocumentBuilderTab) {
      const updated = { ...settings, showDocumentBuilderTab: true };
      setSettings(updated);
      saveSettings(updated);
    }
    setActiveTab(tab);
  };

  const handleOpenUploadDoc = () => {
    if (!settings.showGovernanceTab) {
      const updated = { ...settings, showGovernanceTab: true };
      setSettings(updated);
      saveSettings(updated);
    }
    setActiveTab('governance');
    setGovernanceUploadTrigger(prev => prev + 1);
  };

  // Redirect if current active tab is disabled
  useEffect(() => {
    const isHidden =
      (activeTab === 'governance' && !settings.showGovernanceTab) ||
      (activeTab === 'builder' && !settings.showDocumentBuilderTab) ||
      (activeTab === 'memory' && !settings.showQueryMemoryTab) ||
      (activeTab === 'extract' && !settings.showSchemaExtractorTab) ||
      (activeTab === 'cache' && !settings.showLocalCacheTab);
    if (isHidden) {
      setActiveTab('assistant');
    }
  }, [activeTab, settings]);

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

  const handleOpenWorkspaceWithDocs = (documentIds: string[], initialQuery?: string) => {
    setWorkspaceInitialDocs(documentIds);
    if (initialQuery) {
      setWorkspaceInitialQuery(initialQuery);
    }
    setActiveTab('workspace');
  };

  if (!isStoreReady) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
          <p className="text-sm font-mono">Loading local storage...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Bar Header */}
      <TopBar
        activeTab={activeTab}
        onSelectTab={handleSelectTab}
        connectionStatus={connectionStatus}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onPingConnection={() => checkConnection()}
        isPinging={isPinging}
        activeMemoryCount={activeMemoryCount}
        settings={settings}
        theme={settings.theme || 'dark'}
        onToggleTheme={handleToggleTheme}
        onOpenAbout={() => setIsAboutOpen(true)}
        onOpenUploadDoc={handleOpenUploadDoc}
      />

      {/* Main Content Viewport */}
      <main className="flex-1 flex flex-col w-full min-h-0">
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
            bookmarkedChunkIds={bookmarkedChunkIds}
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
              }
            }}
          />
        )}

        {activeTab === 'graph' && (
          <ErrorBoundary fallbackTitle="Regulatory Knowledge Graph Explorer Error">
            <KnowledgeGraphExplorer
              apiUrl={settings.apiUrl}
              onViewDoc={(doc) => setSelectedDoc(doc)}
              onSendToAssistant={(prompt, chunkIds) => {
                if (chunkIds && chunkIds.length > 0) {
                  setTargetedChunks(chunkIds);
                }
                setActiveTab('assistant');
              }}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'research' && (
          <ResearchTab
            settings={settings}
            onViewDoc={(doc) => setSelectedDoc(doc)}
            onAskAboutChunk={handleAskAboutChunk}
            onOpenWorkspaceWithDocs={handleOpenWorkspaceWithDocs}
          />
        )}

        {activeTab === 'workspace' && (
          <RegulationsWorkspace
            settings={settings}
            onViewDoc={(doc) => setSelectedDoc(doc)}
            onAskAboutChunk={handleAskAboutChunk}
            onSendToAssistant={(prompt, chunkIds) => {
              if (chunkIds && chunkIds.length > 0) {
                setTargetedChunks(chunkIds);
              }
              setActiveTab('assistant');
            }}
            initialSelectedDocIds={workspaceInitialDocs}
            initialQuery={workspaceInitialQuery}
            onClearInitialContext={() => {
              setWorkspaceInitialDocs([]);
              setWorkspaceInitialQuery('');
            }}
          />
        )}

        {activeTab === 'consultation' && (
          <ErrorBoundary fallbackTitle="Document Consultation Workspace Error">
            <ConsultationWorkspace />
          </ErrorBoundary>
        )}

        {activeTab === 'governance' && (
          <ErrorBoundary fallbackTitle="Knowledge Governance Error">
            <KnowledgeGovernance
              settings={settings}
              onOpenInWorkspace={(docId) => handleOpenWorkspaceWithDocs([docId])}
              uploadTrigger={governanceUploadTrigger}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'builder' && (
          <ErrorBoundary fallbackTitle="Regulatory Document Builder Error">
            <DocumentBuilder
              settings={settings}
              onViewDoc={(doc) => setSelectedDoc(doc)}
              onOpenWorkspaceWithDocs={handleOpenWorkspaceWithDocs}
              onSendToAssistant={(prompt, chunkIds) => {
                if (chunkIds && chunkIds.length > 0) {
                  setTargetedChunks(chunkIds);
                }
                setActiveTab('assistant');
              }}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'notes' && (
          <NotesTab settings={settings} />
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

        {activeTab === 'cache' && (
          <CacheExplorer 
            onViewDoc={(doc) => setSelectedDoc(doc)}
            onAskAboutChunk={handleAskAboutChunk}
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
        onOpenAbout={() => setIsAboutOpen(true)}
      />

      {/* About AeroLex EU Modal */}
      <AboutModal
        isOpen={isAboutOpen}
        onClose={() => setIsAboutOpen(false)}
      />

      {/* Full Regulatory Document Viewer Modal */}
      <DocViewerModal
        doc={selectedDoc}
        onClose={() => setSelectedDoc(null)}
        onAskAboutChunk={handleAskAboutChunk}
        initialSearchQuery={activeSearchQuery}
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
