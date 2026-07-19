from paper_audit.pipeline.quote_check import check_quote, check_quotes
from paper_audit.schemas import AtomicClaim, EvidenceRef

SOURCE = (
    "Twenty-four participants completed the task. "
    "Response time decreased by 18% following the intervention. "
    "The café study reported similar results—though not identical. "
    "One author wrote: “don’t overinterpret this.”"
)


def claim(quote: str, claim_id: str = "C1") -> AtomicClaim:
    return AtomicClaim(id=claim_id, text="Some proposition about the study.", evidence=EvidenceRef(quote=quote))


def test_exact_match_passes() -> None:
    result = check_quote(claim("Response time decreased by 18%"), SOURCE)
    assert result.passed is True
    assert result.reason is None
    assert result.claim_id == "C1"


def test_nonmatching_text_fails_with_reason() -> None:
    result = check_quote(claim("Response time increased by 50%"), SOURCE)
    assert result.passed is False
    assert result.reason is not None


def test_trailing_whitespace_mismatch_fails() -> None:
    # exact means exact: a quote with an extra trailing space appended past
    # the end of the source text is not a substring, and this check does not
    # normalize or trim whitespace
    result = check_quote(claim("don’t overinterpret this.” "), SOURCE)
    assert result.passed is False


def test_internal_whitespace_must_match_exactly() -> None:
    result = check_quote(claim("Response time  decreased by 18%"), SOURCE)  # double space
    assert result.passed is False


def test_unicode_em_dash_matches_when_exact() -> None:
    result = check_quote(claim("similar results—though not identical"), SOURCE)
    assert result.passed is True


def test_ascii_hyphen_does_not_match_unicode_em_dash() -> None:
    # a worker that "normalizes" an em dash to a hyphen must fail: it is no
    # longer a verbatim substring
    result = check_quote(claim("similar results-though not identical"), SOURCE)
    assert result.passed is False


def test_smart_quotes_must_match_exactly() -> None:
    result = check_quote(claim("“don’t overinterpret this.”"), SOURCE)
    assert result.passed is True


def test_straight_quotes_do_not_match_smart_quotes() -> None:
    # a common LLM failure mode: reproducing a quote with straight quotes
    # instead of the source's curly quotes
    result = check_quote(claim('"don\'t overinterpret this."'), SOURCE)
    assert result.passed is False


def test_accented_character_matches_when_exact() -> None:
    result = check_quote(claim("The café study"), SOURCE)
    assert result.passed is True


def test_check_quotes_preserves_order_and_claim_ids() -> None:
    claims = [
        claim("Twenty-four participants", "C1"),
        claim("nonexistent quote here", "C2"),
        claim("The café study", "C3"),
    ]
    results = check_quotes(claims, SOURCE)
    assert [r.claim_id for r in results] == ["C1", "C2", "C3"]
    assert [r.passed for r in results] == [True, False, True]


def test_check_quotes_empty_list() -> None:
    assert check_quotes([], SOURCE) == []
