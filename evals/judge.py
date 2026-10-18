"""Step 5: LLM-as-judge. Scores a generated spec 1-5 on a rubric, using a
different model than the one that generated the spec (reduces self-preference
bias — a model is more likely to rate its own phrasing highly).
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError

from pipeline.llm_client import LLMClientError, chat_completion

JUDGE_SYSTEM_PROMPT = """You are a strict reviewer of engineering specs for a \
classifieds-listings API. You did not write this spec; judge it objectively.

Given the original ticket and a generated spec (JSON with user, problem, \
acceptance_criteria, edge_cases, test_cases), score it 1-5 on each dimension:
- clarity: is the problem statement understandable and unambiguous?
- specificity: are acceptance_criteria/test_cases concrete and testable, not vague?
- relevance: does the spec actually address the ticket, not something else?

Output STRICT JSON only, no markdown fences:
{"clarity": <1-5>, "specificity": <1-5>, "relevance": <1-5>, "reasoning": "<one sentence>"}
"""


class JudgeScore(BaseModel):
    clarity: int = Field(ge=1, le=5)
    specificity: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    reasoning: str

    @property
    def average(self) -> float:
        return (self.clarity + self.specificity + self.relevance) / 3


class JudgeError(RuntimeError):
    pass


def judge_spec(ticket_text: str, spec_json: dict, judge_model: str) -> JudgeScore:
    user_prompt = (
        f"Ticket: {ticket_text}\n\nGenerated spec:\n{json.dumps(spec_json, indent=2)}"
    )
    try:
        raw = chat_completion(JUDGE_SYSTEM_PROMPT, user_prompt, model=judge_model)
    except LLMClientError as exc:
        raise JudgeError(f"judge call failed: {exc}") from exc

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise JudgeError(f"judge did not return JSON: {raw!r}")
    try:
        data = json.loads(match.group(0))
        return JudgeScore.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise JudgeError(f"judge output failed validation: {exc}\n{raw}") from exc
