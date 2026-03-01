"""Utilities for parsing F1 event names and mapping days to session types."""

import re
from dataclasses import dataclass
from typing import Optional

# "Friday - Start / Finish Grandstand - 2026 Miami Grand Prix"
# "Joyflight (Thu) - FORMULA 1 QATAR AIRWAYS AUSTRALIAN GRAND PRIX 2026"
NAME_PATTERN = re.compile(
    r"^(?P<day>Friday|Saturday|Sunday|Monday|Thursday|Wed|Thu|Fri|Sat|Sun)"
    r"(?:\)?\s*-\s*|\s*-\s*)"
    r"(?P<section>.+?)\s*-\s*"
    r"(?P<gp>.+)$",
    re.IGNORECASE,
)

# Fallback: "(Day)" pattern like "Park Pass (Thu) - GP NAME"
NAME_PATTERN_ALT = re.compile(
    r"^(?P<section>.+?)\s*\((?P<day>Thu|Fri|Sat|Sun|Friday|Saturday|Sunday)\)\s*-\s*(?P<gp>.+)$",
    re.IGNORECASE,
)

DAY_NORMALIZE = {
    "thu": "Thursday", "thursday": "Thursday",
    "fri": "Friday", "friday": "Friday",
    "sat": "Saturday", "saturday": "Saturday",
    "sun": "Sunday", "sunday": "Sunday",
}

# Standard weekend: Fri=Practice, Sat=Qualifying, Sun=Race
# Sprint weekend:   Fri=Practice+Sprint Quali, Sat=Sprint+Qualifying, Sun=Race
SESSION_STANDARD = {
    "Friday": "practice",
    "Saturday": "qualifying",
    "Sunday": "race",
}

SESSION_SPRINT = {
    "Friday": "practice",
    "Saturday": "sprint_qualifying",
    "Sunday": "race",
}

SESSION_LABELS_RU = {
    "practice": "Практика",
    "qualifying": "Квалификация",
    "sprint_qualifying": "Спринт + Квалификация",
    "race": "Гонка",
}

SESSION_LABELS_EN = {
    "practice": "Practice",
    "qualifying": "Qualifying",
    "sprint_qualifying": "Sprint + Qualifying",
    "race": "Race",
}

SESSION_EMOJI = {
    "practice": "\U0001f527",   # 🔧
    "qualifying": "\u23f1",      # ⏱
    "sprint_qualifying": "\u26a1",  # ⚡
    "race": "\U0001f3c1",       # 🏁
}

# Race day comes first in display order
SESSION_ORDER = {"race": 0, "sprint_qualifying": 1, "qualifying": 1, "practice": 2}


@dataclass
class ParsedEvent:
    day: str          # "Friday", "Saturday", "Sunday"
    section: str      # "Start / Finish Grandstand"
    gp_name: str      # "2026 Miami Grand Prix"
    session: str      # "practice", "qualifying", "sprint_qualifying", "race"


def parse_event_name(name: str, is_sprint: bool = False) -> Optional[ParsedEvent]:
    """Parse a Ticketmaster event name into day, section, and GP name."""
    m = NAME_PATTERN.match(name)
    if not m:
        m = NAME_PATTERN_ALT.match(name)
    if not m:
        return None

    day_raw = m.group("day").lower()
    day = DAY_NORMALIZE.get(day_raw, day_raw.capitalize())
    section = m.group("section").strip()
    gp_name = m.group("gp").strip()

    session_map = SESSION_SPRINT if is_sprint else SESSION_STANDARD
    session = session_map.get(day, "practice")

    return ParsedEvent(day=day, section=section, gp_name=gp_name, session=session)


def session_label(session: str, language: str = "ru") -> str:
    labels = SESSION_LABELS_RU if language == "ru" else SESSION_LABELS_EN
    return labels.get(session, session)


def session_emoji(session: str) -> str:
    return SESSION_EMOJI.get(session, "")
