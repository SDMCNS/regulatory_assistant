/**
 * graphService.ts - Client API Service for Regulatory Knowledge Graph Explorer
 * Interfaces with FastAPI /graph/* endpoints.
 */

export interface GraphStats {
  total_provisions: number;
  provisions_by_type: Record<string, number>;
  relationships: Record<string, number>;
}

export interface RegulatorySource {
  id: string;
  name: string;
  description: string;
  type: string;
  color: string;
  icon: string;
  total_records: number;
  status: string;
}

export interface SkybraryTopic {
  id: string;
  name: string;
  category: string;
  description: string;
  article_count: number;
}

export interface SkybraryCategoryItem {
  name: string;
  count: number;
}

export interface SourcesCatalog {
  sources: RegulatorySource[];
  skybrary_categories: SkybraryCategoryItem[];
  total_sources: number;
}

export interface GraphSearchResult {
  id: string;
  code: string;
  title: string;
  type: string;
  source: string;
  subject?: string;
  preview?: string;
  score?: number;
}

export interface HydeCandidate {
  id: string;
  code: string;
  title: string;
  type: string;
  source: string;
  annex?: string;
  similarity_score: number;
  match_percentage: number;
  text_snippet: string;
}

export interface HydeResponse {
  query: string;
  hypothetical_document: string;
  top_k: number;
  candidates: HydeCandidate[];
  active_sources: string[];
}

