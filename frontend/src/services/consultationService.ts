/**
 * consultationService.ts - API Service for Document Consultation Workspace
 */

export interface ConsultationTemplateField {
  key: string;
  label: string;
  required: boolean;
  type: string;
  description: string;
  aliases: string[];
}

export interface InspectFileResponse {
  status: string;
  detected_delimiter: string;
  row_count: number;
  headers: string[];
  suggested_mapping: Record<string, string>;
  sample_rows: Record<string, string>[];
  unmapped_headers: string[];
  missing_required_fields: string[];
  template_fields: ConsultationTemplateField[];
}

export interface RequiredTextBlock {
  block_id: string;
  document_title: string;
  chapter_section: string;
  status: 'provided' | 'missing';
  content: string;
  source: string;
  comment_count: number;
  critical_comment_count: number;
  referencing_stakeholders: string[];
  sample_comment_snippets: string[];
}

export interface SupportNetwork {
  target_clause: string;
  current_organisation: string;
  total_participating_organisations: number;
  co_objectors: string[];
  defenders: string[];
  silent_organisations: string[];
  support_count: number;
  defense_count: number;
  silence_count: number;
  support_rate_pct: number;
  defense_rate_pct: number;
  silence_rate_pct: number;
  regulatory_interpretation: string;
}

export interface OrganisationAnalysis {
  organisation_name: string;
  stakeholder_category: string;
  total_comments: number;
  critical_comments_count: number;
  average_weighted_score: number;
  average_section_score: number;
  average_document_score: number;
  stance_summary: string;
  primary_direction_of_travel?: string;
  direction_of_travel: string;
  direction_of_travel_summary?: string;
  direction_scores?: Record<string, number>;
  targeted_sections: string[];
  dominant_themes: string[];
  co_objectors_network: string[];
}

export interface ConsultationDocSection {
  title: string;
  content: string;
}

export interface ConsultationDocument {
  doc_id: string;
  filename: string;
  title: string;
  author?: string;
  date?: string;
  word_count: number;
  page_count: number;
  sections: ConsultationDocSection[];
}

export interface ConsultationComment {
  comment_id: string;
  consultation_id?: string;
  document_title?: string;
  chapter_section?: string;
  page?: string;
  original_text?: string;
  comment_text: string;
  comment_type?: string;
  importance?: string;
  proposed_text?: string;
  stakeholder_category?: string;
  organisation_name?: string;
  af_cba?: string;
  response_to_comment?: string;
  rationale_and_changes?: string;
  overall_id?: string;
  stakeholder_name: string;
  stakeholder_group: string;
  target_section: string;
  rationale?: string;
  themes: string[];
  sentiment: string; // 'Strongly Critical' | 'Concerned' | 'Neutral / Inquiring' | 'Supportive'
  sentiment_score: number;
  section_score?: number;
  document_score?: number;
  weighted_score?: number;
  direction_of_travel?: string;
  support_network?: SupportNetwork | null;
  validity: string; // 'Actionable Proposal' | 'Substantive Technical Concern' | 'Clarification Request' | 'Editorial / Minor' | 'General Opinion / Policy Grievance'
  validity_rationale: string;
  matched_section_title?: string;
  matched_section_content?: string;
  human_review_status: string; // 'Pending Review' | 'Under Technical Assessment' | 'In Consideration' | 'Flagged for Legal Review' | 'Draft Response Prepared'
  human_notes: string;
  ai_assistance_notes?: string | null;
  updated_at?: string;
}

export interface ConsultationMetrics {
  total_comments: number;
  sentiment_distribution: Record<string, number>;
  stakeholder_groups: Record<string, number>;
  theme_distribution: Record<string, number>;
  validity_distribution: Record<string, number>;
  review_status_distribution: Record<string, number>;
  actionable_proposal_pct: number;
}

export interface ConsultationSession {
  consultation_id: string;
  title: string;
  description: string;
  domain: string;
  status: string;
  created_at: string;
  updated_at: string;
  documents: ConsultationDocument[];
  metrics: ConsultationMetrics;
  field_mapping?: Record<string, string>;
  required_text_blocks?: RequiredTextBlock[];
  organisations_analysis?: OrganisationAnalysis[];
  comments: ConsultationComment[];
}

