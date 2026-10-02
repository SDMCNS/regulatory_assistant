/**
 * Clean API Client for Regulation Assistant API
 * Directly interacts with live FastAPI endpoints:
 * - GET /search (Semantic vector search)
 * - GET /search/keyword (BM25 SQLite FTS5 search with optional LLM expansion)
 * - GET /search/docs (Semantic search returning full markdown documents)
 * - POST /llm/ask (Contextual regulatory Q&A)
 * - POST /llm/extract (JSON schema extraction)
 */

import {
  AppSettings,
  ConnectionStatus,
  KeywordSearchResponse,
  LLMAskRequest,
  LLMExtractRequest,
  RegulationOrigin,
  SearchDocResponse,
  SearchResponse,
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
};

export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
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
  settings: AppSettings = loadSettings()
): Promise<SearchResponse[]> {
  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin
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
    if (Array.isArray(data)) return data;
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
  settings: AppSettings = loadSettings()
): Promise<KeywordSearchResponse[]> {
  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin
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
    if (Array.isArray(data)) return data;
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
  settings: AppSettings = loadSettings()
): Promise<SearchDocResponse[]> {
  const clean = cleanUrl(settings.apiUrl);
  const params = new URLSearchParams({
    query: query.trim(),
    top_k: String(topK),
    origin: origin
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
    if (Array.isArray(data)) return data;
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
  settings: AppSettings = loadSettings()
): Promise<{ document_id: string; markdown_doc: string }> {
  const clean = cleanUrl(settings.apiUrl);
  
  const headers: Record<string, string> = { 'Accept': 'application/json' };
  if (settings.apiAuthToken) {
    headers['Authorization'] = `Bearer ${settings.apiAuthToken}`;
  }
  
  const doFetch = async (targetBase: string) => {
    // Avoid double encoding if it's already encoded, but safe to just use standard fetch path
    const res = await fetch(`${targetBase}/search/docs/${encodeURIComponent(documentId)}`, { headers });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} from ${targetBase}/search/docs`);
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
