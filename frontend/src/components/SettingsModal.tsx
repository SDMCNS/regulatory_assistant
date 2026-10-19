/**
 * Settings Modal: Configure FastAPI URL, test connectivity, configure memory context & regulatory filters
 */

import React, { useState, useEffect } from 'react';
import { X, Check, RefreshCw, AlertTriangle, ShieldCheck, Database, HardDrive, Terminal, Sparkles, Cloud, Cpu, Eye, EyeOff, SlidersHorizontal, FileText, Brain, Code2, Sun, Moon, Info, Layers } from 'lucide-react';
import { AppSettings, ConnectionStatus } from '../types';
import { pingFastApi, saveSettings, testGeminiApiKey, testReranker } from '../services/apiClient';
import { clearMemory, getQueryMemory } from '../services/memoryService';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: AppSettings;
  onSaveSettings: (newSettings: AppSettings) => void;
  connectionStatus: ConnectionStatus;
  onConnectionChange: (status: ConnectionStatus) => void;
  onOpenAbout?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSaveSettings,
  connectionStatus,
  onConnectionChange,
  onOpenAbout,
}) => {
  const [form, setForm] = useState<AppSettings>(() => {
    const initial = { ...settings };
    if (!initial.geminiModel || initial.geminiModel.startsWith('gemini-1.') || initial.geminiModel.startsWith('gemini-2.')) {
      initial.geminiModel = 'gemini-3.5-flash';
    }
    initial.showGovernanceTab = Boolean(initial.showGovernanceTab);
    initial.showDocumentBuilderTab = Boolean(initial.showDocumentBuilderTab);
    initial.showQueryMemoryTab = Boolean(initial.showQueryMemoryTab);
    initial.showSchemaExtractorTab = Boolean(initial.showSchemaExtractorTab);
    initial.showLocalCacheTab = Boolean(initial.showLocalCacheTab);
    initial.enableReranker = initial.enableReranker !== false;
    initial.rerankerModel = initial.rerankerModel || 'text-embedding-baai-bge-reranker-v2-m3-m3';
    initial.theme = initial.theme === 'light' ? 'light' : 'dark';
    return initial;
  });
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionStatus | null>(connectionStatus);
  const [memoryCount, setMemoryCount] = useState<number>(() => getQueryMemory().length);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Gemini Settings state
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [testingGemini, setTestingGemini] = useState(false);
  const [geminiTestResult, setGeminiTestResult] = useState<{ success: boolean; message: string; model?: string } | null>(null);

  // Reranker Settings state
  const [testingReranker, setTestingReranker] = useState(false);
  const [rerankerTestResult, setRerankerTestResult] = useState<{
    success: boolean;
    message: string;
    device?: string;
    resolved_model?: string;
    test_inference_seconds?: number;
    test_score?: number;
    error?: string;
  } | null>(null);

  useEffect(() => {
    if (isOpen) {
      const initial = { ...settings };
      if (!initial.geminiModel || initial.geminiModel.startsWith('gemini-1.') || initial.geminiModel.startsWith('gemini-2.')) {
        initial.geminiModel = 'gemini-3.5-flash';
      }
      initial.showGovernanceTab = Boolean(initial.showGovernanceTab);
      initial.showDocumentBuilderTab = Boolean(initial.showDocumentBuilderTab);
      initial.showQueryMemoryTab = Boolean(initial.showQueryMemoryTab);
      initial.showSchemaExtractorTab = Boolean(initial.showSchemaExtractorTab);
      initial.showLocalCacheTab = Boolean(initial.showLocalCacheTab);
      initial.enableReranker = initial.enableReranker !== false;
      initial.rerankerModel = initial.rerankerModel || 'text-embedding-baai-bge-reranker-v2-m3-m3';
      initial.theme = initial.theme === 'light' ? 'light' : 'dark';
      setForm(initial);
      setTestResult(connectionStatus);
      setMemoryCount(getQueryMemory().length);
      setRerankerTestResult(null);
    }
  }, [isOpen, settings, connectionStatus]);

  const handleThemeChange = (newTheme: 'dark' | 'light') => {
    setForm(prev => ({ ...prev, theme: newTheme }));
    document.documentElement.classList.toggle('light', newTheme === 'light');
    document.documentElement.classList.toggle('dark', newTheme !== 'light');
  };

  const handleClose = () => {
    const isLight = settings.theme === 'light';
    document.documentElement.classList.toggle('light', isLight);
    document.documentElement.classList.toggle('dark', !isLight);
    onClose();
  };

  if (!isOpen) return null;

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      const res = await pingFastApi(form.apiUrl, form.apiAuthToken);
      setTestResult(res);
      onConnectionChange(res);
    } catch (e: any) {
      const errRes: ConnectionStatus = {
        state: 'offline',
        message: e.message || 'Error testing connection',
        lastChecked: Date.now()
      };
      setTestResult(errRes);
      onConnectionChange(errRes);
    } finally {
      setTesting(false);
    }
  };

  const handleTestGemini = async () => {
    if (!form.geminiApiKey?.trim()) {
      setGeminiTestResult({
        success: false,
        message: 'Please enter a Gemini API Key first before testing.'
      });
      return;
    }
    setTestingGemini(true);
    setGeminiTestResult(null);
    try {
      const res = await testGeminiApiKey(form.geminiApiKey, form.geminiModel || 'gemini-3.5-flash', form);
      setGeminiTestResult(res);
    } catch (e: any) {
      setGeminiTestResult({
        success: false,
        message: e.message || 'Failed to connect to Gemini API endpoint.'
      });
    } finally {
      setTestingGemini(false);
    }
  };

  const handleTestReranker = async () => {
    setTestingReranker(true);
    setRerankerTestResult(null);
    try {
      const res = await testReranker(form.rerankerModel, form);
      setRerankerTestResult(res);
    } catch (e: any) {
      setRerankerTestResult({
        success: false,
        message: e.message || 'Error communicating with reranker service.',
        error: e.message
      });
    } finally {
      setTestingReranker(false);
    }
  };

  const handleSave = () => {
    saveSettings(form);
    onSaveSettings(form);
    onClose();
  };

  const handleClearMemory = (keepPinned: boolean) => {
    clearMemory(keepPinned);
    setMemoryCount(getQueryMemory().length);
    setShowClearConfirm(false);
  };


  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative flex flex-col w-full max-w-2xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90 shrink-0">
          <div>
            <h2 className="text-base font-semibold text-slate-100">API & Knowledge Base Settings</h2>
            <p className="text-xs text-slate-400">Configure connection to your local FastAPI server and query memory preferences</p>
          </div>
          <button
            onClick={handleClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Section 1: FastAPI Endpoint Configuration */}
          <div className="space-y-3">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
              FastAPI Base URL
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={form.apiUrl}
                onChange={(e) => setForm({ ...form, apiUrl: e.target.value })}
                placeholder="http://localhost:8000"
                className="flex-1 px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono"
              />
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={testing}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-sky-600 hover:bg-sky-500 rounded-lg transition-colors disabled:opacity-50 whitespace-nowrap"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
                <span>{testing ? 'Testing...' : 'Test Connection'}</span>
              </button>
            </div>

            {/* Presets */}
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span>Quick Presets:</span>
              <button
                type="button"
                onClick={() => setForm({ ...form, apiUrl: '/api' })}
                className={`px-2 py-0.5 rounded font-mono text-[11px] border transition-colors ${
                  form.apiUrl === '/api'
                    ? 'bg-sky-950 text-sky-400 border-sky-800'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                }`}
                title="Bypasses all browser CORS by proxying through Vite dev server to localhost:8000"
              >
                /api (Vite Proxy - No CORS)
              </button>
              <button
                type="button"
                onClick={() => setForm({ ...form, apiUrl: 'http://127.0.0.1:8000' })}
                className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-mono text-[11px]"
              >
                127.0.0.1:8000
              </button>
              <button
                type="button"
                onClick={() => setForm({ ...form, apiUrl: 'http://localhost:8000' })}
                className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-mono text-[11px]"
              >
                localhost:8000
              </button>
            </div>

            {/* Live Connection Diagnostics Box */}
            {testResult && (
              <div className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                testResult.state === 'connected'
                  ? 'bg-emerald-950/30 border-emerald-800/50 text-emerald-300'
                  : testResult.state === 'cors_issue'
                  ? 'bg-amber-950/30 border-amber-800/50 text-amber-300'
                  : 'bg-rose-950/30 border-rose-800/50 text-rose-300'
              }`}>
                {testResult.state === 'connected' ? (
                  <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                )}
                <div className="space-y-1 w-full">
                  <div className="font-semibold">
                    {testResult.state === 'connected' ? 'FastAPI Connected' : testResult.state === 'cors_issue' ? 'CORS / Preflight Alert' : 'FastAPI Offline / Unreachable'}
                  </div>
                  <div className="text-slate-300 font-sans">
                    {testResult.message}
                  </div>
                  {testResult.state === 'cors_issue' && (
                    <div className="mt-2 text-[11px] text-slate-300 bg-slate-950/90 p-3 rounded border border-slate-800 space-y-2">
                      <p className="text-amber-400 font-semibold font-sans">
                        Quick Fix 1 (Instant): Use the Vite Proxy
                      </p>
                      <p className="text-slate-300 font-sans">
                        Click the <strong className="text-sky-400 font-mono">/api (Vite Proxy)</strong> button above. This routes requests from port 3000 to port 8000 on the server side, completely bypassing browser CORS preflight.
                      </p>

                      <p className="text-amber-400 font-semibold font-sans pt-1">
                        Quick Fix 2 (FastAPI main.py): Add CORSMiddleware BEFORE routers
                      </p>
                      <div className="font-mono text-[10px] text-slate-300 bg-slate-900 p-2 rounded border border-slate-800 space-y-0.5">
                        <div className="text-slate-500"># In your backend/api/main.py:</div>
                        <div>from fastapi.middleware.cors import CORSMiddleware</div>
                        <div className="text-slate-500"># CRITICAL: add_middleware MUST be placed BEFORE app.include_router(...)</div>
                        <div>app.add_middleware(</div>
                        <div className="pl-4">CORSMiddleware,</div>
                        <div className="pl-4">allow_origins=["*"],</div>
                        <div className="pl-4">allow_credentials=False, # Must be False when allow_origins=["*"]</div>
                        <div className="pl-4">allow_methods=["*"],</div>
                        <div className="pl-4">allow_headers=["*"],</div>
                        <div>)</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Section 2: Optional Auth Token */}
          <div className="space-y-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
              API Authorization Token (Optional)
            </label>
            <input
              type="password"
              value={form.apiAuthToken}
              onChange={(e) => setForm({ ...form, apiAuthToken: e.target.value })}
              placeholder="Bearer token or API Key if required"
              className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono"
            />
          </div>

          {/* Section 3: Deep Research Engine & Cloud Acceleration */}
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Deep Research Engine & Cloud Acceleration
                </h3>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800 font-medium">
                Research Activity
              </span>
            </div>

            <p className="text-xs text-slate-400">
              Configure the reasoning engine for recursive regulatory research and adversarial chunk evaluation.
              Standard assistant queries and keyword search remain 100% local on your LM Studio instance.
            </p>

            {/* Provider Selection Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Local Option */}
              <div
                onClick={() => setForm({ ...form, researchProvider: 'local' })}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                  (form.researchProvider || 'local') === 'local'
                    ? 'bg-slate-850 border-indigo-500/80 shadow-sm shadow-indigo-950/40'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-slate-300" />
                    <span className="text-xs font-semibold text-slate-200">Local LLM (LM Studio)</span>
                  </div>
                  <input
                    type="radio"
                    name="researchProvider"
                    checked={(form.researchProvider || 'local') === 'local'}
                    onChange={() => setForm({ ...form, researchProvider: 'local' })}
                    className="accent-indigo-500"
                  />
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  100% on-device local execution using your local LLM model (e.g. Gemma 4). Fully private with zero cloud communication.
                </p>
              </div>

              {/* Gemini Cloud Option */}
              <div
                onClick={() => setForm({ ...form, researchProvider: 'gemini' })}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                  form.researchProvider === 'gemini'
                    ? 'bg-indigo-950/40 border-indigo-500/80 shadow-sm shadow-indigo-950/40'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <span className="text-xs font-semibold text-white">Google Gemini Cloud</span>
                  </div>
                  <input
                    type="radio"
                    name="researchProvider"
                    checked={form.researchProvider === 'gemini'}
                    onChange={() => setForm({ ...form, researchProvider: 'gemini' })}
                    className="accent-indigo-500"
                  />
                </div>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Cloud reasoning acceleration for deep multi-pass research, adversarial chunk falsification, and comprehensive report synthesis.
                </p>
              </div>
            </div>

            {/* Gemini Configuration Drawer */}
            {form.researchProvider === 'gemini' && (
              <div className="p-4 bg-slate-950/90 rounded-xl border border-indigo-900/60 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
                {/* Gemini API Key */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-slate-300">
                      Google Gemini API Key
                    </label>
                    <a
                      href="https://aistudio.google.com/app/apikey"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-indigo-400 hover:text-indigo-300 hover:underline"
                    >
                      Get API Key (Google AI Studio) &rarr;
                    </a>
                  </div>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <input
                        type={showGeminiKey ? 'text' : 'password'}
                        value={form.geminiApiKey || ''}
                        onChange={(e) => setForm({ ...form, geminiApiKey: e.target.value })}
                        placeholder="AIzaSy... or AQ.Ab8..."
                        className="w-full px-3 py-2 pr-9 text-xs bg-slate-900 border border-slate-800 rounded-lg text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                      <button
                        type="button"
                        onClick={() => setShowGeminiKey(!showGeminiKey)}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                      >
                        {showGeminiKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={handleTestGemini}
                      disabled={testingGemini}
                      className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors disabled:opacity-50 whitespace-nowrap shadow-sm"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${testingGemini ? 'animate-spin' : ''}`} />
                      <span>{testingGemini ? 'Verifying...' : 'Test Key'}</span>
                    </button>
                  </div>
                </div>

                {/* Gemini Model Selection */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-medium text-slate-300">
                      Gemini Model for Research
                    </label>
                    <span className="text-[10px] font-mono text-indigo-400">
                      Active: {form.geminiModel || 'gemini-3.5-flash'}
                    </span>
                  </div>
                  <div className="space-y-2">
                    <select
                      value={
                        ['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-3.1-pro-preview'].includes(form.geminiModel || '')
                          ? form.geminiModel
                          : 'custom'
                      }
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val !== 'custom') {
                          setForm({ ...form, geminiModel: val });
                        }
                      }}
                      className="w-full px-3 py-2 text-xs bg-slate-900 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500 font-mono"
                    >
                      <option value="gemini-3.5-flash">gemini-3.5-flash (Recommended: High Availability & Speed)</option>
                      <option value="gemini-3.5-flash-lite">gemini-3.5-flash-lite (Ultra-fast & Lightweight)</option>
                      <option value="gemini-3.8-flash">gemini-3.8-flash (Reasoning Thinking Model)</option>
                      <option value="gemini-3.6-flash">gemini-3.6-flash (Stable Standard)</option>
                      <option value="gemini-3.7-flash">gemini-3.7-flash (Multimodal Reasoning)</option>
                      <option value="gemini-3.1-pro-preview">gemini-3.1-pro-preview (Deep Pro Synthesis)</option>
                      <option value="custom">Custom Model Identifier...</option>
                    </select>

                    {/* Custom Model Input if selected or non-standard */}
                    {(!['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-3.1-pro-preview'].includes(form.geminiModel || '') ||
                      form.geminiModel === 'custom') && (
                      <input
                        type="text"
                        value={form.geminiModel === 'custom' ? '' : form.geminiModel || ''}
                        onChange={(e) => setForm({ ...form, geminiModel: e.target.value })}
                        placeholder="e.g. gemini-3.5-flash or fine-tuned model"
                        className="w-full px-3 py-1.5 text-xs bg-slate-900 border border-indigo-700/60 rounded-lg text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                    )}
                  </div>
                </div>

                {/* Test Result Indicator */}
                {geminiTestResult && (() => {
                  const isSuccess = Boolean(
                    geminiTestResult.success === true ||
                    (geminiTestResult as any).status === 'connected' ||
                    (typeof geminiTestResult.message === 'string' && geminiTestResult.message.toLowerCase().includes('successfully connected'))
                  );
                  return (
                    <div
                      className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                        isSuccess
                          ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                          : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
                      }`}
                    >
                      {isSuccess ? (
                        <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                      )}
                      <div className="space-y-0.5">
                        <div className="font-semibold">
                          {isSuccess ? 'Gemini API Connected Successfully' : 'Gemini Validation Failed'}
                        </div>
                        <div className="text-[11px] opacity-90">{geminiTestResult.message}</div>
                      </div>
                    </div>
                  );
                })()}

                {/* Scientific Rigor Assurance Notice */}
                <div className="text-[11px] text-slate-400 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80 space-y-1">
                  <div className="flex items-center gap-1.5 text-indigo-300 font-medium">
                    <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Scientific Falsification & Adversarial Negation Enabled</span>
                  </div>
                  <p className="leading-relaxed">
                    The research engine actively audits retrieved regulatory chunks, rejecting out-of-scope material (e.g. VTOL airworthiness chunks on CNS queries) and iteratively formulating refined searches to guarantee high-value citations.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Section 4: Query Memory Preferences */}
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-sky-400" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                User Query Memory & Context Retention
              </h3>
            </div>


            <div className="flex items-start justify-between gap-4 p-3 bg-slate-950/60 rounded-lg border border-slate-800">
              <div className="space-y-0.5">
                <div className="text-sm font-medium text-slate-200">Inject Query Memory into LLM Prompts</div>
                <div className="text-xs text-slate-400">
                  Automatically incorporates context from your active query history into subsequent questions to provide continuous conversational memory.
                </div>
              </div>
              <input
                type="checkbox"
                checked={form.enableQueryMemoryContext}
                onChange={(e) => setForm({ ...form, enableQueryMemoryContext: e.target.checked })}
                className="mt-1 w-4 h-4 rounded text-sky-600 focus:ring-sky-500 bg-slate-900 border-slate-700"
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-300">
                <span>Maximum Memory Context Items to Include:</span>
                <span className="font-mono text-sky-400">{form.maxMemoryContextItems} queries</span>
              </div>
              <input
                type="range"
                min={1}
                max={10}
                value={form.maxMemoryContextItems}
                onChange={(e) => setForm({ ...form, maxMemoryContextItems: Number(e.target.value) })}
                className="w-full accent-sky-500 cursor-pointer"
              />
            </div>

            {/* Keyword Search Expansion Default */}
            <div className="flex items-start justify-between gap-4 p-3 bg-slate-950/60 rounded-lg border border-slate-800">
              <div className="space-y-0.5">
                <div className="text-sm font-medium text-slate-200">LLM Keyword Expansion (/search/keyword)</div>
                <div className="text-xs text-slate-400">
                  Enables local LLM synonym and acronym expansion by default for BM25 SQLite FTS5 queries.
                </div>
              </div>
              <input
                type="checkbox"
                checked={form.defaultKeywordUseLLM}
                onChange={(e) => setForm({ ...form, defaultKeywordUseLLM: e.target.checked })}
                className="mt-1 w-4 h-4 rounded text-sky-600 focus:ring-sky-500 bg-slate-900 border-slate-700"
              />
            </div>
          </div>

          {/* Section: Neural Reranker Preprocessing & Screening */}
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Neural Reranker Preprocessing & Relevance Screening
                </h3>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 font-medium">
                Retrieval Filtering
              </span>
            </div>

            <p className="text-xs text-slate-400">
              Evaluates retrieved candidate chunks using a cross-encoder neural model, scoring deep semantic relevance and screening out superficially matched but contextually irrelevant provisions (e.g. filtering out helicopter operations matching &quot;CAT&quot; from CAT III all-weather inquiries).
            </p>

            {/* Toggle Enable */}
            <div className="flex items-start justify-between gap-4 p-3 bg-slate-950/60 rounded-lg border border-slate-800">
              <div className="space-y-0.5">
                <div className="text-sm font-medium text-slate-200">Enable Neural Reranker Preprocessing</div>
                <div className="text-xs text-slate-400">
                  Active for /llm/ask, /search/hybrid, and research activities. Re-ranks wider candidate pools before prompt assembly.
                </div>
              </div>
              <input
                type="checkbox"
                checked={form.enableReranker !== false}
                onChange={(e) => setForm({ ...form, enableReranker: e.target.checked })}
                className="mt-1 w-4 h-4 rounded text-emerald-600 focus:ring-emerald-500 bg-slate-900 border-slate-700"
              />
            </div>

            {/* Model Input & Presets */}
            {form.enableReranker !== false && (
              <div className="space-y-3 p-3.5 bg-slate-950/40 rounded-xl border border-slate-800">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-slate-300">
                      Reranker Model Identifier
                    </label>
                    <button
                      type="button"
                      onClick={handleTestReranker}
                      disabled={testingReranker}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-emerald-400 bg-emerald-950/60 hover:bg-emerald-900/60 border border-emerald-800/80 rounded-md transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3 h-3 ${testingReranker ? 'animate-spin' : ''}`} />
                      {testingReranker ? 'Testing...' : 'Test Reranker'}
                    </button>
                  </div>
                  <input
                    type="text"
                    value={form.rerankerModel || ''}
                    onChange={(e) => setForm({ ...form, rerankerModel: e.target.value })}
                    placeholder="text-embedding-baai-bge-reranker-v2-m3-m3"
                    className="w-full px-3 py-2 text-xs bg-slate-900 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 font-mono"
                  />
                </div>

                {/* Quick Model Presets */}
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                  <span className="text-[11px] text-slate-400">Presets:</span>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, rerankerModel: 'text-embedding-baai-bge-reranker-v2-m3-m3' })}
                    className="px-2 py-0.5 bg-slate-900 hover:bg-slate-800 text-emerald-300 border border-emerald-900/60 rounded font-mono text-[10px]"
                  >
                    LM Studio (bge-reranker-v2-m3)
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, rerankerModel: 'BAAI/bge-reranker-v2-m3' })}
                    className="px-2 py-0.5 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded font-mono text-[10px]"
                  >
                    BAAI/bge-reranker-v2-m3
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, rerankerModel: 'BAAI/bge-reranker-large' })}
                    className="px-2 py-0.5 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded font-mono text-[10px]"
                  >
                    BAAI/bge-reranker-large
                  </button>
                </div>

                {/* Test Result Indicator */}
                {rerankerTestResult && (
                  <div
                    className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                      rerankerTestResult.success
                        ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                        : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
                    }`}
                  >
                    {rerankerTestResult.success ? (
                      <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    )}
                    <div className="space-y-0.5">
                      <div className="font-semibold">
                        {rerankerTestResult.success ? 'Reranker Model Operational' : 'Reranker Initialization Failed'}
                      </div>
                      <div className="text-[11px] opacity-90">{rerankerTestResult.message}</div>
                      {rerankerTestResult.success && (
                        <div className="text-[10px] text-slate-400 font-mono mt-1 flex gap-3">
                          <span>Device: {rerankerTestResult.device?.toUpperCase()}</span>
                          {rerankerTestResult.test_inference_seconds !== undefined && (
                            <span>Latency: {(rerankerTestResult.test_inference_seconds * 1000).toFixed(1)}ms</span>
                          )}
                          {rerankerTestResult.test_score !== undefined && (
                            <span>Sample Score: {rerankerTestResult.test_score}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Section 4: Regulatory Defaults */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-slate-800">
            <div className="space-y-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Default Regulation Origin
              </label>
              <select
                value={form.defaultOrigin}
                onChange={(e) => setForm({ ...form, defaultOrigin: e.target.value as any })}
                className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-sky-500"
              >
                <option value="all">All Sources (EASA + EU + FAA)</option>
                <option value="easa">EASA Easy Access Rules</option>
                <option value="eu">EU Formex Standards</option>
                <option value="faa">FAA Federal Regulations (14 CFR)</option>
                <option value="manual">Internal Documents</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Default Top K Chunks
              </label>
              <select
                value={form.defaultTopK}
                onChange={(e) => setForm({ ...form, defaultTopK: Number(e.target.value) })}
                className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              >
                <option value={3}>3 chunks</option>
                <option value={5}>5 chunks (Standard)</option>
                <option value={8}>8 chunks</option>
                <option value={10}>10 chunks</option>
              </select>
            </div>
          </div>

          {/* Section 5: Appearance & Theme */}
          <div className="space-y-3 pt-4 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Interface Theme
              </label>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                Appearance
              </span>
            </div>

            <p className="text-xs text-slate-400">
              Select your preferred visual style. AeroLex EU dynamically tailors color contrast and surface layers.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => handleThemeChange('dark')}
                className={`flex items-center justify-between p-3 rounded-lg border transition-all cursor-pointer ${
                  (form.theme || 'dark') === 'dark'
                    ? 'bg-slate-800/80 border-sky-500 text-sky-400 shadow-sm'
                    : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Moon className="w-4 h-4 text-sky-400" />
                  <div className="text-left">
                    <span className="text-xs font-medium text-slate-200 block">Dark Mode</span>
                    <span className="text-[10px] text-slate-400 block">Default dark canvas</span>
                  </div>
                </div>
                {(form.theme || 'dark') === 'dark' && <Check className="w-4 h-4 text-sky-400" />}
              </button>

              <button
                type="button"
                onClick={() => handleThemeChange('light')}
                className={`flex items-center justify-between p-3 rounded-lg border transition-all cursor-pointer ${
                  form.theme === 'light'
                    ? 'bg-slate-800/80 border-amber-500 text-amber-500 shadow-sm'
                    : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Sun className="w-4 h-4 text-amber-400" />
                  <div className="text-left">
                    <span className="text-xs font-medium text-slate-200 block">Light Mode</span>
                    <span className="text-[10px] text-slate-400 block">Crisp, clean light theme</span>
                  </div>
                </div>
                {form.theme === 'light' && <Check className="w-4 h-4 text-amber-500" />}
              </button>
            </div>
          </div>

          {/* Section 6: Navigation & Tab Visibility */}
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-sky-400" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Navigation & Tab Visibility
                </h3>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                UI Customization
              </span>
            </div>

            <p className="text-xs text-slate-400">
              Customize which tabs appear in the top navigation bar. Toggle specialized tools and diagnostic views on demand.
            </p>

            <div className="space-y-2.5">
              {/* Governance */}
              <div
                onClick={() => setForm({ ...form, showGovernanceTab: !form.showGovernanceTab })}
                className={`flex items-start justify-between gap-4 p-3 rounded-lg border cursor-pointer transition-colors ${
                  form.showGovernanceTab
                    ? 'bg-purple-950/20 border-purple-800/60 hover:bg-purple-950/30'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <ShieldCheck className={`w-4 h-4 mt-0.5 shrink-0 ${form.showGovernanceTab ? 'text-purple-400' : 'text-slate-400'}`} />
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium text-slate-200">Governance</div>
                    <div className="text-xs text-slate-400">
                      Audit regulatory corpus, inspect obsolescence candidates, and manage document status.
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!form.showGovernanceTab}
                  onChange={(e) => {
                    e.stopPropagation();
                    setForm({ ...form, showGovernanceTab: e.target.checked });
                  }}
                  className="mt-1 w-4 h-4 rounded text-purple-600 focus:ring-purple-500 bg-slate-900 border-slate-700 cursor-pointer"
                />
              </div>

              {/* Document Builder */}
              <div
                onClick={() => setForm({ ...form, showDocumentBuilderTab: !form.showDocumentBuilderTab })}
                className={`flex items-start justify-between gap-4 p-3 rounded-lg border cursor-pointer transition-colors ${
                  form.showDocumentBuilderTab
                    ? 'bg-teal-950/20 border-teal-800/60 hover:bg-teal-950/30'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <FileText className={`w-4 h-4 mt-0.5 shrink-0 ${form.showDocumentBuilderTab ? 'text-teal-400' : 'text-slate-400'}`} />
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium text-slate-200">Document Builder</div>
                    <div className="text-xs text-slate-400">
                      Drafting workspace, custom section composition, and export tools.
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!form.showDocumentBuilderTab}
                  onChange={(e) => {
                    e.stopPropagation();
                    setForm({ ...form, showDocumentBuilderTab: e.target.checked });
                  }}
                  className="mt-1 w-4 h-4 rounded text-teal-600 focus:ring-teal-500 bg-slate-900 border-slate-700 cursor-pointer"
                />
              </div>

              {/* Query Memory */}
              <div
                onClick={() => setForm({ ...form, showQueryMemoryTab: !form.showQueryMemoryTab })}
                className={`flex items-start justify-between gap-4 p-3 rounded-lg border cursor-pointer transition-colors ${
                  form.showQueryMemoryTab
                    ? 'bg-sky-950/20 border-sky-800/60 hover:bg-sky-950/30'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <Brain className={`w-4 h-4 mt-0.5 shrink-0 ${form.showQueryMemoryTab ? 'text-sky-400' : 'text-slate-400'}`} />
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium text-slate-200">Query Memory</div>
                    <div className="text-xs text-slate-400">
                      View past assistant inquiries, re-ask queries, and pin context items.
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!form.showQueryMemoryTab}
                  onChange={(e) => {
                    e.stopPropagation();
                    setForm({ ...form, showQueryMemoryTab: e.target.checked });
                  }}
                  className="mt-1 w-4 h-4 rounded text-sky-600 focus:ring-sky-500 bg-slate-900 border-slate-700 cursor-pointer"
                />
              </div>

              {/* Schema Extractor */}
              <div
                onClick={() => setForm({ ...form, showSchemaExtractorTab: !form.showSchemaExtractorTab })}
                className={`flex items-start justify-between gap-4 p-3 rounded-lg border cursor-pointer transition-colors ${
                  form.showSchemaExtractorTab
                    ? 'bg-sky-950/20 border-sky-800/60 hover:bg-sky-950/30'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <Code2 className={`w-4 h-4 mt-0.5 shrink-0 ${form.showSchemaExtractorTab ? 'text-sky-400' : 'text-slate-400'}`} />
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium text-slate-200">Schema Extractor</div>
                    <div className="text-xs text-slate-400">
                      Technical utility to inspect XML/Formex schemas and structural document trees.
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!form.showSchemaExtractorTab}
                  onChange={(e) => {
                    e.stopPropagation();
                    setForm({ ...form, showSchemaExtractorTab: e.target.checked });
                  }}
                  className="mt-1 w-4 h-4 rounded text-sky-600 focus:ring-sky-500 bg-slate-900 border-slate-700 cursor-pointer"
                />
              </div>

              {/* Local Cache */}
              <div
                onClick={() => setForm({ ...form, showLocalCacheTab: !form.showLocalCacheTab })}
                className={`flex items-start justify-between gap-4 p-3 rounded-lg border cursor-pointer transition-colors ${
                  form.showLocalCacheTab
                    ? 'bg-sky-950/20 border-sky-800/60 hover:bg-sky-950/30'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <Database className={`w-4 h-4 mt-0.5 shrink-0 ${form.showLocalCacheTab ? 'text-sky-400' : 'text-slate-400'}`} />
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium text-slate-200">Local Cache</div>
                    <div className="text-xs text-slate-400">
                      Diagnostic tool to view cached files, vector chunk tables, and storage size.
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={!!form.showLocalCacheTab}
                  onChange={(e) => {
                    e.stopPropagation();
                    setForm({ ...form, showLocalCacheTab: e.target.checked });
                  }}
                  className="mt-1 w-4 h-4 rounded text-sky-600 focus:ring-sky-500 bg-slate-900 border-slate-700 cursor-pointer"
                />
              </div>
            </div>
          </div>

          {/* Section 6: Memory Storage Management */}
          <div className="pt-4 border-t border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">
                Stored Queries: <strong className="text-slate-200 font-mono">{memoryCount}</strong> recorded in local memory
              </span>
              {!showClearConfirm ? (
                <button
                  type="button"
                  onClick={() => setShowClearConfirm(true)}
                  className="text-xs text-rose-400 hover:text-rose-300 hover:underline"
                >
                  Clear Query Memory
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleClearMemory(true)}
                    className="px-2 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded"
                  >
                    Keep Pinned
                  </button>
                  <button
                    type="button"
                    onClick={() => handleClearMemory(false)}
                    className="px-2 py-1 text-xs bg-rose-950 text-rose-300 hover:bg-rose-900 rounded"
                  >
                    Clear All
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowClearConfirm(false)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-900/90 shrink-0">
          <div>
            {onOpenAbout && (
              <button
                type="button"
                onClick={() => {
                  handleClose();
                  onOpenAbout();
                }}
                className="text-xs text-slate-400 hover:text-sky-400 hover:underline flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <Info className="w-3.5 h-3.5 text-sky-400" />
                <span>About AeroLex EU</span>
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="px-4 py-2 text-xs font-medium text-white bg-sky-600 hover:bg-sky-500 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Save Preferences</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