export interface ConsultationSessionSummary {
  consultation_id: string;
  title: string;
  description: string;
  domain: string;
  status: string;
  created_at: string;
  updated_at: string;
  comment_count: number;
  metrics: ConsultationMetrics;
}

const API_BASE = 'http://127.0.0.1:8000';

export async function listConsultationSessions(): Promise<ConsultationSessionSummary[]> {
  const res = await fetch(`${API_BASE}/consultation/sessions`);
  if (!res.ok) {
    throw new Error(`Failed to list consultations: ${res.statusText}`);
  }
  return res.json();
}

export async function getConsultationSession(id: string): Promise<ConsultationSession> {
  const res = await fetch(`${API_BASE}/consultation/session/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch consultation session ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function createConsultationSession(formData: FormData): Promise<ConsultationSession> {
  const res = await fetch(`${API_BASE}/consultation/session/create`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to create consultation session.');
  }
  return res.json();
}

export async function updateCommentReview(
  commentId: string,
  humanReviewStatus: string,
  humanNotes: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/consultation/comment/${commentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      human_review_status: humanReviewStatus,
      human_notes: humanNotes,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to update comment review: ${res.statusText}`);
  }
}

export async function assistCommentFormulation(
  commentId: string,
  consultationId: string,
  provider: string = 'local'
): Promise<string> {
  const res = await fetch(`${API_BASE}/consultation/comment/${commentId}/assist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      consultation_id: consultationId,
      provider: provider,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to generate assistance notes: ${res.statusText}`);
  }
  const data = await res.json();
  return data.ai_assistance_notes || '';
}

