/**
 * Types for EU Aviation Regulation Assistant API & Front-end
 * Fully aligned with OpenAPI 3.1 schema (SEARCH & LLM operations)
 */

export type RegulationOrigin = 'all' | 'eu' | 'easa' | 'faa' | 'icao' | 'manual' | 'skybrary' | 'note' | 'user';

export interface ComparisonMatchItem {
  document_id: string;
  title: string;
  source: string;
  date?: string | null;
  is_active: boolean;
  superseded_by?: string | null;
  similarity_score: number;
  match_type: 'exact_duplicate' | 'update' | 'similar';
  comparison_details: string;
}

export interface UploadAnalysisResponse {
  staging_id: string;
  filename: string;
  format: string;
  workflow: string;
  category: string;
  origin: string;
  is_xml: boolean;
  detection_reason: string;
  extracted_metadata: {
    title: string;
    date?: string | null;
    year?: number | null;
    page_count?: number;
    word_count?: number;
    char_count?: number;
    sha256?: string;
    is_pdf?: boolean;
    is_xml?: boolean;
    author?: string | null;
    is_word?: boolean;
    word_format?: string;
  };
  has_conflict: boolean;
  suggested_action: 'none' | 'supersede' | 'suppress';
  suggested_target_doc_id?: string | null;
  matches: ComparisonMatchItem[];
  diagrams_detected?: number;
  diagram_details?: any[];
}

export interface IngestConfirmRequest {
  staging_id: string;
  executive_action: 'none' | 'supersede' | 'suppress';
  target_doc_id?: string | null;
  custom_title?: string | null;
  custom_date?: string | null;
  gemini_api_key?: string | null;
  gemini_model?: string | null;
}

export interface IngestionResultResponse {
  status: string;
  document_id: string;
  title: string;
  source: string;
  origin: string;
  workflow: string;
  chunks_count: number;
  embeddings_count: number;
  executive_action: string;
  target_doc_id?: string | null;
  action_summary: string;
  diagrams_detected?: number;
}

export interface SkybraryCategoryInfo {
  category: string;
  doc_count: number;
}

export interface SkybraryCategoriesResponse {
  total_categories: number;
  categories: SkybraryCategoryInfo[];
}

export interface SkybrarySearchResultItem {
  chunk_id: string;
  document_id: string;
  title: string;
  category?: string | null;
  author?: string | null;
  date?: string | null;
  page?: number | null;
  score: number;
  source_text: string;
  pdf_url?: string | null;
  summary_url?: string | null;
  pdf_filename?: string | null;
  section_path: string[];
}

export interface SkybrarySearchResponse {
  query: string;
  total_found: number;
  items: SkybrarySearchResultItem[];
}

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
  rerank_score?: number;
  rerank_rank?: number;
  original_rank?: number;
}

export interface SearchDocResponse extends SearchResponse {
  markdown_doc: string;
  matched_chunk_ids?: string[];
  matched_chunks?: { chunk_id: string; text?: string; path?: string[]; score?: number; title?: string }[];
  search_query?: string;
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
  prompt?: string;
  messages?: { role: string; content: string }[];
  chunk_ids?: string[] | null;
  context_sections?: DocSection[] | null;
  deep_research?: boolean;
  origin?: string;
  stakeholder?: string | null;
  document_ids?: string[] | null;
  top_k?: number;
  use_hyde?: boolean;
  context_window?: number;
  provider?: 'local' | 'gemini';
  gemini_api_key?: string;
  gemini_model?: string;
  temperature?: number;
}

