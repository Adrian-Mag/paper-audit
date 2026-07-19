"""Stage 4: deterministic conservative synthesis.

Drops claims that are not supported (quote-check failure, not_supported
verdict, or unknown verdict) from the report's prose, but never hides them:
the ledger records every claim that reached this stage, and the report's
"Dropped" section names each one and why. The prose in the report is
claim.text and evidence quotes copied verbatim from the ledger -- this stage
runs no LLM and introduces no new prose claims.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from paper_audit.pipeline.analyst import RejectedClaim
from paper_audit.pipeline.quote_check import QuoteCheckResult
from paper_audit.schemas import AtomicClaim, CoverageEntry, CoverageReport, Verdict, VerdictLabel


@dataclass(frozen=True)
class SynthesisResult:
    coverage: CoverageReport
    report_markdown: str


def synthesize(
    claims: list[AtomicClaim],
    quote_checks: list[QuoteCheckResult],
    verdicts: dict[str, Verdict],
    rejected: Sequence[RejectedClaim] = (),
) -> SynthesisResult:
    quote_check_by_id = {qc.claim_id: qc for qc in quote_checks}

    entries: list[CoverageEntry] = []
    supported: list[AtomicClaim] = []
    dropped: list[tuple[AtomicClaim, VerdictLabel, str]] = []

    for claim in claims:
        qc = quote_check_by_id.get(claim.id)
        if qc is None or not qc.passed:
            label = VerdictLabel.NOT_SUPPORTED
            reason = qc.reason if qc is not None else "no quote-check result recorded for this claim"
        else:
            verdict = verdicts.get(claim.id)
            if verdict is None:
                label = VerdictLabel.UNKNOWN
                reason = "quote check passed but no verifier verdict was recorded"
            else:
                label = verdict.label
                reason = verdict.rationale

        entries.append(CoverageEntry(claim_id=claim.id, label=label))
        if label == VerdictLabel.SUPPORTED:
            supported.append(claim)
        else:
            dropped.append((claim, label, reason))

    coverage = CoverageReport(entries=entries)
    report_markdown = _render_report(supported, dropped, rejected, coverage)
    return SynthesisResult(coverage=coverage, report_markdown=report_markdown)


def _render_report(
    supported: list[AtomicClaim],
    dropped: list[tuple[AtomicClaim, VerdictLabel, str]],
    rejected: Sequence[RejectedClaim],
    coverage: CoverageReport,
) -> str:
    lines = ["# Audit Report", "", "## Supported claims", ""]
    if supported:
        for claim in supported:
            lines.append(f"- **{claim.id}.** {claim.text}")
            lines.append(f'  - Evidence: "{claim.evidence.quote}"')
    else:
        lines.append("None of the extracted claims were supported by their cited evidence.")
    lines.append("")

    if dropped:
        lines.append("## Dropped claims")
        lines.append("")
        lines.append(
            "Extracted but not included above: their cited evidence did not support them as stated."
        )
        lines.append("")
        for claim, label, reason in dropped:
            lines.append(f"- **{claim.id}** ({label.value}): {claim.text}")
            lines.append(f'  - Evidence cited: "{claim.evidence.quote}"')
            lines.append(f"  - Reason: {reason}")
        lines.append("")

    if rejected:
        lines.append("## Rejected before verification")
        lines.append("")
        lines.append(
            "The analyst stage produced these but they were rejected before reaching "
            "verification (for example, for being compound rather than atomic claims)."
        )
        lines.append("")
        for r in rejected:
            lines.append(f"- {r.text}")
            lines.append(f"  - Reason: {r.reason}")
        lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Total claims: {coverage.total}")
    lines.append(f"- Supported: {coverage.count(VerdictLabel.SUPPORTED)}")
    lines.append(f"- Not supported: {coverage.count(VerdictLabel.NOT_SUPPORTED)}")
    lines.append(f"- Unknown: {coverage.count(VerdictLabel.UNKNOWN)}")
    lines.append("")

    return "\n".join(lines)
