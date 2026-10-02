/**
 * Settings Modal: Configure FastAPI URL, test connectivity, configure memory context & regulatory filters
 */

import React, { useState } from 'react';
import { X, Check, RefreshCw, AlertTriangle, ShieldCheck, Database, HardDrive, Terminal, Sparkles, Cloud, Cpu, Eye, EyeOff } from 'lucide-react';
import { AppSettings, ConnectionStatus } from '../types';
import { pingFastApi, saveSettings, testGeminiApiKey } from '../services/apiClient';
import { clearMemory, getQueryMemory } from '../services/memoryService';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: AppSettings;
  onSaveSettings: (newSettings: AppSettings) => void;
  connectionStatus: ConnectionStatus;
  onConnectionChange: (status: ConnectionStatus) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSaveSettings,
  connectionStatus,
  onConnectionChange,
}) => {
  const [form, setForm] = useState<AppSettings>(() => {
    const initial = { ...settings };
    if (!initial.geminiModel || initial.geminiModel.startsWith('gemini-1.') || initial.geminiModel.startsWith('gemini-2.')) {
      initial.geminiModel = 'gemini-3.5-flash';
    }
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
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
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
                <option value="all">All Sources (EU + EASA)</option>
                <option value="easa">EASA Easy Access Rules</option>
                <option value="eu">EU Formex Standards</option>
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

          {/* Section 5: Memory Storage Management */}
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
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800 bg-slate-900/90 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-2 text-xs font-medium text-white bg-sky-600 hover:bg-sky-500 rounded-lg transition-colors flex items-center gap-1.5"
          >
            <Check className="w-3.5 h-3.5" />
            <span>Save Preferences</span>
          </button>
        </div>
      </div>
    </div>
  );
};
