"""Self-scoring a run against a fixture's ground truth.

Ground truth is keyed by verbatim evidence quotes, not claim IDs (IDs are
assigned per-run and the analyst's decomposition is not fully predictable in
advance -- see fixtures/toy_question.yaml). A claim matches a ground-truth
entry if either string contains the other, compared case-insensitively.
"""

from __future__ import annotations

from dataclasses import dataclass

from paper_audit.schemas import AtomicClaim, CoverageEntry, VerdictLabel


@dataclass(frozen=True)
class ScoreEntry:
    ground_truth_id: str
    expected: VerdictLabel
    actual: VerdictLabel | None
    matched_claim_id: str | None
    is_trap: bool

    @property
    def passed(self) -> bool:
        if self.actual is None:
            return False
        if self.is_trap:
            return self.actual != VerdictLabel.SUPPORTED
        return self.actual == self.expected


@dataclass(frozen=True)
class ScoreReport:
    entries: list[ScoreEntry]

    @property
    def passed(self) -> bool:
        return all(e.passed for e in self.entries)


def score_against_ground_truth(
    claims: list[AtomicClaim],
    coverage_entries: list[CoverageEntry],
    ground_truth: list[dict],
) -> ScoreReport:
    label_by_claim_id = {e.claim_id: e.label for e in coverage_entries}
    entries = []
    for gt in ground_truth:
        quote = gt["quote"].lower()
        matched = next(
            (c for c in claims if quote in c.evidence.quote.lower() or c.evidence.quote.lower() in quote),
            None,
        )
        entries.append(
            ScoreEntry(
                ground_truth_id=gt["id"],
                expected=VerdictLabel(gt["expected_verdict"]),
                actual=label_by_claim_id.get(matched.id) if matched else None,
                matched_claim_id=matched.id if matched else None,
                is_trap=gt.get("is_trap", False),
            )
        )
    return ScoreReport(entries=entries)
