/**
 * Clean API Client for Regulation Assistant API
 * Directly interacts with live FastAPI endpoints:
 * - GET /search (Semantic vector search)
 * - GET /search/keyword (BM25 SQLite FTS5 search with optional LLM expansion)
 * - GET /search/docs (Semantic search returning full markdown documents)
 * - POST /llm/ask (Contextual regulatory Q&A)
 * - POST /llm/extract (JSON schema extraction)
 */

import { get, set, keys } from 'idb-keyval';

import {
  AppSettings,
  ConnectionStatus,
  KeywordSearchResponse,
  LLMAskRequest,
  LLMExtractRequest,
  RegulationOrigin,
  SearchDocResponse,
  SearchResponse,
  ResearchJobSummary,
  ResearchJobDetail,
  CatalogResponse,
  BatchDownloadResponse,
  DownloadedDocItem,
  WorkspaceFtsResponse,
  RegulationQualifier,
  RegulationQualifiersResponse,
  SurroundingChunk,
  ChunkContextResponse,
  ChunkContextSummaryResponse,
  ManualDocumentRequest,
  ManualDocumentResponse,
  SkybraryCategoriesResponse,
  SkybrarySearchResponse,
  CreateNoteRequest,
  NoteActionResponse,
  NoteSummaryItem,
  NoteDetailResponse,
  GovernanceStats,
  BatchGovernanceResponse,
  CategoryGovernanceResponse,
  SkybraryTopicItem,
  SkybraryTopicGovernanceResponse,
  UploadAnalysisResponse,
  IngestConfirmRequest,
  IngestionResultResponse,
  CandidateTitleItem,
  ObsolescenceCandidateFinding,
  AiObsolescenceScanResponse,
} from '../types';

const SETTINGS_KEY = 'aerolex_eu_settings_v2';

export const DEFAULT_SETTINGS: AppSettings = {
  apiUrl: '/api',
  apiAuthToken: '',
  defaultOrigin: 'all',
  defaultTopK: 5,
  defaultKeywordUseLLM: true,
  enableQueryMemoryContext: true,
  maxMemoryContextItems: 5,
  researchProvider: 'local',
  geminiApiKey: '',
  geminiModel: 'gemini-3.5-flash',
  showGovernanceTab: true,
  showDocumentBuilderTab: false,
  showQueryMemoryTab: false,
  showSchemaExtractorTab: false,
  showLocalCacheTab: false,
  enableReranker: true,
  rerankerModel: 'text-embedding-baai-bge-reranker-v2-m3-m3',
  theme: 'dark',
};

export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const parsed = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
      // Auto-migrate deprecated or empty Gemini models to gemini-3.5-flash
      if (!parsed.geminiModel || parsed.geminiModel.startsWith('gemini-1.') || parsed.geminiModel.startsWith('gemini-2.')) {
        parsed.geminiModel = 'gemini-3.5-flash';
      }
      // Ensure hidden tabs default to false if undefined in previously saved settings
      parsed.showGovernanceTab = Boolean(parsed.showGovernanceTab);
      parsed.showDocumentBuilderTab = Boolean(parsed.showDocumentBuilderTab);
      parsed.showQueryMemoryTab = Boolean(parsed.showQueryMemoryTab);
      parsed.showSchemaExtractorTab = Boolean(parsed.showSchemaExtractorTab);
      parsed.showLocalCacheTab = Boolean(parsed.showLocalCacheTab);
      parsed.enableReranker = parsed.enableReranker !== false;
      parsed.rerankerModel = parsed.rerankerModel || 'text-embedding-baai-bge-reranker-v2-m3-m3';
      parsed.theme = parsed.theme === 'light' ? 'light' : 'dark';
      return parsed;
    }
  } catch (e) {
    console.error('Error loading settings from localStorage', e);
  }
  return DEFAULT_SETTINGS;
}

export function saveSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (e) {
    console.error('Error saving settings to localStorage', e);
  }
}

function cleanUrl(baseUrl: string): string {
  const trimmed = baseUrl.trim();
  if (trimmed === '/' || trimmed === '/api') return trimmed;
  return trimmed.replace(/\/+$/, '');
}

