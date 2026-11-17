"""Verify requests and results through Home Assistant's public action."""

from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from homeassistant.components import ai_task
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.openrouter_decisions.ai_task import OpenRouterEvaluationEntity
from custom_components.openrouter_decisions.const import DECISIONS_URL

from .conftest import setup_entry

QUESTIONS = {
    "delivered": {"type": "noul", "instructions": "Has the package arrived?"},
    "location": {
        "type": "choice",
        "instructions": "Where is it?",
        "criteria": {"door": "At the door", "other": "Elsewhere"},
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent?",
        "criteria": ["Not urgent", "Collect now"],
    },
}
ANSWERS = {
    "delivered": {"type": "noul", "noul": 0.9},
    "location": {
        "type": "choice",
        "choice": "door",
        "probabilities": {"door": 0.8, "other": 0.2},
    },
    "urgency": {"type": "score", "score": 0.2, "probabilities": {"1": 0.2, "0": 0.8}},
}


def entity_id(hass, entry):
    """Locate the entity through the registry."""
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)[
        0
    ].entity_id


async def evaluate(hass, entry, state="Delivered", **extra):
    """Call the actual AI Task action with a response."""
    return await hass.services.async_call(
        "ai_task",
        "evaluate",
        {
            "task_name": "Delivery",
            "entity_id": entity_id(hass, entry),
            "questions": QUESTIONS,
            "state": state,
            **extra,
        },
        blocking=True,
        return_response=True,
    )


async def test_evaluate_lifecycle(hass, respx_mock):
    """Preserve IDs on reload and stop serving the entity on unload."""
    route = respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(200, json={"answers": ANSWERS})
    )
    entry = await setup_entry(hass)
    original_id = entity_id(hass, entry)
    result = await evaluate(hass, entry)
    assert result["answers"]["delivered"] == {"type": "noul", "noul": 0.9}
    assert result["answers"]["location"]["choice"] == "door"
    assert result["answers"]["urgency"]["probabilities"] == [0.8, 0.2]
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"
    assert hass.states.get(original_id).state not in ("unknown", "unavailable")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_id(hass, entry) == original_id
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get(original_id).state == "unavailable"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (0, "0"),
        (False, "false"),
        (1.5, "1.5"),
        ({"count": 2}, {"count": 2}),
        (["a", "b"], ["a", "b"]),
    ],
)
async def test_native_request(hass, respx_mock, state, expected):
    """Preserve supported JSON values and encode scalar state."""
    import json

    route = respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(200, json={"answers": ANSWERS})
    )
    entry = await setup_entry(hass)
    await evaluate(hass, entry, state)
    payload = json.loads(route.calls.last.request.content)
    assert payload == {
        "model": "test/decision",
        "state": expected,
        "questions": QUESTIONS,
    }


@pytest.mark.parametrize(
    ("question", "replacement"),
    [
        ("delivered", {"type": "noul", "noul": True}),
        ("delivered", {"type": "noul", "noul": 1.5}),
        (
            "location",
            {
                "type": "choice",
                "choice": "other",
                "probabilities": {"door": 0.8, "other": 0.2},
            },
        ),
        (
            "location",
            {
                "type": "choice",
                "choice": "door",
                "probabilities": {"door": 0.2, "other": 0.2},
            },
        ),
        (
            "urgency",
            {"type": "score", "score": 1, "probabilities": {"0": 0.8, "1": 0.2}},
        ),
        (
            "urgency",
            {"type": "score", "score": 0.2, "probabilities": {"0": 0.8, "2": 0.2}},
        ),
        ("urgency", {"type": "unknown"}),
    ],
)
async def test_invalid_answer(hass, respx_mock, question, replacement):
    """Reject structurally valid but inconsistent provider answers."""
    answers = {**deepcopy(ANSWERS), question: replacement}
    respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(200, json={"answers": answers})
    )
    entry = await setup_entry(hass)
    with pytest.raises(HomeAssistantError):
        await evaluate(hass, entry)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"answers": {}},
        {"answers": []},
        {"answers": {"extra": {"type": "noul", "noul": 0.5}}},
    ],
)
async def test_invalid_response(hass, respx_mock, response):
    """Reject missing, extra, and malformed answers."""
    respx_mock.post(DECISIONS_URL).mock(return_value=httpx.Response(200, json=response))
    entry = await setup_entry(hass)
    with pytest.raises(HomeAssistantError):
        await evaluate(hass, entry)


