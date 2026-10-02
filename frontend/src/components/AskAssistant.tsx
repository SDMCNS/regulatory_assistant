/**
 * AskAssistant Component
 * Clean natural language interaction with local LLM over EU Aviation regulations
 * Injects and maintains memory of user queries directly through live API
 */

import React, { useState, useRef, useEffect } from 'react';
import { 
  Send, Database, Copy, Check, Layers, ChevronDown, 
  ChevronUp, FileText, ExternalLink, CornerDownLeft, Info, X
} from 'lucide-react';
import { AppSettings, ChatMessage, QueryMemoryItem, SearchDocResponse, ChatSession } from '../types';
import { askLLM, searchRegulations } from '../services/apiClient';
import { buildMemoryContextPrompt, recordQuery, getQueryMemory } from '../services/memoryService';
import { getChats, createChat, addMessageToChat, deleteChat, toggleSectionInChat } from '../services/chatService';
import { marked } from 'marked';

interface AskAssistantProps {
  settings: AppSettings;
  targetedChunks: string[];
  onClearTargetedChunks: () => void;
  onViewDoc: (doc: SearchDocResponse) => void;
  onSelectQueryFromMemory?: (query: string) => void;
  activeChatId: string | null;
  onChatChange: (chatId: string) => void;
}

export const AskAssistant: React.FC<AskAssistantProps> = ({
  settings,
  targetedChunks,
  onClearTargetedChunks,
  activeChatId,
  onChatChange,
  onViewDoc,
}) => {
  const [chats, setChats] = useState<ChatSession[]>(getChats());
  
  useEffect(() => {
    const handleUpdate = () => setChats(getChats());
    window.addEventListener('chat_updated', handleUpdate);
    return () => window.removeEventListener('chat_updated', handleUpdate);
  }, []);

  const activeChat = chats.find(c => c.id === activeChatId);
  const messages = activeChat?.messages || [];
  const savedSections = activeChat?.savedSections || [];

  const [inputPrompt, setInputPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [useMemoryInPrompt, setUseMemoryInPrompt] = useState(settings.enableQueryMemoryContext);
  const [showMemoryPreview, setShowMemoryPreview] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeMemoryItems, setActiveMemoryItems] = useState<QueryMemoryItem[]>(() => 
    getQueryMemory().filter(m => m.isActiveInContext)
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const refreshMemoryState = () => {
    setActiveMemoryItems(getQueryMemory().filter(m => m.isActiveInContext));
  };

  const handleSend = async (textToSend?: string) => {
    const prompt = (textToSend || inputPrompt).trim();
    if (!prompt || isLoading) return;

    if (!activeChatId) return;

    setInputPrompt('');

    const userMessage: ChatMessage = {
      id: 'msg-user-' + Date.now(),
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    };

    addMessageToChat(activeChatId, userMessage);
    setIsLoading(true);

    // Build memory context if enabled
    let memoryContext = '';
    let usedMemoryIds: string[] = [];

    if (useMemoryInPrompt) {
      const memBuild = buildMemoryContextPrompt(settings.maxMemoryContextItems);
      memoryContext = memBuild.contextString;
      usedMemoryIds = memBuild.usedItemIds;
    }
    let result: any;
      try {
        // Live call to POST /llm/ask
        result = await askLLM(
          prompt,
          targetedChunks.length > 0 ? targetedChunks : null,
          savedSections.filter(s => s.enabled !== false).length > 0 ? savedSections.filter(s => s.enabled !== false) : null,
          memoryContext,
          settings
        );
      } catch (err: any) {
        const errorMessage: ChatMessage = {
          id: 'msg-err-' + Date.now(),
          role: 'assistant',
          content: `**API Error from \`${settings.apiUrl}/llm/ask\`**: ${err.message || 'Request failed'}.\n\nPlease check your FastAPI server or use the \`/api\` Vite Proxy preset in Settings.`,
          timestamp: Date.now(),
          isError: true,
        };
        addMessageToChat(activeChatId, errorMessage);
        setIsLoading(false);
        return;
      }

      // Search matching documents to provide rich citations from real API
      let matchedChunks: any[] = [];
      try {
        const rawChunks = await searchRegulations(prompt, 3, settings.defaultOrigin, settings);
        // Strip heavy fields to prevent blowing up localStorage quota
        matchedChunks = rawChunks.map(c => {
          const { text, metadata, ...lightweightChunk } = c as any;
          return lightweightChunk;
        });
      } catch (e) {
        console.warn('Could not retrieve supplementary doc chunks', e);
      }

      const assistantMessage: ChatMessage = {
        id: 'msg-asst-' + Date.now(),
        role: 'assistant',
        content: result.answer,
        timestamp: Date.now(),
        referencedChunks: matchedChunks,
        usedMemoryItemIds: usedMemoryIds,
      };

      try {
        addMessageToChat(activeChatId, assistantMessage);

        // Record this query into Query Memory
        recordQuery({
          query: prompt,
          type: 'ask',
          origin: settings.defaultOrigin,
          top_k: settings.defaultTopK,
          resultsCount: matchedChunks.length,
          answerSnippet: result.answer.slice(0, 160).replace(/[#*`]/g, '') + '...',
          fullAnswer: result.answer,
          retrievedChunks: matchedChunks.map(c => ({
            chunk_id: c.chunk_id,
            document_id: c.document_id,
            source: c.source,
            path: c.path,
            score: c.score
          })),
          isPinned: false,
          isActiveInContext: true,
        });

        refreshMemoryState();
      } catch (localErr: any) {
        console.error("Failed to save local state:", localErr);
        alert(`Failed to save chat to local storage. Your browser storage might be full.\n\nError: ${localErr.message}`);
      } finally {
        setIsLoading(false);
      }

  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="flex h-[calc(100vh-61px)] bg-slate-950 overflow-hidden">
      {/* Sidebar for Chats */}
      <div className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0">
        <div className="p-3 border-b border-slate-800">
          <button
            onClick={() => {
              const newChat = createChat('Chat ' + (chats.length + 1));
              onChatChange(newChat.id);
            }}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-md text-sm font-medium transition-colors"
          >
            <span>+ New Chat</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {chats.map(chat => (
            <div key={chat.id} className="group flex items-center justify-between">
              <button
                onClick={() => onChatChange(chat.id)}
                className={`flex-1 text-left px-3 py-2 rounded-md text-sm truncate transition-colors ${
                  activeChatId === chat.id ? 'bg-slate-800 text-sky-400 font-medium' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                }`}
              >
                {chat.title}
              </button>
              <button
                onClick={() => {
                  deleteChat(chat.id);
                  if (activeChatId === chat.id) onChatChange(chats.find(c => c.id !== chat.id)?.id || '');
                }}
                className="p-2 text-slate-500 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0">
      {/* Top Context Subheader */}
      <div className="flex flex-wrap items-center justify-between px-6 py-2.5 bg-slate-900/60 border-b border-slate-800/80 text-xs text-slate-400 gap-3 shrink-0">
        {/* Left: Memory Status & Toggle */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setUseMemoryInPrompt(!useMemoryInPrompt)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border transition-colors ${
              useMemoryInPrompt
                ? 'bg-sky-950/60 border-sky-800 text-sky-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300'
            }`}
            title="Toggle whether previous queries are fed as context to the local LLM"
          >
            <Database className="w-3.5 h-3.5" />
            <span>Query Memory: {useMemoryInPrompt ? 'Active' : 'Disabled'}</span>
            <span className="font-mono text-[10px] ml-1 px-1 bg-sky-900/40 rounded">
              {activeMemoryItems.length} active
            </span>
          </button>

          {activeMemoryItems.length > 0 && (
            <button
              onClick={() => setShowMemoryPreview(!showMemoryPreview)}
              className="flex items-center gap-1 text-slate-400 hover:text-slate-200 transition-colors"
            >
              <span>{showMemoryPreview ? 'Hide context memory' : 'View context memory'}</span>
              {showMemoryPreview ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>

        {/* Right: Targeted Chunks Indicator */}
        <div className="flex items-center gap-2">
          {targetedChunks.length > 0 ? (
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-amber-950/40 border border-amber-800/60 text-amber-300">
              <Layers className="w-3.5 h-3.5" />
              <span>Targeting {targetedChunks.length} specific chunk(s)</span>
              <button
                onClick={onClearTargetedChunks}
                className="hover:underline text-[11px] text-amber-400 ml-1 font-semibold"
              >
                Clear (Auto-search)
              </button>
            </div>
          ) : (
            <span className="text-slate-500 hidden sm:inline">
              Mode: Auto-search ({settings.defaultOrigin.toUpperCase()} regulations)
            </span>
          )}
        </div>
      </div>

      {/* Memory Preview Drawer (Collapsible) */}
      {showMemoryPreview && activeMemoryItems.length > 0 && (
        <div className="px-6 py-3 bg-slate-900 border-b border-slate-800 text-xs animate-in slide-in-from-top-2 duration-200 shrink-0 max-h-48 overflow-y-auto">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-sky-400" />
              Active Query Memory Context (Injected into next LLM call)
            </span>
            <span className="text-[11px] text-slate-500">
              Max {settings.maxMemoryContextItems} items used
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {activeMemoryItems.slice(0, settings.maxMemoryContextItems).map((item, i) => (
              <div key={item.id} className="p-2 bg-slate-950 rounded border border-slate-800">
                <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                  <span className="font-medium text-slate-300 truncate max-w-[200px]">
                    #{i + 1} {item.query}
                  </span>
                  <span className="font-mono text-slate-500">{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <p className="text-slate-400 text-[11px] line-clamp-2">
                  {item.answerSnippet || item.fullAnswer?.slice(0, 100)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Display Saved Sections for context */}
      {savedSections.length > 0 && (
        <div className="px-6 py-2 bg-emerald-950/20 border-b border-emerald-900/50 text-xs shrink-0 flex items-center gap-3 overflow-x-auto whitespace-nowrap">
          <div className="font-semibold text-emerald-400 flex items-center gap-1.5 shrink-0">
            <Database className="w-3.5 h-3.5" />
            Bookmarked Context ({savedSections.filter(s => s.enabled !== false).length}/{savedSections.length}):
            <span className="ml-2 font-mono text-[10px] bg-emerald-900/40 px-1.5 py-0.5 rounded text-emerald-300">
              ~{Math.round(savedSections.filter(s => s.enabled !== false).reduce((acc, s) => acc + s.wordCount, 0) * 1.3)} tokens
            </span>
          </div>
          {savedSections.map(sec => (
            <button 
              key={sec.id} 
              onClick={() => activeChatId && toggleSectionInChat(activeChatId, sec.id)}
              className={`flex items-center gap-1.5 px-2 py-0.5 border rounded-md truncate max-w-xs transition-colors ${
                sec.enabled !== false 
                  ? 'bg-slate-900 border-emerald-700/50 text-slate-300' 
                  : 'bg-slate-950/50 border-slate-800 text-slate-500 opacity-60 line-through'
              }`}
              title={sec.enabled !== false ? 'Click to disable from LLM context' : 'Click to enable for LLM context'}
            >
              {sec.enabled !== false ? <Check className="w-3 h-3 text-emerald-400 shrink-0" /> : <X className="w-3 h-3 shrink-0" />}
              <span className="truncate">{sec.title}</span>
            </button>
          ))}
        </div>
      )}

      {/* Message History Container */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-6">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-4xl mx-auto w-full`}
          >
            {/* Role Header */}
            <div className="flex items-center gap-2 mb-1.5 text-xs text-slate-400 px-1">
              <span className="font-semibold text-slate-300">
                {msg.role === 'user' ? 'You' : 'FastAPI Local LLM'}
              </span>
              <span aria-hidden="true">·</span>
              <span className="font-mono tabular-nums text-slate-500">
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              {msg.usedMemoryItemIds && msg.usedMemoryItemIds.length > 0 && (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="text-sky-400 flex items-center gap-1 font-mono text-[11px]">
                    <Database className="w-3 h-3" />
                    {msg.usedMemoryItemIds.length} queries referenced
                  </span>
                </>
              )}
            </div>

            {/* Bubble Content */}
            <div
              className={`relative rounded-xl p-4 sm:p-5 text-sm leading-relaxed max-w-full ${
                msg.role === 'user'
                  ? 'bg-sky-600 text-white shadow-md rounded-tr-none'
                  : msg.isError
                  ? 'bg-rose-950/40 border border-rose-800/80 text-rose-200 rounded-tl-none'
                  : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none shadow-sm'
              }`}
            >
              {msg.role === 'user' ? (
                <p className="whitespace-pre-wrap font-sans">{msg.content}</p>
              ) : (
                <div
                  className="prose prose-invert prose-slate max-w-none 
                    prose-headings:text-slate-100 prose-headings:font-semibold 
                    prose-h3:text-base prose-h4:text-sm prose-h4:text-sky-400
                    prose-p:text-slate-300 prose-p:my-2
                    prose-ul:text-slate-300 prose-li:my-1
                    prose-strong:text-slate-100 prose-code:text-sky-300 prose-code:bg-slate-950 prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                    prose-blockquote:border-sky-500/50 prose-blockquote:bg-sky-950/20 prose-blockquote:text-slate-300 prose-blockquote:py-1 prose-blockquote:px-3"
                  dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) }}
                />
              )}

              {/* Citations / Referenced Regulatory Documents */}
              {msg.referencedChunks && msg.referencedChunks.length > 0 && (
                <div className="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    <FileText className="w-3.5 h-3.5 text-sky-400" />
                    <span>Referenced Regulatory Standards ({msg.referencedChunks.length})</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {msg.referencedChunks.map((chunk) => (
                      <div
                        key={chunk.chunk_id}
                        className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 hover:border-slate-700 transition-colors"
                      >
                        <div className="min-w-0 pr-2">
                          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                            <span className="font-mono text-sky-400 uppercase">{chunk.source}</span>
                            <span aria-hidden="true">·</span>
                            <span className="truncate">{chunk.document_id}</span>
                          </div>
                          <div className="text-xs font-medium text-slate-200 truncate">
                            {chunk.path[chunk.path.length - 1] || chunk.chunk_id}
                          </div>
                        </div>

                        <button
                          onClick={() => onViewDoc(chunk as SearchDocResponse)}
                          className="p-1.5 text-slate-400 hover:text-sky-300 hover:bg-slate-800 rounded transition-colors shrink-0"
                          title="View complete regulatory document"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Message Actions */}
              {msg.role === 'assistant' && (
                <div className="flex items-center justify-end gap-2 mt-3 pt-2 border-t border-slate-800/40 text-xs text-slate-400">
                  <button
                    onClick={() => handleCopyMessage(msg.id, msg.content)}
                    className="flex items-center gap-1 px-2 py-1 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
                  >
                    {copiedId === msg.id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedId === msg.id ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-start max-w-4xl mx-auto w-full space-x-3">
            <div className="bg-slate-900 border border-slate-800 rounded-xl rounded-tl-none p-4 text-xs text-slate-400 flex items-center gap-3 shadow-sm">
              <div className="flex space-x-1.5">
                <div className="w-2 h-2 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span>Querying local LLM at {settings.apiUrl}/llm/ask...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 sm:p-6 bg-slate-950 border-t border-slate-800/80 shrink-0">
        <div className="max-w-4xl mx-auto w-full space-y-2">
          <div className="relative flex items-end bg-slate-900 border border-slate-800 focus-within:border-sky-500 rounded-xl shadow-lg transition-colors p-2">
            <textarea
              ref={textareaRef}
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about EU/EASA regulations (e.g. Flight Duty Periods, ATSEP licensing, open category drones)..."
              rows={2}
              className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 focus:outline-none resize-none px-3 py-1 font-sans leading-relaxed"
            />

            <div className="flex items-center gap-1.5 pl-2 pb-1 shrink-0">
              <button
                type="button"
                onClick={() => handleSend()}
                disabled={!inputPrompt.trim() || isLoading}
                className="flex items-center justify-center w-9 h-9 rounded-lg bg-sky-600 hover:bg-sky-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Send query (Enter)"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-500 px-1">
            <div className="flex items-center gap-2">
              <span>Press <kbd className="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded text-slate-300 font-mono text-[10px]">Enter</kbd> to submit</span>
              <span>·</span>
              <span><kbd className="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded text-slate-300 font-mono text-[10px]">Shift+Enter</kbd> for new line</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sky-400">Endpoint: {settings.apiUrl}/llm/ask</span>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
};
