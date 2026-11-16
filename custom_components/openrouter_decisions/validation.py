"""Validate provider results without patching Home Assistant.

Adapted from the shared AI Task validation prepared for Home Assistant Core.
"""

from math import isclose
from typing import Any

from homeassistant.components.ai_task import (
    ChoiceAnswer,
    EvaluationQuestion,
    EvaluationTaskResult,
    NoulAnswer,
    ScoreAnswer,
)
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


def _is_probability(value: Any) -> bool:
    """Return whether a value is a finite probability."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and 0 <= value <= 1
    )


def validate_result(
    questions: dict[str, EvaluationQuestion], result: EvaluationTaskResult
) -> None:
    """Enforce the evaluation result contract at the integration boundary."""
    if (
        not isinstance(result, EvaluationTaskResult)
        or not isinstance(result.answers, dict)
        or result.answers.keys() != questions.keys()
    ):
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="unexpected_evaluation_questions",
        )

    for question_id, question in questions.items():
        answer = result.answers[question_id]
        valid = False
        probabilities: list[float] = []
        if question["type"] == "noul" and isinstance(answer, NoulAnswer):
            valid = _is_probability(answer.noul)
        elif question["type"] == "choice" and isinstance(answer, ChoiceAnswer):
            if (
                isinstance(answer.probabilities, dict)
                and answer.probabilities.keys() == question["criteria"].keys()
                and isinstance(answer.choice, str)
                and answer.choice in question["criteria"]
            ):
                probabilities = list(answer.probabilities.values())
                valid = True
        elif question["type"] == "score" and isinstance(answer, ScoreAnswer):
            if (
                isinstance(answer.probabilities, list)
                and len(answer.probabilities) == len(question["criteria"])
                and not isinstance(answer.score, bool)
                and isinstance(answer.score, (int, float))
                and 0 <= answer.score <= len(question["criteria"]) - 1
            ):
                probabilities = answer.probabilities
                valid = True

        if probabilities:
            valid = (
                valid
                and all(_is_probability(value) for value in probabilities)
                and isclose(sum(probabilities), 1, abs_tol=1e-6)
            )
        if valid and isinstance(answer, ChoiceAnswer):
            valid = answer.probabilities[answer.choice] == max(probabilities)
        elif valid and isinstance(answer, ScoreAnswer):
            valid = isclose(
                answer.score,
                sum(index * value for index, value in enumerate(probabilities)),
                abs_tol=1e-6,
            )
        if not valid:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_evaluation_answer",
                translation_placeholders={"question_id": question_id},
            )
