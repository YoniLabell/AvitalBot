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
    {"type": "reply", "buttonId": "1", "buttonText": "עברית"},
    {"type": "reply", "buttonId": "2", "buttonText": "English"},
]

INVALID_LANGUAGE_CHOICE = "לא הבנתי 🙈 | Sorry, I didn't get that"

INTEREST_BODY = "Nice to meet you 🌸\nWhat are you interested in?"

INTEREST_BUTTONS = [
    {"type": "reply", "buttonId": "1", "buttonText": "Pilates Equipment"},
    {"type": "reply", "buttonId": "2", "buttonText": "Barre"},
    {"type": "reply", "buttonId": "3", "buttonText": "Instructor Course"},
]

# Shown under the interest and flow menus, so customers know 0 takes them back.
MENU_FOOTER = "0 to return to the main menu"

INVALID_INTEREST_CHOICE = "Sorry, I didn't get that 🙈"


# --- the three flows -------------------------------------------------------

FLOW_BODY = {
    "pilates": (
        "Pilates Equipment 🌿\n"
        "\n"
        "Classes are held in small groups of up to 6 participants, with "
        "personal attention and exercises tailored to each person's level "
        "and individual needs.\n"
        "\n"
        "What would you like to know?"
    ),
    "barre": (
        "Barre 🤍\n"
        "\n"
        "A dynamic, high-energy group workout combining technique, strength, "
        "cardio, and coordination.\n"
        "An intense full-body workout that challenges the muscles with "
        "precision while getting your heart rate up — leaving you feeling "
        "strong, energized, and accomplished.\n"
        "\n"
        "What would you like to know?"
    ),
    "instructor_course": (
        "Pilates Instructor Training Course 🤍\n"
        "\n"
        "A comprehensive and in-depth Mat & Equipment Pilates Instructor "
        "Training Course, combining professional knowledge, a deep "
        "understanding of movement, and practical teaching tools.\n"
        "\n"
        "The course is taught in collaboration with Rona Segev. Together, we "
        "have created a training program designed to pass on the knowledge "
        "and extensive experience we have gained over the years — giving you "
        "a strong, professional foundation and the confidence to teach "
        "Pilates.\n"
        "\n"
        "What would you like to know?"
    ),
}

FLOW_BUTTONS = {
    "pilates": [
        {"type": "reply", "buttonId": "1", "buttonText": "Pricing & class schedule"},
        {"type": "reply", "buttonId": "2", "buttonText": "Book a trial class"},
        {"type": "reply", "buttonId": "3", "buttonText": "Talk to us"},
    ],
    "barre": [
        {"type": "reply", "buttonId": "1", "buttonText": "Pricing & class schedule"},
        {"type": "reply", "buttonId": "2", "buttonText": "Book a trial class"},
        {"type": "reply", "buttonId": "3", "buttonText": "Talk to us"},
    ],
    "instructor_course": [
        # "Course details & structure" is 26 characters; the GREEN-API button
        # limit is 25, so the label is shortened here.
        {"type": "reply", "buttonId": "1", "buttonText": "Details & structure"},
        {"type": "reply", "buttonId": "2", "buttonText": "Dates & pricing"},
        {"type": "reply", "buttonId": "3", "buttonText": "Talk to us"},
    ],
}

# What the bot answers for each sub-option, as a list of 1-3 messages.
# TODO: replace every placeholder below with the real wording.
FLOW_ANSWERS = {
    "pilates": {
        "1": ["[TODO: Pricing & class schedule - Pilates Equipment]"],
        "2": ["[TODO: Booking a trial class - Pilates Equipment]"],
    },
    "barre": {
        "1": ["[TODO: Pricing & class schedule - Barre]"],
        "2": ["[TODO: Booking a trial class - Barre]"],
    },
    "instructor_course": {
        "1": ["[TODO: Course details & structure]"],
        "2": ["[TODO: Course dates & pricing]"],
    },
}

# Images sent alongside a sub-option's answer, by flow and buttonId. The file
# name is looked up inside ASSETS_DIR (see app/config.py). One schedule sheet
# covers both Pilates and Barre, so both schedule buttons send it.
FLOW_ANSWER_IMAGES = {
    "pilates": {"1": "class_schedule.jpeg"},          # Pricing & class schedule
    "barre": {"1": "class_schedule.jpeg"},            # Pricing & class schedule
}

# Sub-options that hand the chat to a human instead of sending an answer.
HANDOVER_BUTTONS = {
    "pilates": {"3"},
    "barre": {"3"},
    "instructor_course": {"3"},
}

# TODO: the wording sent just before a human takes over.
HANDOVER_MESSAGE = "[TODO: handover message]"
