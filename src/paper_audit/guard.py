"""Billing preflight guard: refuses to run if metered-billing credentials are present.

paper-audit must draw Claude usage only from Max subscription OAuth. An API key
takes precedence over subscription OAuth if both are present, so a stray key
(or CLI override flag) would silently switch billing without any other
symptom. Call enforce_billing_guard() before every batch of worker calls.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

METERED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_PROFILE",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

CLAUDE_SETTINGS_GLOB = "settings*.json"


class MeteredBillingError(RuntimeError):
    """Raised when the environment would route Claude usage through metered billing."""


@dataclass(frozen=True)
class GuardViolation:
    source: str
    detail: str

    def __str__(self) -> str:
        return f"{self.source}: {self.detail}"


def _check_env(environ: Mapping[str, str]) -> list[GuardViolation]:
    return [
        GuardViolation(f"env:{name}", "set; indicates metered/non-subscription billing")
        for name in METERED_ENV_VARS
        if environ.get(name)
    ]


def _check_claude_settings(claude_dir: Path) -> list[GuardViolation]:
    if not claude_dir.is_dir():
        return []
    violations = []
    for settings_file in sorted(claude_dir.glob(CLAUDE_SETTINGS_GLOB)):
        try:
            data = json.loads(settings_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("apiKeyHelper"):
            violations.append(
                GuardViolation(f"file:{settings_file}", "apiKeyHelper is set; would override subscription auth")
            )
    return violations


def check_billing_guard(
    environ: Mapping[str, str] | None = None,
    claude_dir: Path | None = None,
) -> list[GuardViolation]:
    """Return metered-billing violations found in the current environment.

    An empty list means the environment is clean for subscription-only billing.
    """
    environ = environ if environ is not None else os.environ
    claude_dir = claude_dir if claude_dir is not None else Path.home() / ".claude"
    return _check_env(environ) + _check_claude_settings(claude_dir)


def enforce_billing_guard(
    environ: Mapping[str, str] | None = None,
    claude_dir: Path | None = None,
) -> None:
    """Raise MeteredBillingError if any metered-billing indicator is present."""
    violations = check_billing_guard(environ=environ, claude_dir=claude_dir)
    if violations:
        listed = "\n".join(f"  - {v}" for v in violations)
        raise MeteredBillingError(
            "Refusing to run: metered-billing indicators detected.\n"
            f"{listed}\n"
            "paper-audit requires Claude Max subscription billing only. Remove these and retry."
        )