export async function pingFastApi(baseUrl: string, token?: string): Promise<ConnectionStatus> {
  const clean = cleanUrl(baseUrl);
  const startTime = performance.now();
  
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);

    const headers: Record<string, string> = {
      'Accept': 'application/json',
    };
    if (token && token.trim()) {
      headers['Authorization'] = `Bearer ${token.trim()}`;
    }

    const testUrl = `${clean}/search?query=aviation&top_k=1&origin=all`;
    const res = await fetch(testUrl, {
      method: 'GET',
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const latency = Math.round(performance.now() - startTime);

    if (res.ok) {
      // Also verify if OPTIONS preflight is allowed on /llm/ask when testing direct URL
      if (!clean.startsWith('/')) {
        try {
          const preflight = await fetch(`${clean}/llm/ask`, {
            method: 'OPTIONS',
            headers: {
              'Access-Control-Request-Method': 'POST',
              'Access-Control-Request-Headers': 'content-type',
            },
          });
          if (preflight.status === 405) {
            return {
              state: 'cors_issue',
              message: `GET /search connected (${latency}ms), but OPTIONS /llm/ask returned 405 Method Not Allowed. Switch to the '/api' Vite Proxy preset or configure CORSMiddleware in FastAPI.`,
              latencyMs: latency,
              lastChecked: Date.now()
            };
          }
        } catch {
          // Preflight fetch error
        }
      }

      return {
        state: 'connected',
        message: `FastAPI online (${latency}ms latency)`,
        latencyMs: latency,
        lastChecked: Date.now()
      };
    } else {
      return {
        state: 'offline',
        message: `FastAPI responded with HTTP ${res.status}: ${res.statusText}`,
        latencyMs: latency,
        lastChecked: Date.now()
      };
    }
  } catch (err: any) {
    const latency = Math.round(performance.now() - startTime);
    if (err.name === 'AbortError') {
      return {
        state: 'offline',
        message: 'Connection timed out after 4s (FastAPI server unreachable)',
        latencyMs: latency,
        lastChecked: Date.now()
      };
    }

    const errStr = String(err).toLowerCase();
    if (errStr.includes('failed to fetch') || errStr.includes('networkerror') || errStr.includes('cors')) {
      return {
        state: 'cors_issue',
        message: 'Cannot reach endpoint or CORS is not enabled. Switch to the "/api" Vite Proxy preset or check FastAPI host.',
        latencyMs: latency,
        lastChecked: Date.now()
      };
    }

    return {
      state: 'offline',
      message: err.message || 'Cannot connect to FastAPI server',
      latencyMs: latency,
      lastChecked: Date.now()
    };
  }
}

/**
 * GET /search
 * Semantic vector search
 */
export async function searchRegulations(
  query: string,
  topK: number = 5,
  origin: RegulationOrigin = 'all',
  useHyde: boolean = false,
  settings: AppSettings = loadSettings(),
  documentId?: string
): Promise<SearchResponse[]> {
  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin,
    use_hyde: String(useHyde),
    rerank: String(Boolean(settings.enableReranker))
  });
  if (settings.rerankerModel) {
    params.append('reranker_model', settings.rerankerModel);
  }
  if (documentId) {
    params.append('document_id', documentId);
  }

  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search?${params.toString()}`, {
      method: 'GET',
      headers,
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/search: ${res.statusText}`);
    }
    const data = await res.json();
    if (Array.isArray(data)) return data;
    throw new Error('Invalid response from /search: expected an array');
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    // If direct local call failed and user hasn't set /api, retry via /api proxy
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /search/keyword
 * High-speed keyword search using SQLite FTS5 with BM25 ranking and Porter stemming
 */
export async function searchKeywordRegulations(
  query: string,
  topK: number = 5,
  origin: RegulationOrigin = 'all',
  useLLM: boolean = true,
  settings: AppSettings = loadSettings(),
  documentId?: string
): Promise<KeywordSearchResponse[]> {
  const cacheKey = `aerolex_search_cache_kw_${query}_${topK}_${origin}_${useLLM}_${documentId || ''}`;
  try {
    const cached = await get<KeywordSearchResponse[]>(cacheKey);
    if (cached) return cached;
  } catch (err) {
    console.warn("Search cache read error:", err);
  }

  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin,
    use_llm: String(useLLM)
  });
  if (documentId) {
    params.append('document_id', documentId);
  }

  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/keyword?${params.toString()}`, {
      method: 'GET',
      headers,
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/search/keyword: ${res.statusText}`);
    }
    const data = await res.json();
    if (Array.isArray(data)) {
      try { await set(cacheKey, data); } catch (e) { console.warn("Search cache write error:", e); }
      return data;
    }
    throw new Error('Invalid response from /search/keyword: expected an array');
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /search/hybrid
 * Reciprocal Rank Fusion of keyword and semantic search
 */
export async function searchHybridRegulations(
  query: string,
  topK: number = 5,
  origin: RegulationOrigin = 'all',
  useHyde: boolean = false,
  settings: AppSettings = loadSettings(),
  documentId?: string
): Promise<KeywordSearchResponse[]> {
  const cacheKey = `aerolex_search_cache_hybrid_${query}_${topK}_${origin}_${useHyde}_${documentId || ''}`;
  try {
    const cached = await get<KeywordSearchResponse[]>(cacheKey);
    if (cached) return cached;
  } catch (err) {
    console.warn("Search cache read error:", err);
  }

  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin,
    use_hyde: String(useHyde),
    rerank: String(Boolean(settings.enableReranker))
  });
  if (settings.rerankerModel) {
    params.append('reranker_model', settings.rerankerModel);
  }
  if (documentId) {
    params.append('document_id', documentId);
  }

  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/hybrid?${params.toString()}`, {
      method: 'GET',
      headers,
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/search/hybrid: ${res.statusText}`);
    }
    const data = await res.json();
    if (Array.isArray(data)) {
      try { await set(cacheKey, data); } catch (e) { console.warn("Search cache write error:", e); }
      return data;
    }
    throw new Error('Invalid response from /search/hybrid: expected an array');
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /search/docs
 * Semantic search returning full markdown documents
 */