@pytest.mark.parametrize("status", [400, 402, 403, 404, 413, 429, 503])
async def test_api_failure(hass, respx_mock, status):
    """Keep provider details out of translated user-facing errors."""
    respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(
            status, json={"error": {"message": "internal detail"}}
        )
    )
    entry = await setup_entry(hass)
    with pytest.raises(HomeAssistantError) as exc:
        await evaluate(hass, entry)
    assert exc.value.translation_key == "evaluation_api_error"
    assert exc.value.translation_placeholders == {"status": str(status)}
    assert exc.value.__cause__.status_code == status
    assert str(status) in str(exc.value)
    assert "internal detail" not in str(exc.value)


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("application/pdf", "file"),
        ("image/jpeg", "image_url"),
        (" Image/JPG; charset=binary ", "image_url"),
    ],
)
async def test_attachments(hass, respx_mock, tmp_path, mime, expected):
    """Use file parts for PDFs and image parts for images."""
    import json

    entry = await setup_entry(hass)
    entity = OpenRouterEvaluationEntity(entry)
    entity.hass = hass
    file = tmp_path / "receipt.pdf"
    file.write_bytes(b"test-content")
    route = respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(200, json={"answers": ANSWERS})
    )
    await entity._async_evaluate(
        ai_task.EvaluationTask(
            name="Receipt",
            questions=QUESTIONS,
            state=False,
            attachments=[SimpleNamespace(path=file, mime_type=mime)],
        )
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["state"][0] == "false"
    part = payload["state"][1]
    assert part["type"] == expected
    assert "dGVzdC1jb250ZW50" in str(part)


async def test_text_model_rejects_attachments(hass, respx_mock, tmp_path):
    """Advertise and enforce the actual model capabilities."""
    entry = await setup_entry(hass, model="test/text")
    entity = OpenRouterEvaluationEntity(entry)
    entity.hass = hass
    assert (
        not entity.supported_features & ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
    )
    with pytest.raises(HomeAssistantError) as exc:
        await entity._async_evaluate(
            ai_task.EvaluationTask(
                name="Test",
                questions=QUESTIONS,
                attachments=[
                    SimpleNamespace(path=tmp_path / "missing", mime_type="image/jpeg")
                ],
            )
        )
    assert exc.value.translation_key == "unsupported_attachment_type"


async def test_file_read_error(hass, tmp_path):
    """Report unreadable local media with a stable translated message."""
    entry = await setup_entry(hass)
    entity = OpenRouterEvaluationEntity(entry)
    with pytest.raises(HomeAssistantError) as exc:
        entity._prepare_attachments(
            [SimpleNamespace(path=tmp_path / "missing.jpg", mime_type="image/jpeg")]
        )
    assert exc.value.translation_key == "file_read_error"


async def test_service_pdf_attachment(hass, respx_mock, tmp_path):
    """Resolve a permitted local PDF through the public action."""
    import json

    media = tmp_path / "media"
    media.mkdir()
    (media / "receipt.pdf").write_bytes(b"test-content")
    hass.config.media_dirs = {"local": str(media)}
    route = respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(200, json={"answers": ANSWERS})
    )
    entry = await setup_entry(hass)
    result = await evaluate(
        hass,
        entry,
        state=None,
        attachments=[
            {
                "media_content_id": "media-source://media_source/local/receipt.pdf",
                "media_content_type": "application/pdf",
            }
        ],
    )
    assert result["answers"]["delivered"]["noul"] == 0.9
    part = json.loads(route.calls.last.request.content)["state"][0]
    assert part["type"] == "file"
    assert part["file"]["filename"] == "receipt.pdf"


async def test_runtime_authentication_error(hass, respx_mock):
    """Create a reauthentication flow after a rejected evaluation key."""
    respx_mock.post(DECISIONS_URL).mock(
        return_value=httpx.Response(401, json={"error": {"message": "expired"}})
    )
    entry = await setup_entry(hass)
    with pytest.raises(HomeAssistantError) as exc:
        await evaluate(hass, entry)
    assert exc.value.translation_key == "invalid_auth"
    await hass.async_block_till_done()
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (httpx.ConnectError, "evaluation_connection_error"),
        (httpx.ReadTimeout, "evaluation_timeout"),
    ],
)
async def test_connection_failure(hass, respx_mock, error, key):
    """Keep network failures distinct from HTTP response errors."""
    respx_mock.post(DECISIONS_URL).mock(side_effect=error("internal detail"))
    entry = await setup_entry(hass)
    with pytest.raises(HomeAssistantError) as exc:
        await evaluate(hass, entry)
    assert exc.value.translation_key == key
    assert "internal detail" not in str(exc.value)
