"""EASA Parser package.

Note: This is a legacy/standalone parser that depends on an external OPC/input package.
The active pipeline in this repository uses `ingestion.parsers.convert_easa_to_json`.
"""

try:
    from .document import EasaDocumentParser, ParseResult, parse_easa_document
    from .figures import FigureParser
    from .hyperlinks import HyperlinkParser
    from .lists import ListParser
    from .metadata import MetadataParser
    from .paragraphs import ParagraphParser
    from .tables import TableParser
    from .topics import TopicParser

    __all__ = [
        "EasaDocumentParser",
        "FigureParser",
        "HyperlinkParser",
        "ListParser",
        "MetadataParser",
        "ParagraphParser",
        "ParseResult",
        "TableParser",
        "TopicParser",
        "parse_easa_document",
    ]
except ImportError:
    # Graceful fallback if legacy external OPC/input package is not available
    __all__ = []