export interface D3GraphNode {
  id: string;
  label: string;
  type: string;
  title?: string;
  legal_force?: string;
  subject?: string;
  category?: string;
  role_type?: string;
  text?: string;
  is_anchor?: boolean;
  annex?: string;
  similarity_score?: number;
  similarity_reason?: string;
  shared_rules?: number;
  rule_count?: number;
  total_topics?: number;
  annex_count?: number;
  target_doc_id?: string;
  // D3 force simulation attributes
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface EdgeRuleItem {
  id: string;
  code: string;
  title: string;
  content_type?: string;
  legal_force?: string;
  annex?: string;
  annex_name?: string;
  text_snippet?: string;
  relevance?: string;
}

export interface D3GraphLink {
  source: string | D3GraphNode;
  target: string | D3GraphNode;
  type: string;
  label?: string;
  score?: number;
  reason?: string;
  rule_count?: number;
  shared_rules?: number;
  rules?: EdgeRuleItem[];
}

export interface D3GraphData {
  query?: string;
  anchor?: any;
  target?: any;
  concept?: any;
  nodes: D3GraphNode[];
  links: D3GraphLink[];
}

export interface SoftLawItem {
  id: string;
  code: string;
  title: string;
  legal_force: string;
  text_snippet?: string;
  rel_type?: string;
}

export interface SimilarProvisionItem {
  id: string;
  code: string;
  title: string;
  legal_force: string;
  annex: string;
  score: number;
  reason: string;
  text_snippet?: string;
}

export interface CitationItem {
  id?: string;
  code: string;
  title: string;
  content_type?: string;
  subject?: string;
}

export interface NodeInspectionDetails {
  id: string;
  code: string;
  title: string;
  content_type: string;
  legal_force?: string;
  subject?: string;
  source?: string;
  annex?: {
    code: string;
    name: string;
    description?: string;
  };
  text?: string;
  text_snippet?: string;
  full_text?: string;
  upstream?: Array<{ id: string; code: string; title: string; content_type?: string; legal_force?: string; rel?: string }>;
  upstream_rules?: Array<{ id: string; code: string; title: string; type?: string }>;
  downstream_amcs?: SoftLawItem[];
  acceptable_means_of_compliance?: SoftLawItem[];
  downstream_gms?: SoftLawItem[];
  guidance_material?: SoftLawItem[];
  attached_soft_law?: SoftLawItem[];
  similar_provisions?: SimilarProvisionItem[];
  outgoing_citations?: CitationItem[];
  incoming_citations?: CitationItem[];
  stakeholders?: Array<{ name: string; role_type: string; description?: string; obligation?: string }>;
  concepts?: Array<{ name: string; category: string; description?: string }>;
  graph_rag_markdown?: string;
  graphrag_context?: string;
}

async function request<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function fetchGraphStats(apiUrl: string): Promise<GraphStats> {
  return request<GraphStats>(`${apiUrl}/graph/stats`);
}

export async function fetchSourcesCatalog(apiUrl: string): Promise<SourcesCatalog> {
  return request<SourcesCatalog>(`${apiUrl}/graph/sources`);
}

export async function searchGraph(
  apiUrl: string,
  query: string,
  sources: string[] = ['EASA', 'EU', 'FAA', 'SKYBRARY', 'EUROCAE'],
  skybraryTopics: string[] = []
): Promise<{ query: string; active_sources: string[]; results: GraphSearchResult[] }> {
  const params = new URLSearchParams({
    q: query,
    sources: sources.join(','),
    skybrary_topics: skybraryTopics.join(',')
  });
  return request(`${apiUrl}/graph/search?${params.toString()}`);
}

export async function executeHydeSearch(
  apiUrl: string,
  query: string,
  sources: string[] = ['EASA', 'EU', 'FAA', 'SKYBRARY', 'EUROCAE'],
  skybraryTopics: string[] = [],
  topK: number = 12
): Promise<HydeResponse> {
  const params = new URLSearchParams({
    q: query,
    sources: sources.join(','),
    skybrary_topics: skybraryTopics.join(','),
    top_k: String(topK)
  });
  const data: any = await request(`${apiUrl}/graph/hyde?${params.toString()}`);
  const rawList = data.candidates || data.candidate_nodes || [];
  const candidates: HydeCandidate[] = rawList.map((c: any) => ({
    id: c.id || c.code,
    code: c.code || c.id,
    title: c.title || '',
    type: c.type || c.content_type || 'Provision',
    source: c.source || 'EASA',
    annex: c.annex || c.annex_name || '',
    similarity_score: c.similarity_score ?? c.score ?? 0,
    match_percentage: c.match_percentage ?? c.score_pct ?? Math.round((c.score || 0) * 100),
    text_snippet: c.text_snippet || c.snippet || c.text || ''
  }));
  return {
    query: data.query || query,
    hypothetical_document: data.hypothetical_document || '',
    top_k: data.top_k ?? candidates.length,
    candidates: candidates,
    active_sources: data.active_sources || sources
  };
}

export interface ConceptSummary {
  id: string;
  name: string;
  category: string;
  total_provisions: number;
  is_custom?: boolean;
  description?: string;
}

export interface RegulationSummary {
  id: string;
  code: string;
  title: string;
  source: string;
  total_topics: number;
  annex_count: number;
}

export async function fetchRegulationsCatalog(apiUrl: string): Promise<RegulationSummary[]> {
  return request<RegulationSummary[]>(`${apiUrl}/graph/regulations`);
}

export async function fetchRegulationConcepts(apiUrl: string, name: string): Promise<D3GraphData> {
  const params = new URLSearchParams({ name });
  return request<D3GraphData>(`${apiUrl}/graph/regulation/concepts?${params.toString()}`);
}

export async function fetchComplianceChain(apiUrl: string, code: string): Promise<D3GraphData> {
  const params = new URLSearchParams({ code });
  return request<D3GraphData>(`${apiUrl}/graph/chain?${params.toString()}`);
}

export async function fetchBlastRadius(apiUrl: string, code: string): Promise<D3GraphData> {
  const params = new URLSearchParams({ code });
  return request<D3GraphData>(`${apiUrl}/graph/blast?${params.toString()}`);
}

export async function fetchConceptSubgraph(apiUrl: string, name: string): Promise<D3GraphData> {
  const params = new URLSearchParams({ name });
  return request<D3GraphData>(`${apiUrl}/graph/concept?${params.toString()}`);
}

export async function fetchConceptsCatalog(apiUrl: string): Promise<ConceptSummary[]> {
  return request<ConceptSummary[]>(`${apiUrl}/graph/concepts`);
}

export async function generateCustomConcept(
  apiUrl: string,
  payload: { name: string; category?: string; description?: string }
): Promise<D3GraphData> {
  const res = await fetch(`${apiUrl}/graph/concept/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      errorDetail = await res.text();
    }
    throw new Error(errorDetail || `Failed to generate concept: HTTP ${res.status}`);
  }
  return res.json();
}

export async function deleteCustomConcept(apiUrl: string, id: string): Promise<{ status: string; id: string }> {
  const params = new URLSearchParams({ id });
  const res = await fetch(`${apiUrl}/graph/concept/custom?${params.toString()}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      errorDetail = await res.text();
    }
    throw new Error(errorDetail || `Failed to delete custom concept: HTTP ${res.status}`);
  }
  return res.json();
}

export interface ConceptNarrativeResponse {
  concept: string;
  category: string;
  total_provisions: number;
  annexes_covered: string[];
  provider_used: string;
  narrative: string;
  generated_at: string;
  cached?: boolean;
}

export async function fetchConceptNarrative(
  apiUrl: string,
  conceptName: string,
  provider: 'gemini' | 'local' = 'gemini',
  model?: string,
  geminiApiKey?: string,
  forceRefresh: boolean = false
): Promise<ConceptNarrativeResponse> {
  const res = await fetch(`${apiUrl}/graph/concept/narrative`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      concept_name: conceptName,
      provider,
      model,
      gemini_api_key: geminiApiKey,
      force_refresh: forceRefresh
    })
  });
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      errorDetail = await res.text();
    }
    throw new Error(errorDetail || `Failed to generate concept narrative: HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchNodeDetails(apiUrl: string, idOrCode: string): Promise<NodeInspectionDetails> {
  const params = new URLSearchParams({ id: idOrCode });
  return request<NodeInspectionDetails>(`${apiUrl}/graph/node?${params.toString()}`);
}


