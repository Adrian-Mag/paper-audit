"""Typed claim ledger: Question, AtomicClaim, EvidenceRef, Verdict, CoverageReport.

All models forbid unknown fields and are immutable once constructed, so
malformed or tampered worker output fails validation loudly instead of
silently passing a field through.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

CLAIM_ID_PATTERN = r"^C\d+$"

# Deliberately aggressive: these markers over-reject rather than risk letting a
# compound proposition through as if it were atomic. A claim tripping this
# should be rephrased or split by the analyst stage, not worked around here.
#
# "and" is handled separately from the other markers: a bare " and " also
# matches ordinary compound objects that are not compound claims at all (e.g.
# "differed between condition A and condition B" is one proposition about a
# comparison, not two). Only flag "and" when it is immediately followed by a
# pronoun/"there", which is a much stronger signal of a genuine second clause
# with its own subject ("... significant, and this decrease was also...").
# This under-catches determiner-led second clauses ("and the study found...")
# but that gap is an accepted tradeoff for eliminating the comparison false
# positive; the analyst prompt is the primary defense against compound
# claims, this validator is a safety net, not the only line of defense.
_COMPOUND_SUBSTRINGS = (";",)
_COMPOUND_WORD_MARKERS = (" but ", " however ", " whereas ", " although ", " while ")
_AND_NEW_CLAUSE_RE = re.compile(r"\band (it|this|that|these|those|they|he|she|we|there)\b", re.IGNORECASE)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Question(_StrictModel):
    text: str = Field(..., min_length=1)


class EvidenceRef(_StrictModel):
    quote: str = Field(..., min_length=1)


class AtomicClaim(_StrictModel):
    """A single verifiable proposition. IDs are assigned by the controller, never by a worker."""

    id: str = Field(..., pattern=CLAIM_ID_PATTERN)
    text: str = Field(..., min_length=1)
    evidence: EvidenceRef

    @field_validator("text")
    @classmethod
    def reject_compound(cls, v: str) -> str:
        padded = f" {v.lower()} "
        is_compound = (
            any(m in v for m in _COMPOUND_SUBSTRINGS)
            or any(m in padded for m in _COMPOUND_WORD_MARKERS)
            or _AND_NEW_CLAUSE_RE.search(v) is not None
        )
        if is_compound:
            raise ValueError(
                "claim text looks compound (multiple propositions joined together); "
                "split into separate atomic claims instead"
            )
        return v


class VerdictLabel(str, Enum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    UNKNOWN = "unknown"


class Verdict(_StrictModel):
    """The schema-validated output of an entailment verifier worker."""

    claim_id: str = Field(..., pattern=CLAIM_ID_PATTERN)
    label: VerdictLabel
    rationale: str = Field(..., min_length=1)


class CoverageEntry(_StrictModel):
    claim_id: str = Field(..., pattern=CLAIM_ID_PATTERN)
    label: VerdictLabel


class CoverageReport(_StrictModel):
    """Deterministic summary produced by synthesis; never adds claims of its own."""

    entries: list[CoverageEntry]

    @property
    def total(self) -> int:
        return len(self.entries)

    def count(self, label: VerdictLabel) -> int:
        return sum(1 for e in self.entries if e.label == label)
