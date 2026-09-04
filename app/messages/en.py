"""English customer-facing text. Edit wording here, never in the webhook logic.

Menus are sent as interactive buttons. GREEN-API allows at most 3 buttons per
message and at most 25 characters per buttonText, so keep the labels short.
"""

# The first message is bilingual, so it is identical in both catalogues.
LANGUAGE_BODY = (
    "היי ❣️ תודה שפנית אלינו | Hi ❣️ Thanks for reaching out\n"
    "\n"
    "לבחירת שפה | Please choose your language:"
)

LANGUAGE_BUTTONS = [
    {"type": "reply", "buttonId": "1", "buttonText": "עברית 🇮🇱"},
    {"type": "reply", "buttonId": "2", "buttonText": "English 🇬🇧"},
]

INVALID_LANGUAGE_CHOICE = "לא הבנתי 🙈 | Sorry, I didn't get that"

INTEREST_BODY = "Nice to meet you 🌸\nWhat are you interested in?"

INTEREST_BUTTONS = [
    {"type": "reply", "buttonId": "1", "buttonText": "Reformer Pilates"},
    {"type": "reply", "buttonId": "2", "buttonText": "Barre"},
    {"type": "reply", "buttonId": "3", "buttonText": "Instructor Course"},
]

INVALID_INTEREST_CHOICE = "Sorry, I didn't get that 🙈"

# Each flow is a list of messages sent one after the other (about 1-3 each).
# TODO: replace the placeholders below with the final business wording.
FLOW_MESSAGES = {
    "pilates": ["[TODO: Pilates information]"],
    "barre": ["[TODO: Barre information]"],
    "instructor_course": ["[TODO: Instructor course information]"],
}
