"""Run the custom component with a disposable Home Assistant instance."""

from pathlib import Path

import httpx2 as httpx
import pytest
from homeassistant import bootstrap, loader
from homeassistant.const import CONF_API_KEY, CONF_MODEL

pytest_plugins = ["respx.plugin"]

MODELS = {
    "data": [
        {
            "id": "test/decision",
            "name": "Decision model",
            "architecture": {
                "input_modalities": ["text", "image", "file"],
                "output_modalities": ["decisions"],
            },
        },
        {
            "id": "test/text",
            "name": "Text decision model",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["decisions"],
            },
        },
        {
            "id": "test/chat",
            "name": "Chat model",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
        },
    ]
}


@pytest.fixture
def catalog(respx_mock):
    """Mock only OpenRouter HTTP responses, using the real OpenAI client."""
    return respx_mock.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS)
    )


@pytest.fixture
def config_path(tmp_path):
    """Install the source into a temporary configuration directory."""
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components",
        target_is_directory=True,
    )
    return tmp_path


@pytest.fixture
async def hass(config_path, catalog):
    """Start Home Assistant with the custom component installed."""
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(str(config_path))
    loader.async_setup(hass)
    assert await bootstrap.async_from_config_dict(
        {
            "homeassistant": {
                "latitude": 41.9,
                "longitude": 12.5,
                "time_zone": "Europe/Rome",
            }
        },
        hass,
    )
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)
        await hass.async_block_till_done()


async def setup_entry(hass, model="test/decision"):
    """Configure through the public flow and finish actual platform setup."""
    from custom_components.openrouter_decisions.const import DOMAIN

    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: "test-key"}
    )
    assert flow["step_id"] == "model"
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_MODEL: model}
    )
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()
    assert flow["result"].state.value == "loaded"
    return flow["result"]
