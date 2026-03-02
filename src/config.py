import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class EventConfig:
    """Event to monitor. Specify event_id directly, or name to search for it."""
    event_id: Optional[str] = None
    name: Optional[str] = None
    label: Optional[str] = None
    sprint: bool = False  # True if sprint weekend (changes Saturday schedule)


@dataclass
class NotificationsConfig:
    notify_on_new_event: bool = True
    notify_on_price_change: bool = True


@dataclass
class AppConfig:
    ticketmaster_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    check_interval_seconds: int = 3600
    timezone: str = "America/New_York"
    language: str = "ru"
    events: list[EventConfig] = field(default_factory=list)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    price_history_path: str = "data/price_history.json"


def load_config(config_path: str = "config.yaml") -> AppConfig:
    load_dotenv()

    # Secrets from environment
    api_key = os.environ.get("TICKETMASTER_API_KEY", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    missing = []
    if not api_key:
        missing.append("TICKETMASTER_API_KEY")
    if not bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Copy .env.example to .env and fill in the values.", file=sys.stderr)
        sys.exit(1)

    # Structure from YAML
    raw: dict = {}
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

    # Parse events
    events = []
    for ev in raw.get("events") or []:
        event_id = ev.get("event_id")
        name = ev.get("name")
        if not event_id and not name:
            print("WARNING: event entry has neither event_id nor name, skipping", file=sys.stderr)
            continue
        events.append(EventConfig(
            event_id=event_id,
            name=name,
            label=ev.get("label"),
            sprint=ev.get("sprint", False),
        ))

    if not events:
        print("WARNING: no events configured in config.yaml", file=sys.stderr)

    # Parse notifications
    notif_raw = raw.get("notifications", {})
    notifications = NotificationsConfig(
        notify_on_new_event=notif_raw.get("notify_on_new_event", True),
        notify_on_price_change=notif_raw.get("notify_on_price_change", True),
    )

    # Check interval: env var takes priority over config.yaml
    env_interval = os.environ.get("CHECK_INTERVAL_SECONDS")
    interval = int(env_interval) if env_interval else raw.get("check_interval_seconds", 3600)

    return AppConfig(
        ticketmaster_api_key=api_key,
        telegram_bot_token=bot_token,
        telegram_chat_id=chat_id,
        check_interval_seconds=interval,
        timezone=raw.get("timezone", "America/New_York"),
        language=raw.get("language", "ru"),
        events=events,
        notifications=notifications,
        price_history_path=raw.get("price_history_path", "data/price_history.json"),
    )
