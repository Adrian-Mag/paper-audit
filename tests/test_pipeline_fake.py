from pathlib import Path

import yaml

from paper_audit.backends.base import WorkerJob
from paper_audit.backends.fake import FakeAgentBackend
from paper_audit.pipeline.analyst import RawClaim, RawClaimList, run_analyst
from paper_audit.pipeline.quote_check import check_quotes
from paper_audit.pipeline.synthesize import synthesize
from paper_audit.pipeline.verifier import RawVerdict, run_verifier
from paper_audit.schemas import Question, VerdictLabel

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture() -> tuple[str, dict]:
    paper_text = (FIXTURES / "toy_paper.md").read_text()
    ground_truth = yaml.safe_load((FIXTURES / "toy_question.yaml").read_text())
    return paper_text, ground_truth


def test_full_pipeline_on_toy_fixture_matches_ground_truth() -> None:
    paper_text, gt = _load_fixture()
    question = Question(text=gt["question"]["text"].strip())
    ground_truth_by_quote = {entry["quotes"][0]: entry for entry in gt["ground_truth"]}

    # One raw claim per ground-truth entry, plus a compound claim that must
    # be rejected before verification, plus a claim citing a quote that is
    # not actually in the paper (must fail quote-check and never reach the
    # verifier).
    raw_claims = [
        RawClaim(
            text="Twenty-four undergraduate students participated in the study.",
            evidence_quote="Twenty-four undergraduate students",
        ),
        RawClaim(
            text="Response time on the digit-span task was 612 ms following paced breathing.",
            evidence_quote="response time on the digit-span task was 612 ms",
        ),
        RawClaim(
            text="Accuracy on the digit-span task did not differ significantly between conditions.",
            evidence_quote="Accuracy on the digit-span task did not differ significantly",
        ),
        RawClaim(
            text="The paper states that the sample was limited to undergraduate students at a single university.",
            evidence_quote="our sample was limited to undergraduate students at a single university",
        ),
        RawClaim(
            text="Paced breathing improves cognitive performance.",
            evidence_quote="paced breathing improves cognitive performance",
        ),
        RawClaim(
            text="The method is simple and it is cheap to deploy.",  # compound -> rejected
            evidence_quote="Twenty-four undergraduate students",
        ),
        RawClaim(
            text="The intervention cures insomnia in the elderly.",  # fabricated quote
            evidence_quote="paced breathing cures insomnia in the elderly",
        ),
    ]

    verifier_jobs: list[WorkerJob] = []

    def responder(job: WorkerJob, schema: type):
        if schema is RawClaimList:
            return RawClaimList(claims=raw_claims)
        if schema is RawVerdict:
            verifier_jobs.append(job)
            for quote, entry in ground_truth_by_quote.items():
                if quote.lower() in job.prompt.lower():
                    return RawVerdict(
                        label=VerdictLabel(entry["expected_verdict"]),
                        rationale=f"matches ground truth entry {entry['id']}",
                    )
            raise AssertionError(f"no ground-truth entry matched verifier prompt: {job.prompt}")
        raise AssertionError(f"unexpected schema requested: {schema}")

    backend = FakeAgentBackend(responder)

    analyst_output, _analyst_usage = run_analyst(paper_text, question, backend, model="haiku")

    assert len(analyst_output.rejected) == 1
    assert "compound" in analyst_output.rejected[0].reason.lower()
    assert len(analyst_output.claims) == 6
    assert [c.id for c in analyst_output.claims] == ["C1", "C2", "C3", "C4", "C5", "C6"]

    quote_checks = check_quotes(analyst_output.claims, paper_text)
    quote_check_by_id = {qc.claim_id: qc for qc in quote_checks}

    fabricated_claim = next(c for c in analyst_output.claims if c.text.startswith("The intervention cures"))
    assert quote_check_by_id[fabricated_claim.id].passed is False

    verdicts = {}
    for claim in analyst_output.claims:
        if not quote_check_by_id[claim.id].passed:
            continue
        verdict, _usage = run_verifier(claim, backend, model="sonnet")
        verdicts[claim.id] = verdict

    # the fabricated-quote claim's citation was broken before verification,
    # so it must never have consumed a verifier call
    assert len(verifier_jobs) == 5
    assert not any("cures insomnia" in job.prompt.lower() for job in verifier_jobs)

    result = synthesize(analyst_output.claims, quote_checks, verdicts, rejected=analyst_output.rejected)

    assert result.coverage.total == 6
    assert result.coverage.count(VerdictLabel.SUPPORTED) == 4
    assert result.coverage.count(VerdictLabel.NOT_SUPPORTED) == 2  # the trap + the fabricated-quote claim

    trap_claim = next(c for c in analyst_output.claims if "improves cognitive performance" in c.text.lower())
    trap_entry = next(e for e in result.coverage.entries if e.claim_id == trap_claim.id)
    assert trap_entry.label == VerdictLabel.NOT_SUPPORTED

    supported_section = result.report_markdown.split("## Supported claims", 1)[1].split("## Dropped claims", 1)[0]
    dropped_section = result.report_markdown.split("## Dropped claims", 1)[1]
    assert trap_claim.id in dropped_section
    assert trap_claim.id not in supported_section
    assert fabricated_claim.id in dropped_section

    assert "Rejected before verification" in result.report_markdown
    assert "cheap to deploy" in result.report_markdown


def test_pipeline_stops_at_quote_check_for_all_bad_citations() -> None:
    """A claim whose citation is entirely fabricated never reaches the verifier, at all."""
    paper_text, gt = _load_fixture()
    question = Question(text=gt["question"]["text"].strip())

    def responder(job: WorkerJob, schema: type):
        if schema is RawClaimList:
            return RawClaimList(
                claims=[RawClaim(text="The paper was written on a Tuesday.", evidence_quote="written on a Tuesday")]
            )
        raise AssertionError("verifier should never be called: quote check must fail first")

    backend = FakeAgentBackend(responder)
    analyst_output, _ = run_analyst(paper_text, question, backend, model="haiku")
    quote_checks = check_quotes(analyst_output.claims, paper_text)

    assert quote_checks[0].passed is False

    result = synthesize(analyst_output.claims, quote_checks, verdicts={}, rejected=analyst_output.rejected)
    assert result.coverage.count(VerdictLabel.NOT_SUPPORTED) == 1
    assert result.coverage.count(VerdictLabel.SUPPORTED) == 0
