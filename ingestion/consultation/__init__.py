"""
Consultation Package - Document Consultation & Stakeholder Feedback Analytics.
"""

from .csv_parser import (
    CONSULTATION_TEMPLATE_FIELDS,
    parse_feedback_csv,
    parse_feedback_csv_with_mapping,
    detect_csv_columns,
    inspect_feedback_csv,
    detect_delimiter,
)
from .text_blocks import (
    build_required_text_blocks,
)
from .analyzer import (
    analyze_comment_themes,
    analyze_comment_sentiment,
    assess_comment_validity,
    extract_document_sections,
    enrich_feedback_comments,
    compute_consultation_metrics,
    compute_organisations_analysis,
    evaluate_comment_dual_context,
    analyze_critical_comment_support_and_silence,
    extract_direction_of_travel,
    compute_full_consultation_synthesis,
    generate_ai_deep_synthesis,
)
from .storage import (
    save_consultation_session,
    get_consultation_session,
    list_consultation_sessions,
    update_comment_review,
    update_session_text_block,
    delete_consultation_session,
)

__all__ = [
    "CONSULTATION_TEMPLATE_FIELDS",
    "parse_feedback_csv",
    "parse_feedback_csv_with_mapping",
    "detect_csv_columns",
    "inspect_feedback_csv",
    "detect_delimiter",
    "build_required_text_blocks",
    "analyze_comment_themes",
    "analyze_comment_sentiment",
    "assess_comment_validity",
    "extract_document_sections",
    "enrich_feedback_comments",
    "compute_consultation_metrics",
    "compute_organisations_analysis",
    "evaluate_comment_dual_context",
    "analyze_critical_comment_support_and_silence",
    "extract_direction_of_travel",
    "compute_full_consultation_synthesis",
    "generate_ai_deep_synthesis",
    "save_consultation_session",
    "get_consultation_session",
    "list_consultation_sessions",
    "update_comment_review",
    "update_session_text_block",
    "delete_consultation_session",
]
