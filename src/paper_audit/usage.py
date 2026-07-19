"""Token/model usage ledger.

Every worker call is recorded here: under flat-rate subscription billing the
real currency is Max session/weekly limits, not dollars, so token counts (not
total_cost_usd, which is only a client-side estimate) are the numbers that
matter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    model: str
    session_id: str
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    duration_ms: int
    claim_id: str | None = None

    @property
    def overhead_tokens(self) -> int:
        """Per-session preamble cost, distinct from real prompt content."""
        return self.cache_creation_input_tokens + self.cache_read_input_tokens


class UsageLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[UsageRecord] = Field(default_factory=list)

    def add(self, record: UsageRecord) -> None:
        self.records.append(record)

    @property
    def total_calls(self) -> int:
        return len(self.records)

    @property
    def total_content_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_overhead_tokens(self) -> int:
        return sum(r.overhead_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)
