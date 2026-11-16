"""Test configuration, reconfiguration, and authentication."""

import httpx
import pytest
from homeassistant.const import CONF_API_KEY, CONF_MODEL
from homeassistant.helpers.translation import async_get_translations

from custom_components.openrouter_decisions.const import DOMAIN

from .conftest import setup_entry


async def test_model_selection_and_duplicates(hass, catalog):
    """Exclude generation-only models and prevent duplicate entries."""
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: "test-key"}
    )
    assert "test/chat" not in str(flow["data_schema"])
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_MODEL: "test/decision"}
    )
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    duplicate = await hass.config_entries.flow.async_configure(
        duplicate["flow_id"], {CONF_API_KEY: "test-key"}
    )
    duplicate = await hass.config_entries.flow.async_configure(
        duplicate["flow_id"], {CONF_MODEL: "test/decision"}
    )
    assert duplicate["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"error": {"message": "invalid key"}}, "invalid_auth"),
        (503, {"error": {"message": "offline"}}, "cannot_connect"),
        (200, {"data": []}, "no_models"),
        (200, {}, "invalid_catalog"),
    ],
)
async def test_catalog_errors(hass, catalog, status, body, error):
    """Show actionable configuration errors without leaking credentials."""
    catalog.mock(return_value=httpx.Response(status, json=body))
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: "secret-never-log"}
    )
    assert flow["errors"] == {"base": error}
    assert "secret-never-log" not in str(flow)


async def test_reconfigure(hass):
    """Reload the existing entry when choosing another model."""
    entry = await setup_entry(hass)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: "new-key"}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_MODEL: "test/text"}
    )
    await hass.async_block_till_done()
    assert flow["type"] == "abort"
    assert entry.data[CONF_API_KEY] == "new-key"
    assert entry.data[CONF_MODEL] == "test/text"
    assert entry.runtime_data.modalities == ["text"]
    assert entry.title == "Text decision model"


async def test_reauth(hass):
    """Replace a rejected API key without creating a new entry."""
    entry = await setup_entry(hass)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_KEY: "replacement-key"}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_MODEL: "test/decision"}
    )
    await hass.async_block_till_done()
    assert flow["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "replacement-key"


@pytest.mark.parametrize("language", ["en", "it"])
async def test_translations(hass, language):
    """Load real configuration translations for both shipped languages."""
    translations = await async_get_translations(
        hass, language, "config", integrations={DOMAIN}
    )
    key = f"component.{DOMAIN}.config.step.user.data.api_key"
    assert translations[key]
