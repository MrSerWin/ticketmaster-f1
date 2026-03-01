from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from src.scraper import TicketListing

logger = logging.getLogger(__name__)

BASE_URL = "https://app.ticketmaster.com/discovery/v2"


@dataclass
class PriceRange:
    currency: str
    min_price: float
    max_price: float


@dataclass
class EventInfo:
    event_id: str
    name: str
    url: str
    venue_name: str
    venue_city: str
    venue_state: str
    venue_country: str
    start_date: str
    start_time: Optional[str]
    timezone: Optional[str]
    date_tba: bool
    time_tba: bool
    price_ranges: list[PriceRange] = field(default_factory=list)
    tickets: list[TicketListing] = field(default_factory=list)
    status: str = ""
    location_str: str = ""

    def __post_init__(self):
        parts = [self.venue_name]
        if self.venue_city:
            parts.append(self.venue_city)
        if self.venue_state:
            parts.append(self.venue_state)
        self.location_str = ", ".join(p for p in parts if p)


class TicketmasterClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.Client(timeout=15.0)
        self._last_request_time = 0.0

    def search_by_name(self, name: str) -> list[EventInfo]:
        """Search events by name/keyword. Returns all matching onsale events."""
        params = {
            "keyword": name,
            "size": "20",
            "sort": "date,asc",
        }
        data = self._make_request("/events.json", params)
        if not data:
            return []

        embedded = data.get("_embedded", {})
        raw_events = embedded.get("events", [])
        logger.info("Search '%s': %d results", name, len(raw_events))

        results = []
        for raw in raw_events:
            event = self._parse_event(raw)
            if event and event.status == "onsale":
                results.append(event)
        return results

    def get_event_details(self, event_id: str) -> Optional[EventInfo]:
        data = self._make_request(f"/events/{event_id}.json", {})
        if not data:
            return None
        return self._parse_event(data)

    def _parse_event(self, raw: dict) -> Optional[EventInfo]:
        try:
            event_id = raw.get("id", "")
            name = raw.get("name", "Unknown Event")
            url = raw.get("url", "")

            # Venue
            venues = raw.get("_embedded", {}).get("venues", [])
            venue = venues[0] if venues else {}
            venue_name = venue.get("name", "")
            city = venue.get("city", {}).get("name", "")
            state_obj = venue.get("state", {})
            state = state_obj.get("stateCode", "") if state_obj else ""
            country = venue.get("country", {}).get("countryCode", "")

            # Dates
            dates = raw.get("dates", {})
            start = dates.get("start", {})
            start_date = start.get("localDate", "")
            start_time = start.get("localTime")
            tz = dates.get("timezone")
            date_tba = start.get("dateTBA", False)
            time_tba = start.get("timeTBA", False)

            # Status
            status_obj = dates.get("status", {})
            status = status_obj.get("code", "") if status_obj else ""

            # Price ranges
            price_ranges = []
            for pr in raw.get("priceRanges", []):
                price_ranges.append(PriceRange(
                    currency=pr.get("currency", "USD"),
                    min_price=float(pr.get("min", 0)),
                    max_price=float(pr.get("max", 0)),
                ))

            return EventInfo(
                event_id=event_id,
                name=name,
                url=url,
                venue_name=venue_name,
                venue_city=city,
                venue_state=state,
                venue_country=country,
                start_date=start_date,
                start_time=start_time,
                timezone=tz,
                date_tba=date_tba,
                time_tba=time_tba,
                price_ranges=price_ranges,
                status=status,
            )
        except Exception as e:
            logger.error("Failed to parse event: %s", e)
            return None

    def _make_request(self, endpoint: str, params: dict) -> Optional[dict]:
        # Rate limit: 0.25s between requests
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)

        url = f"{BASE_URL}{endpoint}"
        params["apikey"] = self.api_key

        try:
            self._last_request_time = time.monotonic()
            r = self.client.get(url, params=params)

            if r.status_code == 429:
                logger.warning("Rate limited by Ticketmaster, sleeping 60s")
                time.sleep(60)
                self._last_request_time = time.monotonic()
                r = self.client.get(url, params=params)

            r.raise_for_status()
            return r.json()

        except httpx.HTTPStatusError as e:
            logger.error("HTTP %d for %s: %s", e.response.status_code, endpoint, e)
            return None
        except httpx.RequestError as e:
            logger.error("Request error for %s: %s", endpoint, e)
            return None
        except Exception as e:
            logger.error("Unexpected error for %s: %s", endpoint, e)
            return None

    def close(self):
        self.client.close()
