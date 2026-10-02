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
  settings: AppSettings = loadSettings()
): Promise<SearchResponse[]> {
  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin,
    use_hyde: String(useHyde)
  });

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
  settings: AppSettings = loadSettings()
): Promise<KeywordSearchResponse[]> {
  const cacheKey = `aerolex_search_cache_kw_${query}_${topK}_${origin}_${useLLM}`;
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
  settings: AppSettings = loadSettings()
): Promise<KeywordSearchResponse[]> {
  const cacheKey = `aerolex_search_cache_hybrid_${query}_${topK}_${origin}_${useHyde}`;
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
    use_hyde: String(useHyde)
  });

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
  settings: AppSettings = loadSettings()
): Promise<SearchDocResponse[]> {
  const cacheKey = `aerolex_search_cache_docs_${query}_${topK}_${origin}_${useHyde}`;
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

/**
 * POST /llm/ask
 * Ask question to local LLM with optional targeted chunk IDs
 */
export async function askLLM(
  prompt: string,
  chunkIds?: string[] | null,
  contextSections?: import('../types').DocSection[] | null,
  memoryContext?: string,
  settings: AppSettings = loadSettings()
): Promise<{ answer: string; rawResponse?: any }> {
  const clean = cleanUrl(settings.apiUrl);

  let finalPrompt = prompt;
  if (memoryContext && memoryContext.trim()) {
    finalPrompt = `[CONTEXT FROM PREVIOUS USER QUERIES IN THIS SESSION]:\n${memoryContext.trim()}\n\n[USER INQUIRY]:\n${prompt}`;
  }

  const reqBody: LLMAskRequest = {
    prompt: finalPrompt,
    chunk_ids: chunkIds && chunkIds.length > 0 ? chunkIds : null,
    context_sections: contextSections && contextSections.length > 0 ? contextSections : null,
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
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

    if (typeof data === 'string') {
      textAnswer = data;
    } else if (typeof data === 'object' && data !== null) {
      textAnswer = data.answer || data.response || data.result || data.text || JSON.stringify(data, null, 2);
    } else {
      textAnswer = String(data);
    }

    return { answer: textAnswer, rawResponse: data };
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
  settings: AppSettings = loadSettings()
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
    origin?: 'all' | 'eu' | 'easa';
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