export async function searchDocsRegulations(
  query: string,
  topK: number = 5,
  origin: RegulationOrigin = 'all',
  useHyde: boolean = false,
  settings: AppSettings = loadSettings(),
  documentId?: string
): Promise<SearchDocResponse[]> {
  const cacheKey = `aerolex_search_cache_docs_${query}_${topK}_${origin}_${useHyde}_${documentId || ''}`;
  try {
    const cached = await get<SearchDocResponse[]>(cacheKey);
    if (cached) return cached;
  } catch (err) {
    console.warn("Search cache read error:", err);
  }

  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin,
    use_hyde: String(useHyde)
  });
  if (documentId) {
    params.append('document_id', documentId);
  }

  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/docs?${params.toString()}`, {
      method: 'GET',
      headers,
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/search/docs: ${res.statusText}`);
    }
    const data = await res.json();
    if (Array.isArray(data)) {
      try { await set(cacheKey, data); } catch (e) { console.warn("Search cache write error:", e); }
      return data;
    }
    throw new Error('Invalid response from /search/docs: expected an array');
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /search/chunks/{chunk_id}/context
 * Retrieve immediate surrounding chunks from the same document in strict sequence
 */
export async function getChunkContext(
  chunkId: string,
  window: number = 2,
  settings: AppSettings = loadSettings()
): Promise<ChunkContextResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/chunks/${encodeURIComponent(chunkId)}/context?window=${window}`, {
      method: 'GET',
      headers,
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from /search/chunks/context: ${res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /search/chunks/{chunk_id}/context-summary
 * Grabs surrounding chunks and asks LLM to summarize context & practical implications
 */
export async function getChunkContextSummary(
  chunkId: string,
  query: string,
  window: number = 2,
  settings: AppSettings = loadSettings()
): Promise<ChunkContextSummaryResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const body = JSON.stringify({
    query: query.trim(),
    window: window,
    provider: settings.researchProvider || 'local',
    gemini_api_key: settings.geminiApiKey || undefined,
    gemini_model: settings.geminiModel || undefined,
  });

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/chunks/${encodeURIComponent(chunkId)}/context-summary`, {
      method: 'POST',
      headers,
      body,
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from /search/chunks/context-summary: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /search/docs/{document_id}
 * Fetch full markdown document for a specific document_id
 */
export async function getDocumentMarkdown(
  documentId: string,
  settings: AppSettings = loadSettings(),
  query?: string
): Promise<{ document_id: string; markdown_doc: string; section_scores?: {sectionId: string, score: number}[] }> {
  // Use a different cache key if query is provided, or just ignore cache
  const cacheKey = query ? `aerolex_doc_cache_${documentId}_${query}` : `aerolex_doc_cache_${documentId}`;
  try {
    const cached = await get<{ document_id: string; markdown_doc: string; section_scores?: {sectionId: string, score: number}[] }>(cacheKey);
    if (cached) return cached;
  } catch (err) {
    console.warn("Doc cache read error:", err);
  }

  const clean = cleanUrl(settings.apiUrl);
  
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }
  
  const doFetch = async (targetBase: string) => {
    const url = new URL(`${targetBase}/search/docs/${encodeURIComponent(documentId)}`, window.location.origin);
    if (query) {
      url.searchParams.append('query', query);
    }
    const res = await fetch(targetBase.startsWith('http') ? url.toString() : url.pathname + url.search, { headers });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/search/docs`);
    }
    const data = await res.json();
    try {
      await set(cacheKey, data);
    } catch (err) {
      console.warn("Doc cache write error:", err);
    }
    return data;
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

export interface AskLLMOptions {
  prompt?: string;
  messages?: { role: string; content: string }[];
  chunkIds?: string[] | null;
  contextSections?: import('../types').DocSection[] | null;
  memoryContext?: string;
  origin?: string;
  origins?: string[] | null;
  keywordFilter?: string | null;
  domain?: string | null;
  domains?: string[] | null;
  stakeholder?: string | null;
  documentIds?: string[] | null;
  topK?: number;
  useHyde?: boolean;
  contextWindow?: number;
  settings?: AppSettings;
}

/**
 * POST /llm/ask
 * Ask question to LLM (LM Studio or Gemini) with multi-turn messages, hybrid retrieval, and surrounding context.
 */
export async function askLLM(
  promptOrOptions: string | AskLLMOptions,
  chunkIds?: string[] | null,
  contextSections?: import('../types').DocSection[] | null,
  memoryContext?: string,
  customSettings?: AppSettings
): Promise<{
  answer: string;
  referencedChunks: any[];
  suggestedFollowups?: string[];
  providerInfo?: Record<string, any>;
  rawResponse?: any;
}> {
  let options: AskLLMOptions;
  if (typeof promptOrOptions === 'string') {
    options = {
      prompt: promptOrOptions,
      chunkIds: chunkIds,
      contextSections: contextSections,
      memoryContext: memoryContext,
      settings: customSettings || loadSettings(),
    };
  } else {
    options = {
      ...promptOrOptions,
      settings: promptOrOptions.settings || customSettings || loadSettings(),
    };
  }

  const activeSettings = options.settings || loadSettings();
  const clean = cleanUrl(activeSettings.apiUrl);

  let finalPrompt = options.prompt || '';
  if (options.memoryContext && options.memoryContext.trim() && finalPrompt) {
    finalPrompt = `[CONTEXT FROM PREVIOUS USER QUERIES IN THIS SESSION]:\n${options.memoryContext.trim()}\n\n[USER INQUIRY]:\n${finalPrompt}`;
  }

  const reqBody: any = {
    prompt: finalPrompt || undefined,
    messages: options.messages && options.messages.length > 0 ? options.messages : undefined,
    chunk_ids: options.chunkIds && options.chunkIds.length > 0 ? options.chunkIds : null,
    context_sections: options.contextSections && options.contextSections.length > 0 ? options.contextSections : null,
    origin: options.origin || activeSettings.defaultOrigin || 'all',
    origins: options.origins && options.origins.length > 0 ? options.origins : undefined,
    keyword_filter: options.keywordFilter || undefined,
    domain: options.domain || undefined,
    domains: options.domains || undefined,
    stakeholder: options.stakeholder || null,
    document_ids: options.documentIds && options.documentIds.length > 0 ? options.documentIds : null,
    top_k: options.topK || activeSettings.defaultTopK || 5,
    use_hyde: options.useHyde || false,
    context_window: options.contextWindow ?? 1,
    rerank: activeSettings.enableReranker !== false,
    reranker_model: activeSettings.rerankerModel || 'text-embedding-baai-bge-reranker-v2-m3-m3',
    provider: activeSettings.researchProvider || 'local',
    gemini_api_key: activeSettings.geminiApiKey || undefined,
    gemini_model: activeSettings.geminiModel || undefined,
    temperature: 0.2,
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (activeSettings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${activeSettings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/llm/ask`, {
      method: 'POST',
      headers,
      body: JSON.stringify(reqBody),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/llm/ask: ${res.statusText}`);
    }

    const data = await res.json();
    let textAnswer = '';
    let referencedChunks: any[] = [];
    let suggestedFollowups: string[] | undefined = undefined;
    let providerInfo: Record<string, any> | undefined = undefined;

    if (typeof data === 'string') {
      textAnswer = data;
    } else if (typeof data === 'object' && data !== null) {
      textAnswer = data.answer || data.response || data.result || data.text || JSON.stringify(data, null, 2);
      if (Array.isArray(data.referenced_chunks)) {
        referencedChunks = data.referenced_chunks;
      }
      if (Array.isArray(data.suggested_followups)) {
        suggestedFollowups = data.suggested_followups;
      }
      if (data.provider_info) {
        providerInfo = data.provider_info;
      }
    } else {
      textAnswer = String(data);
    }

    return {
      answer: textAnswer,
      referencedChunks,
      suggestedFollowups,
      providerInfo,
      rawResponse: data,
    };
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /llm/extract
 * Guaranteed structured JSON extraction using user-provided schema
 */
export async function extractStructuredData(
  text: string,
  jsonSchema: Record<string, any>,
  settings: AppSettings = loadSettings()
): Promise<any> {
  const clean = cleanUrl(settings.apiUrl);
  const reqBody: LLMExtractRequest = {
    text,
    json_schema: jsonSchema,
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/llm/extract`, {
      method: 'POST',
      headers,
      body: JSON.stringify(reqBody),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/llm/extract: ${res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /research/jobs
 * Initiates an autonomous deep regulatory research job
 */
export async function createResearchJob(
  query: string,
  recursionLevel: number = 2,
  forceRefresh: boolean = false,
  settings: AppSettings = loadSettings(),
  origins?: string[] | null,
  documentIds?: string[] | null
): Promise<{ job_id: string; cached?: boolean; status?: string; message?: string }> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/research/jobs`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ 
        query: query.trim(), 
        recursion_level: recursionLevel,
        force_refresh: forceRefresh,
        provider: settings.researchProvider || 'local',
        gemini_api_key: settings.geminiApiKey?.trim() || undefined,
        gemini_model: settings.geminiModel?.trim() || 'gemini-3.5-flash',
        origins: origins && origins.length > 0 ? origins : undefined,
        document_ids: documentIds && documentIds.length > 0 ? documentIds : undefined,
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from ${targetBase}/research/jobs: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /research/jobs
 * Returns a lightweight summary of all research jobs
 */
export async function listResearchJobs(
  settings: AppSettings = loadSettings()
): Promise<ResearchJobSummary[]> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/research/jobs`, { method: 'GET', headers });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/research/jobs: ${res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /research/jobs/:id
 * Returns full details of a specific research job (including report and referenced chunks)
 */
export async function getResearchJob(
  jobId: string,
  settings: AppSettings = loadSettings()
): Promise<ResearchJobDetail> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/research/jobs/${encodeURIComponent(jobId)}`, { method: 'GET', headers });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/research/jobs/${jobId}: ${res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * DELETE /research/jobs/:id
 * Deletes a research job
 */
export async function deleteResearchJob(
  jobId: string,
  settings: AppSettings = loadSettings()
): Promise<void> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/research/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE', headers });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/research/jobs/${jobId}: ${res.statusText}`);
    }
  };

  try {
    await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      await doFetch('/api');
      return;
    }
    throw err;
  }
}

