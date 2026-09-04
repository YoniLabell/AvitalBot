# WhatsApp Flow Bot (MVP)

A very small FastAPI service that answers WhatsApp messages through
[GREEN-API](https://green-api.com/en/docs/) with **predefined flows only** — no AI,
no database, no background workers.

What it does:

1. A new customer sends any text → the bot replies with a bilingual language menu
   (two tappable buttons: עברית / English).
2. The customer picks a language → the bot sends the interest menu in that language
   (three tappable buttons: Pilates / Barre / instructor course).
3. The customer picks an interest → the bot sends that flow's messages (placeholders for now).
4. The moment the business owner replies manually from WhatsApp, the bot goes silent for that chat.

---

## Requirements

- Python 3.11+
- A GREEN-API instance (instance id + API token)

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your GREEN-API credentials
uvicorn app.main:app --reload
```

Then:

- Health check: <http://127.0.0.1:8000/health>
- API docs: <http://127.0.0.1:8000/docs>

Run the tests (GREEN-API is mocked, no real WhatsApp messages are sent):

```bash
pytest
```

## Environment variables

| Variable | Secret | Description |
| --- | --- | --- |
| `GREEN_API_INSTANCE_ID` | yes | Your GREEN-API instance number. |
| `GREEN_API_TOKEN` | yes | Your GREEN-API `apiTokenInstance`. |
| `GREEN_API_API_URL` | yes | API host, e.g. `https://api.green-api.com` or your instance host `https://7105.api.greenapi.com`. |
| `ADMIN_API_KEY` | yes | Any long random string. Required by the `/admin/*` endpoints. |
| `DATA_FILE_PATH` | no | Where customer state is written. `data/users.json` on Render Free. |
| `LOG_LEVEL` | no | `INFO` by default. `DEBUG` also logs every webhook body and GREEN-API response. |

Never commit `.env`. A blank value (`GREEN_API_API_URL=`) is treated as "not set" and
falls back to the default, and a host pasted without a scheme gets `https://` added.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Render health check. Returns `{"status": "ok"}`. Never contacts GREEN-API. |
| `POST` | `/webhook/green-api` | GREEN-API notifications. Always returns HTTP 200. |
| `GET` | `/admin/diagnostics` | **Start here when something is wrong.** Checks the whole setup. |
| `GET` | `/admin/user/{chat_id}` | Read a customer's stored state. |
| `POST` | `/admin/pause/{chat_id}` | Stop automatic replies for a customer. |
| `POST` | `/admin/resume/{chat_id}` | Re-enable automatic replies. |
| `POST` | `/admin/reset/{chat_id}` | Forget a customer so onboarding starts again. |

Admin endpoints require the header `X-Admin-Key: <ADMIN_API_KEY>`:

```bash
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://<service-name>.onrender.com/admin/user/972501234567@c.us
```

## Human takeover

GREEN-API distinguishes the two kinds of outgoing message, and the bot relies on that:

- `outgoingMessageReceived` — the owner typed the message on their phone / WhatsApp Web /
  Desktop. The bot immediately sets `bot_enabled: false` and `flow: "human"` for that chat
  and stops replying.
- `outgoingAPIMessageReceived` — the message was sent by this application through GREEN-API.
  The bot is **not** disabled.

To bring the bot back for that customer, call `POST /admin/resume/{chat_id}` (keeps the
conversation state) or `POST /admin/reset/{chat_id}` (starts onboarding over).

## Storage is temporary on Render Free

Render Free Web Services have an **ephemeral filesystem**. `data/users.json` is wiped
whenever the service spins down, restarts, or redeploys. When that happens a returning
customer looks like a new inquiry and gets the language menu again.

**This is intentional for the MVP.** There is deliberately no Git/GitHub/database workaround.

All state access goes through `app/storage/json_store.py`, so upgrading later is a
configuration change, not a rewrite:

1. Upgrade the Render instance to a paid plan.
2. Attach a Persistent Disk mounted at `/var/data`.
3. Set `DATA_FILE_PATH=/var/data/users.json`.

No bot or flow code changes.

## When something is not working

**1. Ask the service what is wrong.** This one endpoint checks the configuration, the
GREEN-API instance state and the instance's webhook settings, and answers in plain words:

```bash
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://<service-name>.onrender.com/admin/diagnostics
```

```json
{
  "status": "problems_found",
  "problems": [
    "GREEN-API instance state is 'notAuthorized', expected 'authorized'. Scan the QR code again in the GREEN-API console.",
    "The instance webhookUrl is 'https://old-bot.example.com/hook', which does not end in /webhook/green-api - notifications are going somewhere else.",
    "GREEN-API setting outgoingMessageWebhook is 'no', expected 'yes' - needed to detect a manual reply and switch the bot off."
  ]
}
```

`"status": "ok"` with an empty `problems` list means the setup is fine and the issue is
in the conversation itself — read the logs.

**2. Read the logs.** On Render: your service → **Logs**. Every startup prints the
resolved configuration (never the secrets themselves):

```text
INFO app.main: WhatsApp flow bot starting
INFO app.main:   GREEN_API_API_URL     = https://api.green-api.com
INFO app.main:   GREEN_API_INSTANCE_ID = 1101234567
INFO app.main:   GREEN_API_TOKEN       = set
ERROR app.main: CONFIG PROBLEM: ADMIN_API_KEY is not set - the /admin endpoints will answer 503.
```

and every message is traceable end to end:

```text
INFO app.routers.webhook: Webhook received: type='incomingMessageReceived' chatId='972501112222@c.us' idMessage='F2' typeMessage='interactiveButtonsReply'
INFO app.services.bot: Handling '1' from 972501112222@c.us (step=1, language=None, flow=None)
INFO app.services.bot: 972501112222@c.us chose language he
INFO app.services.green_api: Sending 3 buttons to 972501112222@c.us: ['Pilates מכשירים', 'Barre', 'קורס הכשרת מדריכות']
INFO app.services.green_api: GREEN-API -> POST https://api.green-api.com/waInstance1101234567/sendInteractiveButtons/***TOKEN***
INFO app.services.green_api: Sent button menu BAE5A7BA6D6E28EB to 972501112222@c.us
```

The API token is masked as `***TOKEN***` everywhere, including inside error messages.
Set `LOG_LEVEL=DEBUG` to also log every webhook body and every GREEN-API response body.

**3. Common causes, and the log line that shows each one.**

| Symptom in the log | Cause |
| --- | --- |
| `CONFIG PROBLEM: GREEN_API_TOKEN is not set` | The env var is missing on Render. |
| `GREEN_API_API_URL looks wrong` | The URL has no `http://` or `https://`. |
| `returned HTTP 401` | `GREEN_API_TOKEN` does not match the instance. |
| `returned HTTP 404` | `GREEN_API_INSTANCE_ID` or `GREEN_API_API_URL` is wrong. |
| `returned HTTP 466` | The GREEN-API instance is out of quota. |
| `Bot is OFF for … - ignoring the message` | A manual reply switched the bot off. `POST /admin/resume/{chat_id}` turns it back on. |
| `Ignoring imageMessage from …` | The customer sent media; the bot only reads text and button taps. |
| `Duplicate notification … - already answered` | GREEN-API redelivered a notification. Working as intended. |
| Nothing at all in the log | The webhook never arrived — check `webhookUrl` and `incomingWebhook` in `/admin/diagnostics`. |

Every webhook still answers HTTP 200 (so GREEN-API stops retrying), but a failed one
returns `{"status": "error", "reason": "..."}` naming the cause.

## Menus are interactive buttons

Both menus are sent with GREEN-API's
[`sendInteractiveButtons`](https://green-api.com/en/docs/api/sending/SendInteractiveButtons/).
GREEN-API limits a message to **3 buttons**, each with a **`buttonText` of at most 25
characters**; `app/services/green_api.py` enforces both before sending.

GREEN-API marks that method as **beta**, so the bot never depends on it:

- If the button call fails, the same menu is re-sent as a numbered text message
  (`1. …` / `2. …` / `3. …`) built from the very same wording — nothing to maintain twice.
- A customer is understood whether they **tap a button**, **type the number**, or
  **type the button's label** ("English", "barre").

## Editing the wording

All customer-facing text lives in `app/messages/he.py` and `app/messages/en.py`:

- `LANGUAGE_BODY` / `LANGUAGE_BUTTONS` — the opening bilingual menu.
- `INTEREST_BODY` / `INTEREST_BUTTONS` — the three interest buttons.
- `FLOW_MESSAGES` — the `[TODO: ...]` placeholders, one list of 1–3 messages per interest.

Each button's `buttonId` is what routes the customer: `1` → `pilates`, `2` → `barre`,
`3` → `instructor_course` (see `FLOW_BY_BUTTON_ID` in `app/services/bot.py`). Change a
`buttonText` freely; change a `buttonId` only together with that mapping. Keep labels
within 25 characters, and keep the list at three buttons or fewer.

## Deploy to Render (Free)

1. **Push this repository to GitHub.**
2. Open the [Render Dashboard](https://dashboard.render.com/).
3. **New → Blueprint**, connect this repository. Render reads `render.yaml`.
4. **Confirm the instance type is `Free`** (`plan: free` is already set in `render.yaml`).
5. Render prompts for the values marked `sync: false` — enter your
   `GREEN_API_INSTANCE_ID`, `GREEN_API_TOKEN`, `GREEN_API_API_URL` and `ADMIN_API_KEY`.
6. **Apply / Deploy.**
7. Verify the service is up:

   ```text
   https://<service-name>.onrender.com/health
   ```

   It must return `{"status": "ok"}`.
8. In the GREEN-API console, set the instance **Webhook URL** to:

   ```text
   https://<service-name>.onrender.com/webhook/green-api
   ```

9. Enable these instance settings in GREEN-API:
   - `incomingWebhook` — **yes** (receive customer messages)
   - `outgoingMessageWebhook` — **yes** (required for human takeover detection)
   - `outgoingAPIMessageWebhook` — **yes**
   - `stateWebhook` — optional (ignored by the bot)

Render binds the port it gives you through `$PORT`; the start command in `render.yaml` is
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Port 8000 is never hardcoded for production.

> Free services sleep after inactivity, so the first webhook after a sleep may take a few
> seconds to be answered while the service wakes up.

## Project structure

```text
app/
    main.py              FastAPI app, /health, router wiring
    config.py            Pydantic Settings
    routers/
        webhook.py       POST /webhook/green-api
        admin.py         /admin/* endpoints (X-Admin-Key)
    services/
        green_api.py     All GREEN-API HTTP calls (httpx)
        bot.py           Flow rules, human takeover
    storage/
        json_store.py    JSON state, atomic writes, duplicate detection
    messages/
        he.py / en.py    All customer-facing text
data/                    Temporary state (users.json, gitignored)
tests/test_bot.py        Flow tests with GREEN-API mocked
render.yaml              Render Blueprint (Free plan, no disk, no database)
```
