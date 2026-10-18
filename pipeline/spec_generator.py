"""Step 1 exercise: turn a vague ticket into a structured, validated spec.

Step 4 adds LangFuse tracing: every call becomes a trace with the ticket id,
model, and prompt version attached as metadata, plus a nested "generation"
observation for the actual LLM call (so cost/latency show up per call).
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client
from pydantic import BaseModel, Field, ValidationError

from pipeline.llm_client import DEFAULT_MODEL, chat_completion

load_dotenv()

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "spec_prompt.md"
# bump this when prompts/spec_prompt.md changes meaningfully (Step 5 compares versions)
PROMPT_VERSION = "v1"


class TicketSpec(BaseModel):
    user: str
    problem: str
    acceptance_criteria: list[str] = Field(min_length=3)
    edge_cases: list[str] = Field(min_length=2)
    test_cases: list[str] = Field(min_length=2)


class SpecGenerationError(RuntimeError):
    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def _extract_json(text: str) -> str:
    """Find the first balanced {...} object (brace-counting, not greedy regex
    to the last '}' — small/weak models sometimes emit trailing junk after a
    valid object, which a greedy match would swallow into the JSON string)."""
    start = text.find("{")
    if start == -1:
        raise SpecGenerationError(f"No JSON object found in model output: {text!r}", raw=text)

    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    raise SpecGenerationError(f"Unbalanced JSON object in model output: {text!r}", raw=text)


def generate_spec(
    ticket_text: str,
    model: str | None = None,
    ticket_id: str | None = None,
    prompt_path: Path | None = None,
    prompt_version: str | None = None,
) -> TicketSpec:
    """Generate a spec for a ticket.

    prompt_path/prompt_version let Step 5's eval harness compare prompt
    versions without touching the default prompt used everywhere else.
    """
    model_name = model or DEFAULT_MODEL
    path = prompt_path or PROMPT_PATH
    version = prompt_version or (PROMPT_VERSION if path == PROMPT_PATH else path.stem)
    system_prompt = path.read_text()
    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="span",
        name="generate_spec",
        input={"ticket_text": ticket_text},
    ) as span:
        span.update(
            metadata={
                "ticket_id": ticket_id,
                "prompt_version": version,
                "model": model_name,
            },
            version=version,
        )

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="spec_llm_call",
            model=model_name,
            metadata={"ticket_id": ticket_id, "model": model_name},
            input={"system": system_prompt, "user": ticket_text},
        ) as generation:
            raw = chat_completion(system_prompt, ticket_text, model=model_name)
            generation.update(output=raw)

        json_str = _extract_json(raw)
        try:
            data = json.loads(json_str)
            spec = TicketSpec.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            span.update(output={"error": str(exc)})
            raise SpecGenerationError(f"Spec generation failed: {exc}", raw=raw) from exc

        span.update(output=spec.model_dump())
        return spec


if __name__ == "__main__":
    import sys

    ticket = sys.argv[1] if len(sys.argv) > 1 else "Search is broken, fix it"
    spec = generate_spec(ticket)
    print(spec.model_dump_json(indent=2))
    get_client().flush()
