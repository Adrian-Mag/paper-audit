"""Global configuration: model-tier assignment per pipeline stage.

Billing policy is enforced independently in guard.py and is not configurable
here -- per-project config must never be able to weaken it, so it is simplest
and safest for it to not be a config knob at all in v0.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_GLOBAL_CONFIG_PATH = Path.home() / ".config" / "paper-audit" / "config.toml"


class ModelTiers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analyst: str = "haiku"
    verifier: str = "sonnet"
    hard_case: str = "opus"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_tiers: ModelTiers = Field(default_factory=ModelTiers)


def load_config(path: Path | None = None) -> Config:
    path = path if path is not None else DEFAULT_GLOBAL_CONFIG_PATH
    if not path.is_file():
        return Config()
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Config.model_validate(data)
