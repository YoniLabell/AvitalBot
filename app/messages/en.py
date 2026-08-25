"""English customer-facing text. Edit wording here, never in the webhook logic."""

# The very first message is bilingual, so it is identical in both modules.
LANGUAGE_MENU = (
    "היי ❣️ תודה שפנית אלינו | Hi ❣️ Thanks for reaching out\n"
    "\n"
    "לבחירת שפה | Please choose your language:\n"
    "\n"
    "1. עברית 🇮🇱\n"
    "2. English 🇬🇧"
)

INVALID_LANGUAGE_CHOICE = "לא הבנתי 🙈 | Sorry, I didn't get that"

INTEREST_MENU = (
    "Nice to meet you 🌸\n"
    "What are you interested in?\n"
    "\n"
    "1. Reformer Pilates\n"
    "2. Barre\n"
    "3. Instructor Training Course\n"
    "4. Something else"
)

INVALID_INTEREST_CHOICE = "Sorry, I didn't get that 🙈"

# Each flow is a list of messages sent one after the other (about 1-3 each).
# TODO: replace the placeholders below with the final business wording.
FLOW_MESSAGES = {
    "pilates": ["[TODO: Pilates information]"],
    "barre": ["[TODO: Barre information]"],
    "instructor_course": ["[TODO: Instructor course information]"],
    "other": ["[TODO: Other question - handover text]"],
}

FLOW_DONE = "[TODO: closing message]"
