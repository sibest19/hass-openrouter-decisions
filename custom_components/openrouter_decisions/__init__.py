"""OpenRouter decision models for Home Assistant."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_MODEL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from openai import AsyncOpenAI, AuthenticationError, OpenAIError

from .client import async_get_models, create_client
from .const import DOMAIN

PLATFORMS = [Platform.AI_TASK]


@dataclass
class RuntimeData:
    """The API client and current model capabilities."""

    client: AsyncOpenAI
    modalities: list[str]


type OpenRouterConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: OpenRouterConfigEntry) -> None:
    """Validate the configured model and set up its AI Task entity."""
    client = create_client(hass, entry.data[CONF_API_KEY])
    try:
        models = await async_get_models(client)
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except OpenAIError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    except (KeyError, TypeError, ValueError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="invalid_catalog"
        ) from err

    if (model := models.get(entry.data[CONF_MODEL])) is None:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="model_unavailable"
        )
    entry.runtime_data = RuntimeData(
        client=client, modalities=model["architecture"]["input_modalities"]
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: OpenRouterConfigEntry) -> None:
    """Unload the evaluation entity."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
