"""Step 1 exercise: turn a vague ticket into a structured, validated spec.

Step 4 adds LangFuse tracing: every call becomes a trace with the ticket id,
model, and prompt version attached as metadata, plus a nested "generation"
observation for the actual LLM call (so cost/latency show up per call).
"""
from __future__ import annotations

import json
import re
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
    pass


def _extract_json(text: str) -> str:
    """Strip markdown code fences if the model added them anyway."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise SpecGenerationError(f"No JSON object found in model output: {text!r}")
    return match.group(0)


def generate_spec(
    ticket_text: str, model: str | None = None, ticket_id: str | None = None
) -> TicketSpec:
    model_name = model or DEFAULT_MODEL
    system_prompt = PROMPT_PATH.read_text()
    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="span",
        name="generate_spec",
        input={"ticket_text": ticket_text},
    ) as span:
        span.update(
            metadata={
                "ticket_id": ticket_id,
                "prompt_version": PROMPT_VERSION,
                "model": model_name,
            },
            version=PROMPT_VERSION,
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
            raise SpecGenerationError(f"Spec generation failed: {exc}\n{raw}") from exc

        span.update(output=spec.model_dump())
        return spec


if __name__ == "__main__":
    import sys

    ticket = sys.argv[1] if len(sys.argv) > 1 else "Search is broken, fix it"
    spec = generate_spec(ticket)
    print(spec.model_dump_json(indent=2))
    get_client().flush()
