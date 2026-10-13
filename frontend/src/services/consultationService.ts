/**
 * consultationService.ts - API Service for Document Consultation Workspace
 */

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
  stakeholder_name: string;
  stakeholder_group: string;
  target_section: string;
  comment_text: string;
  proposed_text?: string;
  rationale?: string;
  themes: string[];
  sentiment: string; // 'Strongly Critical' | 'Concerned' | 'Neutral / Inquiring' | 'Supportive'
  sentiment_score: number;
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
