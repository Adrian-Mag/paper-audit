"""Stage 3: one fresh worker per claim, sees only its claim and cited passage
-- never the analyst's narrative, the paper, or any sibling verdict.

claim_id is assigned by the controller after the call returns, not asked of
the worker: the worker never even sees which ID it is (there is nothing
epistemic about that number for it to get right or wrong).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from paper_audit.backends.base import AgentBackend, RawUsage, WorkerJob
from paper_audit.pipeline._common import load_prompt
from paper_audit.schemas import AtomicClaim, Verdict, VerdictLabel


class RawVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: VerdictLabel
    rationale: str = Field(..., min_length=1)


def build_verifier_prompt(claim: AtomicClaim) -> str:
    return f'Claim:\n{claim.text}\n\nCited passage (verbatim from the source):\n"{claim.evidence.quote}"'


def run_verifier(claim: AtomicClaim, backend: AgentBackend, model: str = "sonnet") -> tuple[Verdict, RawUsage]:
    job = WorkerJob(
        prompt=build_verifier_prompt(claim),
        system_prompt=load_prompt("entailment_verifier.md"),
        model=model,
        stage="verifier",
    )
    result = backend.run(job, RawVerdict)
    verdict = Verdict(claim_id=claim.id, label=result.output.label, rationale=result.output.rationale)
    return verdict, result.usage
