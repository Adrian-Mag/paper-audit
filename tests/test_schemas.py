import pytest
from pydantic import ValidationError

from paper_audit.schemas import (
    AtomicClaim,
    CoverageEntry,
    CoverageReport,
    EvidenceRef,
    Question,
    Verdict,
    VerdictLabel,
)


def make_claim(text: str = "The model achieves 92% accuracy on the test set.", claim_id: str = "C1") -> AtomicClaim:
    return AtomicClaim(id=claim_id, text=text, evidence=EvidenceRef(quote="92% accuracy"))


def test_valid_atomic_claim_constructs() -> None:
    claim = make_claim()
    assert claim.id == "C1"
    assert claim.evidence.quote == "92% accuracy"


@pytest.mark.parametrize(
    "text",
    [
        "The model is fast and it is accurate.",
        "The result holds; the authors confirm it separately.",
        "The method is simple but it is not scalable.",
        "The claim held, however the sample size was small.",
    ],
)
def test_compound_claim_text_rejected(text: str) -> None:
    with pytest.raises(ValidationError, match="compound"):
        make_claim(text=text)


@pytest.mark.parametrize(
    "text",
    [
        "Accuracy did not differ significantly between the paced-breathing condition and the control condition.",
        "Twenty-four participants completed the digit-span task and the reading-control task.",
    ],
)
def test_compound_object_and_is_not_rejected(text: str) -> None:
    # "X and Y" naming two objects of a single proposition (a comparison, a
    # list) is not a compound claim, even though it contains the word "and"
    claim = make_claim(text=text)
    assert claim.text == text


def test_and_followed_by_pronoun_is_rejected() -> None:
    with pytest.raises(ValidationError, match="compound"):
        make_claim(text="Response time decreased significantly, and this decrease held across all trials.")


def test_missing_text_field_rejected() -> None:
    with pytest.raises(ValidationError):
        AtomicClaim(id="C1", evidence=EvidenceRef(quote="x"))


def test_empty_text_rejected() -> None:
    with pytest.raises(ValidationError):
        make_claim(text="")


def test_malformed_id_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        make_claim(claim_id="1")


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        AtomicClaim(
            id="C1",
            text="A valid single proposition.",
            evidence=EvidenceRef(quote="x"),
            confidence=0.9,
        )


def test_claim_is_immutable() -> None:
    claim = make_claim()
    with pytest.raises(ValidationError):
        claim.text = "changed"


def test_evidence_ref_empty_quote_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(quote="")


def test_question_requires_nonempty_text() -> None:
    with pytest.raises(ValidationError):
        Question(text="")
    assert Question(text="Does the paper support claim X?").text.startswith("Does")


def test_verdict_valid_construction_and_roundtrip() -> None:
    verdict = Verdict(claim_id="C1", label=VerdictLabel.SUPPORTED, rationale="The quote directly states this.")
    dumped = verdict.model_dump()
    assert dumped["label"] == "supported"
    assert dumped["claim_id"] == "C1"


def test_verdict_invalid_label_rejected() -> None:
    with pytest.raises(ValidationError):
        Verdict(claim_id="C1", label="maybe", rationale="unclear")


def test_verdict_empty_rationale_rejected() -> None:
    with pytest.raises(ValidationError):
        Verdict(claim_id="C1", label=VerdictLabel.UNKNOWN, rationale="")


def test_verdict_malformed_claim_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Verdict(claim_id="claim-one", label=VerdictLabel.SUPPORTED, rationale="ok")


def test_coverage_report_counts() -> None:
    report = CoverageReport(
        entries=[
            CoverageEntry(claim_id="C1", label=VerdictLabel.SUPPORTED),
            CoverageEntry(claim_id="C2", label=VerdictLabel.SUPPORTED),
            CoverageEntry(claim_id="C3", label=VerdictLabel.NOT_SUPPORTED),
            CoverageEntry(claim_id="C4", label=VerdictLabel.UNKNOWN),
        ]
    )
    assert report.total == 4
    assert report.count(VerdictLabel.SUPPORTED) == 2
    assert report.count(VerdictLabel.NOT_SUPPORTED) == 1
    assert report.count(VerdictLabel.UNKNOWN) == 1


def test_coverage_report_empty() -> None:
    report = CoverageReport(entries=[])
    assert report.total == 0
    assert report.count(VerdictLabel.SUPPORTED) == 0