/**
 * POST /research/jobs/:id/generate-comprehensive
 * Triggers sub-research jobs addressing identified gaps and generates a comprehensive report.
 */
export async function generateComprehensiveReport(
  jobId: string,
  settings: AppSettings = loadSettings()
): Promise<{ job_id: string; status: string; message: string }> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const payload = {
    provider: settings.researchProvider || 'local',
    gemini_api_key: settings.geminiApiKey || undefined,
    gemini_model: settings.geminiModel || 'gemini-3.5-flash',
  };

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/research/jobs/${encodeURIComponent(jobId)}/generate-comprehensive`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /research/test-gemini
 * Validates a Google Gemini API Key and checks model connectivity.
 */
export async function testGeminiApiKey(
  apiKey: string,
  model: string = 'gemini-3.5-flash',
  settings: AppSettings = loadSettings()
): Promise<{ success: boolean; message: string; model?: string }> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/research/test-gemini`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        api_key: apiKey.trim(),
        model: model.trim() || 'gemini-3.5-flash',
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    const data = await res.json();
    const isConn = Boolean(
      data.success === true ||
      data.status === 'connected' ||
      (typeof data.message === 'string' && data.message.toLowerCase().includes('successfully connected'))
    );
    return {
      success: isConn,
      message: data.message || (isConn ? 'Successfully connected to Google Gemini Cloud.' : 'Gemini validation completed.'),
      model: data.model || model,
    };
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

