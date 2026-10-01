"""Point nesting and list regrouping logic for Formex documents.

Formex often stores "(1) ... (a) ... (b) ... (2) ..." as flat siblings, and a
bullet list as a sibling that follows its point. For storage/embedding each
numbered point must stay whole, so sub-points and bullet lists are moved
inside the point they belong to.
"""
from __future__ import annotations

import re
from typing import Any

from .constants import _ROMAN, _STARTERS

Block = dict[str, Any]


def _point_token(number: str) -> str:
    """Extract clean token from point label by stripping punctuation."""
    return number.strip().strip("()[].:;").strip()


def _wrap_of(number: str) -> str:
    """Classify the wrapping style of a point number."""
    raw = number.strip().rstrip(".;:")
    if raw.startswith("(") and raw.endswith(")"):
        return "paren"  # (1) (a) (i)
    if raw.endswith(")"):
        return "close"  # 1) a)
    return "dot" if number.strip().endswith(".") else "bare"  # 1. / 1


def _signature(number: str, stack: list[tuple[str, str]]) -> tuple[str, str, str] | None:
    """Return (style, wrap, token) for a point label, or None if not a point label.

    Style is what a human reads off the label: 1 / a / i / A / 1.1 ..., and the
    wrapper ((x), x), x.) - so "1." and "(1)" are different levels. The
    letter-vs-roman ambiguity of (i), (v), (x) is settled from the sequence:
    (h) -> (i) continues the alphabet, (a) -> (i) starts a roman sub-list.
    """
    token, wrap = _point_token(number), _wrap_of(number)
    if re.fullmatch(r"\d+[a-z]?", token):
        return "num", wrap, token
    if re.fullmatch(r"\d+(\.\d+)+", token):
        return f"num{token.count('.') + 1}", wrap, token
    if token.isalpha() and token.islower():
        if len(token) > 1:
            return ("roman" if _ROMAN.match(token) else "alpha"), wrap, token
        prev = next((sig[2] for sig, _t in reversed(stack)
                     if sig[0] == "alpha" and sig[1] == wrap), None)
        if prev and len(prev) == 1 and ord(prev) + 1 == ord(token):
            return "alpha", wrap, token
        return ("roman" if token in "ivx" else "alpha"), wrap, token
    if token.isalpha() and token.isupper():
        return "ualpha", wrap, token
    return None


def _attach(parent: Block, child: Block) -> None:
    """Attach a child block into parent's content list, converting parent if needed."""
    if "content" not in parent:
        parent["content"] = ([{"type": "text", "text": parent.pop("text")}]
                             if "text" in parent else [])
    parent["content"].append(child)


def _regroup(blocks: list[Block]) -> list[Block]:
    """Single pass with previous point kept in memory (a stack of open points).

    * new label already open in the stack  -> sibling: close it and everything below
      (unless it is a starter such as "1"/"a"/"i" - that is a restart, so a child)
    * new label not open                   -> child of the current point
    * a list (dash/bullet/lettered)        -> belongs to the current point
    * anything else (plain paragraph)      -> closes all open points
    """
    out: list[Block] = []
    stack: list[tuple[tuple[str, str, str], str, Block]] = []  # (sig, token, node)
    for b in blocks:
        if b.get("type") in ("item", "paragraph") and b.get("number"):
            sig = _signature(b["number"], [(e[0], e[1]) for e in stack])
            if sig:
                style, wrap, token = sig
                idx = next((i for i, e in enumerate(stack)
                            if e[0][0] == style and e[0][1] == wrap), None)
                restart = style in _STARTERS and token == _STARTERS[style]
                if idx is not None and not restart:
                    del stack[idx:]  # sibling of an open point
                if stack:
                    _attach(stack[-1][2], b)  # child of the current point
                else:
                    out.append(b)
                stack.append((sig, token, b))
                continue
        if b.get("type") == "list" and stack:
            _attach(stack[-1][2], b)
            continue
        stack.clear()
        out.append(b)
    return out


def group_points(blocks: list[Block]) -> list[Block]:
    """Recursively nest lettered/roman sub-points and lists under their point."""
    for b in blocks:
        if "content" in b:
            b["content"] = group_points(b["content"])
        if b.get("type") == "list" and "items" in b:
            b["items"] = group_points(b["items"])
    return _regroup(blocks)
