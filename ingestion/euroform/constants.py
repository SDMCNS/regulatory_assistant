"""Constants and tag classifications for Formex 4 XML processing."""
from __future__ import annotations

import re

# Sentinel for <BR/> so it survives whitespace normalisation
_BR = "\x00"

# Unicode superscript and subscript character maps
_SUP: dict[str, str] = dict(zip("0123456789+-−=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱ"))
_SUB: dict[str, str] = dict(zip("0123456789+-−=()aehiklmnoprstx", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₕᵢₖₗₘₙₒₚᵣₛₜₓ"))

# Elements whose content is mixed text and never a block of its own.
INLINE_TAGS: set[str] = {
    "HT", "FT", "DATE", "NOTE", "QUOT.START", "QUOT.END", "BR", "IE",
    "ANONYMOUS", "LINK", "ADDR", "REF.DOC", "REF.DOC.OJ", "REF.DOC.ECR",
    "REF.DOC.SE", "REF.NP.ECR", "NO.CASE", "NO.ECLI", "NO.ELI", "NO.DOC.C",
    "PL.DATE",
    # formulas
    "FORMULA", "EXPR", "EXPONENT", "IND", "FRACTION", "DIVIDEND", "DIVISOR",
    "ROOT", "DEGREE", "OVERLINE", "VECTOR", "BAR", "SUM", "PRODUCT",
    "INTEGRAL", "FUNCTION", "OP.CMP", "OP.MATH", "FMT.VALUE", "OVER", "UNDER",
}

# Text-bearing elements that become their own paragraph even when they have
# no child elements (everything typed t_btx / t_btx.seq block-ish in the manual).
FLAT_TAGS: set[str] = {
    "P", "TXT", "ALINEA", "KEYWORD", "VISA", "TERM", "DEFINITION", "INTRO",
    "HINT", "NAME.COMMON", "NOTICE", "DESCRIPTION", "APPLICANT", "ITEM.CONT",
    "PREAMBLE.INIT", "PREAMBLE.FINAL", "TI", "STI", "TI.CJT", "SIGNATORY",
    "NO.P", "NO.PARAG", "TI.ART", "STI.ART", "CURR.TITLE",
}

# Pure plumbing: never contributes text.
DROP_TAGS: set[str] = {
    "DOCUMENT.REF", "DOCUMENT.REF.CONS", "NO.SEQ", "PROD.ID", "FIN.ID",
    "DURAB", "INCLUSIONS", "REF.CORE.METADATA", "REF.BIB.RECORD", "REF.PHYS",
    "ASSOCIATED.TO", "ASSOCIATES", "PDF.ECR", "PDF.GEN", "PAPER.GEN",
    "FMX.GEN", "NO.DOC.SUMMARY", "DOC.CORR", "DOC.CORR.SE",
}

# Regex for lowercase Roman numerals
_ROMAN: re.Pattern[str] = re.compile(r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")

# Point starters for detection of list restarts
_STARTERS: dict[str, str] = {"num": "1", "alpha": "a", "roman": "i", "ualpha": "A"}
