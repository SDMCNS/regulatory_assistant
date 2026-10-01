import re
from typing import Optional
from models import ExtractedSemanticMetadata, LegalRole, Modality

class DeterministicSemanticExtractor:
    """Extracts structured legal roles and modalities without external dependencies."""

    @classmethod
    def extract(cls, text: str) -> ExtractedSemanticMetadata:
        text_lower = text.lower()
        
        modality = cls._extract_modality(text_lower)
        role = cls._extract_legal_role(text_lower, modality)
        
        subject = cls._extract_regex(text, r"(?:the)\s+([a-zA-Z0-9\s\-_]+?)\s+(?:shall|must|may|is prohibited)")
        action = cls._extract_regex(text, r"(?:shall|must|may)\s+([a-zA-Z0-9\s\-_]+?)(?:\.|;|\s+when|\s+if|$)")
        condition = cls._extract_regex(text, r"(?:if|where|provided that|subject to)\s+([^,;\.]+)")
        exception = cls._extract_regex(text, r"(?:unless|except when|derogation from)\s+([^,;\.]+)")
        deadline = cls._extract_regex(text, r"(?:by|no later than|within)\s+([0-9]+\s+(?:days|months|years)|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})")

        return ExtractedSemanticMetadata(
            legal_role=role,
            modality=modality,
            subject=subject,
            action=action,
            condition=condition,
            exception=exception,
            deadline=deadline
        )

    @staticmethod
    def _extract_modality(text_lower: str) -> Modality:
        if "shall not" in text_lower:
            return Modality.SHALL_NOT
        if "must not" in text_lower:
            return Modality.MUST_NOT
        if "may not" in text_lower:
            return Modality.MAY_NOT
        if "should not" in text_lower:
            return Modality.SHOULD_NOT
        if "shall" in text_lower:
            return Modality.SHALL
        if "must" in text_lower:
            return Modality.MUST
        if "may" in text_lower:
            return Modality.MAY
        if "should" in text_lower:
            return Modality.SHOULD
        return Modality.NONE

    @staticmethod
    def _extract_legal_role(text_lower: str, modality: Modality) -> LegalRole:
        if modality in [Modality.SHALL, Modality.MUST]:
            return LegalRole.REQUIREMENT
        if modality in [Modality.SHALL_NOT, Modality.MUST_NOT, Modality.MAY_NOT]:
            return LegalRole.PROHIBITION
        if modality in [Modality.MAY]:
            return LegalRole.PERMISSION
        if "means" in text_lower or "defined as" in text_lower:
            return LegalRole.DEFINITION
        if "shall apply to" in text_lower or "scope of this" in text_lower:
            return LegalRole.SCOPE
        if "by way of derogation" in text_lower or "unless" in text_lower:
            return LegalRole.EXCEPTION
        return LegalRole.INFORMATION

    @staticmethod
    def _extract_regex(text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
