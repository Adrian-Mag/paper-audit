"""Entry point: `paper-audit run --fixture toy`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from paper_audit.backends.base import AgentBackend
from paper_audit.backends.cli_backend import CliAgentBackend
from paper_audit.backends.sdk_backend import SdkAgentBackend
from paper_audit.config import load_config
from paper_audit.guard import MeteredBillingError, enforce_billing_guard
from paper_audit.pipeline.analyst import run_analyst
from paper_audit.pipeline.quote_check import check_quotes
from paper_audit.pipeline.synthesize import synthesize
from paper_audit.pipeline.verifier import run_verifier
from paper_audit.schemas import Question, VerdictLabel
from paper_audit.score import score_against_ground_truth
from paper_audit.store import RunStore, slugify
from paper_audit.usage import UsageLedger, UsageRecord

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"


def _load_fixture(name: str) -> tuple[str, Question, dict]:
    paper_path = FIXTURES_DIR / f"{name}_paper.md"
    question_path = FIXTURES_DIR / f"{name}_question.yaml"
    if not paper_path.is_file() or not question_path.is_file():
        raise FileNotFoundError(f"fixture '{name}' not found under {FIXTURES_DIR}")
    paper_text = paper_path.read_text()
    data = yaml.safe_load(question_path.read_text())
    question = Question(text=data["question"]["text"].strip())
    return paper_text, question, data


def _make_backend(name: str) -> AgentBackend:
    if name == "cli":
        return CliAgentBackend()
    if name == "sdk":
        return SdkAgentBackend()
    raise ValueError(f"unknown backend: {name}")


def _record(stage: str, usage, claim_id: str | None = None) -> UsageRecord:
    return UsageRecord(
        stage=stage,
        claim_id=claim_id,
        model=usage.model,
        session_id=usage.session_id,
        input_tokens=usage.input_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        output_tokens=usage.output_tokens,
        duration_ms=usage.duration_ms,
    )


def run(fixture: str, backend_name: str, project_root: Path) -> int:
    enforce_billing_guard()

    config = load_config()
    paper_text, question, fixture_data = _load_fixture(fixture)
    backend = _make_backend(backend_name)

    store = RunStore(project_root, fixture=fixture, question_slug=slugify(question.text))
    store.prepare()

    ledger = UsageLedger()

    print(f"[analyst] extracting claims ({config.model_tiers.analyst}, backend={backend_name})...", file=sys.stderr)
    analyst_output, analyst_usage = run_analyst(paper_text, question, backend, model=config.model_tiers.analyst)
    ledger.add(_record("analyst", analyst_usage))
    store.write_claims(analyst_output)
    print(
        f"  {len(analyst_output.claims)} claims accepted, {len(analyst_output.rejected)} rejected",
        file=sys.stderr,
    )

    quote_checks = check_quotes(analyst_output.claims, paper_text)
    store.write_quote_check(quote_checks)
    quote_check_by_id = {qc.claim_id: qc for qc in quote_checks}

    verdicts = {}
    for claim in analyst_output.claims:
        qc = quote_check_by_id[claim.id]
        if not qc.passed:
            print(f"[verifier] {claim.id}: skipped (quote check failed)", file=sys.stderr)
            continue
        print(f"[verifier] {claim.id}: verifying ({config.model_tiers.verifier})...", file=sys.stderr)
        verdict, usage = run_verifier(claim, backend, model=config.model_tiers.verifier)
        verdicts[claim.id] = verdict
        ledger.add(_record("verifier", usage, claim_id=claim.id))
        store.write_verdict(verdict, usage)
        print(f"  {claim.id}: {verdict.label.value}", file=sys.stderr)

    result = synthesize(analyst_output.claims, quote_checks, verdicts, rejected=analyst_output.rejected)
    store.write_report(result)
    store.write_usage(ledger)

    print(file=sys.stderr)
    print(f"Report written to {store.run_dir / 'report.md'}", file=sys.stderr)
    print(
        f"Coverage: {result.coverage.total} claims -- "
        f"{result.coverage.count(VerdictLabel.SUPPORTED)} supported, "
        f"{result.coverage.count(VerdictLabel.NOT_SUPPORTED)} not supported, "
        f"{result.coverage.count(VerdictLabel.UNKNOWN)} unknown",
        file=sys.stderr,
    )
    print(
        f"Usage: {ledger.total_calls} calls, "
        f"{ledger.total_content_input_tokens} content input tokens, "
        f"{ledger.total_overhead_tokens} overhead tokens, "
        f"{ledger.total_output_tokens} output tokens",
        file=sys.stderr,
    )

    ground_truth = fixture_data.get("ground_truth")
    if ground_truth:
        score = score_against_ground_truth(analyst_output.claims, result.coverage.entries, ground_truth)
        print(file=sys.stderr)
        print("Self-score against ground truth:", file=sys.stderr)
        for entry in score.entries:
            status = "PASS" if entry.passed else "FAIL"
            trap = " [TRAP]" if entry.is_trap else ""
            if entry.matches:
                actual = ", ".join(f"{m.claim_id}={m.verdict.value}" for m in entry.matches)
            else:
                actual = "no matching claim"
            print(
                f"  [{status}] {entry.ground_truth_id}{trap}: expected={entry.expected.value} actual={actual}",
                file=sys.stderr,
            )
        print(f"Overall: {'PASS' if score.passed else 'FAIL'}", file=sys.stderr)
        return 0 if score.passed else 1

    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="paper-audit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an audit against a fixture")
    run_parser.add_argument("--fixture", required=True, help="Fixture name, e.g. 'toy'")
    run_parser.add_argument("--backend", choices=["cli", "sdk"], default="cli")
    run_parser.add_argument("--project-root", type=Path, default=Path.cwd())

    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            code = run(args.fixture, args.backend, args.project_root)
        except MeteredBillingError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        sys.exit(code)


if __name__ == "__main__":
    main()
