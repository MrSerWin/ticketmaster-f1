import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.ticketmaster import EventInfo

logger = logging.getLogger(__name__)

MAX_HISTORY_ENTRIES = 720  # ~30 days at hourly checks


@dataclass
class PriceChange:
    event_id: str
    event_name: str
    change_type: str  # new_event, min_decreased, min_increased, max_decreased, max_increased, prices_removed
    old_min: Optional[float]
    old_max: Optional[float]
    new_min: Optional[float]
    new_max: Optional[float]
    currency: str = "USD"


class PriceTracker:
    def __init__(self, history_path: str = "data/price_history.json"):
        self.history_path = Path(history_path)
        self.history: dict = self._load()

    def _load(self) -> dict:
        if not self.history_path.exists():
            return {}
        try:
            with open(self.history_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load price history: %s. Starting fresh.", e)
            return {}

    def save(self):
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.history_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.history_path)
        except OSError as e:
            logger.error("Failed to save price history: %s", e)

    def check_and_update(self, event: EventInfo) -> Optional[PriceChange]:
        now = datetime.now().isoformat(timespec="seconds")
        eid = event.event_id

        # Current prices
        cur_min = None
        cur_max = None
        currency = "USD"
        if event.price_ranges:
            pr = event.price_ranges[0]
            cur_min = pr.min_price
            cur_max = pr.max_price
            currency = pr.currency

        # New event
        if eid not in self.history:
            self.history[eid] = {
                "name": event.name,
                "last_min": cur_min,
                "last_max": cur_max,
                "currency": currency,
                "first_seen": now,
                "last_checked": now,
                "check_count": 1,
                "history": [],
            }
            if cur_min is not None:
                self.history[eid]["history"].append({"ts": now, "min": cur_min, "max": cur_max})
            return PriceChange(
                event_id=eid,
                event_name=event.name,
                change_type="new_event",
                old_min=None,
                old_max=None,
                new_min=cur_min,
                new_max=cur_max,
                currency=currency,
            )

        # Existing event
        entry = self.history[eid]
        entry["name"] = event.name
        entry["last_checked"] = now
        entry["check_count"] = entry.get("check_count", 0) + 1

        old_min = entry.get("last_min")
        old_max = entry.get("last_max")

        change: Optional[PriceChange] = None

        # Prices disappeared
        if cur_min is None and old_min is not None:
            change = PriceChange(
                event_id=eid, event_name=event.name,
                change_type="prices_removed",
                old_min=old_min, old_max=old_max,
                new_min=None, new_max=None,
                currency=currency,
            )
        # Prices appeared or changed
        elif cur_min is not None:
            if old_min is not None and cur_min < old_min:
                change = PriceChange(
                    event_id=eid, event_name=event.name,
                    change_type="min_decreased",
                    old_min=old_min, old_max=old_max,
                    new_min=cur_min, new_max=cur_max,
                    currency=currency,
                )
            elif old_min is not None and cur_min > old_min:
                change = PriceChange(
                    event_id=eid, event_name=event.name,
                    change_type="min_increased",
                    old_min=old_min, old_max=old_max,
                    new_min=cur_min, new_max=cur_max,
                    currency=currency,
                )
            elif old_max is not None and cur_max is not None and cur_max < old_max:
                change = PriceChange(
                    event_id=eid, event_name=event.name,
                    change_type="max_decreased",
                    old_min=old_min, old_max=old_max,
                    new_min=cur_min, new_max=cur_max,
                    currency=currency,
                )
            elif old_max is not None and cur_max is not None and cur_max > old_max:
                change = PriceChange(
                    event_id=eid, event_name=event.name,
                    change_type="max_increased",
                    old_min=old_min, old_max=old_max,
                    new_min=cur_min, new_max=cur_max,
                    currency=currency,
                )

            # Append to history
            history_list = entry.setdefault("history", [])
            history_list.append({"ts": now, "min": cur_min, "max": cur_max})
            # Cap history size
            if len(history_list) > MAX_HISTORY_ENTRIES:
                entry["history"] = history_list[-MAX_HISTORY_ENTRIES:]

        # Update stored values
        entry["last_min"] = cur_min
        entry["last_max"] = cur_max
        entry["currency"] = currency

        return change
