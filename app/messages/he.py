"""Hebrew customer-facing text. Edit wording here, never in the webhook logic.

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

INTEREST_BODY = "נעים להכיר 🌸\nבמה התעניינת?"

INTEREST_BUTTONS = [
    {"type": "reply", "buttonId": "1", "buttonText": "Pilates מכשירים"},
    {"type": "reply", "buttonId": "2", "buttonText": "Barre"},
    {"type": "reply", "buttonId": "3", "buttonText": "קורס הכשרת מדריכות"},
]

# Shown under the interest and flow menus, so customers know 0 takes them back.
MENU_FOOTER = "0 לחזרה לתפריט הראשי"

INVALID_INTEREST_CHOICE = "לא הבנתי 🙈"


# --- the three flows -------------------------------------------------------

FLOW_BODY = {
    "pilates": (
        "פילאטיס מכשירים 🌿\n"
        "\n"
        "השיעורים מתקיימים בקבוצות קטנות של עד 6 מתאמנים, עם יחס אישי "
        "והתאמה לרמה ולצרכים של כל מתאמן.\n"
        "\n"
        "ניתן להתאמן במסגרת מנוי חודשי או כרטיסייה.\n"
        "\n"
        "מה תרצי לדעת?"
    ),
    "barre": (
        "Barre 🤍\n"
        "\n"
        "אימון קבוצתי דינמי בקצב גבוה, שילוב של טכניקה, כוח, אירובי וקואורדינציה.\n"
        "עבודה אינטנסיבית על כל הגוף, אתגר מדויק לשריר בשילוב עליית דופק "
        "משאיר תחושה של אימון עצים בגוף ואנרגיה גבוהה.\n"
        "\n"
        "מה תרצי לדעת?"
    ),
    "instructor_course": (
        "קורס הכשרת מדריכות פילאטיס 🤍\n"
        "\n"
        "קורס מקיף ומעמיק להכשרת מדריכות פילאטיס מזרן ומכשירים, המשלב ידע "
        "מקצועי, הבנה תנועתית וכלים מעשיים להוראה.\n"
        "\n"
        "הקורס מועבר בשיתוף עם רונה שגב. יחד בנינו מערך הכשרה שמטרתו להעביר "
        "הלאה את הידע והניסיון שצברנו לאורך השנים — ולתת לכן בסיס מקצועי, "
        "עמוק ובטוח לעבודה כמדריכות.\n"
        "\n"
        "מה תרצי לדעת?"
    ),
}

FLOW_BUTTONS = {
    "pilates": [
        {"type": "reply", "buttonId": "1", "buttonText": "מחירים ומנויים"},
        {"type": "reply", "buttonId": "2", "buttonText": "מערכת שעות"},
        {"type": "reply", "buttonId": "3", "buttonText": "לקבוע שיעור ניסיון"},
    ],
    "barre": [
        {"type": "reply", "buttonId": "1", "buttonText": "מחירים ומערכת שעות"},
        {"type": "reply", "buttonId": "2", "buttonText": "לקבוע שיעור ניסיון"},
        {"type": "reply", "buttonId": "3", "buttonText": "לדבר איתנו"},
    ],
    "instructor_course": [
        {"type": "reply", "buttonId": "1", "buttonText": "פרטים ומבנה הקורס"},
        {"type": "reply", "buttonId": "2", "buttonText": "מועדים ועלויות"},
        {"type": "reply", "buttonId": "3", "buttonText": "לדבר איתנו"},
    ],
}

# What the bot answers for each sub-option, as a list of 1-3 messages.
# TODO: replace every placeholder below with the real wording.
FLOW_ANSWERS = {
    "pilates": {
        "1": ["[TODO: מחירים ומנויים - פילאטיס מכשירים]"],
        "2": ["[TODO: מערכת שעות - פילאטיס מכשירים]"],
        "3": ["[TODO: קביעת שיעור ניסיון - פילאטיס מכשירים]"],
    },
    "barre": {
        "1": ["[TODO: מחירים ומערכת שעות - Barre]"],
        "2": ["[TODO: קביעת שיעור ניסיון - Barre]"],
    },
    "instructor_course": {
        "1": ["[TODO: פרטים ומבנה הקורס]"],
        "2": ["[TODO: מועדים ועלויות של הקורס]"],
    },
}

# Images sent alongside a sub-option's answer, by flow and buttonId. The file
# name is looked up inside ASSETS_DIR (see app/config.py). One schedule sheet
# covers both Pilates and Barre, so both schedule buttons send it.
FLOW_ANSWER_IMAGES = {
    "pilates": {"2": "class_schedule.jpeg"},          # מערכת שעות
    "barre": {"1": "class_schedule.jpeg"},            # מחירים ומערכת שעות
}

# Sub-options that hand the chat to a human instead of sending an answer.
HANDOVER_BUTTONS = {
    "pilates": set(),
    "barre": {"3"},
    "instructor_course": {"3"},
}

# TODO: the wording sent just before a human takes over.
HANDOVER_MESSAGE = "[TODO: הודעת מעבר לנציגה]"
