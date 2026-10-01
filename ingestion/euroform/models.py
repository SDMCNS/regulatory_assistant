"""Pydantic models for request validation and API responses."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ConversionOptions(BaseModel):
    """Options controlling Formex XML parsing and output generation."""

    keep_toc: bool = Field(default=False, description="Whether to retain table of contents (TOC)")
    include_metadata: bool = Field(default=True, description="Whether to extract and include the metadata block")
    nest_points: bool = Field(default=True, description="Whether to nest sub-points and lists under parent points")
    output_format: Literal["json", "text"] = Field(
        default="json", description="Desired output format: 'json' or 'text'"
    )


class XmlPayloadRequest(BaseModel):
    """JSON payload containing raw XML string and parsing options."""

    xml: str = Field(..., description="Formex 4 XML content string")
    keep_toc: bool = Field(default=False, description="Whether to retain table of contents")
    include_metadata: bool = Field(default=True, description="Whether to extract metadata")
    nest_points: bool = Field(default=True, description="Whether to nest sub-points")
    output_format: Literal["json", "text"] = Field(
        default="json", description="Output format: 'json' or 'text'"
    )


class BatchItemResult(BaseModel):
    """Result for an individual file in a batch conversion request."""

    filename: str
    success: bool
    error: str | None = None
    document: dict[str, Any] | None = None
    text: str | None = None


class BatchConversionResponse(BaseModel):
    """Response containing batch conversion results."""

    total: int
    successful: int
    failed: int
    results: list[BatchItemResult]


class ErrorResponse(BaseModel):
    """Structured error response for parsing or processing errors."""

    detail: str
    error_type: str = "ParseError"
    line: int | None = None
    column: int | None = None
