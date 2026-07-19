"""Primary backend: Agent SDK query() per worker, one fresh session each call.

`tools=[]` (not `allowed_tools=[]`) is what actually strips tool definitions
from context; `allowed_tools` only changes permission, not what gets sent to
the model, and leaves the full Claude Code tool manifest (~12k tokens of
preamble) in every call. Defaults `cli_path` to the CLI on PATH rather than
the SDK's bundled copy, so the SDK and CLI backends provably run the same
binary -- useful for telling apart "the SDK behaves differently" from "this
machine has two different Claude binaries."
"""

from __future__ import annotations

import shutil
import time
from typing import TypeVar

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import BaseModel, ValidationError

from paper_audit.backends.base import RawUsage, WorkerError, WorkerJob, WorkerResult

T = TypeVar("T", bound=BaseModel)


class SdkAgentBackend:
    """AgentBackend backed by the Claude Agent SDK, one fresh query() session per call."""

    def __init__(self, cli_path: str | None = None) -> None:
        self._cli_path = cli_path or shutil.which("claude")

    def run(self, job: WorkerJob, output_schema: type[T]) -> WorkerResult[T]:
        return anyio.run(self._run_async, job, output_schema)

    async def _run_async(self, job: WorkerJob, output_schema: type[T]) -> WorkerResult[T]:
        schema = output_schema.model_json_schema()
        opts = ClaudeAgentOptions(
            model=job.model,
            tools=[],
            # No turn cap: JSON-schema-constrained output uses an internal
            # StructuredOutput tool call as a separate turn after the
            # reasoning turn, so max_turns=1 truncates non-trivial responses
            # before that tool call happens. tools=[] leaves StructuredOutput
            # as the only callable tool, so there is no runaway-turns risk to
            # cap against -- this matches the CLI backend, which has no
            # turn-cap flag at all.
            system_prompt=job.system_prompt,
            setting_sources=[],
            cli_path=self._cli_path,
            output_format={"type": "json_schema", "schema": schema},
        )

        result_msg: ResultMessage | None = None
        start = time.monotonic()
        async for msg in query(prompt=job.prompt, options=opts):
            if isinstance(msg, ResultMessage):
                result_msg = msg
        duration_ms = int((time.monotonic() - start) * 1000)

        if result_msg is None:
            raise WorkerError(f"SDK query produced no ResultMessage for stage={job.stage}")
        if result_msg.is_error:
            raise WorkerError(f"SDK query reported an error for stage={job.stage}: {result_msg}")

        structured = result_msg.structured_output
        if structured is None:
            raise WorkerError(f"SDK query returned no structured_output for stage={job.stage}: {result_msg}")

        try:
            output = output_schema.model_validate(structured)
        except ValidationError as exc:
            raise WorkerError(
                f"worker output failed schema validation against {output_schema.__name__} "
                f"for stage={job.stage}: {exc}"
            ) from exc

        usage = result_msg.usage or {}
        raw_usage = RawUsage(
            model=job.model,
            session_id=result_msg.session_id,
            input_tokens=usage.get("input_tokens", 0),
            cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=result_msg.duration_ms or duration_ms,
        )
        return WorkerResult(output=output, usage=raw_usage)
