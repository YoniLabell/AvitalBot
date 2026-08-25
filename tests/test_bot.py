"""Flow tests. GREEN-API is always mocked - no real WhatsApp message is sent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.messages import en, he
from app.services import green_api
from app.storage import json_store

CHAT_ID = "972501234567@c.us"
ADMIN_KEY = "test-admin-key"


@pytest.fixture
def sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Point storage at a temp file and capture outgoing GREEN-API messages."""
    monkeypatch.setattr(settings, "data_file_path", str(tmp_path / "data" / "users.json"))
    monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)

    outbox: list[tuple[str, str]] = []

    async def fake_send_text(chat_id: str, message: str) -> dict[str, str]:
        outbox.append((chat_id, message))
        return {"idMessage": f"MOCK{len(outbox)}"}

    monkeypatch.setattr(green_api, "send_text", fake_send_text)
    return outbox


@pytest.fixture
def client(sent: list[tuple[str, str]]) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def incoming(text: str, message_id: str = "MSG1", chat_id: str = CHAT_ID) -> dict:
    """A GREEN-API incomingMessageReceived text notification."""
    return {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": 1101234567, "wid": "972500000000@c.us", "typeInstance": "whatsapp"},
        "timestamp": 1588091580,
        "idMessage": message_id,
        "senderData": {
            "chatId": chat_id,
            "sender": chat_id,
            "chatName": "Customer",
            "senderName": "Customer",
        },
        "messageData": {
            "typeMessage": "textMessage",
            "textMessageData": {"textMessage": text},
        },
    }


def outgoing(type_webhook: str, chat_id: str = CHAT_ID) -> dict:
    """A GREEN-API outgoing notification (manual from phone, or via our API)."""
    return {
        "typeWebhook": type_webhook,
        "instanceData": {"idInstance": 1101234567, "wid": "972500000000@c.us", "typeInstance": "whatsapp"},
        "timestamp": 1588091580,
        "idMessage": "OUT1",
        "senderData": {"chatId": chat_id, "sender": "972500000000@c.us", "senderName": "Studio"},
        "messageData": {
            "typeMessage": "textMessage",
            "textMessageData": {"textMessage": "Hi, this is the studio"},
        },
    }


def post(client: TestClient, payload: dict):
    response = client.post("/webhook/green-api", json=payload)
    assert response.status_code == 200
    return response


def test_health_is_cheap_and_ok(client: TestClient, sent: list) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert sent == []


def test_first_message_starts_onboarding(client: TestClient, sent: list) -> None:
    post(client, incoming("שלום"))

    user = json_store.get_user(CHAT_ID)
    assert user is not None
    assert user["language"] is None
    assert user["step"] == 1
    assert user["bot_enabled"] is True


def test_language_menu_is_sent(client: TestClient, sent: list) -> None:
    post(client, incoming("hi"))

    assert sent == [(CHAT_ID, he.LANGUAGE_MENU)]
    assert "1. עברית 🇮🇱" in sent[0][1]
    assert "2. English 🇬🇧" in sent[0][1]


def test_hebrew_selection(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))

    assert json_store.get_user(CHAT_ID)["language"] == "he"
    assert sent[-1] == (CHAT_ID, he.INTEREST_MENU)


def test_english_selection(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("2", "M2"))

    assert json_store.get_user(CHAT_ID)["language"] == "en"
    assert sent[-1] == (CHAT_ID, en.INTEREST_MENU)


def test_interest_menu_lists_four_options(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("2", "M2"))

    menu = sent[-1][1]
    assert json_store.get_user(CHAT_ID)["step"] == 2
    for option in ("1. Reformer Pilates", "2. Barre", "3. Instructor Training Course", "4. Something else"):
        assert option in menu


def test_pilates_selection_changes_flow(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))
    post(client, incoming("1", "M3"))

    user = json_store.get_user(CHAT_ID)
    assert user["flow"] == "pilates"
    assert user["step"] == 3
    assert sent[-len(he.FLOW_MESSAGES["pilates"]):] == [
        (CHAT_ID, message) for message in he.FLOW_MESSAGES["pilates"]
    ]


def test_all_interest_options_map_to_flows(client: TestClient, sent: list) -> None:
    for choice, flow in (("1", "pilates"), ("2", "barre"), ("3", "instructor_course"), ("4", "other")):
        chat_id = f"9725000000{choice}@c.us"
        post(client, incoming("hi", f"A{choice}", chat_id))
        post(client, incoming("2", f"B{choice}", chat_id))
        post(client, incoming(choice, f"C{choice}", chat_id))
        assert json_store.get_user(chat_id)["flow"] == flow


