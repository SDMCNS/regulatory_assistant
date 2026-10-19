"""
EUROCAE and European Aviation Standards Package.

Provides parsing, acronym expansion, HyDE embedding generation,
and curated supporting standard recommendations for European aviation standards.
"""

from .models import EurocaeStandard, EurocaeReadingMaterial
from .acronyms import expand_acronyms, get_acronym_definitions, AVIATION_ACRONYMS
from .parser import parse_published_standards, parse_upcoming_tracker, harmonize_standards
from .hyde import generate_hyde_embedding_text
from .storage import (
    upsert_standards, 
    get_standard_by_reference, 
    search_standards, 
    get_all_standards,
    get_eurocae_stats
)
from .matcher import find_supporting_standards

__all__ = [
    "EurocaeStandard",
    "EurocaeReadingMaterial",
    "expand_acronyms",
    "get_acronym_definitions",
    "AVIATION_ACRONYMS",
    "parse_published_standards",
    "parse_upcoming_tracker",
    "harmonize_standards",
    "generate_hyde_embedding_text",
    "upsert_standards",
    "get_standard_by_reference",
    "search_standards",
    "get_all_standards",
    "get_eurocae_stats",
    "find_supporting_standards",
]