// =============================================================
// Regulations Catalog & Workspace FTS Endpoints
// =============================================================

/**
 * GET /regulations/catalog
 * Retrieve the catalog of European aviation regulations with title search and metadata
 */
export async function getRegulationsCatalog(
  params: {
    query?: string;
    origin?: RegulationOrigin | string;
    subtopic?: string;
    status?: 'all' | 'active' | 'deactivated';
    stakeholder?: string;
    year_min?: number;
    year_max?: number;
    pattern_flag?: string;
    fuzzy?: boolean;
    sort_by?: 'chunks' | 'title' | 'date';
    sort_order?: 'asc' | 'desc';
    limit?: number;
    offset?: number;
  } = {},
  settings: AppSettings = loadSettings()
): Promise<CatalogResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const searchParams = new URLSearchParams();
  if (params.query) searchParams.append('query', params.query);
  if (params.origin) searchParams.append('origin', params.origin);
  if (params.subtopic) searchParams.append('subtopic', params.subtopic);
  if (params.status) searchParams.append('status', params.status);
  if (params.stakeholder) searchParams.append('stakeholder', params.stakeholder);
  if (params.year_min !== undefined) searchParams.append('year_min', String(params.year_min));
  if (params.year_max !== undefined) searchParams.append('year_max', String(params.year_max));
  if (params.pattern_flag) searchParams.append('pattern_flag', params.pattern_flag);
  if (params.fuzzy) searchParams.append('fuzzy', 'true');
  if (params.sort_by) searchParams.append('sort_by', params.sort_by);
  if (params.sort_order) searchParams.append('sort_order', params.sort_order);
  if (params.limit) searchParams.append('limit', String(params.limit));
  if (params.offset) searchParams.append('offset', String(params.offset));

  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const url = `${targetBase}/regulations/catalog?${searchParams.toString()}`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from ${targetBase}/regulations/catalog: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /regulations/governance/stats
 * Retrieves global knowledge governance and forgetting statistics
 */
