"""Evaluate questions with OpenRouter's native Decisions API."""

import base64
from mimetypes import guess_file_type
from typing import Any

from homeassistant.components import ai_task
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.json import json_dumps
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAIError,
)

from . import OpenRouterConfigEntry
from .const import DECISIONS_URL, DOMAIN
from .validation import validate_result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenRouterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one evaluation entity per configured model."""
    async_add_entities([OpenRouterEvaluationEntity(entry)])


def _parse_answer(answer: dict[str, Any]) -> ai_task.EvaluationAnswer:
    """Convert a native Decisions answer to the Home Assistant contract."""
    if answer["type"] == "noul":
        return ai_task.NoulAnswer(noul=answer["noul"])
    if answer["type"] == "choice":
        return ai_task.ChoiceAnswer(
            choice=answer["choice"], probabilities=answer["probabilities"]
        )
    if answer["type"] == "score":
        probabilities = answer["probabilities"]
        if not isinstance(probabilities, dict) or set(probabilities) != {
            str(i) for i in range(len(probabilities))
        }:
            raise ValueError("Invalid score probability indices")
        return ai_task.ScoreAnswer(
            score=answer["score"],
            probabilities=[probabilities[str(i)] for i in range(len(probabilities))],
        )
    raise ValueError("Unknown answer type")


class OpenRouterEvaluationEntity(ai_task.AITaskEntity):
    """A standalone OpenRouter decision task entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: OpenRouterConfigEntry) -> None:
        """Initialize the selected model and its advertised capabilities."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_supported_features = ai_task.AITaskEntityFeature.EVALUATE
        if {"image", "file"}.intersection(entry.runtime_data.modalities):
            self._attr_supported_features |= (
                ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "OpenRouter",
            "model": entry.data[CONF_MODEL],
            "entry_type": "service",
        }

    async def _async_evaluate(
        self, task: ai_task.EvaluationTask
    ) -> ai_task.EvaluationTaskResult:
        """Prepare, submit, parse, and validate an evaluation."""
        state = (
            json_dumps(task.state)
            if isinstance(task.state, (bool, int, float))
            else task.state
        )
        body: dict[str, Any] = {
            "model": self.entry.data[CONF_MODEL],
            "state": state,
            "questions": task.questions,
        }
        if task.attachments:
            # Core resolves permitted local media before invoking this method.
            content = await self.hass.async_add_executor_job(
                self._prepare_attachments, task.attachments
            )
            body["state"] = [*([] if state is None else [state]), *content]
        try:
            response = await self.entry.runtime_data.client.post(
                DECISIONS_URL, cast_to=dict[str, Any], body=body
            )
        except AuthenticationError as err:
            self.entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except APIStatusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="evaluation_api_error",
                translation_placeholders={"status": str(err.status_code)},
            ) from err
        except APITimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="evaluation_timeout"
            ) from err
        except APIConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="evaluation_connection_error"
            ) from err
        except OpenAIError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="evaluation_error"
            ) from err
        try:
            result = ai_task.EvaluationTaskResult(
                answers={
                    question_id: _parse_answer(answer)
                    for question_id, answer in response["answers"].items()
                }
            )
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_evaluation"
            ) from err
        validate_result(task.questions, result)
        return result

    def _prepare_attachments(self, attachments: list[Any]) -> list[dict[str, Any]]:
        """Encode permitted image and PDF files in one executor job."""
        content: list[dict[str, Any]] = []
        for attachment in attachments:
            mime = attachment.mime_type or guess_file_type(attachment.path)[0]
            mime = (mime or "").partition(";")[0].strip().lower()
            if mime == "image/jpg":
                mime = "image/jpeg"
            modality = "file" if mime == "application/pdf" else "image"
            if (
                not mime.startswith("image/") and mime != "application/pdf"
            ) or modality not in self.entry.runtime_data.modalities:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="unsupported_attachment_type",
                )
            try:
                encoded = base64.b64encode(attachment.path.read_bytes()).decode("ascii")
            except OSError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="file_read_error"
                ) from err
            data_url = f"data:{mime};base64,{encoded}"
            if modality == "file":
                content.append(
                    {
                        "type": "file",
                        "file": {
                            "filename": attachment.path.name,
                            "file_data": data_url,
                        },
                    }
                )
            else:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
        return content