def test_disabled_customer_gets_no_reply(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    json_store.pause_user(CHAT_ID)
    sent.clear()

    post(client, incoming("1", "M2"))

    assert sent == []


def test_duplicate_message_is_not_answered_twice(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "SAME"))
    post(client, incoming("hi", "SAME"))

    assert len(sent) == 1


def test_outgoing_manual_message_disables_bot(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    sent.clear()

    post(client, outgoing("outgoingMessageReceived"))

    user = json_store.get_user(CHAT_ID)
    assert user["bot_enabled"] is False
    assert user["flow"] == "human"

    post(client, incoming("1", "M2"))
    assert sent == []


def test_outgoing_api_message_does_not_disable_bot(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))

    post(client, outgoing("outgoingAPIMessageReceived"))

    user = json_store.get_user(CHAT_ID)
    assert user["bot_enabled"] is True
    assert user["flow"] != "human"


def test_reset_starts_onboarding_again(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))
    sent.clear()

    response = client.post(f"/admin/reset/{CHAT_ID}", headers={"X-Admin-Key": ADMIN_KEY})
    assert response.status_code == 200
    assert json_store.get_user(CHAT_ID) is None

    post(client, incoming("hi", "M3"))
    assert sent == [(CHAT_ID, he.LANGUAGE_MENU)]
    assert json_store.get_user(CHAT_ID)["step"] == 1


def test_invalid_language_choice_repeats_menu(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    sent.clear()

    post(client, incoming("maybe later", "M2"))

    assert sent == [
        (CHAT_ID, he.INVALID_LANGUAGE_CHOICE),
        (CHAT_ID, he.LANGUAGE_MENU),
    ]
    assert json_store.get_user(CHAT_ID)["step"] == 1


def test_invalid_interest_choice_repeats_menu(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("2", "M2"))
    sent.clear()

    post(client, incoming("9", "M3"))

    assert sent == [
        (CHAT_ID, en.INVALID_INTEREST_CHOICE),
        (CHAT_ID, en.INTEREST_MENU),
    ]
    assert json_store.get_user(CHAT_ID)["flow"] is None


def test_missing_users_file_is_created(sent: list) -> None:
    path = Path(settings.data_file_path)
    assert not path.exists()

    with TestClient(app) as client:
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == {}
        post(client, incoming("hi"))

    assert CHAT_ID in json.loads(path.read_text(encoding="utf-8"))


def test_completed_onboarding_does_not_restart(client: TestClient, sent: list) -> None:
    post(client, incoming("hi", "M1"))
    post(client, incoming("1", "M2"))
    post(client, incoming("1", "M3"))
    sent.clear()

    post(client, incoming("שאלה נוספת", "M4"))

    assert sent == []
    assert json_store.get_user(CHAT_ID)["step"] == 3


def test_processed_message_ids_are_capped(sent: list) -> None:
    json_store.create_user(CHAT_ID)
    for index in range(json_store.MAX_PROCESSED_MESSAGE_IDS + 20):
        json_store.mark_message_processed(CHAT_ID, f"ID{index}")

    ids = json_store.get_user(CHAT_ID)["processed_message_ids"]
    assert len(ids) == json_store.MAX_PROCESSED_MESSAGE_IDS
    assert ids[-1] == f"ID{json_store.MAX_PROCESSED_MESSAGE_IDS + 19}"


def test_admin_requires_key(client: TestClient, sent: list) -> None:
    post(client, incoming("hi"))

    assert client.get(f"/admin/user/{CHAT_ID}").status_code == 401
    assert client.get(f"/admin/user/{CHAT_ID}", headers={"X-Admin-Key": "wrong"}).status_code == 401

    response = client.get(f"/admin/user/{CHAT_ID}", headers={"X-Admin-Key": ADMIN_KEY})
    assert response.status_code == 200
    assert response.json()["user"]["step"] == 1


def test_admin_pause_and_resume(client: TestClient, sent: list) -> None:
    post(client, incoming("hi"))
    headers = {"X-Admin-Key": ADMIN_KEY}

    assert client.post(f"/admin/pause/{CHAT_ID}", headers=headers).json()["user"]["bot_enabled"] is False
    assert client.post(f"/admin/resume/{CHAT_ID}", headers=headers).json()["user"]["bot_enabled"] is True
