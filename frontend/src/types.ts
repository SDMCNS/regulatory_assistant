/**
 * Types for EU Aviation Regulation Assistant API & Front-end
 * Fully aligned with OpenAPI 3.1 schema (SEARCH & LLM operations)
 */

export type RegulationOrigin = 'all' | 'eu' | 'easa';

export type SearchMethod = 'semantic' | 'docs' | 'keyword';

export interface SearchResponse {
  chunk_id: string;
  score: number;
  source: string;
  document_id: string;
  path: string[];
  text: string;
  metadata: Record<string, any>;
}

export interface SearchDocResponse extends SearchResponse {
  markdown_doc: string;
}

export interface DocSection {
  index: number;
  id: string;
  type: string;
  title: string;
  meta: Record<string, any>;
  markdown: string;
  wordCount: number;
  enabled?: boolean;
}

export interface KeywordSearchResponse {
  chunk_id: string;
  score: number;
  source: string;
  document_id: string;
  path: string[];
  text: string;
  metadata: Record<string, any>;
  expanded_terms?: string[] | null;
}

export interface LLMAskRequest {
  prompt: string;
  chunk_ids?: string[] | null;
  context_sections?: DocSection[] | null;
}

export interface LLMExtractRequest {
  text: string;
  json_schema: Record<string, any>;
}

export interface ConnectionStatus {
  state: 'connected' | 'offline' | 'checking' | 'cors_issue';
  message: string;
  latencyMs?: number;
  lastChecked?: number;
}

export interface AppSettings {
  apiUrl: string;
  apiAuthToken: string;
  defaultOrigin: RegulationOrigin;
  defaultTopK: number;
  defaultKeywordUseLLM: boolean;
  enableQueryMemoryContext: boolean;
  maxMemoryContextItems: number;
}

export interface QueryMemoryItem {
  id: string;
  timestamp: number;
  query: string;
  type: 'ask' | 'search' | 'extract';
  searchMethod?: SearchMethod;
  origin?: RegulationOrigin;
  top_k?: number;
  resultsCount?: number;
  answerSnippet?: string;
  fullAnswer?: string;
  retrievedChunks?: {
    chunk_id: string;
    document_id: string;
    source: string;
    path: string[];
    score?: number;
  }[];
  isPinned?: boolean;
  tags?: string[];
  isActiveInContext: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  referencedChunks?: (SearchResponse | KeywordSearchResponse | SearchDocResponse)[];
  usedMemoryItemIds?: string[];
  isError?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  savedSections: DocSection[];
  createdAt: number;
  updatedAt: number;
}
