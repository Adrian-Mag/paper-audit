from __future__ import annotations

from importlib.resources import files


def load_prompt(name: str) -> str:
    return files("paper_audit").joinpath("prompts", name).read_text(encoding="utf-8")
