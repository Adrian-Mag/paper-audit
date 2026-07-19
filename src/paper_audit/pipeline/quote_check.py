"""Stage 2: deterministic, pure-Python exact-quote check. No Claude usage."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from paper_audit.schemas import AtomicClaim


class QuoteCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    passed: bool
    reason: str | None = None


def check_quote(claim: AtomicClaim, source_text: str) -> QuoteCheckResult:
    if claim.evidence.quote in source_text:
        return QuoteCheckResult(claim_id=claim.id, passed=True)
    return QuoteCheckResult(
        claim_id=claim.id,
        passed=False,
        reason="evidence quote is not a verbatim substring of the source text",
    )


def check_quotes(claims: list[AtomicClaim], source_text: str) -> list[QuoteCheckResult]:
    return [check_quote(claim, source_text) for claim in claims]
