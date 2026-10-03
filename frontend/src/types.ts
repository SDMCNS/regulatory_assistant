/**
 * Types for EU Aviation Regulation Assistant API & Front-end
 * Fully aligned with OpenAPI 3.1 schema (SEARCH & LLM operations)
 */

export type RegulationOrigin = 'all' | 'eu' | 'easa';

export type SearchMethod = 'semantic' | 'docs' | 'keyword' | 'hybrid';

export interface SearchResponse {
  chunk_id: string;
  score: number;
  raw_vector_score?: number;
  act_prior_score?: number;
  source: string;
  document_id: string;
  path: string[];
  text: string;
  metadata: Record<string, any>;
  primary_stakeholder?: string;
  stakeholder_scores?: Record<string, number>;
}

export interface SearchDocResponse extends SearchResponse {
  markdown_doc: string;
}

export interface RegulationQualifier {
  qualifier_id: string;
  parent_regulation_id?: string | null;
  target_regulation_ref?: string | null;
  qualifier_type: string;
  celex?: string | null;
  title: string;
  date?: string | null;
  source_file?: string | null;
  content_preview?: string | null;
  metadata?: Record<string, any>;
}

export interface RegulationQualifiersResponse {
  document_id: string;
  count: number;
  qualifiers: RegulationQualifier[];
  error?: string;
}

export interface DocSection {
  index: number;
  id: string;
  type: string;
  title: string;
  meta: Record<string, any>;
  markdown: string;
  wordCount: number;
  citationCount?: number;
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
  researchProvider?: 'local' | 'gemini';
  geminiApiKey?: string;
  geminiModel?: string;
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

export interface ConsultedRegulation {
  document_id: string;
  document_title?: string;
  title?: string;
  source?: string;
  regulation_number?: string;
  publication_date?: string;
  [key: string]: any;
}

export interface ResearchJobSummary {
  job_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  query: string;
  recursion_level: number;
  progress?: string | null;
  provider?: string | null;
  model?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationSummary {
  total_evaluated: number;
  validated_count: number;
  negated_count: number;
  target_domains: string[];
  excluded_domains: string[];
  negated_chunks: Record<string, string>;
  validated_chunks: Record<string, string>;
}

export interface ResearchJobDetail extends ResearchJobSummary {
  report_markdown?: string | null;
  consulted_regulations?: ConsultedRegulation[] | null;
  referenced_chunks?: Record<string, string> | null;
  evaluation_summary?: EvaluationSummary | null;
}

// -------------------------------------------------------------
// Regulations Catalog & Workspace Overlap Types
// -------------------------------------------------------------

export interface RegulationItem {
  document_id: string;
  title: string;
  raw_title?: string | null;
  date?: string | null;
  origin: 'easa' | 'eu';
  source?: string | null;
  chunk_count: number;
  qualifier_count?: number;
  primary_stakeholder?: string | null;
  metadata?: Record<string, any> | null;
}

export interface CatalogResponse {
  total: number;
  filtered_count: number;
  regulations: RegulationItem[];
}

export interface DownloadedDocItem {
  document_id: string;
  title: string;
  origin: string;
  markdown_doc: string;
  metadata: Record<string, any>;
  chunk_count: number;
}

export interface BatchDownloadResponse {
  count: number;
  documents: DownloadedDocItem[];
}

export interface WorkspaceChunkMatch {
  chunk_id: string;
  document_id: string;
  section_path: string[];
  section_title: string;
  source_text: string;
  text?: string;
  snippet: string;
  rank: number;
  score: number;
}

export interface DocumentOverlapSummary {
  document_id: string;
  title: string;
  origin: string;
  chunk_count: number;
  match_count: number;
  best_score: number;
  has_match: boolean;
  top_section?: string | null;
}

export interface WorkspaceOverlapSummary {
  query: string;
  total_documents_queried: number;
  total_documents_matched: number;
  overlap_rate: number;
  all_documents_matched: boolean;
  total_chunks_matched: number;
  matched_document_ids: string[];
  shared_search_terms: string[];
  document_summaries: DocumentOverlapSummary[];
}

export interface WorkspaceFtsResponse {
  query: string;
  fts_expression: string;
  total_matches: number;
  overlap_summary: WorkspaceOverlapSummary;
  results_by_document: Record<string, WorkspaceChunkMatch[]>;
  all_results: WorkspaceChunkMatch[];
}



