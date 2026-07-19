"""AgentBackend protocol: the intersection of SDK and CLI capabilities this project uses.

Workers never get tools or file access in v0. The controller builds the
complete prompt text (paper, question, claim, cited passage) before calling
run(); every call is a fresh, isolated session with no continuation and no
access to any other worker's output. Output is constrained to the given
schema by the backend itself (JSON-schema-constrained decoding, native to
both the CLI and the SDK), not by prompt instructions -- Pydantic validation
on receipt is a second, independent check, not the primary enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class WorkerJob:
    prompt: str
    model: str
    stage: str
    system_prompt: str | None = None


@dataclass(frozen=True)
class RawUsage:
    model: str
    session_id: str
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    duration_ms: int


@dataclass(frozen=True)
class WorkerResult(Generic[T]):
    output: T
    usage: RawUsage


class WorkerError(RuntimeError):
    """Raised when a worker call fails, or its output does not validate against the requested schema."""


class AgentBackend(Protocol):
    def run(self, job: WorkerJob, output_schema: type[T]) -> WorkerResult[T]: ...
