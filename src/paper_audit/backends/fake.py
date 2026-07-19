"""Canned-response backend for tests. Never touches Claude; zero usage."""

from __future__ import annotations

from typing import Callable, TypeVar

from pydantic import BaseModel

from paper_audit.backends.base import RawUsage, WorkerJob, WorkerResult

T = TypeVar("T", bound=BaseModel)

Responder = Callable[[WorkerJob, type[BaseModel]], BaseModel]


class FakeAgentBackend:
    """AgentBackend that returns pre-programmed outputs via a responder callable."""

    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self._call_count = 0

    def run(self, job: WorkerJob, output_schema: type[T]) -> WorkerResult[T]:
        output = self._responder(job, output_schema)
        if not isinstance(output, output_schema):
            raise TypeError(f"fake responder returned {type(output).__name__}, expected {output_schema.__name__}")
        self._call_count += 1
        usage = RawUsage(
            model=job.model,
            session_id=f"fake-session-{self._call_count}",
            input_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            output_tokens=0,
            duration_ms=0,
        )
        return WorkerResult(output=output, usage=usage)
