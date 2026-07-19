"""JSON run artifacts: per-project run directory with claims, quote-check
results, verdicts, report, and usage ledger.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from paper_audit.backends.base import RawUsage
from paper_audit.pipeline.analyst import AnalystOutput
from paper_audit.pipeline.quote_check import QuoteCheckResult
from paper_audit.pipeline.synthesize import SynthesisResult
from paper_audit.schemas import Verdict
from paper_audit.usage import UsageLedger

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "run"


class RunStore:
    """Owns one run directory: <project>/.paper-audit/runs/<date>_<fixture>_<question>/."""

    def __init__(self, project_root: Path, fixture: str, question_slug: str, run_date: date | None = None) -> None:
        run_date = run_date or date.today()
        run_name = f"{run_date.isoformat()}_{slugify(fixture)}_{slugify(question_slug)}"
        self.run_dir = project_root / ".paper-audit" / "runs" / run_name
        self.verdicts_dir = self.run_dir / "verdicts"

    def prepare(self) -> None:
        self.verdicts_dir.mkdir(parents=True, exist_ok=True)

    def write_claims(self, analyst_output: AnalystOutput) -> None:
        (self.run_dir / "claims.json").write_text(analyst_output.model_dump_json(indent=2))

    def write_quote_check(self, results: list[QuoteCheckResult]) -> None:
        payload = [r.model_dump(mode="json") for r in results]
        (self.run_dir / "quote_check.json").write_text(json.dumps(payload, indent=2))

    def write_verdict(self, verdict: Verdict, usage: RawUsage) -> None:
        record = {**verdict.model_dump(mode="json"), "session_id": usage.session_id, "usage": _usage_dict(usage)}
        (self.verdicts_dir / f"{verdict.claim_id}.json").write_text(json.dumps(record, indent=2))

    def write_report(self, synthesis: SynthesisResult) -> None:
        (self.run_dir / "report.md").write_text(synthesis.report_markdown)

    def write_usage(self, ledger: UsageLedger) -> None:
        (self.run_dir / "usage.json").write_text(ledger.model_dump_json(indent=2))


def _usage_dict(usage: RawUsage) -> dict:
    return {
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
        "output_tokens": usage.output_tokens,
        "duration_ms": usage.duration_ms,
    }