export async function getGovernanceStats(
  settings: AppSettings = loadSettings()
): Promise<GovernanceStats> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/stats`, { headers });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/{document_id}/deactivate
 * Deactivates a document and its chunks in the database (knowledge forgetting)
 */
export async function deactivateDocument(
  documentId: string,
  reason: string,
  supersededBy?: string,
  settings: AppSettings = loadSettings()
): Promise<any> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const encodedId = encodeURIComponent(documentId);
    const res = await fetch(`${targetBase}/regulations/governance/${encodedId}/deactivate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        reason,
        superseded_by: supersededBy || null
      })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/{document_id}/activate
 * Reactivates a document and its chunks in the database
 */
export async function activateDocument(
  documentId: string,
  settings: AppSettings = loadSettings()
): Promise<any> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const encodedId = encodeURIComponent(documentId);
    const res = await fetch(`${targetBase}/regulations/governance/${encodedId}/activate`, {
      method: 'POST',
      headers
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/batch/deactivate
 * Batch deactivates multiple documents with a common reason
 */
export async function batchDeactivateDocuments(
  documentIds: string[],
  reason: string,
  supersededBy?: string,
  settings: AppSettings = loadSettings()
): Promise<BatchGovernanceResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/batch/deactivate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        document_ids: documentIds,
        reason,
        superseded_by: supersededBy || null
      })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/batch/activate
 * Batch reactivates multiple documents
 */
export async function batchActivateDocuments(
  documentIds: string[],
  settings: AppSettings = loadSettings()
): Promise<BatchGovernanceResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/batch/activate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        document_ids: documentIds
      })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/category/{category}/deactivate
 * Deactivates an entire category of documents
 */
export async function deactivateCategory(
  category: string,
  reason: string,
  supersededBy?: string,
  settings: AppSettings = loadSettings()
): Promise<CategoryGovernanceResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const encCat = encodeURIComponent(category);
    const res = await fetch(`${targetBase}/regulations/governance/category/${encCat}/deactivate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        reason,
        superseded_by: supersededBy || null
      })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/category/{category}/activate
 * Reactivates an entire category of documents
 */
export async function activateCategory(
  category: string,
  settings: AppSettings = loadSettings()
): Promise<CategoryGovernanceResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const encCat = encodeURIComponent(category);
    const res = await fetch(`${targetBase}/regulations/governance/category/${encCat}/activate`, {
      method: 'POST',
      headers
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /regulations/governance/skybrary/topics
 * Retrieve list of all SKYbrary subtopics with active/deactivated counts
 */
export async function getSkybraryTopics(
  settings: AppSettings = loadSettings()
): Promise<SkybraryTopicItem[]> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/skybrary/topics`, { headers });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/skybrary/topic/deactivate
 * Suppresses an entire SKYbrary subtopic
 */
export async function deactivateSkybraryTopic(
  topic: string,
  reason: string,
  supersededBy?: string,
  settings: AppSettings = loadSettings()
): Promise<SkybraryTopicGovernanceResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/skybrary/topic/deactivate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        topic,
        reason,
        superseded_by: supersededBy || null
      })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/skybrary/topic/activate
 * Reactivates an entire SKYbrary subtopic
 */
export async function activateSkybraryTopic(
  topic: string,
  settings: AppSettings = loadSettings()
): Promise<SkybraryTopicGovernanceResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/skybrary/topic/activate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ topic })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/governance/ai-obsolescence-scan
 * Uses aviation legal domain heuristics and LLM inference to identify candidate obsolete/superseded documents
 */
export async function scanObsolescenceWithAI(
  documents: CandidateTitleItem[],
  focus: string = 'all',
  settings: AppSettings = loadSettings()
): Promise<AiObsolescenceScanResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const payload = {
    documents,
    focus,
    provider: (settings as any).llmProvider === 'gemini' ? 'gemini' : 'local',
    gemini_api_key: (settings as any).geminiApiKey,
    gemini_model: (settings as any).geminiModel || 'gemini-3.5-flash'
  };

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/governance/ai-obsolescence-scan`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from AI obsolescence scan: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * GET /regulations/{document_id}/qualifiers
 * Retrieve supporting qualifiers (Decisions, Corrigenda, Implementing acts)
 */
export async function getRegulationQualifiers(
  documentId: string,
  settings: AppSettings = loadSettings()
): Promise<RegulationQualifiersResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const encId = encodeURIComponent(documentId);
    const url = `${targetBase}/regulations/${encId}/qualifiers`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from ${url}: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/batch
 * Fetch multiple full regulation markdown documents for local viewing and caching
 */
export async function batchDownloadRegulations(
  documentIds: string[],
  settings: AppSettings = loadSettings()
): Promise<BatchDownloadResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/batch`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ document_ids: documentIds }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from ${targetBase}/regulations/batch: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /regulations/workspace-fts
 * High-speed FTS search restricted to workspace regulations with cross-document overlap analysis
 */
