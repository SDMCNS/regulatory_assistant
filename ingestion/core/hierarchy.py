from enum import Enum

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

TAG_HIERARCHY_MAP = {
    'ACT': LegalHierarchyType.ACT,
    'DOC': LegalHierarchyType.ACT,
    'PREAMBLE': LegalHierarchyType.PREAMBLE,
    'PREAMBLE.INIT': LegalHierarchyType.PREAMBLE,
    'VISA': LegalHierarchyType.PREAMBLE_CITATION,
    'GR.VISA': LegalHierarchyType.PREAMBLE,
    'CITATIONS': LegalHierarchyType.PREAMBLE,
    'CITATION': LegalHierarchyType.PREAMBLE_CITATION,
    'CONSID': LegalHierarchyType.PREAMBLE_RECITAL,
    'GR.CONSID': LegalHierarchyType.PREAMBLE,
    'RECITAL': LegalHierarchyType.PREAMBLE_RECITAL,
    'RECITALS': LegalHierarchyType.PREAMBLE,
    'CHAPTER': LegalHierarchyType.CHAPTER,
    'SECTION': LegalHierarchyType.SECTION,
    'DIVISION': LegalHierarchyType.DIVISION,
    'ARTICLE': LegalHierarchyType.ARTICLE,
    'PARAGRAPH': LegalHierarchyType.PARAGRAPH,
    'PARAG': LegalHierarchyType.PARAGRAPH,
    'ALINEA': LegalHierarchyType.SUBPARAGRAPH,
    'POINT': LegalHierarchyType.POINT,
    'ITEM': LegalHierarchyType.POINT,
    'SUBPOINT': LegalHierarchyType.SUBPOINT,
    'ANNEX': LegalHierarchyType.ANNEX,
    'FINAL': LegalHierarchyType.FINAL_PROVISION,
    'ENACTING.TERMS': LegalHierarchyType.ACT
}

def map_tag_to_hierarchy(tag: str) -> LegalHierarchyType:
    return TAG_HIERARCHY_MAP.get(tag.upper(), LegalHierarchyType.OTHER)
