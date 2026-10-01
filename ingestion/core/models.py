from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class LegalHierarchyType(str, Enum):
    ACT = "ACT"
    PREAMBLE = "PREAMBLE"
    PREAMBLE_CITATION = "PREAMBLE_CITATION"     # <VISA>
    PREAMBLE_RECITAL = "PREAMBLE_RECITAL"       # <CONSID>, <RECITAL>
    CHAPTER = "CHAPTER"
    SECTION = "SECTION"
    DIVISION = "DIVISION"
    ARTICLE = "ARTICLE"
    PARAGRAPH = "PARAGRAPH"
    SUBPARAGRAPH = "SUBPARAGRAPH"               # <ALINEA>
    POINT = "POINT"
    SUBPOINT = "SUBPOINT"
    ANNEX = "ANNEX"
    FINAL_PROVISION = "FINAL_PROVISION"
    OTHER = "OTHER"

class RelationshipType(str, Enum):
    CONTAINS = "CONTAINS"
    AMENDS = "AMENDS"
    AMENDED_BY = "AMENDED_BY"
    REPEALS = "REPEALS"
    REPEALED_BY = "REPEALED_BY"
    IMPLEMENTS = "IMPLEMENTS"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    SUPPLEMENTS = "SUPPLEMENTS"
    DEROGATES_FROM = "DEROGATES_FROM"
    REFERS_TO = "REFERS_TO"
    DEFINES = "DEFINES"
    APPLIES_TO = "APPLIES_TO"
    RELATED_TO = "RELATED_TO"
    CONSOLIDATES = "CONSOLIDATES"
    CORRECTS = "CORRECTS"
    SUPERSEDES = "SUPERSEDES"
    PRECEDES = "PRECEDES"

class LegalRole(str, Enum):
    REQUIREMENT = "REQUIREMENT"
    PROHIBITION = "PROHIBITION"
    PERMISSION = "PERMISSION"
    DEFINITION = "DEFINITION"
    SCOPE = "SCOPE"
    EXCEPTION = "EXCEPTION"
    PROCEDURE = "PROCEDURE"
    INFORMATION = "INFORMATION"
    OBJECTIVE = "OBJECTIVE"
    RECITAL = "RECITAL"

class Modality(str, Enum):
    SHALL = "SHALL"
    SHALL_NOT = "SHALL_NOT"
    MUST = "MUST"
    MUST_NOT = "MUST_NOT"
    MAY = "MAY"
    MAY_NOT = "MAY_NOT"
    SHOULD = "SHOULD"
    SHOULD_NOT = "SHOULD_NOT"
    NONE = "NONE"

class EmbeddingType(str, Enum):
    ACT = "ACT"
    ARTICLE = "ARTICLE"
    REQUIREMENT = "REQUIREMENT"
    CHUNK = "CHUNK"

class LegalFragment(BaseModel):
    fragment_id: str
    act_id: str
    parent_id: Optional[str] = None
    celex: Optional[str] = None
    eli: Optional[str] = None
    document_type: str
    hierarchy_type: LegalHierarchyType
    chapter_number: Optional[str] = None
    section_number: Optional[str] = None
    article_number: Optional[str] = None
    paragraph_number: Optional[str] = None
    point_number: Optional[str] = None
    subpoint_number: Optional[str] = None
    heading: Optional[str] = None
    text: str
    context_path: str
    language: str = "EN"
    version_date: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    status: str = "IN_FORCE"
    source_authority: Optional[str] = "EU"
    source_url: Optional[str] = None
    source_file: str
    publication_date: Optional[str] = None
    consolidation_date: Optional[str] = None
    source_hash: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class Relationship(BaseModel):
    relationship_id: str
    source_fragment_id: str
    relationship_type: RelationshipType
    target_fragment_id: str
    source_act_id: str
    target_act_id: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class ExtractedSemanticMetadata(BaseModel):
    legal_role: LegalRole
    modality: Modality
    subject: Optional[str] = None
    action: Optional[str] = None
    condition: Optional[str] = None
    exception: Optional[str] = None
    deadline: Optional[str] = None
    threshold: Optional[str] = None
    geographical_scope: Optional[str] = None
    temporal_scope: Optional[str] = None

class EmbeddingCandidate(BaseModel):
    fragment_id: str
    embedding_type: EmbeddingType
    source_text: str
    embedding_text: str
    text_hash: str

class EmbeddingRecord(BaseModel):
    embedding_id: str
    fragment_id: str
    embedding_type: EmbeddingType
    model: str
    dimensions: int
    vector: List[float]
    text_hash: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