export async function searchWorkspaceFts(
  query: string,
  documentIds: string[],
  topKPerDoc: number = 8,
  totalTopK: number = 50,
  settings: AppSettings = loadSettings()
): Promise<WorkspaceFtsResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/workspace-fts`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        query,
        document_ids: documentIds,
        top_k_per_doc: topKPerDoc,
        total_top_k: totalTopK,
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from ${targetBase}/regulations/workspace-fts: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Saves downloaded regulations directly into IndexedDB local cache for instant in-app viewing
 */
export async function saveRegulationsToLocalCache(documents: DownloadedDocItem[]): Promise<number> {
  let count = 0;
  for (const doc of documents) {
    try {
      const cacheKey = `aerolex_doc_cache_${doc.document_id}`;
      await set(cacheKey, {
        document_id: doc.document_id,
        markdown_doc: doc.markdown_doc,
        metadata: doc.metadata,
      });
      count++;
    } catch (e) {
      console.warn(`Failed to cache ${doc.document_id}`, e);
    }
  }
  return count;
}

/**
 * Exports regulations bundle to disk as a .json file for local offline storage
 */
export function downloadRegulationsAsJsonFile(
  documents: DownloadedDocItem[],
  filename = 'aerolex_regulations_workspace_bundle.json'
): void {
  const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(documents, null, 2));
  const downloadAnchor = document.createElement('a');
  downloadAnchor.setAttribute('href', dataStr);
  downloadAnchor.setAttribute('download', filename);
  document.body.appendChild(downloadAnchor);
  downloadAnchor.click();
  downloadAnchor.remove();
}

/**
 * Retrieves the set of document IDs currently stored in local IndexedDB
 */
export async function getCachedRegulationDocIds(): Promise<Set<string>> {
  try {
    const allKeys = await keys();
    const docIds = new Set<string>();
    for (const k of allKeys) {
      if (typeof k === 'string' && k.startsWith('aerolex_doc_cache_')) {
        docIds.add(k.replace('aerolex_doc_cache_', ''));
      }
    }
    return docIds;
  } catch (e) {
    console.warn('Failed to read cached keys from IndexedDB', e);
    return new Set();
  }
}

/**
 * POST /regulations/manual-document
 * Manually build, structure, chunk, and index an aviation regulation or policy document.
 */
export async function createManualDocument(
  data: ManualDocumentRequest,
  settings: AppSettings = loadSettings()
): Promise<ManualDocumentResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/manual-document`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from /regulations/manual-document: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Perform dedicated high-speed search across SKYbrary Bookshelf documents
 */
