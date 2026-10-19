"""
Data models for EUROCAE and European aviation standards.
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class EurocaeStandard(BaseModel):
    standard_id: str = Field(..., description="Unique canonical identifier for database and search")
    reference: str = Field(..., description="Standard reference number, e.g. ED-275A, ED-XXX, EUROCONTROL-SPEC-147")
    title: str = Field(..., description="Official title of the standard")
    expanded_title: str = Field(..., description="Title with acronyms (MASPS, MOPS, ACAS, etc.) interpreted")
    status: str = Field(default="Published", description="Publication status: 'Published', 'Ongoing', 'Planned'")
    organization: str = Field(default="EUROCAE", description="Standard Developing Organization: EUROCAE or EUROCONTROL")
    working_group: Optional[str] = Field(default=None, description="Working group identifier, e.g. WG-75, WG-112")
    working_group_desc: Optional[str] = Field(default=None, description="Descriptive name of the working group")
    domain: Optional[str] = Field(default=None, description="Technical domain: Avionics, IAS, Air Traffic Management, etc.")
    publication_date: Optional[str] = Field(default=None, description="Publication date or planned release window (e.g. September 2026, Q2/2026)")
    master_plan_ref: Optional[str] = Field(default=None, description="European ATM Master Plan reference code, e.g. STD-174")
    cps_af: Optional[str] = Field(default=None, description="Common Project / ATM Functionality mapping, e.g. AF2")
    sdm_families: Optional[str] = Field(default=None, description="SESAR Deployment Manager family reference")
    easa_reference: Optional[str] = Field(default=None, description="Extracted EASA regulatory reference or AMC linkage")
    comment: Optional[str] = Field(default=None, description="Operational notes, consultation dates, and regulatory links")
    hyde_summary: Optional[str] = Field(default=None, description="Synthetic HyDE technical scope summary used exclusively for semantic embedding")
    unique_ardp_id: Optional[str] = Field(default=None, description="Unique identifier from the A-RDP upcoming publications tracker")
    recognized_acronyms: Dict[str, str] = Field(default_factory=dict, description="Dictionary of recognized acronyms and their definitions")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class EurocaeReadingMaterial(BaseModel):
    standard_id: str
    reference: str
    title: str
    expanded_title: str
    status: str
    organization: str
    working_group: Optional[str] = None
    working_group_desc: Optional[str] = None
    domain: Optional[str] = None
    publication_date: Optional[str] = None
    easa_reference: Optional[str] = None
    relevance_score: float = 0.0
    match_rationale: Optional[str] = None
    is_supporting_only: bool = True  # Explicit flag indicating this is follow-up reading, not source for answer text
