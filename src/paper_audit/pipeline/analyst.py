"""Stage 1: paper + question in, claims JSON out.

IDs are assigned here, by the controller, never by the worker: they are
bookkeeping, not epistemic content. A raw claim whose text turns out to be
compound (or otherwise malformed once validated as an AtomicClaim) is
rejected rather than silently dropped -- it is recorded so nothing vanishes
from the audit trail, but it does not get an ID and does not proceed to
verification.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from paper_audit.backends.base import AgentBackend, RawUsage, WorkerJob
from paper_audit.pipeline._common import load_prompt
from paper_audit.schemas import AtomicClaim, EvidenceRef, Question


class RawClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    evidence_quote: str = Field(..., min_length=1)


class RawClaimList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[RawClaim]


class RejectedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    evidence_quote: str
    reason: str


class AnalystOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claims: list[AtomicClaim]
    rejected: list[RejectedClaim]


def build_analyst_prompt(paper_text: str, question: Question) -> str:
    return f"# Question\n\n{question.text}\n\n# Paper\n\n{paper_text}"


def run_analyst(
    paper_text: str,
    question: Question,
    backend: AgentBackend,
    model: str = "haiku",
) -> tuple[AnalystOutput, RawUsage]:
    job = WorkerJob(
        prompt=build_analyst_prompt(paper_text, question),
        system_prompt=load_prompt("analyst.md"),
        model=model,
        stage="analyst",
    )
    result = backend.run(job, RawClaimList)

    claims: list[AtomicClaim] = []
    rejected: list[RejectedClaim] = []
    next_id = 1
    for raw in result.output.claims:
        try:
            claim = AtomicClaim(id=f"C{next_id}", text=raw.text, evidence=EvidenceRef(quote=raw.evidence_quote))
        except ValidationError as exc:
            rejected.append(RejectedClaim(text=raw.text, evidence_quote=raw.evidence_quote, reason=str(exc)))
            continue
        claims.append(claim)
        next_id += 1

    return AnalystOutput(claims=claims, rejected=rejected), result.usage
