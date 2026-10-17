"""Step 1 exercise: turn a vague ticket into a structured, validated spec."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from pipeline.llm_client import chat_completion

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "spec_prompt.md"


class TicketSpec(BaseModel):
    user: str
    problem: str
    acceptance_criteria: list[str] = Field(min_length=3)
    edge_cases: list[str] = Field(min_length=2)
    test_cases: list[str] = Field(min_length=2)


class SpecGenerationError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    """Strip markdown code fences if the model added them anyway."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise SpecGenerationError(f"No JSON object found in model output: {text!r}")
    return match.group(0)


def generate_spec(ticket_text: str, model: str | None = None) -> TicketSpec:
    system_prompt = PROMPT_PATH.read_text()
    kwargs = {"model": model} if model else {}
    raw = chat_completion(system_prompt, ticket_text, **kwargs)

    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise SpecGenerationError(f"Model output was not valid JSON: {exc}\n{raw}") from exc

    try:
        return TicketSpec.model_validate(data)
    except ValidationError as exc:
        raise SpecGenerationError(f"Spec failed schema validation: {exc}") from exc


if __name__ == "__main__":
    import sys

    ticket = sys.argv[1] if len(sys.argv) > 1 else "Search is broken, fix it"
    spec = generate_spec(ticket)
    print(spec.model_dump_json(indent=2))
