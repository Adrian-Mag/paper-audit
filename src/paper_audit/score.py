"""Self-scoring a run against a fixture's ground truth.

Ground truth is keyed by verbatim quotes, not claim IDs (IDs are assigned
per-run and the analyst's decomposition is not fully predictable in advance
-- see fixtures/toy_question.yaml). Each ground-truth entry lists `quotes`
(one or more acceptable variants, since a paper often states the same fact
in more than one place, worded differently) and `match_on`, which field of a
claim those variants are compared against:

  evidence_quote (default) -- the claim's cited passage. Use for entries
    representing a fact the paper states.

  claim_text -- the claim's own asserted text. Use for entries representing
    a proposition we expect to be extracted regardless of what gets cited
    as its evidence -- notably a trap, where varying evidence is itself
    informative, not noise.

A ground-truth entry can match more than one claim (a trap phrase in
particular often does). All matches are scored: a trap entry only passes if
every matching claim resolved to something other than `supported`; a normal
entry passes if any matching claim resolved to the expected verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from paper_audit.schemas import AtomicClaim, CoverageEntry, VerdictLabel


@dataclass(frozen=True)
class MatchedClaim:
    claim_id: str
    verdict: VerdictLabel


@dataclass(frozen=True)
class ScoreEntry:
    ground_truth_id: str
    expected: VerdictLabel
    matches: list[MatchedClaim]
    is_trap: bool

    @property
    def passed(self) -> bool:
        if not self.matches:
            return False
        if self.is_trap:
            return all(m.verdict != VerdictLabel.SUPPORTED for m in self.matches)
        return any(m.verdict == self.expected for m in self.matches)


@dataclass(frozen=True)
class ScoreReport:
    entries: list[ScoreEntry]

    @property
    def passed(self) -> bool:
        return all(e.passed for e in self.entries)


def _claim_field(claim: AtomicClaim, match_on: str) -> str:
    if match_on == "claim_text":
        return claim.text.lower()
    return claim.evidence.quote.lower()


def _matches_variant(field_value: str, variant: str, match_on: str) -> bool:
    if match_on == "claim_text":
        return variant in field_value
    return variant in field_value or field_value in variant


def score_against_ground_truth(
    claims: list[AtomicClaim],
    coverage_entries: list[CoverageEntry],
    ground_truth: list[dict],
) -> ScoreReport:
    label_by_claim_id = {e.claim_id: e.label for e in coverage_entries}
    entries = []
    for gt in ground_truth:
        match_on = gt.get("match_on", "evidence_quote")
        variants = [q.lower() for q in gt["quotes"]]

        matches = [
            MatchedClaim(claim_id=c.id, verdict=label_by_claim_id[c.id])
            for c in claims
            if any(_matches_variant(_claim_field(c, match_on), v, match_on) for v in variants)
        ]

        entries.append(
            ScoreEntry(
                ground_truth_id=gt["id"],
                expected=VerdictLabel(gt["expected_verdict"]),
                matches=matches,
                is_trap=gt.get("is_trap", False),
            )
        )
    return ScoreReport(entries=entries)
