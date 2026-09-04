"""Flow tests. GREEN-API is always mocked - no real WhatsApp message is sent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.messages import en, he, menu_as_text
from app.services import green_api
from app.storage import json_store

CHAT_ID = "972501234567@c.us"
ADMIN_KEY = "test-admin-key"


class Outbox(list):
    """Records what the bot sent: ("text"|"buttons", chat_id, payload)."""

    def texts(self) -> list[str]:
        return [payload for kind, _, payload in self if kind == "text"]

    def menus(self) -> list[list[dict]]:
        return [payload for kind, _, payload in self if kind == "buttons"]


@pytest.fixture
def sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Outbox:
    """Point storage at a temp file and capture outgoing GREEN-API calls."""
    monkeypatch.setattr(settings, "data_file_path", str(tmp_path / "data" / "users.json"))
    monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)

    outbox = Outbox()

    async def fake_send_text(chat_id: str, message: str) -> dict[str, str]:
        outbox.append(("text", chat_id, message))
        return {"idMessage": f"MOCK{len(outbox)}"}

    async def fake_send_buttons(chat_id, body, buttons, header=None, footer=None):
        # Enforce the documented GREEN-API limits in tests too.
        assert 1 <= len(buttons) <= green_api.MAX_BUTTONS
        for button in buttons:
            assert len(button["buttonText"]) <= green_api.MAX_BUTTON_TEXT_LENGTH
        outbox.append(("buttons", chat_id, buttons))
        outbox.append(("text", chat_id, body))
        return {"idMessage": f"MOCK{len(outbox)}"}

    monkeypatch.setattr(green_api, "send_text", fake_send_text)
    monkeypatch.setattr(green_api, "send_buttons", fake_send_buttons)
    return outbox


@pytest.fixture
def client(sent: Outbox) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def incoming(text: str, message_id: str = "MSG1", chat_id: str = CHAT_ID) -> dict:
    """A GREEN-API incomingMessageReceived text notification."""
    return _notification(
        "incomingMessageReceived",
        message_id,
        chat_id,
        {"typeMessage": "textMessage", "textMessageData": {"textMessage": text}},
    )


def button_tap(button_id: str, button_text: str, message_id: str = "MSG1", chat_id: str = CHAT_ID) -> dict:
    """A tapped button, in the shape GREEN-API documents for a button selection:
    green-api.com/en/docs/api/receiving/notifications-format/selected-buttons/ButtonsResponseMessage/
    """
    return _notification(
        "incomingMessageReceived",
        message_id,
        chat_id,
        {
            "typeMessage": "buttonsResponseMessage",
            "buttonsResponseMessage": {
                "stanzaId": "BAE53AFDD5F0C137",
                "selectedButtonId": button_id,
                "selectedButtonText": button_text,
            },
        },
    )


def outgoing(type_webhook: str, chat_id: str = CHAT_ID) -> dict:
    """A GREEN-API outgoing notification (manual from phone, or via our API)."""
    return _notification(
        type_webhook,
        "OUT1",
        chat_id,
        {"typeMessage": "textMessage", "textMessageData": {"textMessage": "Hi, this is the studio"}},
    )


def _notification(type_webhook: str, message_id: str, chat_id: str, message_data: dict) -> dict:
    return {
        "typeWebhook": type_webhook,
        "instanceData": {"idInstance": 1101234567, "wid": "972500000000@c.us", "typeInstance": "whatsapp"},
        "timestamp": 1588091580,
        "idMessage": message_id,
        "senderData": {
            "chatId": chat_id,
            "sender": chat_id,
            "chatName": "Customer",
            "senderName": "Customer",
        },
        "messageData": message_data,
    }


def post(client: TestClient, payload: dict):
    response = client.post("/webhook/green-api", json=payload)
    assert response.status_code == 200
    return response


def test_health_is_cheap_and_ok(client: TestClient, sent: Outbox) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert sent == []


def test_first_message_starts_onboarding(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("שלום"))

    user = json_store.get_user(CHAT_ID)
    assert user is not None
    assert user["language"] is None
    assert user["step"] == 1
    assert user["bot_enabled"] is True


def test_language_menu_is_sent_as_two_buttons(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi"))

    assert sent.menus() == [he.LANGUAGE_BUTTONS]
    assert sent.texts() == [he.LANGUAGE_BODY]
    assert [button["buttonText"] for button in sent.menus()[0]] == ["עברית", "English"]
    assert "🇮🇱" not in str(sent.menus()[0]) and "🇬🇧" not in str(sent.menus()[0])


def test_menu_notification_is_not_mistaken_for_a_tap(client: TestClient, sent: Outbox) -> None:
    """interactiveButtonsReply is a button MENU arriving as a message, not a tap:
    it echoes every button, so no choice can be read out of it."""
    post(client, incoming("hi", "M1"))
    sent.clear()

    post(client, _notification("incomingMessageReceived", "M2", CHAT_ID, {
        "typeMessage": "interactiveButtonsReply",
        "interactiveButtonsReply": {
            "titleText": "Header",
            "contentText": "Body",
            "footerText": "Footer",
            "buttons": [
                {"type": "reply", "buttonId": "1", "buttonText": "First"},
                {"type": "reply", "buttonId": "2", "buttonText": "Second"},
                {"type": "reply", "buttonId": "3", "buttonText": "Third"},
            ],
        },
    }))

    assert sent == []
    assert json_store.get_user(CHAT_ID)["language"] is None


def test_interest_menu_has_exactly_three_buttons(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("2", "M2"))

    assert json_store.get_user(CHAT_ID)["step"] == 2
    assert [button["buttonText"] for button in sent.menus()[-1]] == [
        "Pilates Equipment",
        "Barre",
        "Instructor Course",
    ]


def test_hebrew_selection(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, button_tap("1", "עברית", "M2"))

    assert json_store.get_user(CHAT_ID)["language"] == "he"
    assert sent.menus()[-1] == he.INTEREST_BUTTONS


def test_english_selection(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, button_tap("2", "English", "M2"))

    assert json_store.get_user(CHAT_ID)["language"] == "en"
    assert sent.menus()[-1] == en.INTEREST_BUTTONS


def test_pilates_button_changes_flow(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, button_tap("1", "עברית", "M2"))
    post(client, button_tap("1", "Pilates מכשירים", "M3"))

    user = json_store.get_user(CHAT_ID)
    assert user["flow"] == "pilates"
    assert user["step"] == 3
    assert sent.texts()[-1] == he.FLOW_BODY["pilates"]
    assert sent.menus()[-1] == he.FLOW_BUTTONS["pilates"]


def test_all_three_buttons_map_to_flows(client: TestClient, sent: Outbox) -> None:
    for button_id, flow in (("1", "pilates"), ("2", "barre"), ("3", "instructor_course")):
        chat_id = f"9725000000{button_id}@c.us"
        post(client, incoming("hi", f"A{button_id}", chat_id))
        post(client, button_tap("2", "English", f"B{button_id}", chat_id))
        label = en.INTEREST_BUTTONS[int(button_id) - 1]["buttonText"]
        post(client, button_tap(button_id, label, f"C{button_id}", chat_id))
        assert json_store.get_user(chat_id)["flow"] == flow


def test_typed_number_still_works_when_buttons_do_not_render(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))
    post(client, incoming("3", "M3"))

    assert json_store.get_user(CHAT_ID)["flow"] == "instructor_course"


def test_typed_button_label_is_understood(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("English", "M2"))
    post(client, incoming("barre", "M3"))

    user = json_store.get_user(CHAT_ID)
    assert user["language"] == "en"
    assert user["flow"] == "barre"


def test_menu_falls_back_to_text_when_buttons_fail(
    client: TestClient, sent: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_send_buttons(*args, **kwargs):
        raise green_api.GreenAPIError("buttons unavailable")

    monkeypatch.setattr(green_api, "send_buttons", failing_send_buttons)

    post(client, incoming("hi"))

    assert sent.menus() == []
    assert sent.texts() == [menu_as_text(he.LANGUAGE_BODY, he.LANGUAGE_BUTTONS)]
    assert "1. עברית" in sent.texts()[0]


def test_disabled_customer_gets_no_reply(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    json_store.pause_user(CHAT_ID)
    sent.clear()

    post(client, incoming("1", "M2"))

    assert sent == []


def test_duplicate_message_is_not_answered_twice(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "SAME"))
    post(client, incoming("hi", "SAME"))

    assert sent.menus() == [he.LANGUAGE_BUTTONS]


def test_outgoing_manual_message_disables_bot(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    sent.clear()

    post(client, outgoing("outgoingMessageReceived"))

    user = json_store.get_user(CHAT_ID)
    assert user["bot_enabled"] is False
    assert user["flow"] == "human"

    post(client, incoming("1", "M2"))
    assert sent == []


def test_outgoing_api_message_does_not_disable_bot(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))

    post(client, outgoing("outgoingAPIMessageReceived"))

    user = json_store.get_user(CHAT_ID)
    assert user["bot_enabled"] is True
    assert user["flow"] != "human"


def test_reset_starts_onboarding_again(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))
    sent.clear()

    response = client.post(f"/admin/reset/{CHAT_ID}", headers={"X-Admin-Key": ADMIN_KEY})
    assert response.status_code == 200
    assert json_store.get_user(CHAT_ID) is None

    post(client, incoming("hi", "M3"))
    assert sent.menus() == [he.LANGUAGE_BUTTONS]
    assert json_store.get_user(CHAT_ID)["step"] == 1


def test_invalid_language_choice_repeats_menu(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    sent.clear()

    post(client, incoming("maybe later", "M2"))

    assert sent.texts() == [he.INVALID_LANGUAGE_CHOICE, he.LANGUAGE_BODY]
    assert sent.menus() == [he.LANGUAGE_BUTTONS]
    assert json_store.get_user(CHAT_ID)["step"] == 1


def test_invalid_interest_choice_repeats_menu(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("2", "M2"))
    sent.clear()

    post(client, incoming("4", "M3"))

    assert sent.texts() == [en.INVALID_INTEREST_CHOICE, en.INTEREST_BODY]
    assert sent.menus() == [en.INTEREST_BUTTONS]
    assert json_store.get_user(CHAT_ID)["flow"] is None


def test_missing_users_file_is_created(sent: Outbox) -> None:
    path = Path(settings.data_file_path)
    assert not path.exists()

    with TestClient(app) as client:
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == {}
        post(client, incoming("hi"))

    assert CHAT_ID in json.loads(path.read_text(encoding="utf-8"))


def test_completed_onboarding_does_not_restart(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))
    post(client, incoming("1", "M3"))
    post(client, incoming("1", "M4"))
    sent.clear()

    post(client, incoming("שאלה נוספת", "M5"))

    assert sent == []
    assert json_store.get_user(CHAT_ID)["step"] == 4


def test_processed_message_ids_are_capped(sent: Outbox) -> None:
    json_store.create_user(CHAT_ID)
    for index in range(json_store.MAX_PROCESSED_MESSAGE_IDS + 20):
        json_store.mark_message_processed(CHAT_ID, f"ID{index}")

    ids = json_store.get_user(CHAT_ID)["processed_message_ids"]
    assert len(ids) == json_store.MAX_PROCESSED_MESSAGE_IDS
    assert ids[-1] == f"ID{json_store.MAX_PROCESSED_MESSAGE_IDS + 19}"


def test_admin_requires_key(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi"))

    assert client.get(f"/admin/user/{CHAT_ID}").status_code == 401
    assert client.get(f"/admin/user/{CHAT_ID}", headers={"X-Admin-Key": "wrong"}).status_code == 401

    response = client.get(f"/admin/user/{CHAT_ID}", headers={"X-Admin-Key": ADMIN_KEY})
    assert response.status_code == 200
    assert response.json()["user"]["step"] == 1


def test_admin_pause_and_resume(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi"))
    headers = {"X-Admin-Key": ADMIN_KEY}

    assert client.post(f"/admin/pause/{CHAT_ID}", headers=headers).json()["user"]["bot_enabled"] is False
    assert client.post(f"/admin/resume/{CHAT_ID}", headers=headers).json()["user"]["bot_enabled"] is True


# --- regression tests for the bugs this logging pass uncovered -------------


def test_blank_env_var_does_not_override_the_default_api_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copying .env.example used to leave GREEN_API_API_URL as an empty string,
    which produced a URL with no scheme and an unexplained send failure."""
    from app.config import DEFAULT_API_URL, _build_settings

    env_file = tmp_path / ".env"
    env_file.write_text(
        "GREEN_API_INSTANCE_ID=1101234567\nGREEN_API_TOKEN=abc\nGREEN_API_API_URL=\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for name in ("GREEN_API_API_URL", "GREEN_API_INSTANCE_ID", "GREEN_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    fresh = _build_settings()

    assert fresh.green_api_api_url == DEFAULT_API_URL


def test_api_url_without_a_scheme_gets_https(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import _build_settings

    monkeypatch.setenv("GREEN_API_API_URL", "7105.api.greenapi.com/")

    assert _build_settings().green_api_api_url == "https://7105.api.greenapi.com"


def test_missing_credentials_raise_a_named_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "green_api_token", "")

    with pytest.raises(green_api.GreenAPIError, match="GREEN_API_TOKEN"):
        green_api._check_configured("sendMessage")


def test_failed_send_leaves_the_message_unprocessed(
    client: TestClient, sent: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A send failure must not mark the message processed, or GREEN-API's retry
    would be dropped as a duplicate and the customer would get nothing."""

    working_send_buttons = green_api.send_buttons
    working_send_text = green_api.send_text

    async def always_fails(*args, **kwargs):
        raise green_api.GreenAPIError("GREEN-API is down")

    monkeypatch.setattr(green_api, "send_buttons", always_fails)
    monkeypatch.setattr(green_api, "send_text", always_fails)

    response = client.post("/webhook/green-api", json=incoming("hi", "RETRY"))
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    # The half-created customer was rolled back, so the retry starts clean.
    assert json_store.get_user(CHAT_ID) is None

    # GREEN-API recovers and redelivers the same notification.
    monkeypatch.setattr(green_api, "send_buttons", working_send_buttons)
    monkeypatch.setattr(green_api, "send_text", working_send_text)
    post(client, incoming("hi", "RETRY"))

    assert sent.menus() == [he.LANGUAGE_BUTTONS]


def test_webhook_error_response_names_the_cause(
    client: TestClient, sent: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def always_fails(*args, **kwargs):
        raise green_api.GreenAPIError("HTTP 401: token is wrong")

    monkeypatch.setattr(green_api, "send_buttons", always_fails)
    monkeypatch.setattr(green_api, "send_text", always_fails)

    body = client.post("/webhook/green-api", json=incoming("hi")).json()

    assert body["status"] == "error"
    assert "token is wrong" in body["reason"]


def test_diagnostics_reports_a_bad_setup(
    client: TestClient, sent: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_state():
        return {"stateInstance": "notAuthorized"}

    async def fake_settings():
        return {
            "webhookUrl": "https://example.com/wrong-path",
            "webhookUrlToken": "",
            "incomingWebhook": "yes",
            "outgoingMessageWebhook": "no",
            "outgoingAPIMessageWebhook": "yes",
            "stateWebhook": "no",
        }

    monkeypatch.setattr(green_api, "get_state_instance", fake_state)
    monkeypatch.setattr(green_api, "get_settings", fake_settings)

    body = client.get("/admin/diagnostics", headers={"X-Admin-Key": ADMIN_KEY}).json()

    assert body["status"] == "problems_found"
    joined = " | ".join(body["problems"])
    assert "notAuthorized" in joined
    assert "/webhook/green-api" in joined
    assert "outgoingMessageWebhook" in joined
    assert body["config"]["green_api_token_set"] is False


def test_diagnostics_is_clean_when_everything_is_configured(
    client: TestClient, sent: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "green_api_instance_id", "1101234567")
    monkeypatch.setattr(settings, "green_api_token", "a-token")

    async def fake_state():
        return {"stateInstance": "authorized"}

    async def fake_settings():
        return {
            "webhookUrl": "https://bot.onrender.com/webhook/green-api",
            "webhookUrlToken": "",
            "incomingWebhook": "yes",
            "outgoingMessageWebhook": "yes",
            "outgoingAPIMessageWebhook": "yes",
            "stateWebhook": "no",
        }

    monkeypatch.setattr(green_api, "get_state_instance", fake_state)
    monkeypatch.setattr(green_api, "get_settings", fake_settings)

    body = client.get("/admin/diagnostics", headers={"X-Admin-Key": ADMIN_KEY}).json()

    assert body["problems"] == []
    assert body["status"] == "ok"


def test_diagnostics_requires_the_admin_key(client: TestClient, sent: Outbox) -> None:
    assert client.get("/admin/diagnostics").status_code == 401


def test_logs_never_contain_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "green_api_token", "super-secret-token")
    monkeypatch.setattr(settings, "green_api_instance_id", "1101234567")

    assert "super-secret-token" not in green_api._safe_url("sendMessage")
    assert "***TOKEN***" in green_api._safe_url("sendMessage")


# --- the flow sub-menus ----------------------------------------------------


def reach_flow(client: TestClient, language_button: str, interest_button: str, prefix: str) -> None:
    """Walk a fresh customer as far as a flow's follow-up menu."""
    post(client, incoming("hi", f"{prefix}1"))
    post(client, button_tap(language_button, "", f"{prefix}2"))
    post(client, button_tap(interest_button, "", f"{prefix}3"))


def test_flow_message_is_followed_by_its_own_menu(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "1", "2", "B")

    assert sent.texts()[-1] == he.FLOW_BODY["barre"]
    assert [button["buttonText"] for button in sent.menus()[-1]] == [
        "מחירים ומערכת שעות",
        "לקבוע שיעור ניסיון",
        "לדבר איתנו",
    ]
    assert json_store.get_user(CHAT_ID)["step"] == 3


def test_sub_option_sends_its_answer(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "2", "3", "C")
    sent.clear()

    post(client, button_tap("2", "Dates & pricing", "C4"))

    assert sent.texts() == en.FLOW_ANSWERS["instructor_course"]["2"]
    assert json_store.get_user(CHAT_ID)["step"] == 4


def test_talk_to_us_hands_over_to_a_human(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "2", "2", "D")
    sent.clear()

    post(client, button_tap("3", "Talk to us", "D4"))

    assert sent.texts() == [en.HANDOVER_MESSAGE]
    user = json_store.get_user(CHAT_ID)
    assert user["bot_enabled"] is False
    assert user["flow"] == "human"

    # The bot stays quiet from now on.
    sent.clear()
    post(client, incoming("still there?", "D5"))
    assert sent == []


def test_invalid_sub_option_repeats_the_flow_menu(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "1", "1", "E")
    sent.clear()

    post(client, incoming("אולי אחר כך", "E4"))

    assert sent.texts() == [he.INVALID_INTEREST_CHOICE, he.FLOW_BODY["pilates"]]
    assert sent.menus() == [he.FLOW_BUTTONS["pilates"]]
    assert json_store.get_user(CHAT_ID)["step"] == 3


def test_sub_option_accepts_a_typed_number(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "1", "3", "F")
    sent.clear()

    post(client, incoming("1", "F4"))

    assert sent.texts() == he.FLOW_ANSWERS["instructor_course"]["1"]


def test_every_flow_button_leads_somewhere(client: TestClient, sent: Outbox) -> None:
    """Every button must have either an answer or a handover, in both languages."""
    for messages in (he, en):
        for flow, buttons in messages.FLOW_BUTTONS.items():
            assert 1 <= len(buttons) <= green_api.MAX_BUTTONS, (flow, len(buttons))
            for button in buttons:
                assert len(button["buttonText"]) <= green_api.MAX_BUTTON_TEXT_LENGTH, button
            ids = {button["buttonId"] for button in buttons}
            handled = set(messages.FLOW_ANSWERS.get(flow, {})) | messages.HANDOVER_BUTTONS[flow]
            assert ids == handled, (flow, ids, handled)


def test_both_languages_define_the_same_flows(sent: Outbox) -> None:
    from app.services.bot import FLOW_BY_BUTTON_ID

    flows = set(FLOW_BY_BUTTON_ID.values())
    assert set(he.FLOW_BODY) == flows
    assert set(en.FLOW_BODY) == flows
    assert set(he.FLOW_BUTTONS) == flows
    assert set(en.FLOW_BUTTONS) == flows


# --- every button-reply shape GREEN-API documents --------------------------


@pytest.mark.parametrize(
    ("message_data", "expected"),
    [
        pytest.param(
            {
                "typeMessage": "buttonsResponseMessage",
                "buttonsResponseMessage": {
                    "stanzaId": "BAE53AFDD5F0C137",
                    "selectedButtonId": "1",
                    "selectedButtonText": "Green",
                },
            },
            "1",
            id="buttonsResponseMessage",
        ),
        pytest.param(
            {
                "typeMessage": "templateButtonsReplyMessage",
                "templateButtonsReplyMessage": {
                    "stanzaId": "BAE5",
                    "selectedIndex": 1,
                    "selectedId": "2",
                    "selectedDisplayText": "Barre",
                },
            },
            "2",
            id="templateButtonsReplyMessage",
        ),
        pytest.param(
            {
                "typeMessage": "listResponseMessage",
                "listResponseMessage": {
                    "stanzaId": "BAE5",
                    "singleSelectReply": {"selectedRowId": "3"},
                },
            },
            "3",
            id="listResponseMessage",
        ),
        pytest.param(
            {
                "typeMessage": "buttonsResponseMessage",
                "buttonsResponseMessage": {"selectedButtonText": "English"},
            },
            "English",
            id="label-only",
        ),
        pytest.param(
            {
                "typeMessage": "buttonsResponseMessage",
                "buttonsResponseMessage": {"selectedButtonId": 2},
            },
            "2",
            id="numeric-id",
        ),
        # What production instances actually send. No published GREEN-API page
        # documents this type, so the exact inner keys are matched generically.
        pytest.param(
            {
                "typeMessage": "interactiveButtonsResponse",
                "interactiveButtonsResponse": {
                    "stanzaId": "3EB0",
                    "selectedButtonId": "2",
                    "selectedButtonText": "Barre",
                },
            },
            "2",
            id="interactiveButtonsResponse",
        ),
        pytest.param(
            {
                "typeMessage": "interactiveButtonsResponse",
                "interactiveButtonsResponse": {"buttonId": "3", "buttonText": "לדבר איתנו"},
            },
            "3",
            id="interactiveButtonsResponse-bare-buttonId",
        ),
        pytest.param(
            {
                "typeMessage": "interactiveButtonsResponse",
                "interactiveButtonsResponse": {"reply": {"buttonId": "1"}},
            },
            "1",
            id="interactiveButtonsResponse-nested",
        ),
        pytest.param(
            {
                "typeMessage": "someFutureButtonReply",
                "someFutureButtonReply": {"selectedButtonId": "1"},
            },
            "1",
            id="unknown-type-name-still-works",
        ),
        # A menu echoed back to us: every button present, none selected.
        pytest.param(
            {
                "typeMessage": "interactiveButtons",
                "interactiveButtons": {
                    "titleText": "Header",
                    "contentText": "Body",
                    "buttons": [
                        {"type": "reply", "buttonId": "1", "buttonText": "First"},
                        {"type": "reply", "buttonId": "2", "buttonText": "Second"},
                    ],
                },
            },
            None,
            id="echoed-menu-is-not-a-choice",
        ),
        pytest.param(
            {"typeMessage": "textMessage", "textMessageData": {"textMessage": "1"}},
            "1",
            id="plain-text",
        ),
        pytest.param({"typeMessage": "imageMessage"}, None, id="image-ignored"),
    ],
)
def test_extract_reply_handles_every_documented_shape(message_data, expected) -> None:
    from app.services.bot import extract_reply

    assert extract_reply(message_data) == expected


def test_unreadable_message_is_logged_in_full(
    client: TestClient, sent: Outbox, caplog: pytest.LogCaptureFixture
) -> None:
    """The one thing needed to support a new shape is the payload itself."""
    payload = _notification("incomingMessageReceived", "U1", CHAT_ID, {
        "typeMessage": "someBrandNewType",
        "someBrandNewType": {"somethingUnexpected": {"deeply": "nested"}},
    })

    with caplog.at_level("WARNING"):
        post(client, payload)

    assert "somethingUnexpected" in caplog.text
    assert "someBrandNewType" in caplog.text


def test_ignored_media_does_not_dump_its_payload(
    client: TestClient, sent: Outbox, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _notification("incomingMessageReceived", "U2", CHAT_ID, {
        "typeMessage": "imageMessage",
        "fileMessageData": {"downloadUrl": "https://example.com/a.jpg"},
    })

    with caplog.at_level("WARNING"):
        post(client, payload)

    assert "downloadUrl" not in caplog.text


def test_a_tap_is_understood_at_every_step(client: TestClient, sent: Outbox) -> None:
    """Language, interest and follow-up menus all accept a real button tap."""
    post(client, incoming("hi", "T1"))
    post(client, button_tap("2", "English", "T2"))
    assert json_store.get_user(CHAT_ID)["language"] == "en"

    post(client, button_tap("1", "Pilates Equipment", "T3"))
    assert json_store.get_user(CHAT_ID)["flow"] == "pilates"

    sent.clear()
    post(client, button_tap("2", "Book a trial class", "T4"))
    assert sent.texts() == en.FLOW_ANSWERS["pilates"]["2"]
    assert json_store.get_user(CHAT_ID)["step"] == 4


def test_real_interactive_buttons_response_drives_the_whole_flow(
    client: TestClient, sent: Outbox
) -> None:
    """The shape seen in production: interactiveButtonsResponse at every step."""

    def tap(button_id: str, message_id: str) -> None:
        post(client, _notification("incomingMessageReceived", message_id, CHAT_ID, {
            "typeMessage": "interactiveButtonsResponse",
            "interactiveButtonsResponse": {
                "stanzaId": "3EB0BD1B1CD8CB04B14D7E",
                "selectedButtonId": button_id,
            },
        }))

    post(client, incoming("היי", "R1"))
    tap("1", "R2")
    tap("3", "R3")
    sent.clear()
    tap("2", "R4")

    user = json_store.get_user(CHAT_ID)
    assert user["language"] == "he"
    assert user["flow"] == "instructor_course"
    assert user["step"] == 4
    assert sent.texts() == he.FLOW_ANSWERS["instructor_course"]["2"]


# --- "0" returns to the main menu ------------------------------------------


def test_zero_returns_from_a_flow_menu(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "1", "2", "Z")
    assert json_store.get_user(CHAT_ID)["flow"] == "barre"
    sent.clear()

    post(client, incoming("0", "Z4"))

    user = json_store.get_user(CHAT_ID)
    assert user["step"] == 2
    assert user["flow"] is None
    assert user["language"] == "he"
    assert sent.menus() == [he.INTEREST_BUTTONS]


def test_zero_returns_after_the_flow_is_finished(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "2", "1", "Y")
    post(client, button_tap("1", "Pricing & class schedule", "Y4"))
    assert json_store.get_user(CHAT_ID)["step"] == 4
    sent.clear()

    post(client, incoming("0", "Y5"))

    assert json_store.get_user(CHAT_ID)["step"] == 2
    assert sent.menus() == [en.INTEREST_BUTTONS]


def test_zero_on_the_interest_menu_resends_it(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "X1"))
    post(client, button_tap("1", "עברית", "X2"))
    sent.clear()

    post(client, incoming("0", "X3"))

    assert sent.menus() == [he.INTEREST_BUTTONS]
    assert json_store.get_user(CHAT_ID)["step"] == 2


def test_zero_before_a_language_is_chosen_repeats_the_language_menu(
    client: TestClient, sent: Outbox
) -> None:
    post(client, incoming("hi", "W1"))
    sent.clear()

    post(client, incoming("0", "W2"))

    assert sent.menus() == [he.LANGUAGE_BUTTONS]
    assert json_store.get_user(CHAT_ID)["step"] == 1


def test_zero_works_as_a_tapped_button_too(client: TestClient, sent: Outbox) -> None:
    reach_flow(client, "1", "3", "V")
    sent.clear()

    post(client, button_tap("0", "", "V4"))

    assert sent.menus() == [he.INTEREST_BUTTONS]
    assert json_store.get_user(CHAT_ID)["step"] == 2


def test_zero_does_not_revive_a_chat_a_human_took_over(client: TestClient, sent: Outbox) -> None:
    """A stray 0 must never pull the bot back into a conversation a person is having."""
    reach_flow(client, "2", "2", "U")
    post(client, outgoing("outgoingMessageReceived"))
    assert json_store.get_user(CHAT_ID)["bot_enabled"] is False
    sent.clear()

    post(client, incoming("0", "U5"))

    assert sent == []
    assert json_store.get_user(CHAT_ID)["bot_enabled"] is False


def test_menus_carry_the_return_hint(client: TestClient, sent: Outbox) -> None:
    post(client, incoming("hi", "H1"))
    # The language menu has nowhere to go back to, so it has no hint.
    assert he.MENU_FOOTER not in sent.texts()

    post(client, button_tap("2", "English", "H2"))
    post(client, button_tap("2", "Barre", "H3"))

    assert en.MENU_FOOTER == "0 to return to the main menu"


def test_text_fallback_menu_shows_the_return_hint(
    client: TestClient, sent: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    post(client, incoming("hi", "G1"))

    async def failing_send_buttons(*args, **kwargs):
        raise green_api.GreenAPIError("buttons unavailable")

    monkeypatch.setattr(green_api, "send_buttons", failing_send_buttons)
    sent.clear()

    post(client, incoming("1", "G2"))

    assert sent.texts() == [
        menu_as_text(he.INTEREST_BODY, he.INTEREST_BUTTONS, he.MENU_FOOTER)
    ]
    assert sent.texts()[0].endswith(he.MENU_FOOTER)