export interface LLMAskResponse {
  answer: string;
  referenced_chunks: {
    chunk_id: string;
    document_id: string;
    title?: string;
    path: string[];
    source?: string;
    text?: string;
    score?: number;
  }[];
  suggested_followups?: string[];
  provider_info?: Record<string, any>;
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
  showGovernanceTab?: boolean;
  showDocumentBuilderTab?: boolean;
  showQueryMemoryTab?: boolean;
  showSchemaExtractorTab?: boolean;
  showLocalCacheTab?: boolean;
  enableReranker?: boolean;
  rerankerModel?: string;
  theme?: 'dark' | 'light';
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
  referencedChunks?: (SearchResponse | KeywordSearchResponse | SearchDocResponse | any)[];
  usedMemoryItemIds?: string[];
  suggestedFollowups?: string[];
  providerInfo?: Record<string, any>;
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

export interface ResearchGap {
  gap_id: string;
  topic: string;
  description: string;
  sub_query: string;
  rationale?: string | null;
}

export interface SkybraryReadingMaterial {
  document_id: string;
  title: string;
  category?: string | null;
  author?: string | null;
  summary_url?: string | null;
  pdf_url?: string | null;
  relevance_score: number;
  match_rationale?: string | null;
  key_excerpt?: string | null;
}

export interface ResearchJobSummary {
  job_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  query: string;
  recursion_level: number;
  progress?: string | null;
  has_gaps?: boolean;
  comprehensive_status?: 'NOT_STARTED' | 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  provider?: string | null;
  model?: string | null;
  origins?: string[] | null;
  document_ids?: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationSummary {
  total_evaluated: number;
  validated_count: number;
  negated_count: number;
  target_domains: string[];
  excluded_domains: string[];
  origins?: string[] | null;
  document_ids?: string[] | null;
  negated_chunks: Record<string, string>;
  validated_chunks: Record<string, string>;
  surrounding_context_expanded?: boolean;
}

export interface ResearchJobDetail extends ResearchJobSummary {
  report_markdown?: string | null;
  consulted_regulations?: ConsultedRegulation[] | null;
  referenced_chunks?: Record<string, string> | null;
  evaluation_summary?: EvaluationSummary | null;
  research_gaps?: ResearchGap[] | null;
  comprehensive_report_markdown?: string | null;
  skybrary_reading_materials?: SkybraryReadingMaterial[] | null;
  user_notes_reading_materials?: UserNoteReadingMaterial[] | null;
  eurocae_standards?: EurocaeReadingMaterial[] | null;
}

export interface EurocaeReadingMaterial {
  standard_id: string;
  reference: string;
  title: string;
  expanded_title: string;
  status: string;
  organization: string;
  working_group?: string | null;
  working_group_desc?: string | null;
  domain?: string | null;
  publication_date?: string | null;
  easa_reference?: string | null;
  relevance_score: number;
  match_rationale?: string | null;
  is_supporting_only: boolean;
}

export interface UserNoteReadingMaterial {
  document_id: string;
  title: string;
  note_type: string;
  project?: string | null;
  author?: string | null;
  date?: string | null;
  relevance_score: number;
  match_rationale?: string | null;
  key_excerpt?: string | null;
}

// -------------------------------------------------------------
// Regulations Catalog & Workspace Overlap Types
// -------------------------------------------------------------

export interface RegulationItem {
  document_id: string;
  title: string;
  raw_title?: string | null;
  date?: string | null;
  origin: 'easa' | 'eu' | 'faa' | 'manual' | string;
  subtopic?: string | null;
  source?: string | null;
  chunk_count: number;
  qualifier_count?: number;
  primary_stakeholder?: string | null;
  metadata?: Record<string, any> | null;
  is_active?: boolean;
  deactivation_reason?: string | null;
  deactivated_at?: string | null;
  superseded_by?: string | null;
  detected_years?: number[];
  primary_year?: number | null;
  obsolescence_flags?: string[];
}

export interface CandidateTitleItem {
  document_id: string;
  title: string;
  origin?: string;
  subtopic?: string | null;
  year?: number | null;
}

export interface ObsolescenceCandidateFinding {
  document_id: string;
  title: string;
  is_suspect_obsolete: boolean;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  likely_status?: string;
  detected_year?: number | null;
  reason: string;
  suggested_action: string;
  superseded_by?: string | null;
}

export interface AiObsolescenceScanResponse {
  total_scanned: number;
  flagged_count: number;
  high_confidence_count: number;
  medium_confidence_count: number;
  low_confidence_count: number;
  summary: string;
  findings: ObsolescenceCandidateFinding[];
}

export interface GovernanceLogItem {
  id: number;
  document_id: string;
  action: 'DEACTIVATE' | 'ACTIVATE' | 'SUPERSEDE' | string;
  reason?: string | null;
  superseded_by?: string | null;
  performed_at: string;
}

export interface CategoryStatsItem {
  total: number;
  active: number;
  deactivated: number;
}

export interface SkybraryTopicItem {
  topic: string;
  total: number;
  active: number;
  deactivated: number;
}

export interface SkybraryTopicGovernanceResponse {
  topic: string;
  deactivated_documents?: number;
  reactivated_documents?: number;
  affected_chunks: number;
  reason?: string;
  superseded_by?: string | null;
  message: string;
}

export interface GovernanceStats {
  total_documents: number;
  active_documents: number;
  deactivated_documents: number;
  total_chunks: number;
  active_chunks: number;
  forgotten_chunks: number;
  category_stats?: Record<string, CategoryStatsItem>;
  recent_logs: GovernanceLogItem[];
}

export interface BatchGovernanceResponse {
  deactivated_documents?: number;
  reactivated_documents?: number;
  affected_chunks: number;
  reason?: string;
  superseded_by?: string | null;
  message: string;
}

export interface CategoryGovernanceResponse {
  category: string;
  deactivated_documents?: number;
  reactivated_documents?: number;
  affected_chunks: number;
  reason?: string;
  superseded_by?: string | null;
  message: string;
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
  previous_chunk_id?: string;
  next_chunk_id?: string;
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

export interface SurroundingChunk {
  chunk_id: string;
  section_path: string[];
  text: string;
  is_target: boolean;
  position: 'before' | 'target' | 'after';
}

export interface ChunkContextResponse {
  target_chunk_id: string;
  document_id: string;
  document_title: string;
  window: number;
  total_chunks: number;
  chunks: SurroundingChunk[];
}

export interface ChunkContextSummaryResponse {
  chunk_id: string;
  document_id: string;
  document_title: string;
  query: string;
  surrounding_chunks: SurroundingChunk[];
  summary: string;
}

export interface ManualSectionInput {
  section_number: string;
  title: string;
  subpart?: string;
  subject_group?: string;
  text: string;
}

export interface ManualDocumentRequest {
  title: string;
  document_id?: string;
  source?: string;
  date?: string;
  language?: string;
  stakeholder?: string;
  description?: string;
  sections: ManualSectionInput[];
}

export interface ManualDocumentResponse {
  success: boolean;
  document_id: string;
  title: string;
  chunk_count: number;
  message: string;
}

// -------------------------------------------------------------
// User Notes & Internal Documentation Types
// -------------------------------------------------------------

export interface NoteSectionInput {
  section_number?: string;
  heading: string;
  content: string;
  tags?: string[];
  keywords?: string[];
  order_index?: number;
}

export interface CreateNoteRequest {
  title: string;
  document_id?: string;
  note_type: string;
  date?: string;
  created_by: string;
  author?: string;
  project?: string;
  is_indefinite?: boolean;
  expires_at?: string | null;
  keywords?: string[];
  tags?: string[];
  description?: string;
  auto_embed?: boolean;
  sections: NoteSectionInput[];
}

export interface NoteSummaryItem {
  document_id: string;
  title: string;
  note_type: string;
  project: string;
  author: string;
  created_by: string;
  date: string;
  chunk_count: number;
  is_embedded: boolean;
  tags: string[];
  keywords: string[];
  is_indefinite: boolean;
  expires_at?: string | null;
  is_expired?: boolean;
  created_at?: string;
}

export interface NoteSectionDetail {
  section_number?: string;
  heading: string;
  content: string;
  order_index?: number;
  chunk_id?: string;
  tags?: string[];
}

export interface NoteDetailResponse {
  document_id: string;
  title: string;
  note_type: string;
  project: string;
  author: string;
  created_by: string;
  date: string;
  chunk_count: number;
  is_embedded: boolean;
  tags: string[];
  keywords: string[];
  is_indefinite: boolean;
  expires_at?: string | null;
  is_expired?: boolean;
  description?: string;
  created_at?: string;
  sections: NoteSectionInput[];
  markdown_doc: string;
  rendered_markdown?: string;
}

export interface NoteActionResponse {
  success: boolean;
  document_id: string;
  title?: string;
  message: string;
  chunk_count?: number;
  embedded_count?: number;
  is_embedded?: boolean;
}