export async function searchSkybrary(
  params: {
    query: string;
    category?: string;
    author?: string;
    top_k?: number;
    sort_by?: 'relevance' | 'date';
  },
  settings: AppSettings = loadSettings()
): Promise<SkybrarySearchResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const qParams = new URLSearchParams({
    query: params.query,
    top_k: String(params.top_k ?? 10),
    sort_by: params.sort_by ?? 'relevance',
  });
  if (params.category && params.category !== 'all') {
    qParams.append('category', params.category);
  }
  if (params.author && params.author !== 'all') {
    qParams.append('author', params.author);
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/skybrary?${qParams.toString()}`);
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from /search/skybrary: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Retrieve all SKYbrary Bookshelf publication categories
 */
export async function getSkybraryCategories(
  settings: AppSettings = loadSettings()
): Promise<SkybraryCategoriesResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/skybrary/categories`);
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status} from /regulations/skybrary/categories: ${errText || res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

// -------------------------------------------------------------
// User Notes & Internal Documentation API Client
// -------------------------------------------------------------

/**
 * Create a new user note / documentation, chunk it by sections, and optionally embed it.
 */
export async function createNote(
  req: CreateNoteRequest,
  settings: AppSettings = loadSettings()
): Promise<NoteActionResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/notes`, {
      method: 'POST',
      headers,
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      let msg = `HTTP ${res.status} when creating note`;
      if (typeof errData?.detail === 'string') {
        msg = errData.detail;
      } else if (Array.isArray(errData?.detail)) {
        msg = errData.detail.map((d: any) => `${d.loc ? d.loc.slice(-1) : 'field'}: ${d.msg}`).join(', ');
      }
      throw new Error(msg);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Generate domain and regulatory keywords for a note using the LLM
 */
export async function generateNoteKeywords(
  req: {
    title: string;
    content?: string;
    sections?: any[];
    project?: string;
    provider?: string;
  },
  settings: AppSettings = loadSettings()
): Promise<string[]> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const payload = {
    ...req,
    provider: req.provider || (settings.researchProvider === 'gemini' ? 'gemini' : 'local'),
    gemini_api_key: settings.geminiApiKey,
    gemini_model: settings.geminiModel,
  };

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/notes/generate-keywords`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when generating note keywords`);
    }
    const data = await res.json();
    return data?.keywords || [];
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * List all user notes, optionally filtered by project
 */
export async function listNotes(
  project?: string,
  settings: AppSettings = loadSettings()
): Promise<NoteSummaryItem[]> {
  const clean = cleanUrl(settings.apiUrl);
  const qParams = new URLSearchParams();
  if (project && project.trim() && project !== 'all') {
    qParams.append('project', project.trim());
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/notes?${qParams.toString()}`);
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when listing notes`);
    }
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.notes)) return data.notes;
    return [];
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Get full note details with structured sections and rendered markdown
 */
export async function getNote(
  documentId: string,
  settings: AppSettings = loadSettings()
): Promise<NoteDetailResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/notes/${encodeURIComponent(documentId)}`);
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when getting note`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Delete a user note and its chunks
 */
export async function deleteNote(
  documentId: string,
  settings: AppSettings = loadSettings()
): Promise<NoteActionResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/notes/${encodeURIComponent(documentId)}`, {
      method: 'DELETE',
      headers,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      let msg = `HTTP ${res.status} when deleting note`;
      if (typeof errData?.detail === 'string') {
        msg = errData.detail;
      } else if (Array.isArray(errData?.detail)) {
        msg = errData.detail.map((d: any) => `${d.loc ? d.loc.slice(-1) : 'field'}: ${d.msg}`).join(', ');
      }
      throw new Error(msg);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Trigger on-demand FAISS embedding for an existing note
 */
export async function embedNote(
  documentId: string,
  settings: AppSettings = loadSettings()
): Promise<NoteActionResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/regulations/notes/${encodeURIComponent(documentId)}/embed`, {
      method: 'POST',
      headers,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when embedding note`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Analyze an uploaded document for format detection, duplicate/update comparison, and executive recommendations
 * POST /documents/analyze
 */
export async function analyzeDocumentUpload(
  file: File,
  settings: AppSettings = loadSettings()
): Promise<UploadAnalysisResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const formData = new FormData();
  formData.append('file', file);
  if (settings.geminiApiKey && settings.geminiApiKey.trim()) {
    formData.append('gemini_api_key', settings.geminiApiKey.trim());
  }
  if (settings.geminiModel && settings.geminiModel.trim()) {
    formData.append('gemini_model', settings.geminiModel.trim());
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/documents/analyze`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when analyzing document`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Confirm and execute ingestion of a staged document with executive action (none, supersede, suppress)
 * POST /documents/confirm
 */
export async function confirmDocumentIngestion(
  req: IngestConfirmRequest,
  settings: AppSettings = loadSettings()
): Promise<IngestionResultResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const payload: IngestConfirmRequest = {
    ...req,
    gemini_api_key: req.gemini_api_key ?? (settings.geminiApiKey?.trim() || undefined),
    gemini_model: req.gemini_model ?? (settings.geminiModel?.trim() || undefined),
  };

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/documents/confirm`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when confirming document ingestion`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * Direct single-step document upload and ingestion
 * POST /documents/upload
 */
export async function directDocumentUpload(
  file: File,
  executiveAction: 'none' | 'supersede' | 'suppress' = 'none',
  targetDocId?: string,
  customTitle?: string,
  customDate?: string,
  settings: AppSettings = loadSettings()
): Promise<IngestionResultResponse> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('executive_action', executiveAction);
  if (targetDocId) formData.append('target_doc_id', targetDocId);
  if (customTitle) formData.append('custom_title', customTitle);
  if (customDate) formData.append('custom_date', customDate);
  if (settings.geminiApiKey && settings.geminiApiKey.trim()) {
    formData.append('gemini_api_key', settings.geminiApiKey.trim());
  }
  if (settings.geminiModel && settings.geminiModel.trim()) {
    formData.append('gemini_model', settings.geminiModel.trim());
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/documents/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(errData?.detail || `HTTP ${res.status} when uploading document`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}

/**
 * POST /search/rerank/test
 * Test connectivity, device status, and latency of neural reranker model.
 */
export async function testReranker(
  modelName?: string,
  settings: AppSettings = loadSettings()
): Promise<{
  success: boolean;
  message: string;
  model_name?: string;
  resolved_model?: string;
  device?: string;
  cuda_available?: boolean;
  load_time_seconds?: number;
  test_inference_seconds?: number;
  test_score?: number;
  error?: string;
}> {
  const clean = cleanUrl(settings.apiUrl);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken && settings.apiAuthToken.trim()) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken.trim()}`;
  }

  const doFetch = async (targetBase: string) => {
    const res = await fetch(`${targetBase}/search/rerank/test`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ model_name: modelName || settings.rerankerModel }),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return await res.json();
  };

  try {
    return await doFetch(clean);
  } catch (err: any) {
    if (clean.includes('8000') && !clean.startsWith('/api')) {
      return await doFetch('/api');
    }
    throw err;
  }
}
