"""Access the OpenRouter Decisions model catalog."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from openai import AsyncOpenAI

from .const import BASE_URL, REPOSITORY_URL


def create_client(hass: HomeAssistant, api_key: str) -> AsyncOpenAI:
    """Use Home Assistant's shared HTTP client."""
    return AsyncOpenAI(
        api_key=api_key,
        base_url=BASE_URL,
        http_client=get_async_client(hass),
        timeout=30,
        max_retries=1,
        default_headers={
            "X-Title": "Home Assistant OpenRouter Decisions",
            "HTTP-Referer": REPOSITORY_URL,
        },
    )


async def async_get_models(client: AsyncOpenAI) -> dict[str, dict[str, Any]]:
    """Return models that explicitly advertise Decisions output."""
    response = await client.get(
        "/models",
        cast_to=dict[str, Any],
        options={"params": {"output_modalities": "decisions"}},
    )
    models: dict[str, dict[str, Any]] = {}
    for model in response["data"]:
        architecture = model["architecture"]
        if "decisions" not in architecture["output_modalities"]:
            continue
        model_id = model["id"]
        name = model["name"]
        modalities = architecture["input_modalities"]
        if (
            not isinstance(model_id, str)
            or not isinstance(name, str)
            or not isinstance(modalities, list)
            or not all(isinstance(value, str) for value in modalities)
        ):
            raise ValueError("Invalid model catalog")
        models[model_id] = model
    return models