export async function loadSampleConsultation(): Promise<ConsultationSession> {
  const res = await fetch(`${API_BASE}/consultation/session/load-sample`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to load sample consultation: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteConsultationSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/consultation/session/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to delete consultation session: ${res.statusText}`);
  }
}

export function getExportConsultationUrl(id: string, format: 'csv' | 'json' = 'csv'): string {
  return `${API_BASE}/consultation/session/${id}/export?format=${format}`;
}

export interface OverallAssessment {
  overall_sentiment_label: string;
  overall_sentiment_score: number;
  total_comments: number;
  total_stakeholders: number;
  sentiment_breakdown_pct: Record<string, number>;
  actionable_rate: number;
  executive_summary: string;
  top_friction_zones: Array<{
    topic: string;
    affected_articles: string;
    contesting_groups: string[];
    core_issue: string;
  }>;
  areas_of_broad_consensus: string[];
  stakeholder_coalition_dynamics: Array<{
    group: string;
    stance: string;
    friction_with: string;
  }>;
  rulemaker_action_roadmap: string[];
}

export interface StakeholderTypeSynthesis {
  stakeholder_group: string;
  comment_count: number;
  stakeholders: string[];
  average_sentiment_score: number;
  sentiment_distribution: Record<string, number>;
  primary_targeted_sections: string[];
  dominant_themes: string[];
  collective_stance_summary: string;
  core_concerns_vs_consulted_text: Array<{
    stakeholder: string;
    target: string;
    concern: string;
    proposed_change: string;
    stance: string;
  }>;
  cross_sector_alignment_and_conflicts: string;
  rulemaker_deliberation_advice: string;
}

export interface CategorySynthesis {
  category_name: string;
  comment_count: number;
  average_sentiment_score: number;
  sentiment_distribution: Record<string, number>;
  participating_groups: string[];
  implicated_sections: string[];
  thematic_conflict_summary: string;
  stakeholder_positions: Array<{
    stakeholder: string;
    group: string;
    target_section: string;
    argument: string;
    proposal: string;
    sentiment: string;
  }>;
  consulted_text_evaluation: string;
  policy_tradeoffs_and_remedies: string[];
}

export interface SectionSynthesis {
  section_title: string;
  section_excerpt: string;
  comment_count: number;
  average_sentiment_score: number;
  sentiment_distribution: Record<string, number>;
  commenting_groups: string[];
  synthesized_feedback_vs_text: string;
  contentious_provisions: string[];
  supported_provisions: string[];
  suggested_amendments: Array<{
    stakeholder: string;
    target_clause: string;
    proposed_text: string;
    rationale: string;
  }>;
  deliberation_guidance: string;
}

export interface CommentSynthesis {
  comment_id: string;
  stakeholder_name: string;
  stakeholder_group: string;
  target_section: string;
  matched_section_title: string;
  sentiment: string;
  sentiment_score: number;
  validity: string;
  themes: string[];
  comment_text: string;
  proposed_text: string;
  rationale: string;
  text_stipulation: string;
  stakeholder_concern: string;
  divergence_analysis: string;
  operational_and_safety_impact: string;
  drafting_options: string[];
}

export interface ConsultationSynthesisBundle {
  consultation_id: string;
  title: string;
  overall_assessment: OverallAssessment;
  stakeholder_type_synthesis: StakeholderTypeSynthesis[];
  category_synthesis: CategorySynthesis[];
  section_synthesis: SectionSynthesis[];
  comment_synthesis: CommentSynthesis[];
}

export interface DeepSynthesisResult {
  status: string;
  scope: string;
  target_id?: string | null;
  target_summary: string;
  synthesis_narrative: string;
  structured_data: ConsultationSynthesisBundle;
}

export async function getTemplateFields(): Promise<{ status: string; template_fields: ConsultationTemplateField[] }> {
  const res = await fetch(`${API_BASE}/consultation/template-fields`);
  if (!res.ok) {
    throw new Error(`Failed to load template fields: ${res.statusText}`);
  }
  return res.json();
}

export async function inspectFeedbackFile(file: File, delimiter?: string): Promise<InspectFileResponse> {
  const fd = new FormData();
  fd.append('feedback_file', file);
  if (delimiter) {
    fd.append('delimiter', delimiter);
  }
  const res = await fetch(`${API_BASE}/consultation/inspect-file`, {
    method: 'POST',
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to inspect file.');
  }
  return res.json();
}

export async function getSessionTextBlocks(consultationId: string): Promise<RequiredTextBlock[]> {
  const res = await fetch(`${API_BASE}/consultation/session/${consultationId}/text-blocks`);
  if (!res.ok) {
    throw new Error(`Failed to fetch text blocks: ${res.statusText}`);
  }
  const data = await res.json();
  return data.text_blocks || [];
}

export async function updateSessionTextBlock(consultationId: string, blockId: string, content: string): Promise<RequiredTextBlock[]> {
  const res = await fetch(`${API_BASE}/consultation/session/${consultationId}/text-block/${blockId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    throw new Error(`Failed to update text block: ${res.statusText}`);
  }
  const data = await res.json();
  return data.text_blocks || [];
}

export async function getSessionOrganisations(consultationId: string): Promise<OrganisationAnalysis[]> {
  const res = await fetch(`${API_BASE}/consultation/session/${consultationId}/organisations`);
  if (!res.ok) {
    throw new Error(`Failed to fetch organisations analysis: ${res.statusText}`);
  }
  const data = await res.json();
  return data.organisations || [];
}

export async function getConsultationSynthesis(id: string): Promise<ConsultationSynthesisBundle> {
  const res = await fetch(`${API_BASE}/consultation/session/${id}/synthesis`);
  if (!res.ok) {
    throw new Error(`Failed to load consultation synthesis: ${res.statusText}`);
  }
  return res.json();
}

export async function generateDeepSynthesis(
  id: string,
  scope: 'overall' | 'stakeholder_type' | 'category' | 'section' | 'comment' | 'organisation' | 'silence_accounting',
  targetId?: string,
  provider: string = 'local'
): Promise<DeepSynthesisResult> {
  const res = await fetch(`${API_BASE}/consultation/session/${id}/synthesis/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scope,
      target_id: targetId,
      provider,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to generate deep synthesis: ${res.statusText}`);
  }
  return res.json();
}

export function getExportSynthesisReportUrl(id: string, format: 'markdown' | 'json' = 'markdown'): string {
  return `${API_BASE}/consultation/session/${id}/synthesis/export?format=${format}`;
}

