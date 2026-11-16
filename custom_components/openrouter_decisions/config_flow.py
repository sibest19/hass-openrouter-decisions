"""Configure an OpenRouter decision model."""

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_MODEL
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from openai import AuthenticationError, OpenAIError

from .client import async_get_models, create_client
from .const import DOMAIN


class OpenRouterDecisionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Validate an API key, then select a Decisions model."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient configuration data."""
        self._api_key = ""
        self._models: dict[str, dict[str, Any]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate credentials without making a paid evaluation request."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = create_client(self.hass, user_input[CONF_API_KEY])
            try:
                self._models = await async_get_models(client)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except OpenAIError:
                errors["base"] = "cannot_connect"
            except KeyError, TypeError, ValueError:
                errors["base"] = "invalid_catalog"
            else:
                if not self._models:
                    errors["base"] = "no_models"
                else:
                    self._api_key = user_input[CONF_API_KEY]
                    return await self.async_step_model()
        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a model that advertises Decisions output."""
        if user_input is not None:
            model = self._models[user_input[CONF_MODEL]]
            data = {CONF_API_KEY: self._api_key, CONF_MODEL: model["id"]}
            if self.source == "reauth":
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), title=model["name"], data_updates=data
                )
            if self.source == "reconfigure":
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    title=model["name"],
                    data_updates=data,
                )
            self._async_abort_entries_match(data)
            return self.async_create_entry(title=model["name"], data=data)
        return self.async_show_form(
            step_id="model",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_MODEL): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=model["id"], label=model["name"])
                                for model in self._models.values()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                            sort=True,
                        )
                    )
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the API key or selected model."""
        return await self.async_step_user(user_input)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Replace rejected credentials and select the model again."""
        return await self.async_step_user()
