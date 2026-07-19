"""Fallback backend: `claude -p` subprocess runner. Kept live so a switch away
from the SDK never requires redesigning the pipeline -- see
paper-audit-HANDOVER.md.

`--tools ""` is what actually removes tool definitions from context (unlike
`--allowedTools`, which only changes permission, not what's defined). Every
call passes `--no-session-persistence`: v0 never resumes a session.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from paper_audit.backends.base import RawUsage, WorkerError, WorkerJob, WorkerResult

T = TypeVar("T", bound=BaseModel)

DEFAULT_TIMEOUT_S = 180


class CliAgentBackend:
    """AgentBackend that shells out to the claude CLI in --print mode, one fresh session per call."""

    def __init__(self, cli_path: str | None = None, timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
        self._cli_path = cli_path or shutil.which("claude")
        if self._cli_path is None:
            raise WorkerError("claude CLI not found on PATH")
        self._timeout_s = timeout_s

    def run(self, job: WorkerJob, output_schema: type[T]) -> WorkerResult[T]:
        schema = output_schema.model_json_schema()
        argv = [
            self._cli_path,
            "-p",
            job.prompt,
            "--model",
            job.model,
            "--output-format",
            "json",
            "--tools",
            "",
            "--setting-sources",
            "",
            "--no-session-persistence",
            "--json-schema",
            json.dumps(schema),
        ]
        if job.system_prompt:
            argv += ["--system-prompt", job.system_prompt]

        start = time.monotonic()
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=self._timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"claude CLI timed out after {self._timeout_s}s for stage={job.stage}") from exc
        duration_ms = int((time.monotonic() - start) * 1000)

        if proc.returncode != 0:
            raise WorkerError(f"claude CLI exited {proc.returncode} for stage={job.stage}\nstderr:\n{proc.stderr}")

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise WorkerError(f"claude CLI produced non-JSON output for stage={job.stage}:\n{proc.stdout}") from exc

        if envelope.get("is_error"):
            raise WorkerError(f"claude CLI reported an error for stage={job.stage}: {envelope}")

        structured = envelope.get("structured_output")
        if structured is None:
            raise WorkerError(f"claude CLI returned no structured_output for stage={job.stage}: {envelope}")

        try:
            output = output_schema.model_validate(structured)
        except ValidationError as exc:
            raise WorkerError(
                f"worker output failed schema validation against {output_schema.__name__} "
                f"for stage={job.stage}: {exc}"
            ) from exc

        usage = envelope.get("usage") or {}
        raw_usage = RawUsage(
            model=job.model,
            session_id=envelope.get("session_id", ""),
            input_tokens=usage.get("input_tokens", 0),
            cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=envelope.get("duration_ms", duration_ms),
        )
        return WorkerResult(output=output, usage=raw_usage)
